"""HTTP boundary tests use only disposable synthetic draft fixtures, never the app."""
import http.client
import json
import threading
import time
import unittest
from unittest.mock import patch
from pathlib import Path
import test_drafts
import draft_ui
import studio

class UITests(unittest.TestCase):
    setUp = test_drafts.DraftTests.setUp

    def server(self, owner="owner-a", idle=30):
        server = draft_ui.DraftServer(self.home, "task-a", owner, idle)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        def cleanup():
            server.stopping = True
            thread.join(4)
            self.assertFalse(thread.is_alive())
        self.addCleanup(cleanup)
        return server

    def request(self, server, path="/api/state", data=None, headers=None, method=None):
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=4)
        body = json.dumps(data) if data is not None else None
        actual = {"X-Studio-Token": server.token}
        if body:
            actual["Content-Type"] = "application/json"
        actual.update(headers or {})
        conn.request(method or ("POST" if data is not None else "GET"), path, body=body, headers=actual)
        response = conn.getresponse()
        result = (response.status, response.read(), dict(response.getheaders()))
        conn.close()
        return result

    def test_two_servers_unique_ports_and_tokens(self):
        a, b = self.server(), self.server()
        self.assertNotEqual(a.server_port, b.server_port)
        self.assertNotEqual(a.token, b.token)
        self.assertEqual(a.server_address[0], "127.0.0.1")
        self.assertEqual(self.request(b, headers={"X-Studio-Token": a.token})[0], 401)

    def test_missing_token_bad_host_and_cross_origin(self):
        s = self.server()
        for headers, expected in [
            ({"X-Studio-Token": ""}, 401),
            ({"Host": "evil.example"}, 403),
            ({"Origin": "https://evil.example"}, 403)]:
            self.assertEqual(self.request(s, headers=headers)[0], expected)

    def test_save_reopen_conflict_and_recovery(self):
        s = self.server()
        status, _, _ = self.request(s, "/api/action", {"action": "new", "name": "Test"})
        self.assertEqual(status, 200)
        command = {"action": "save", "expected_revision": 0, "files": ["screen.html"]}
        self.assertEqual(self.request(s, "/api/action", command)[0], 200)
        self.assertEqual(self.request(s, "/api/action", command)[0], 409)
        status, payload, _ = self.request(s)
        self.assertEqual(json.loads(payload)["draft"]["revision"], 1)
        status, payload, _ = self.request(s, "/api/action", {"action": "recover", "revision": 1})
        self.assertEqual(status, 200)
        recovery = Path(json.loads(payload)["recovery_path"])
        self.assertEqual((recovery/"screen.html").read_bytes(), self.source.read_bytes())

    def test_scope_cannot_be_overridden_and_owner_change_denied(self):
        s = self.server()
        payload = {"action": "new", "name": "Scoped", "owner": "intruder", "task_id": "other", "home": "C:/"}
        _, body, _ = self.request(s, "/api/action", payload)
        self.assertEqual(json.loads(body)["task_id"], "task-a")
        registry = studio.read(self.home/".studio/registry.json")
        registry["tasks"][0]["owner"] = "changed"
        studio.atomic(self.home/".studio/registry.json", registry)
        self.assertEqual(self.request(s)[0], 409)

    def test_wrong_owner_cannot_start(self):
        with self.assertRaises(RuntimeError):
            draft_ui.DraftServer(self.home, "task-a", "intruder")

    def test_preview_and_source_paths_denied(self):
        s = self.server()
        self.request(s, "/api/action", {"action": "new", "name": "Test"})
        for action in ("start-preview", "stop-preview", "restart-preview", "execute", "restore"):
            self.assertEqual(self.request(s, "/api/action", {"action": action})[0], 409)
        for path in ("/../studio.py", "/screen.html", "/.env", "/api/state?task=other"):
            self.assertEqual(self.request(s, path)[0], 404)
        bad = {"action": "save", "expected_revision": 0, "files": ["../screen.html"]}
        self.assertEqual(self.request(s, "/api/action", bad)[0], 409)

    def test_static_csp_and_no_source_execution(self):
        s = self.server()
        status, body, headers = self.request(s, "/")
        self.assertEqual(status, 200)
        self.assertIn(b"Isolated development previews", body)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertNotIn(s.token.encode(), body)
        self.assertNotIn(b"Original", body)
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_invalid_payloads_fail_closed(self):
        s = self.server()
        self.assertEqual(self.request(s, "/api/action", ["not", "object"])[0], 409)
        self.assertEqual(self.request(s, "/api/action", {"action":"new","name":"x"*17000})[0], 409)
        self.assertEqual(self.request(s, "/api/action", {}, {"Content-Type":"text/plain"})[0], 409)

    def test_idle_shutdown_and_reopen(self):
        s = draft_ui.DraftServer(self.home, "task-a", "owner-a", idle_seconds=0.05)
        start = time.monotonic()
        s.run()
        self.assertLess(time.monotonic()-start, 2)
        fresh = self.server()
        self.assertEqual(self.request(fresh)[0], 200)

    def test_editor_http_allowlist_and_stale_save(self):
        import test_editor
        (self.root/"app.py").write_text(test_editor.FIXTURE)
        s=self.server()
        self.request(s,"/api/action",{"action":"new","name":"Editor HTTP"})
        status,payload,_=self.request(s,"/api/action",{"action":"editor-open","path":"app.py"})
        self.assertEqual(status,200)
        opened=json.loads(payload)
        command={"action":"editor-save","path":"app.py","expected_hash":opened["hash"],
                 "expected_revision":opened["revision"],"component":"title","changes":{"text":"HTTP edit"}}
        self.assertEqual(self.request(s,"/api/action",command)[0],200)
        self.assertEqual(self.request(s,"/api/action",command)[0],409)
        for path in ["../app.py",".env","sc_auth.py"]:
            self.assertEqual(self.request(s,"/api/action",{"action":"editor-open","path":path})[0],409)

    def test_editor_invalid_restore_is_rejected(self):
        import test_editor
        (self.root/"app.py").write_text(test_editor.FIXTURE)
        s=self.server()
        self.request(s,"/api/action",{"action":"new","name":"Editor HTTP"})
        _,payload,_=self.request(s,"/api/action",{"action":"editor-open","path":"app.py"})
        opened=json.loads(payload)
        command={"action":"editor-save","path":"app.py","expected_hash":opened["hash"],
                 "expected_revision":opened["revision"],"restore":["invalid"]}
        self.assertEqual(self.request(s,"/api/action",command)[0],409)
        self.assertEqual((self.root/"app.py").read_text(),test_editor.FIXTURE)

    def test_authenticated_stop_without_draft(self):
        s = self.server()
        self.assertEqual(self.request(s, "/api/action", {"action":"close"})[0], 200)
        self.assertTrue(s.stopping)

if __name__ == "__main__":
    unittest.main()
