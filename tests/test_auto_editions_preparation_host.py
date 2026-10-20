import json
import sys
from pathlib import Path
from unittest.mock import patch
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/studio'))
import auto_editions_local as local
import device_trust


@pytest.fixture(autouse=True)
def isolated_host_file(monkeypatch,tmp_path):
    # Never inspect or use this computer's registered host capability in tests.
    monkeypatch.setattr(local,'HOST_FILE',tmp_path/'isolated-host.dpapi')
    monkeypatch.setattr(local,'cancellation_check',lambda *a,**kw:False)
    from companion_transfer import Controller
    controller=Controller();controller.configure({'mode':'Maximum speed'})
    monkeypatch.setattr(local,'transfer_controller',lambda:controller)


def test_completed_bulk_jobs_do_not_exhaust_interactive_slots(tmp_path):
    completed={str(i):dict(created=local.time.monotonic(),status='Blocked' if i%2 else 'Prepared',
                           context={'automatic':True}) for i in range(8)}
    with patch.object(local,'JOBS',completed),patch.object(local,'context',return_value={'automatic':True}),\
         patch.object(Path,'home',return_value=tmp_path),patch.object(local.threading,'Thread'):
        result=local.start({})
        assert result['status']=='Working'
        assert list(completed)==[result['job_id']]


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
    assert not (folder/'prepared.zip').exists()
    assert json.loads((folder/'receipt.json').read_text())['preparation_hash']=='c'*64
    with patch.object(Path,'home',return_value=tmp_path):
        with pytest.raises(ValueError):local.release_verified_temporary_files({**row,'folder':tmp_path})


def test_recovery_package_requires_exact_revision_and_settings(tmp_path):
    import zipfile
    root=tmp_path/'host';folder=root/('a'*48);folder.mkdir(parents=True)
    ctx={'automatic':True,'source':{'file_id':'id:a','revision':'rev1'},'total':100}
    manifest={'source':ctx['source'],'edition_total':100,'source_dimensions':[2835,2004],
              'preparation_geometry':{'scale':4},'colour_evidence':{'icc_sha256':'a'*64,'pixels_converted':False}}
    archive=folder/'prepared.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr('manifest.json',json.dumps(manifest))
    with patch.object(local,'HOST_FILE',root/'host.dpapi'):
        assert local.find_reusable_package(ctx)==archive
        assert local.find_reusable_package({**ctx,'source':{'file_id':'id:a','revision':'rev2'}}) is None
        assert local.find_reusable_package({**ctx,'total':200}) is None


def test_legacy_oversized_or_unprofiled_package_is_preserved_but_never_reuploaded(tmp_path):
    import zipfile
    import auto_editions_package as package_limits
    root=tmp_path/'host';folder=root/('a'*48);folder.mkdir(parents=True)
    ctx={'automatic':True,'source':{'file_id':'id:a','revision':'rev1'},'total':100}
    manifest={'source':ctx['source'],'edition_total':100,'source_dimensions':[2835,2004],
              'preparation_geometry':{'scale':4}}
    archive=folder/'prepared.zip'
    def write():
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('manifest.json',json.dumps(manifest));z.writestr('large-old-export',b'x'*2048)
    with patch.object(local,'HOST_FILE',root/'host.dpapi'):
        write();before=archive.read_bytes()
        assert local.find_reusable_package(ctx) is None
        assert archive.read_bytes()==before
        manifest['colour_evidence']={'icc_sha256':'a'*64,'pixels_converted':False};write()
        assert local.find_reusable_package(ctx)==archive
        with patch.object(package_limits,'MAX_PACKAGE_BYTES',1024):
            assert archive.stat().st_size<1024 # compressed bytes fit, expanded bytes do not
            assert local.find_reusable_package(ctx) is None
        with patch.object(package_limits,'MAX_PACKAGE_BYTES',100):
            assert local.find_reusable_package(ctx) is None
        assert archive.exists()


def test_upload_reconnects_after_restart_without_reopening_photoshop(tmp_path):
    import requests
    from unittest.mock import Mock
    archive=tmp_path/'prepared.zip';archive.write_bytes(b'validated test package')
    row=dict(grant={'base_url':'https://sports-cave-image-factory.onrender.com','ticket':'a','secret':'b'},
             context={'automatic':True},status='Working')
    failed=Mock();failed.raise_for_status.side_effect=requests.HTTPError('expired transfer')
    success=Mock();success.json.return_value={'preparation_hash':'c'*64}
    with patch.object(local,'JOBS',{'job':row}),patch('requests.Session.send',side_effect=[failed,success]) as post,\
         patch.object(local,'reconnect') as reconnect,patch.object(local,'release_verified_temporary_files') as cleanup:
        local.upload_prepared('job',archive)
        assert row['status']=='Prepared' and post.call_count==2
        reconnect.assert_called_once_with(row);cleanup.assert_called_once_with(row)


def test_failed_upload_keeps_recoverable_package(tmp_path):
    import requests
    archive=tmp_path/'prepared.zip';archive.write_bytes(b'retained')
    row=dict(grant={'base_url':'https://sports-cave-image-factory.onrender.com','ticket':'a','secret':'b'},
             context={'automatic':True},status='Working')
    with patch.object(local,'JOBS',{'job':row}),patch('requests.Session.send',side_effect=requests.ConnectionError()),\
         patch.object(local,'reconnect'),patch.object(local,'report_failure'),patch.object(local,'release_verified_temporary_files') as cleanup:
        local.upload_prepared('job',archive)
        assert row['status']=='Recovering' and archive.read_bytes()==b'retained'
        cleanup.assert_not_called()


def test_receipt_failure_never_deletes_recovery_assets(tmp_path):
    folder=tmp_path/'Documents'/'SportsCaveAutoEditions'/('d'*48);folder.mkdir(parents=True)
    archive=folder/'prepared.zip';archive.write_bytes(b'recovery')
    row=dict(folder=folder,preparation_hash='e'*64,context={'source':{'file_id':'id:source'}})
    with patch.object(Path,'home',return_value=tmp_path),patch.object(local.os,'replace',side_effect=OSError('disk failure')):
        with pytest.raises(OSError):local.release_verified_temporary_files(row)
    assert archive.read_bytes()==b'recovery'
    assert not (folder/'receipt.json').exists()


def test_cleanup_resumes_after_restart_and_preserves_unconfirmed_packages(tmp_path):
    root=tmp_path/'Documents'/'SportsCaveAutoEditions';folder=root/('e'*48);folder.mkdir(parents=True)
    archive=folder/'prepared.zip';archive.write_bytes(b'verified package')
    unconfirmed=root/('f'*48);unconfirmed.mkdir();(unconfirmed/'prepared.zip').write_bytes(b'pending upload')
    row=dict(folder=folder,preparation_hash='a'*64,context={'source':{'file_id':'id:source'}},
             timings={'prepare_validate_seconds':42},server_timings={'dropbox_upload_seconds':7})
    original_unlink=Path.unlink
    def fail_archive(path,*args,**kwargs):
        if path==archive:raise PermissionError('temporarily locked')
        return original_unlink(path,*args,**kwargs)
    with patch.object(Path,'home',return_value=tmp_path),patch.object(Path,'unlink',fail_archive):
        with pytest.raises(PermissionError):local.release_verified_temporary_files(row)
    receipt=json.loads((folder/'receipt.json').read_text())
    assert receipt['cleanup_complete'] is False and receipt['timings']['prepare_validate_seconds']==42
    with patch.object(Path,'home',return_value=tmp_path),patch.object(local,'HOST_FILE',root/'host.dpapi'):
        local.retry_verified_cleanup()
    assert not archive.exists()
    assert (unconfirmed/'prepared.zip').read_bytes()==b'pending upload'
    final=json.loads((folder/'receipt.json').read_text())
    assert final['cleanup_complete'] is True and final['confirmed_at']==receipt['confirmed_at']
    assert final['server_timings']=={'dropbox_upload_seconds':7}


def test_lost_success_response_uses_receipt_without_second_upload(tmp_path):
    import requests
    archive=tmp_path/'prepared.zip';archive.write_bytes(b'recovery')
    row=dict(grant={'base_url':'https://sports-cave-image-factory.onrender.com','ticket':'a','secret':'b'},
             context={'automatic':True},status='Working')
    with patch.object(local,'JOBS',{'job':row}),patch('requests.Session.send',side_effect=requests.Timeout()) as post,\
         patch.object(local,'reconnect',return_value={'preparation_hash':'c'*64,'timings':{'validation_seconds':5}}),\
         patch.object(local,'release_verified_temporary_files') as cleanup:
        local.upload_prepared('job',archive)
    assert row['status']=='Prepared' and post.call_count==1
    assert row['server_timings']['validation_seconds']==5
    cleanup.assert_called_once_with(row)


def test_interrupted_photoshop_releases_only_its_lease_and_preserves_source(tmp_path):
    folder=tmp_path/'job';folder.mkdir()
    original=folder/'input.psd';original.write_bytes(b'synthetic working source')
    lease=folder/'processor.lock';lease.write_bytes(b'owned lease')
    ctx={'automatic':True,'source':{'file_id':'id:synthetic'},'number':1,'total':100}
    row={'folder':folder,'grant':{},'context':ctx,'status':'Working'}
    with patch.object(local,'JOBS',{'job':row}),patch.object(local,'context',return_value=ctx),\
            patch.object(local,'processor_lease',return_value=lease),\
            patch('scripts.prepare_auto_editions.prepare',side_effect=RuntimeError('Photoshop interrupted')):
        local.prepare_worker('job',{'number':'Number','plaque':'Plaque'})
    assert row['status']=='Blocked' and not lease.exists()
    assert original.read_bytes()==b'synthetic working source'
    assert not (folder/'prepared.zip').exists()


def test_existing_shared_photoshop_lock_is_never_stolen(tmp_path):
    lock=tmp_path/'Documents'/'SportsCavePrintJobs'/'processor.lock'
    lock.parent.mkdir(parents=True);lock.write_bytes(b'unknown existing operation')
    with patch.object(Path,'home',return_value=tmp_path):
        with pytest.raises(FileExistsError):local.processor_lease()
    assert lock.read_bytes()==b'unknown existing operation'
