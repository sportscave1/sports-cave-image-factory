from pathlib import Path
from types import SimpleNamespace

import dropbox
import pytest
import requests

import auto_editions as ae
import dropbox_integration as integration
from edition_asset_publisher import ImmutableAssetUploader


class Client:
    def __init__(self):
        self.records = {}
        self.calls = []
        self.errors = []
        self.lost_ack = False
        self.reads = 0
        self.maximum_chunk = 0

    def clone(self, **kwargs):
        assert kwargs == dict(max_retries_on_error=1, max_retries_on_rate_limit=1, timeout=60)
        return self

    def files_upload(self, data, destination, **kwargs):
        self.calls.append(destination)
        assert kwargs['mode'] == dropbox.files.WriteMode.add
        assert kwargs['autorename'] is False and kwargs['strict_conflict'] is True
        if self.errors:
            raise self.errors.pop(0)
        if destination in self.records:
            raise conflict()
        row = dict(id='id:'+destination, rev='r1', path_lower=destination.lower(),
                   size=len(data), content_hash=kwargs['content_hash'])
        self.records[destination] = row
        if self.lost_ack:
            raise requests.ConnectionError('Synthetic lost response')
        return row

    def files_get_metadata(self, destination):
        self.reads += 1
        if destination not in self.records:
            raise dropbox.exceptions.ApiError('synthetic', dropbox.files.GetMetadataError.path(
                dropbox.files.LookupError.not_found), None, None)
        return self.records[destination]


def conflict():
    return dropbox.exceptions.ApiError('synthetic', dropbox.files.UploadError.path(
        dropbox.files.UploadWriteFailed(reason=dropbox.files.WriteError.conflict(
            dropbox.files.WriteConflictError.file))), None, None)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    client = Client()
    monkeypatch.setattr(integration, 'team_space_client', lambda _: client)
    path = tmp_path/'master.png'; path.write_bytes(b'synthetic bytes')
    clock = [100.0]; sleeps = []
    monkeypatch.setattr('edition_asset_publisher.time.monotonic', lambda: clock[0])
    def sleep(delay):
        sleeps.append(delay); clock[0] += delay
    monkeypatch.setattr('edition_asset_publisher.time.sleep', sleep)
    return SimpleNamespace(client=client, path=path, uploader=integration.immutable_asset_uploader('synthetic'),
                           sleeps=sleeps, clock=clock)


def test_no_preflight_and_exact_strict_add_receipt(setup):
    e=setup; receipt=e.uploader('/synthetic/master.png', e.path)
    assert receipt['content_hash']==ae.file_hash(e.path, dropbox=True)
    assert len(e.client.calls)==1 and e.client.reads==0
    assert e.uploader.metrics['provider_calls']==1


def test_lost_ack_reconciles_without_retransmitting(setup):
    e=setup; e.client.lost_ack=True
    receipt=e.uploader('/synthetic/master.png', e.path)
    assert receipt['rev']=='r1' and len(e.client.calls)==e.client.reads==1
    assert e.uploader.metrics['recovered_assets']==1


def test_concurrent_exact_add_is_reused_but_mismatch_is_never_replaced(setup):
    e=setup; first=e.uploader('/synthetic/master.png',e.path)
    assert e.uploader('/synthetic/master.png',e.path)==first
    e.client.records['/synthetic/master.png']['content_hash']='0'*64
    with pytest.raises(ValueError,match='not overwritten'):
        e.uploader('/synthetic/master.png',e.path)
    assert len(e.client.records)==1 and first['rev']=='r1'


@pytest.mark.parametrize('field,value', [('id',''),('rev',''),('path_lower','/different'),('size',1)])
def test_receipt_identity_and_path_are_required(setup,field,value):
    e=setup; e.uploader('/synthetic/master.png',e.path)
    e.client.records['/synthetic/master.png'][field]=value
    with pytest.raises(ValueError,match='not overwritten'):
        e.uploader('/synthetic/master.png',e.path)


def test_rate_limit_honours_retry_after_and_shares_cooldown(setup):
    e=setup; e.client.errors=[dropbox.exceptions.RateLimitError('synthetic',backoff=7)]
    assert e.uploader('/synthetic/master.png',e.path)['rev']=='r1'
    assert e.sleeps==[7] and e.client.reads==1 and len(e.client.calls)==2
    assert e.uploader.metrics['rate_limits']==1
    e.uploader._cooldown(9)
    e.uploader('/synthetic/next.png',e.path)
    assert e.sleeps==[7,9]


@pytest.mark.parametrize('error', [requests.Timeout('synthetic'),
    dropbox.exceptions.InternalServerError('synthetic',503,'synthetic')])
def test_transient_failures_have_three_cycle_ceiling(setup,error):
    e=setup; e.client.errors=[error]*3
    with pytest.raises(type(error)):
        e.uploader('/synthetic/master.png',e.path)
    assert len(e.client.calls)==e.client.reads==3
    assert e.uploader.metrics['retry_cycles']==2 and e.sleeps==[1,2,4]


def test_permission_failure_is_terminal_without_retry_or_metadata_read(setup):
    e=setup; e.client.errors=[dropbox.exceptions.HttpError('synthetic',403,'synthetic')]
    with pytest.raises(dropbox.exceptions.HttpError):
        e.uploader('/synthetic/master.png',e.path)
    assert len(e.client.calls)==1 and e.client.reads==0 and not e.sleeps


@pytest.mark.parametrize('lost_ack',[False,True])
def test_large_asset_streams_eight_mib_chunks_with_strict_commit(setup,lost_ack):
    e=setup; e.path.write_bytes(b'x'*(17*1024*1024+11)); chunks=[]
    e.client.files_upload_session_start=lambda data: (chunks.append(len(data)) or SimpleNamespace(session_id='s'))
    def append(data,cursor):
        assert cursor.offset==sum(chunks);chunks.append(len(data))
    e.client.files_upload_session_append_v2=append
    def finish(data,cursor,commit):
        assert cursor.offset==sum(chunks);chunks.append(len(data))
        assert commit.mode==dropbox.files.WriteMode.add and commit.strict_conflict and not commit.autorename
        result=dict(id='id:large',rev='r1',path_lower=commit.path.lower(),size=sum(chunks),
                    content_hash=ae.file_hash(e.path,dropbox=True))
        e.client.records[commit.path]=result
        if lost_ack:raise requests.ConnectionError('Synthetic lost session finish response')
        return result
    e.client.files_upload_session_finish=finish
    assert e.uploader('/synthetic/large.png',e.path)['size']==e.path.stat().st_size
    assert max(chunks)==8*1024*1024 and len(chunks)==3 and e.client.reads==int(lost_ack)


def test_real_publisher_uses_strict_uploader_and_reuses_complete_listing(tmp_path,monkeypatch):
    from tests.test_auto_editions import package
    from auto_editions_cloud import DropboxAssets
    manifest=package(tmp_path);client=Client()
    monkeypatch.setattr(integration,'team_space_client',lambda _:client)
    monkeypatch.setattr(integration,'ensure_folder_path',lambda *a,**k:None)
    monkeypatch.setattr(integration,'list_folder_page',lambda *a,**k:
        dict(entries=[dict(row,name=Path(path).name) for path,row in client.records.items()],has_more=False))
    monkeypatch.setattr(integration,'resolve_upload_destination',lambda *a,**k:pytest.fail('Redundant preflight'))
    storage=DropboxAssets('synthetic',integration)
    first=storage.publish_preparation(manifest,tmp_path)
    assert storage.timings['prepared_provider_calls']==3 and client.reads==0
    assert first==storage.publish_preparation(manifest,tmp_path)
    assert storage.timings['prepared_upload_requests']==0 and len(client.calls)==3
    assert storage.timings['prepared_provider_calls']==0


@pytest.mark.parametrize('change',['truncate','modify','grow'])
def test_changed_stream_is_rejected_before_immutable_commit(setup,change):
    e=setup;e.path.write_bytes(b'x'*(17*1024*1024+11))
    def start(data):
        with e.path.open('r+b') as stream:
            if change=='truncate':stream.truncate(8*1024*1024)
            elif change=='grow':stream.seek(0,2);stream.write(b'extra')
            else:stream.seek(8*1024*1024);stream.write(b'y')
        return SimpleNamespace(session_id='s')
    e.client.files_upload_session_start=start
    e.client.files_upload_session_append_v2=lambda *a:None
    e.client.files_upload_session_finish=lambda *a:pytest.fail('Changed asset committed')
    with pytest.raises(ValueError,match='changed during publication'):
        e.uploader('/synthetic/large.png',e.path)
    assert not e.client.records and e.client.reads==0


def test_real_publisher_keeps_partial_receipts_and_only_retries_missing_asset(tmp_path,monkeypatch):
    from tests.test_auto_editions import package
    from auto_editions_cloud import DropboxAssets
    manifest=package(tmp_path);client=Client()
    client.errors=[dropbox.exceptions.HttpError('synthetic',403,'synthetic')]
    monkeypatch.setattr(integration,'team_space_client',lambda _:client)
    monkeypatch.setattr(integration,'ensure_folder_path',lambda *a,**k:None)
    monkeypatch.setattr(integration,'list_folder_page',lambda *a,**k:
        dict(entries=[dict(row,name=Path(path).name) for path,row in client.records.items()],has_more=False))
    storage=DropboxAssets('synthetic',integration)
    with pytest.raises(dropbox.exceptions.HttpError):storage.publish_preparation(manifest,tmp_path)
    before={key:dict(value) for key,value in client.records.items()}
    assert len(before)==2
    result=storage.publish_preparation(manifest,tmp_path)
    assert len(result['assets'])==3 and len(client.calls)==4
    assert storage.timings['prepared_reused_assets']==2
    assert all(client.records[key]==value for key,value in before.items())
