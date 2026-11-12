"""Focused tests with a credential-free environment; fixed disposable PostgreSQL."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA"}
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env["SPORTS_CAVE_AI_ENABLED"] = "0"
    env["SPORTS_CAVE_AI_WORKER_ENABLED"] = "0"
    env["PYTHONUTF8"] = "1"
    raise SystemExit(subprocess.call([sys.executable, "-m", "unittest",
        *(sys.argv[1:] or ["tests.test_source_data_repairs"]), "-v"], cwd=ROOT, env=env))
