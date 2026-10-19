"""Confirmed Dropbox HTTP400 regression; actual SDK, isolated upstream bytes."""
from unittest.mock import Mock
import io
import json
import dropbox
from dropbox.exceptions import BadInputError
import pytest
import requests
import dropbox_integration as integration
from product_upload_services import Dropbox

REV = '0165e251a26bf2f000000036d367e13'
PAYLOAD = b'8BPS\x00\x01original-document-bytes'


@pytest.fixture
def download(monkeypatch):
    client = dropbox.Dropbox(oauth2_access_token='isolated-token').with_path_root(dropbox.common.PathRoot.root('12345'))
    metadata = dict(id='id:exact', rev=REV, size=len(PAYLOAD), content_hash='a'*64)
    response = Mock(iter_content=Mock(return_value=iter([PAYLOAD[:2], PAYLOAD[2:]])))
    calls = []
    def request(scoped, route, namespace, arg, binary):
        calls.append((scoped, arg))
        if arg.rev is not None:
            # Exact provider failure captured in Render with SDK12.2.3.
            raise BadInputError('isolated-request', "'Rev' parameter is deprecated. Please provide rev in path parameter as 'rev:{rev}'")
        assert arg.path == 'rev:' + REV
        return dict(metadata), response
    monkeypatch.setattr(dropbox.Dropbox, 'request', request)
    rooted = Mock(return_value=client)
    monkeypatch.setattr(integration, 'team_space_client', rooted)
    provider = object.__new__(Dropbox)
    provider.api, provider.token = integration, 'isolated-token'
    return provider, metadata, response, calls, client, rooted


def test_provider_rejects_old_request_corrected_request_keeps_namespace_and_identity(download, tmp_path):
    provider, metadata, response, calls, client, rooted = download
    with pytest.raises(BadInputError, match='deprecated'):
        client.files_download(metadata['id'], rev=REV)
    target = tmp_path/'selected.psd'
    provider.download(metadata, target)
    assert target.read_bytes() == PAYLOAD
    scoped, arg = calls[-1]
    assert arg.rev is None and arg.path == 'rev:' + REV
    assert scoped._headers['Dropbox-API-Path-Root'] == client._headers['Dropbox-API-Path-Root']
    assert scoped._session is client._session
    assert scoped._timeout == 60 and scoped._max_retries_on_error == 2 and scoped._max_retries_on_rate_limit == 2
    rooted.assert_called_once_with('isolated-token')
    response.close.assert_called_once()


@pytest.mark.parametrize('field,value', [('id','id:other'),('rev','abcdef123'),('size',999),('content_hash','b'*64)])
def test_wrong_identity_revision_size_or_hash_never_writes(download, tmp_path, field, value):
    provider, actual, response, calls, client, rooted = download
    selected = dict(actual)
    actual[field] = value
    with pytest.raises(integration.DropboxSourceChangedError, match='reselect'):
        provider.download(selected, tmp_path/'selected.psd')
    assert not (tmp_path/'selected.psd').exists()
    response.iter_content.assert_not_called()
    response.close.assert_called_once()


@pytest.mark.parametrize('payload', [b'<html>provider error</html>', PAYLOAD[:-1], PAYLOAD+b'excess', b'thumbnail'])
def test_bad_original_bytes_removed_and_response_closed(download, tmp_path, payload):
    provider, metadata, response, *_ = download
    response.iter_content.return_value = iter([payload])
    with pytest.raises(integration.DropboxOriginalDownloadError):
        provider.download(metadata, tmp_path/'selected.psd')
    assert not (tmp_path/'selected.psd').exists()
    response.close.assert_called_once()


def test_interrupted_download_removes_partial_then_same_selection_can_retry(download, tmp_path):
    provider, metadata, response, *_ = download
    def interrupted():
        yield PAYLOAD[:6]
        raise requests.ReadTimeout('isolated timeout')
    response.iter_content.return_value = interrupted()
    target = tmp_path/'selected.psd'
    with pytest.raises(requests.ReadTimeout):
        provider.download(metadata, target)
    assert not target.exists()
    response.iter_content.return_value = iter([PAYLOAD])
    provider.download(metadata, target)
    assert target.read_bytes() == PAYLOAD and response.close.call_count == 2


def test_download_never_overwrites_existing_file(download, tmp_path):
    provider, metadata, response, *_ = download
    target = tmp_path/'existing.psd'; target.write_bytes(b'preserve')
    with pytest.raises(FileExistsError):
        provider.download(metadata, target)
    assert target.read_bytes() == b'preserve'
    response.close.assert_called_once()


def test_original_download_reports_actual_bytes_without_a_browser_upload(download,tmp_path):
    provider,metadata,response,*_=download
    progress=Mock()
    provider.download(metadata,tmp_path/'selected.psd',progress=progress)
    progress.assert_called_once_with(len(PAYLOAD),len(PAYLOAD))


@pytest.mark.parametrize('revision', ['rev:'+REV, 'not-a-revision', '123', '', None])
def test_malformed_revision_is_rejected_before_request(download, revision):
    provider, metadata, response, calls, *_ = download
    with pytest.raises(ValueError, match='identity'):
        integration.get_psd_file_response(provider.token, metadata['id'], revision)
    assert not calls


def test_actual_sdk_content_request_serializes_revision_path_and_root_header(monkeypatch, tmp_path):
    # No SDK request stub: inspect the actual HTTP call emitted by SDK12.2.3.
    client = dropbox.Dropbox(oauth2_access_token='isolated-token').with_path_root(dropbox.common.PathRoot.root('12345'))
    selected = dict(id='id:exact', rev=REV, size=len(PAYLOAD), content_hash='a'*64)
    response = requests.Response()
    response.status_code = 200
    response.raw = io.BytesIO(PAYLOAD)
    response.close = Mock(wraps=response.close)
    response.headers['dropbox-api-result'] = json.dumps(dict(selected, name='exact.psd',
        client_modified='2026-10-18T08:15:45Z', server_modified='2026-10-18T22:41:45Z', is_downloadable=True))
    calls = []
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return response
    monkeypatch.setattr(client._session, 'post', post)
    monkeypatch.setattr(integration, 'team_space_client', lambda token:client)
    provider = object.__new__(Dropbox); provider.api = integration; provider.token = 'isolated-token'
    provider.download(selected, tmp_path/'exact.psd')
    url, kwargs = calls[0]
    assert len(calls) == 1 and url == 'https://content.dropboxapi.com/2/files/download'
    assert json.loads(kwargs['headers']['Dropbox-API-Arg']) == {'path':'rev:'+REV}
    assert json.loads(kwargs['headers']['Dropbox-API-Path-Root']) == {'.tag':'root','root':'12345'}
    assert kwargs['stream'] is True and kwargs['timeout'] == 60 and kwargs['data'] is None
    response.close.assert_called_once()
    assert (tmp_path/'exact.psd').read_bytes() == PAYLOAD


def test_wrapped_provider_status_and_request_id_logged_without_body(caplog):
    import product_upload_artwork as artwork
    raw = BadInputError('isolated-request', 'Bearer secret-token provider response')
    wrapped = integration.DropboxApiError('safe wrapper'); wrapped.__cause__ = raw
    row = dict(id='isolated-workflow', data=dict(source=dict(id='id:exact', rev=REV, content_hash='a'*64)))
    artwork.log_failure(wrapped, 'retrieve original PSD', 'test-reference', row)
    assert 'provider_status=400' in caplog.text and 'provider_request_id=isolated-request' in caplog.text
    assert 'secret-token' not in caplog.text and 'provider response' not in caplog.text
