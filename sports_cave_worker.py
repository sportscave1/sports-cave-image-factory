"""Supervise the existing SEO and CRM workers in one Render worker service."""

import logging
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent
LOG = logging.getLogger(__name__)
WORKERS = {
    "seo": ("google_seo_import.py", "worker", "--poll-seconds", "15"),
    "crm": ("crm_worker.py",),
}
RESTART_SECONDS = 5
SHUTDOWN_SECONDS = 20


class Supervisor:
    def __init__(self):
        self.stop = threading.Event()
        self.children = {}
        self.restart_at = {}

    def request_stop(self, *_args):
        self.stop.set()

    def check_children(self):
        for name, args in WORKERS.items():
            if self.stop.is_set():
                break
            child = self.children.get(name)
            if child is not None:
                code = child.poll()
                if code is None:
                    continue
                LOG.warning("worker_exited worker=%s exit_code=%s restart_seconds=%s",
                            name, code, RESTART_SECONDS)
                del self.children[name]
                self.restart_at[name] = time.monotonic() + RESTART_SECONDS
            if time.monotonic() < self.restart_at.get(name, 0):
                continue
            try:
                # No env override: both children inherit the service's complete
                # environment. Streams remain attached to Render's log capture.
                child = subprocess.Popen([sys.executable, "-u", *args], cwd=ROOT)
            except OSError as exc:
                # Never print exception text, commands, or environment values.
                LOG.error("worker_start_failed worker=%s error_type=%s restart_seconds=%s",
                          name, type(exc).__name__, RESTART_SECONDS)
                self.restart_at[name] = time.monotonic() + RESTART_SECONDS
            else:
                self.children[name] = child
                LOG.info("worker_started worker=%s pid=%s", name, child.pid)

    def shutdown(self):
        self.stop.set()
        deadline = time.monotonic() + SHUTDOWN_SECONDS
        # Signal all children before waiting on either one.
        for name, child in self.children.items():
            if child.poll() is None:
                LOG.info("worker_stopping worker=%s", name)
                try:
                    child.terminate()
                except ProcessLookupError:
                    pass
        for name, child in self.children.items():
            try:
                child.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                LOG.warning("worker_shutdown_timeout worker=%s", name)
                try:
                    child.kill()
                except ProcessLookupError:
                    pass
                child.wait()
        self.children.clear()

    def run(self):
        try:
            while not self.stop.is_set():
                self.check_children()
                self.stop.wait(0.5)
        finally:
            self.shutdown()
        return 0


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    supervisor = Supervisor()
    previous = {}
    try:
        for sig in (signal.SIGTERM, signal.SIGINT):
            previous[sig] = signal.signal(sig, supervisor.request_stop)
        return supervisor.run()
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    raise SystemExit(main())
