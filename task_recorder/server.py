"""Authenticated loopback service; intentionally independent of Sports Cave workers."""
import argparse
import asyncio
import concurrent.futures
import contextlib
import hmac
import json
import os
import secrets
import socket
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from .runner import Runner
from .schema import Invalid
from .store import atomic

ASSETS = Path(__file__).parent
DEFAULT_PORT = 18931

def default_root():
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / "SportsCaveOS" / "TaskRecorderV1"

def protect(data, decrypt=False):
    # Reuse existing Windows DPAPI primitive without importing its companion or queues.
    sys.path.insert(0, str(ASSETS.parent / "scripts" / "studio"))
    try:
        from device_trust import protect as dpapi
        return dpapi(data, decrypt)
    finally:
        sys.path.pop(0)

@contextlib.contextmanager
def instance_lock(path):
    """Lock only the recorder's own profile; never import/start a companion."""
    import msvcrt
    with path.open("a+b", buffering=0) as handle:
        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b"0")
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError("Task Recorder is already starting or running.")
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

class Bridge(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def __init__(self, root, port=DEFAULT_PORT, *, headless=False):
        self.origin = "http://127.0.0.1:" + str(port)
        self.token = secrets.token_urlsafe(32)
        self.root = Path(root)
        self.loop = asyncio.new_event_loop()
        self.runner = Runner(root, headless=headless)
        super().__init__(("127.0.0.1", port), Handler)
        self.origin = "http://127.0.0.1:" + str(self.server_port)
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()

    def invoke(self, command, data=None):
        future = asyncio.run_coroutine_threadsafe(self.runner.command(command, data or {}), self.loop)
        try: return future.result(timeout=45)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise Invalid("Command timed out. Inspect the browser; use Stop before trying again.")

    def close(self):
        try:
            asyncio.run_coroutine_threadsafe(self.runner.close(), self.loop).result(timeout=15)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(timeout=5)
            if not self.thread.is_alive():
                self.loop.close()
            self.server_close()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # Never log request headers, URL fragments, inputs or browser content.

    def reply(self, code, body, mime="application/json"):
        raw = json.dumps(body).encode() if mime == "application/json" else body
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
            "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
            "img-src 'self' data:; frame-ancestors 'self' http://127.0.0.1:8501 http://localhost:8501; "
            "base-uri 'none'; form-action 'self'; " +
            ("frame-src 'self'" if self.path.startswith("/demo") else "frame-src 'none'"))
        self.end_headers()
        try: self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError): pass

    def guard(self, auth=False):
        if self.headers.get_all("Host") != [self.server.origin.removeprefix("http://")]:
            self.reply(403, {"error": "Host rejected."}); return False
        origin = self.headers.get("Origin")
        if origin and origin != self.server.origin:
            self.reply(403, {"error": "Origin rejected."}); return False
        if auth:
            candidate = self.headers.get("X-Recorder-Key", "")
            if not hmac.compare_digest(candidate.encode(), self.server.token.encode()):
                self.reply(401, {"error": "Open Start Task Recorder.cmd to connect locally."}); return False
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                self.reply(403, {"error": "Cross-site API requests rejected."}); return False
        return True

    def do_OPTIONS(self):
        self.reply(403, {"error": "Cross-origin control is disabled."})

    def do_GET(self):
        if not self.guard(auth=self.path.startswith("/api/")): return
        if self.path == "/api/state":
            self.reply(200, self.server.invoke("state")); return
        routes = {"/": ("ui.html", "text/html; charset=utf-8"),
                  "/ui.js": ("ui.js", "text/javascript; charset=utf-8"),
                  "/ui.css": ("ui.css", "text/css; charset=utf-8"),
                  "/demo": ("demo.html", "text/html; charset=utf-8"),
                  "/demo/form": ("demo.html", "text/html; charset=utf-8"),
                  "/demo/signin": ("demo.html", "text/html; charset=utf-8"),
                  "/demo.js": ("demo.js", "text/javascript; charset=utf-8")}
        if self.path not in routes:
            self.reply(404, {"error": "Not found."}); return
        file, mime = routes[self.path]
        self.reply(200, (ASSETS / file).read_bytes(), mime)

    def do_POST(self):
        if not self.guard(auth=True): return
        if self.headers.get("Content-Type") != "application/json" or self.headers.get("Transfer-Encoding"):
            self.reply(415, {"error": "JSON with Content-Length required."}); return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 512000: raise Invalid("Request size rejected.")
            self.connection.settimeout(5)
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict): raise Invalid("Expected a JSON object.")
            if self.path == "/api/shutdown":
                self.server.invoke("stop")
                self.reply(200, {"stopping": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if not self.path.startswith("/api/"): raise Invalid("Unknown endpoint.")
            self.reply(200, self.server.invoke(self.path.removeprefix("/api/"), data))
        except Invalid as exc:
            self.reply(400, {"error": str(exc)})
        except (ValueError, TimeoutError, OSError):
            self.reply(400, {"error": "Invalid or incomplete request."})
        except Exception:
            self.reply(500, {"error": "Local runner error. Inspect the browser, then Stop; no automatic retries."})

def existing(root):
    try:
        cfg = json.loads((root / "connection.json").read_text(encoding="utf-8"))
        key = protect(bytes.fromhex(cfg["protected"]), True).decode()
        origin = cfg["origin"]
        # Only accept the exact loopback address and a numeric port.
        from urllib.parse import urlsplit
        parsed = urlsplit(origin)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.path or parsed.query or parsed.fragment:
            return None
        if origin != "http://127.0.0.1:" + str(parsed.port): return None
        with urlopen(Request(origin + "/api/state", headers={"X-Recorder-Key": key}), timeout=2) as response:
            json.load(response)
        return origin, key
    except Exception:
        return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=default_root())
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--shutdown", action="store_true")
    args = parser.parse_args()
    root = args.data_dir.resolve()
    repo = ASSETS.parent.resolve()
    if root == repo or repo in root.parents:
        raise SystemExit("Recorder data/profile must be outside the Git worktree.")
    root.mkdir(parents=True, exist_ok=True)
    live = existing(root)
    if live:
        origin, key = live
        if args.shutdown:
            with urlopen(Request(origin + "/api/shutdown", data=b"{}", headers={
                "X-Recorder-Key": key, "Content-Type": "application/json"}), timeout=15):
                pass
        elif args.open: webbrowser.open(origin + "/#key=" + key)
        else: print("Task Recorder is already running.")
        return
    if args.shutdown: return
    # Independent lock: never touch editions companion locks or process IDs.
    with instance_lock(root / "recorder.lock"):
        server = Bridge(root, args.port)
        atomic(root / "connection.json", {"origin": server.origin, "protected": protect(server.token.encode()).hex()})
        if args.open: webbrowser.open(server.origin + "/#key=" + server.token)
        print("Task Recorder ready at " + server.origin + " (authenticated local control).", flush=True)
        try: server.serve_forever(poll_interval=.2)
        except KeyboardInterrupt: pass
        finally: server.close()

if __name__ == "__main__":
    main()
