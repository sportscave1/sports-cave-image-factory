"""Mocked local outbox; never starts Codex or contacts production."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock
import uuid

sys.path.insert(0,str(Path(__file__).parents[1]/'scripts/studio'))
import edition_repair_local as local

def setup(monkeypatch,tmp_path):
    monkeypatch.setattr(local,'TARGET',tmp_path/'target.json')
    monkeypatch.setattr(local,'OUTBOX',tmp_path/'outbox')
    local.TARGET.write_text(json.dumps(dict(thread_id=str(uuid.uuid4()),cwd=str(tmp_path))))
    monkeypatch.setattr(local.shutil,'which',lambda _: 'C:/trusted/codex.exe')
    import device_trust
    monkeypatch.setattr(device_trust,'protect',lambda value,decrypt=False:value)

def test_local_handoff_is_once_and_acknowledged_only_after_result(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    entry=dict(request_id=str(uuid.uuid4()),product_gid='gid://shopify/Product/1',prompt='Inspect this exact PSD.',handoff_token=str(uuid.uuid4()))
    host=Mock(return_value={'repair':entry});launch=Mock()
    monkeypatch.setattr(local.subprocess,'Popen',launch)
    assert local.poll({},host)
    assert local.poll({},host)
    assert host.call_count==1 and launch.call_count==1
    file=next(local.OUTBOX.glob('*.dpapi'))
    local.atomic(file.with_suffix('.result.json'),dict(ok=False))
    assert local.poll({},host)
    assert host.call_args.args[1].endswith('repair-result')
    assert host.call_args.args[2]['ok'] is False
    assert not list(local.OUTBOX.glob('*.dpapi'))

def test_executor_uses_pinned_chat_stdin_and_existing_permissions(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    state=tmp_path/'state.dpapi';target=json.loads(local.TARGET.read_text())
    state.write_text(json.dumps(dict(target=target,repair=dict(prompt='exact scoped repair'),executable='C:/trusted/codex.exe')))
    execute=Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(local.subprocess,'run',execute)
    local.execute(state)
    command=execute.call_args.args[0]
    assert command==['C:/trusted/codex.exe','exec','resume','--json',target['thread_id'],'-']
    assert execute.call_args.kwargs['input']==b'exact scoped repair'
    assert json.loads(state.with_suffix('.result.json').read_text())==dict(ok=True)

def test_unconfigured_companion_does_not_claim(monkeypatch,tmp_path):
    monkeypatch.setattr(local,'TARGET',tmp_path/'missing.json');host=Mock()
    assert local.poll({},host) is False
    host.assert_not_called()


def test_background_path_falls_back_to_registered_desktop_package(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    monkeypatch.setattr(local.shutil,'which',lambda _:None)
    binary=tmp_path/'app/resources/codex.exe';binary.parent.mkdir(parents=True);binary.write_bytes(b'synthetic')
    monkeypatch.setattr(local.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=json.dumps(str(tmp_path))))
    assert local.executable()==str(binary)


def test_missing_executable_is_visible_without_claim(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    monkeypatch.setattr(local,'executable',lambda:None)
    host=Mock()
    assert not local.poll({},host)
    assert local.LAST_STATUS['state']=='Unavailable'
    host.assert_not_called()
