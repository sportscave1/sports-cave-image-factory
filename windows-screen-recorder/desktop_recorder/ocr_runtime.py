"""Select only local OCR dependencies belonging to this installed release."""
import os
from pathlib import Path


def configure(data, package=None):
    package = Path(package or Path(__file__).resolve().parent).resolve()
    if not (package / 'bin/DesktopRecorder.exe').is_file():
        return False
    release = package.parent.parent
    paths = {
        'PYTHON': release / 'venv/Scripts/python.exe',
        'WORKER': package / 'thumbnail_ocr_worker.py',
        'LIBRARY': release / 'ocr',
        'DATA': Path(data).resolve() / 'thumbnail-proof',
    }
    if not all(paths[key].is_file() for key in ('PYTHON', 'WORKER')) or not paths['LIBRARY'].is_dir():
        raise RuntimeError('Installed local caption runtime is incomplete. Repair this release before playback.')
    for name, path in paths.items():
        os.environ['SC_RECORDER_OCR_' + name] = str(path)
    return True
