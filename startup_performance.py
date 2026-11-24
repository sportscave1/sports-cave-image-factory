"""Small, credential-free startup diagnostics. No storage or provider imports."""
from contextlib import contextmanager
import json
import logging
import re
import time

LOG = logging.getLogger(__name__)


class StartupTrace:
    """Process startup stages; values are developer-defined labels and timings."""

    def __init__(self, *, clock=time.perf_counter, emit=None):
        self.clock = clock
        self.started = self.previous = clock()
        self.emit = emit or (lambda value: LOG.info("PERF_BOOT %s", json.dumps(value, sort_keys=True)))

    def mark(self, stage):
        if not re.fullmatch(r"[a-z_]{1,48}", stage):
            raise ValueError("Use a fixed startup stage label.")
        now = self.clock()
        record = dict(stage=stage, elapsed_ms=round((now-self.started)*1000, 3),
                      stage_ms=round((now-self.previous)*1000, 3))
        self.previous = now
        self.emit(record)
        return record

    @contextmanager
    def span(self, stage):
        self.mark(stage + "_start")
        try:
            yield
        except BaseException:
            self.mark(stage + "_failed")
            raise
        else:
            self.mark(stage + "_done")


class StartupTimingMiddleware:
    """Time public shell/assets and WebSocket acceptance, never payloads or IDs.

    Server-Timing ends at response headers, not at download completion or page
    readiness. No response buffering, extra requests, cache or polling is added.
    Liveness, private APIs, media and event streams pass through untouched.
    """

    def __init__(self, app, *, trace=None, clock=time.perf_counter, emit=None):
        self.app, self.trace, self.clock = app, trace, clock
        self.emit = emit or (lambda value: LOG.info("PERF_TRANSPORT %s", json.dumps(value, sort_keys=True)))

    async def __call__(self, scope, receive, send):
        kind, path = scope.get("type"), scope.get("path", "")
        if kind == "lifespan" and self.trace is not None:
            async def lifespan_send(message):
                if message["type"] == "lifespan.startup.complete":
                    self.trace.mark("lifespan_ready")
                await send(message)
            return await self.app(scope, receive, lifespan_send)
        root = scope.get("root_path", "").rstrip("/")
        if root and path.startswith(root + "/"):
            path = path[len(root):]
        document = path in {"/", "/app", "/app/"}
        bundle = ((path.startswith("/static/js/") and path.endswith(".js")) or
                  (path.startswith("/static/css/") and path.endswith(".css")))
        websocket = kind == "websocket" and path == "/_stcore/stream"
        if not websocket and not (kind == "http" and scope.get("method") == "GET" and (document or bundle)):
            return await self.app(scope, receive, send)
        started = self.clock()
        recorded = False

        async def timed_send(message):
            nonlocal recorded
            response = message["type"] == "http.response.start"
            accepted = message["type"] == "websocket.accept"
            if not recorded and (response or accepted):
                recorded = True
                duration = round((self.clock()-started)*1000, 3)
                category = "websocket_accept" if accepted else "document" if document else "bundle"
                self.emit(dict(stage=category, duration_ms=duration,
                               **({"status": message["status"]} if response else {})))
                if response:
                    message = {**message, "headers": [
                        *message.get("headers", []),
                        (b"server-timing", f"os_headers;dur={duration:.3f}".encode("ascii")),
                    ]}
            await send(message)
        await self.app(scope, receive, timed_send)
