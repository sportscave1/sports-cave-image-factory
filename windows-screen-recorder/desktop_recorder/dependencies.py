"""Load the normal helper package; recovery archives are never runtime inputs."""
import importlib.util
import os
from pathlib import Path
import sys


def load(root):
    # Release packaging installs task_recorder alongside desktop_recorder.
    source = os.environ.get("SPORTS_CAVE_RECORDER_SOURCE")
    if source:
        source = Path(source).resolve()
        if not (source / "task_recorder" / "store.py").is_file():
            raise RuntimeError("Configured helper package is missing task_recorder/store.py.")
        if str(source) not in sys.path:
            sys.path.insert(0, str(source))
    spec = importlib.util.find_spec("task_recorder")
    if spec is None:
        raise RuntimeError("Install the reviewed task_recorder package, or set SPORTS_CAVE_RECORDER_SOURCE to its source directory. Recovery archives are not runtime dependencies.")
    return Path(next(iter(spec.submodule_search_locations))).parent
