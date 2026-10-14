import json
import sys
from pathlib import Path
from unittest.mock import patch
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/studio'))
import auto_editions_local as local
import device_trust


def test_host_config_is_exact_and_dpapi_encrypted(tmp_path):
    target=tmp_path/'host.dpapi';config={'base_url':'https://sports-cave-image-factory.onrender.com','token':'a'*43}
    with patch.object(local,'HOST_FILE',target),patch.object(local,'restore_host') as restore:
        for bad in ({**config,'base_url':'https://outside.test'}, {**config,'token':'short'}, {**config,'path':'source.psd'}):
            with pytest.raises(ValueError):local.configure_host(bad)
        assert not target.exists()
        local.configure_host(config);restore.assert_called_once()
        assert config['token'].encode() not in target.read_bytes()
        assert json.loads(device_trust.protect(target.read_bytes(),decrypt=True))==config


def test_only_owned_verified_temp_copies_released(tmp_path):
    folder=tmp_path/'Documents'/'SportsCaveAutoEditions'/('b'*48);folder.mkdir(parents=True)
    prepared=folder/'prepared';prepared.mkdir();(prepared/'master.png').write_bytes(b'copy')
    (folder/'input.psd').write_bytes(b'working copy');(folder/'prepared.zip').write_bytes(b'recovery package')
    row={'folder':folder,'preparation_hash':'c'*64,'context':{'source':{'file_id':'id:original'}}}
    with patch.object(Path,'home',return_value=tmp_path):local.release_verified_temporary_files(row)
    assert not prepared.exists() and not (folder/'input.psd').exists()
    assert (folder/'prepared.zip').read_bytes()==b'recovery package'
    assert json.loads((folder/'receipt.json').read_text())['preparation_hash']=='c'*64
    with patch.object(Path,'home',return_value=tmp_path):
        with pytest.raises(ValueError):local.release_verified_temporary_files({**row,'folder':tmp_path})
