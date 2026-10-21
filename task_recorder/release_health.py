"""Offline package import check: no helper, native window, data store or relay starts."""
import argparse
import asyncio
from importlib import metadata
from pathlib import Path
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", required=True, type=Path)
    args = parser.parse_args()
    root = args.app.resolve()
    sys.path.insert(0, str(root))
    from task_recorder.release import verify_directory
    verify_directory(root)
    import task_recorder.server
    import desktop_recorder.helper
    from desktop_recorder.helper import DesktopRunner, native_path
    assert root in Path(task_recorder.server.__file__).resolve().parents
    assert root in Path(desktop_recorder.helper.__file__).resolve().parents
    assert native_path().resolve() == root / "desktop_recorder/bin/DesktopRecorder.exe"
    assert issubclass(DesktopRunner, task_recorder.server.Runner)
    for requirement in (root / "task_recorder/requirements-windows.txt").read_text().splitlines():
        requirement = requirement.strip()
        if not requirement or requirement.startswith("#"):
            continue
        name, version = requirement.split("==")
        if metadata.version(name) != version:
            raise RuntimeError("Installed dependency does not match package: " + name)
    with tempfile.TemporaryDirectory(prefix="recorder-package-check-") as temporary:
        runner = DesktopRunner(Path(temporary))
        try:
            state = runner.state()
            assert state["desktop_capabilities"]["capture"] is True
            assert state["desktop_capabilities"]["playback"] is True
            assert state["tasks"] == []
        finally:
            asyncio.run(runner.close())
    print("Windows recorder package verified; isolated adapter initialized. No server or native window started.")


if __name__ == "__main__":
    main()
