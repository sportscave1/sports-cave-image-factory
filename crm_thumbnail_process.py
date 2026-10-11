"""Bounded renderer output and cleanup of its browser/installer process tree."""
import os
import signal
import subprocess
import tempfile


def run_renderer(command, *, timeout=120, env=None):
    options = {'start_new_session': True} if os.name == 'posix' else {
        'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0)}
    # Browser/installer output must not accumulate in the long-lived worker.
    with tempfile.TemporaryFile() as errors:
        child = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=errors, env=env, **options)
        try:
            code = child.wait(timeout=timeout)
            errors.seek(max(0, errors.tell() - 1024))
            return subprocess.CompletedProcess(command, code, b'', errors.read(1024))
        finally:
            if os.name == 'posix':
                # subprocess.run(timeout=...) kills only the Python parent;
                # Chromium, Playwright and an installer may otherwise survive.
                try: os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError: pass
            elif child.poll() is None:
                import psutil
                try: descendants = psutil.Process(child.pid).children(recursive=True)
                except psutil.NoSuchProcess: descendants = []
                for process in reversed(descendants):
                    try: process.kill()
                    except psutil.NoSuchProcess: pass
                child.kill()
                psutil.wait_procs(descendants, timeout=5)
            child.wait()
