"""Run Files contracts with outbound sockets denied and no inherited provider secrets."""
import os
import subprocess
import sys
from pathlib import Path

MODULES = ["tests.test_files_window", "tests.test_files_upload_api", "tests.test_files_window_launcher",
           "tests.test_files_performance_v2", "tests.test_files_native_v2", "tests.test_files_premium_native",
           "tests.test_files_premium_preservation"]
if __name__ == "__main__":
    if "--child" not in sys.argv:
        env = {k: v for k, v in os.environ.items() if k.upper() in {
            "SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "COMSPEC", "USERPROFILE", "APPDATA", "LOCALAPPDATA"}}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        raise SystemExit(subprocess.call([sys.executable, __file__, "--child", *sys.argv[1:]], env=env))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import socket
    original_connect = socket.socket.connect
    def guarded_connect(sock, address):
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1", "localhost"}:
            return original_connect(sock, address)
        raise RuntimeError("External networking is forbidden in Files synthetic tests")
    socket.socket.connect = guarded_connect
    if "--baseline" in sys.argv:
        sys.argv.remove("--baseline")
        import types
        root = Path(__file__).resolve().parents[1]
        baseline = "823a1966"
        paths = ["files_upload_api.py", "components/files_window/index.html", "components/files_image_viewer/index.html", "components/files_window_launcher/index.html"]
        sources = {str((root / name).resolve()): subprocess.check_output(["git", "show", f"{baseline}:{name}"], cwd=root).decode("utf-8") for name in paths}
        read_text = Path.read_text
        def baseline_read(path, *args, **kwargs):
            return sources.get(str(path.resolve())) if str(path.resolve()) in sources else read_text(path, *args, **kwargs)
        Path.read_text = baseline_read
        mod = types.ModuleType("files_upload_api")
        mod.__file__ = str(root / "files_upload_api.py")
        sys.modules[mod.__name__] = mod
        exec(compile(sources[mod.__file__], mod.__file__, "exec"), mod.__dict__)
    import unittest
    modules = [a for a in sys.argv[1:] if a != "--child"] or MODULES
    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    raise SystemExit(not result.wasSuccessful())
