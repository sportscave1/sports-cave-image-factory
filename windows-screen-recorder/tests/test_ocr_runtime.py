from pathlib import Path
import os
import pytest
from desktop_recorder.ocr_runtime import configure


def test_release_paths_are_complete_and_replace_inherited_candidate_settings(tmp_path, monkeypatch):
    package = tmp_path / 'release/app/desktop_recorder'
    package.mkdir(parents=True)
    monkeypatch.setenv('SC_RECORDER_OCR_WORKER', 'old-candidate')
    assert configure(tmp_path / 'data', package) is False
    assert os.environ['SC_RECORDER_OCR_WORKER'] == 'old-candidate'
    (package / 'bin').mkdir()
    (package / 'bin/DesktopRecorder.exe').touch()
    with pytest.raises(RuntimeError, match='incomplete'):
        configure(tmp_path / 'data', package)
    assert os.environ['SC_RECORDER_OCR_WORKER'] == 'old-candidate'
    release = package.parent.parent
    (release / 'venv/Scripts').mkdir(parents=True)
    (release / 'venv/Scripts/python.exe').touch()
    (release / 'ocr').mkdir()
    (package / 'thumbnail_ocr_worker.py').touch()
    for key in ('PYTHON', 'LIBRARY', 'DATA'):
        monkeypatch.setenv('SC_RECORDER_OCR_' + key, 'old-candidate')
    assert configure(tmp_path / 'data', package)
    assert Path(os.environ['SC_RECORDER_OCR_LIBRARY']) == release / 'ocr'
    assert Path(os.environ['SC_RECORDER_OCR_WORKER']) == package / 'thumbnail_ocr_worker.py'
    assert Path(os.environ['SC_RECORDER_OCR_DATA']) == tmp_path / 'data/thumbnail-proof'
