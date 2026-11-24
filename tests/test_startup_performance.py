"""Offline timing contracts; never import the production application/server."""
import ast
import json
from pathlib import Path
import unittest
from types import SimpleNamespace

from startup_performance import StartupTrace, StartupTimingMiddleware

ROOT = Path(__file__).resolve().parents[1]


class TraceTests(unittest.TestCase):
    def test_clock_stages_failures_and_fixed_labels(self):
        values = iter([1, 1.1, 1.2, 1.5])
        records = []
        trace = StartupTrace(clock=lambda: next(values), emit=records.append)
        trace.mark("imports_done")
        with self.assertRaisesRegex(RuntimeError, "original failure"):
            with trace.span("migrations"):
                raise RuntimeError("original failure")
        self.assertEqual([r["stage"] for r in records],
                         ["imports_done", "migrations_start", "migrations_failed"])
        self.assertEqual(records[-1]["elapsed_ms"], 500)
        self.assertEqual(records[-1]["stage_ms"], 300)
        with self.assertRaises(ValueError):
            trace.mark("customer@example.test")

    def test_script_timer_includes_first_application_import(self):
        tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
        timer = next(i for i, n in enumerate(tree.body) if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == "APP_START_TIME" for t in n.targets))
        prompt = next(i for i, n in enumerate(tree.body) if isinstance(n, ast.ImportFrom)
                      and n.module == "product_upload_prompt_core")
        self.assertLess(timer, prompt)


class MiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def call(self, scope, outgoing):
        records, delivered = [], []
        ticks = iter([1, 1.025])
        async def app(scope, receive, send):
            for message in outgoing:
                await send(message)
        async def send(message):
            delivered.append(message)
        await StartupTimingMiddleware(app, clock=lambda: next(ticks), emit=records.append)(
            scope, None, send)
        return records, delivered

    async def test_document_headers_body_and_existing_cache_contract(self):
        headers = [(b"cache-control", b"no-cache"), (b"vary", b"Accept-Encoding"),
                   (b"server-timing", b"existing;dur=1"), (b"content-length", b"5")]
        messages = [dict(type="http.response.start", status=200, headers=headers),
                    dict(type="http.response.body", body=b"hello")]
        records, delivered = await self.call(dict(type="http", method="GET", path="/"), messages)
        self.assertEqual(delivered[0]["headers"][:-1], headers)
        self.assertEqual(delivered[0]["headers"][-1], (b"server-timing", b"os_headers;dur=25.000"))
        self.assertEqual(delivered[1:], messages[1:])
        self.assertEqual(records, [dict(stage="document", duration_ms=25, status=200)])
        self.assertEqual(messages[0]["headers"], headers)  # no upstream mutation

    async def test_bundle_root_path_and_conditional_response(self):
        for path, root in [("/static/js/index.hash.js", ""), ("/os/static/css/index.hash.css", "/os")]:
            records, delivered = await self.call(dict(type="http", method="GET", path=path, root_path=root),
                [dict(type="http.response.start", status=304, headers=[(b"etag", b'"public"')]),
                 dict(type="http.response.body", body=b"")])
            self.assertEqual(records[0]["stage"], "bundle")
            self.assertEqual(delivered[0]["status"], 304)
            self.assertEqual(delivered[1]["body"], b"")

    async def test_private_health_media_and_head_are_untouched(self):
        for path, method in [("/api/orders", "GET"), ("/healthz", "GET"),
                             ("/_stcore/health", "GET"), ("/media/customer.png", "GET"),
                             ("/", "HEAD"), ("/", "POST")]:
            messages = [dict(type="http.response.start", status=200, headers=[]),
                        dict(type="http.response.body", body=b"private")]
            records, delivered = await self.call(dict(type="http", method=method, path=path,
                query_string=b"secret=never-log", headers=[(b"cookie", b"private")]), messages)
            self.assertEqual(records, [])
            self.assertEqual(delivered, messages)

    async def test_websocket_payloads_never_logged_or_changed(self):
        messages = [dict(type="websocket.accept"), dict(type="websocket.send", bytes=b"customer")]
        records, delivered = await self.call(dict(type="websocket", path="/_stcore/stream",
            query_string=b"token=private"), messages)
        self.assertEqual(records, [dict(stage="websocket_accept", duration_ms=25)])
        self.assertEqual(delivered, messages)
        self.assertNotIn("private", json.dumps(records))
        self.assertNotIn("customer", json.dumps(records))

    async def test_lifespan_failure_preserved_and_success_measured(self):
        records, messages = [], []
        trace = StartupTrace(clock=lambda: 1, emit=records.append)
        async def app(scope, receive, send):
            await send(dict(type="lifespan.startup.complete"))
            await send(dict(type="lifespan.shutdown.complete"))
        async def send(message):
            messages.append(message)
        await StartupTimingMiddleware(app, trace=trace)(dict(type="lifespan"), None, send)
        self.assertEqual(records[0]["stage"], "lifespan_ready")
        self.assertEqual(len(messages), 2)
        async def fail(scope, receive, send):
            await send(dict(type="lifespan.startup.failed", message="original"))
        records.clear()
        await StartupTimingMiddleware(fail, trace=trace)(dict(type="lifespan"), None, send)
        self.assertEqual(records, [])
        self.assertEqual(messages[-1]["message"], "original")

    async def test_actual_health_wrapper_still_bypasses_all_inner_work(self):
        tree = ast.parse((ROOT / "sports_cave_server.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                    and n.name == "ConstantTimeHealthMiddleware")
        ns = dict(MAIN_HEALTH_PATHS=frozenset({"/_stcore/health", "/healthz"}))
        exec(compile(ast.Module(body=[node], type_ignores=[]), "<health wrapper>", "exec"), ns)
        async def forbidden(*args):
            raise AssertionError("Health reached application lifecycle")
        app = ns["ConstantTimeHealthMiddleware"](StartupTimingMiddleware(forbidden))
        for path in ns["MAIN_HEALTH_PATHS"]:
            messages = []
            async def send(message):
                messages.append(message)
            await app(dict(type="http", path=path, method="GET"), None, send)
            self.assertEqual(messages[0]["status"], 200)
            self.assertEqual(messages[1]["body"], b"ok\n")


class ServerWiringTests(unittest.TestCase):
    def execute_entrypoint(self, fail_migrations=False):
        tree = ast.parse((ROOT / "sports_cave_server.py").read_text(encoding="utf-8"))
        entrypoint = next(n for n in tree.body if isinstance(n, ast.If)
                          and ast.unparse(n.test) == "__name__ == '__main__'")
        calls = []
        def action(name):
            def run(*args, **kwargs):
                calls.append(name)
                if fail_migrations and name == "migrations":
                    raise RuntimeError("fixture migration failure")
            return run
        modules = {
            "uvicorn": SimpleNamespace(run=action("listen")),
            "product_quiz_worker": SimpleNamespace(start_app_reconciler=action("quiz")),
            "home_crm_reporting": SimpleNamespace(start_app_reconciler=action("crm")),
            "crm_thumbnail_cache": SimpleNamespace(warm_renderer=action("thumbnail")),
            "auto_editions_runtime": SimpleNamespace(start_worker=action("editions")),
            "prodigi_status_sync": SimpleNamespace(start_worker=action("tracking")),
            "database_read_pool": SimpleNamespace(warm_application_reads=action("pool")),
        }
        import builtins
        ns = dict(__builtins__={**vars(builtins), "__import__":lambda name, *a, **k: modules[name]},
            BOOT_TRACE=StartupTrace(emit=lambda record: None), app=object(),
            os=SimpleNamespace(getenv=lambda key, default=None: True if key=="RENDER" else default),
            run_migrations=SimpleNamespace(run_deployment_migrations=action("migrations"),
                get_database_url=lambda: ("", "")),
            prepare_google_seo_storage=action("seo"),
            collector_vault=SimpleNamespace(log_collector_vault_readiness=action("vault")))
        try:
            exec(compile(ast.Module(body=entrypoint.body, type_ignores=[]), "<server entrypoint>", "exec"), ns)
        except RuntimeError:
            if not fail_migrations:
                raise
        return calls

    def test_actual_entrypoint_keeps_startup_order_and_migration_failure_closed(self):
        self.assertEqual(self.execute_entrypoint(), ["migrations","seo","vault","quiz","crm",
                         "thumbnail","editions","tracking","pool","listen"])
        self.assertEqual(self.execute_entrypoint(fail_migrations=True), ["migrations"])


class FixtureIsolationTests(unittest.TestCase):
    def test_child_environment_excludes_provider_settings(self):
        from scripts.benchmark_app_startup import child_environment
        from unittest.mock import patch
        with patch.dict("os.environ", {"PATH":"local", "DATABASE_URL":"private",
                "RENDER":"true", "SHOPIFY_TOKEN":"private", "PYTHONPATH":"private"}, clear=True):
            child = child_environment()
        self.assertEqual(child["PATH"], "local")
        self.assertNotIn("DATABASE_URL", child)
        self.assertNotIn("RENDER", child)
        self.assertNotIn("SHOPIFY_TOKEN", child)
        self.assertNotIn("PYTHONPATH", child)

    def test_fixture_rejects_external_connects_before_network_io(self):
        from scripts.startup_fixture_server import deny_external_network
        for address in [("127.0.0.1", 9000), ("::1", 9000), ("localhost", 9000)]:
            deny_external_network("socket.connect", (None,address))
        for address in [("203.0.113.1", 443), ("provider.invalid", 443)]:
            with self.assertRaises(PermissionError):
                deny_external_network("socket.connect", (None,address))


if __name__ == "__main__":
    unittest.main()
