"""Disposable release transactions; no installation, native input or package downloads."""
import io
import asyncio
import json
import re
from pathlib import Path
import struct
import zipfile

import pytest
from unittest.mock import AsyncMock
from task_recorder.release import (activate, build_package, prepare, rollback,
                                   verify_archive, verify_directory)

ROOT = Path(__file__).resolve().parents[1]


def package(tmp_path, suffix=b""):
    # PE header fixture validates archive architecture rules, not executable behavior.
    pe = bytearray(128)
    pe[:2] = b"MZ"
    struct.pack_into("<I", pe, 60, 64)
    pe[64:68] = b"PE\0\0"
    struct.pack_into("<H", pe, 68, 0x8664)
    native = tmp_path / "synthetic.exe"
    native.write_bytes(pe + suffix)
    return build_package(ROOT, native)


def extract(data, target):
    verify_archive(data)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        archive.extractall(target)
    return target


def prepared_commands(argv):
    # Simulate dependency setup only; never run pip, native code or the helper.
    if argv[1:3] == ["-m", "venv"]:
        python = Path(argv[3]) / "Scripts/python.exe"
        python.parent.mkdir(parents=True)
        python.write_bytes(b"synthetic-python")


def test_bundle_is_deterministic_complete_and_rejects_tampering(tmp_path):
    data = package(tmp_path)
    assert data == package(tmp_path)
    source = extract(data, tmp_path / "source")
    manifest, identity = verify_directory(source)
    assert identity == verify_archive(data)
    assert "desktop_recorder/bin/DesktopRecorder.exe" in manifest["files"]
    assert "desktop_recorder/helper.py" in manifest["files"]
    with zipfile.ZipFile(io.BytesIO(data)) as original:
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as changed:
            for name in original.namelist():
                changed.writestr(name, original.read(name) + (b"changed" if name == "task_recorder/server.py" else b""))
    with pytest.raises(ValueError, match="integrity"):
        verify_archive(stream.getvalue())
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("../outside", "no")
    with pytest.raises(ValueError, match="path"):
        verify_archive(stream.getvalue())


def test_update_failure_and_rollback_preserve_all_data(tmp_path):
    install = tmp_path / "TaskRecorderHelper"
    data = tmp_path / "TaskRecorderV1"
    data.mkdir()
    expected = {"saved.json":b"saved", "draft.json":b"interrupted", "commands.sqlite":b"receipts",
                "settings.json":b"startup-and-settings", "browser-profile/cookies":b"private-profile"}
    for name, value in expected.items():
        path = data / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(value)
    source = extract(package(tmp_path), tmp_path / "source")
    first = prepare(source, install, "synthetic-bootstrap", prepared_commands)
    assert len(first) == 20
    ready = json.loads((install / "releases" / first / "ready.json").read_text())
    assert ready["package_id"] == verify_archive(package(tmp_path))
    activate(install, first, lambda:None)
    active = (install / "active.txt").read_bytes()
    def fail(argv):
        prepared_commands(argv)
        if "pip" in argv:
            raise RuntimeError("synthetic dependency failure")
    with pytest.raises(RuntimeError, match="dependency failure"):
        prepare(source, install, "synthetic-bootstrap", fail)
    assert (install / "active.txt").read_bytes() == active
    second_source = extract(package(tmp_path, b"second"), tmp_path / "second-source")
    second = prepare(second_source, install, "synthetic-bootstrap", prepared_commands)
    assert second != first
    def busy():
        raise RuntimeError("recorder busy")
    with pytest.raises(RuntimeError, match="busy"):
        activate(install, second, busy)
    assert (install / "active.txt").read_bytes() == active
    activate(install, second, lambda:None)
    assert rollback(install, lambda:None) == first
    assert (install / "active.txt").read_text().strip() == first
    assert {name:(data/name).read_bytes() for name in expected} == expected
    assert (install / "releases" / second / "ready.json").exists()


def test_source_tampering_cannot_prepare_or_change_active_release(tmp_path):
    source = extract(package(tmp_path), tmp_path / "source")
    install = tmp_path / "TaskRecorderHelper"
    (source / "desktop_recorder/helper.py").write_text("changed")
    calls = []
    with pytest.raises(ValueError, match="integrity"):
        prepare(source, install, "synthetic-bootstrap", calls.append)
    assert not calls and not install.exists()


def test_authenticated_download_serves_verified_bundle_or_reports_unavailable(tmp_path, monkeypatch):
    from task_recorder import hosted_api
    actor = AsyncMock(return_value={"id":"synthetic-admin"})
    monkeypatch.setattr(hosted_api, "actor", actor)
    monkeypatch.setattr(hosted_api, "ROOT", tmp_path / "no-native-build")
    monkeypatch.delenv("SPORTS_CAVE_RECORDER_WINDOWS_PACKAGE", raising=False)
    unavailable = asyncio.run(hosted_api.setup(object()))
    assert unavailable.status_code == 503
    data = package(tmp_path)
    archive = tmp_path / "reviewed.zip"
    archive.write_bytes(data)
    monkeypatch.setenv("SPORTS_CAVE_RECORDER_WINDOWS_PACKAGE", str(archive))
    response = asyncio.run(hosted_api.setup(object()))
    assert response.status_code == 200 and response.body == data
    assert response.media_type == "application/zip"
    assert actor.await_count == 2
    # Linux production serves the exact reviewed Windows artifact, without
    # compiling native code or changing service environment variables.
    reviewed = hosted_api.ROOT / "recorder-releases/windows/SportsCaveTaskRecorder.zip"
    reviewed.parent.mkdir(parents=True)
    reviewed.write_bytes(data)
    monkeypatch.delenv("SPORTS_CAVE_RECORDER_WINDOWS_PACKAGE")
    response = asyncio.run(hosted_api.setup(object()))
    assert response.status_code == 200 and response.body == data
    assert actor.await_count == 3


def test_generated_launchers_accept_prepared_and_previous_release_ids(tmp_path):
    from task_recorder.install import write_launchers
    source = extract(package(tmp_path), tmp_path / "source")
    install = tmp_path / "TaskRecorderHelper"
    prepared = prepare(source, install, "synthetic-bootstrap", prepared_commands)
    write_launchers(install)
    rollback_script = (install / "Rollback.ps1").read_text(encoding="utf-8")
    start_script = (install / "Start.vbs").read_text(encoding="utf-8")
    patterns = [re.search(r"-notmatch '([^']+)'", rollback_script).group(1),
                re.search(r'pattern.Pattern = "([^"]+)"', start_script).group(1)]
    for pattern in patterns:
        assert re.fullmatch(pattern, prepared)
        assert re.fullmatch(pattern, "a" * 64)
        assert not re.fullmatch(pattern, "../other-release")
        assert not re.fullmatch(pattern, "a" * 19)


def test_update_shutdown_reset_waits_for_listener_refusal(monkeypatch,tmp_path):
    from task_recorder import install
    from urllib.error import URLError
    from unittest.mock import Mock, MagicMock
    monkeypatch.setattr(install,"connection",lambda data:("http://127.0.0.1:18999","synthetic-key"))
    state=Mock(side_effect=[{"mode":"stopped"},ConnectionResetError(),URLError(ConnectionRefusedError())])
    monkeypatch.setattr(install,"state_at",state)
    shutdown=MagicMock()
    monkeypatch.setattr(install,"urlopen",shutdown)
    monkeypatch.setattr(install.time,"sleep",lambda seconds:None)
    install.stop_idle(tmp_path)
    assert state.call_count==3  # A reset is not proof that the listener exited.
    assert shutdown.call_count==1


@pytest.mark.skipif(__import__('os').name!='nt',reason='Windows recorder process lock')
def test_offline_update_requires_exclusive_recorder_lock(tmp_path,monkeypatch):
    from task_recorder import install
    from task_recorder.server import instance_lock
    from unittest.mock import Mock
    lock=tmp_path/'recorder.lock';lock.write_bytes(b'0')
    state=Mock(side_effect=AssertionError('Offline update must not use a stale connection'))
    monkeypatch.setattr(install,'state_at',state)
    with instance_lock(lock):
        assert not install.recorder_inactive(tmp_path)
    assert install.recorder_inactive(tmp_path)
    install.stop_idle(tmp_path)
    state.assert_not_called()
    assert lock.read_bytes()==b'0'


@pytest.mark.skipif(__import__('os').name!='nt',reason='Actual Windows Script Host')
def test_actual_start_launcher_reads_newline_terminated_release_pointer(tmp_path):
    from task_recorder.install import write_launchers
    import subprocess
    for selected,ending in [('a'*20,'\n'),('b'*64,'\r\n'),('legacy','\n')]:
        write_launchers(tmp_path)
        (tmp_path/'active.txt').write_bytes((selected+ending).encode())
        app=(tmp_path if selected=='legacy' else tmp_path/'releases'/selected)/'app'
        app.mkdir(parents=True,exist_ok=True)
        script=tmp_path/'Start.vbs'
        lines=script.read_text().splitlines()
        # Execute the real generated selection/validation code. Intercept only
        # its final helper launch, so this check never starts a server or UI.
        assert lines[-1].startswith('sh.Run ')
        script.write_text('\r\n'.join(lines[:-1]+['WScript.Echo selected'])+'\r\n')
        result=subprocess.run(['cscript.exe','//nologo',str(script)],capture_output=True,text=True,
                              timeout=5,creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode==0,result.stderr
        assert result.stdout.strip()==selected
