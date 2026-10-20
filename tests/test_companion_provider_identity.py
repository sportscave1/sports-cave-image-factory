from types import SimpleNamespace
import pytest
import dropbox_integration as integration

def test_receipt_download_preserves_permanent_id(monkeypatch):
    seen=[];response=SimpleNamespace(close=lambda:None)
    def download(path):seen.append(path);return 'metadata',response
    monkeypatch.setattr(integration,'team_space_client',lambda token:SimpleNamespace(files_download=download))
    monkeypatch.setattr(integration,'_metadata_to_dict',lambda value:{'id':'id:verified_123'})
    meta,stream=integration.get_file_response('synthetic-fixture-only','id:verified_123')
    assert seen==['id:verified_123'] and meta['id']=='id:verified_123' and stream is response
    integration.get_file_response('synthetic-fixture-only','folder/file.zip')
    assert seen[-1]=='/folder/file.zip'

@pytest.mark.parametrize('path',['id:','id:bad/path','id:bad\\path','id:bad?query'])
def test_invalid_permanent_id_rejected_before_sdk(monkeypatch,path):
    monkeypatch.setattr(integration,'team_space_client',lambda *a:pytest.fail('SDK reached'))
    with pytest.raises(ValueError,match='Invalid Dropbox'):integration.get_file_response('synthetic-fixture-only',path)
