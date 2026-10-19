import json
from copy import deepcopy
from unittest.mock import Mock, patch
import pytest
from PIL import Image
from auto_editions_preflight import validate, verify_resize
from tests.test_auto_editions_onboarding import inspection


def test_preflight_cleanup_cannot_release_a_later_uncertain_rpc(tmp_path):
    from scripts.prepare_auto_editions import native_dispatch,native_cleanup_uncertain
    (tmp_path/'photoshop-dispatch.json').write_text('{"started":true}')
    (tmp_path/'native-status.json').write_text('{"completed":true,"owned_document_closed":true}')
    def interrupted(script):
        assert not (tmp_path/'native-status.json').exists()
        raise RuntimeError('RPC disconnected after preflight')
    with pytest.raises(RuntimeError):native_dispatch(interrupted,'script',tmp_path)
    assert native_cleanup_uncertain(tmp_path)
    assert (tmp_path/'preflight-native-status.json').exists()


def test_invalid_source_identity_stops_before_native_processing(tmp_path):
    from scripts.prepare_auto_editions import prepare
    with patch('scripts.photoshop_dispatch.run') as native_run:
        with pytest.raises(ValueError,match='permanent ID'):
            prepare(tmp_path/'source.psd',tmp_path/'output',dict(product_gid='gid://shopify/Product/1',
                file_id='id:local-fixture',revision='not-a-dropbox-revision',content_hash='a'*64),
                number_layer='n',plaque_layer='p',total=100,reference_number=1)
        native_run.assert_not_called()
    assert not (tmp_path/'output').exists()


def native(tmp_path):
    data=inspection()
    Image.new('RGB',(2835,2004),(31,72,111)).save(tmp_path/'preflight-original.png')
    Image.new('RGB',(2835,2004),(31,72,111)).save(tmp_path/'preflight-artwork.png')
    return dict(inspection=data,resize_background={'layer_id':46,'name':'Artwork'})


def check(tmp_path,report):
    return validate(tmp_path,report,{},100,'001 / 100','limited-edition-plaque',4)


def test_opaque_artwork_keeps_the_exact_pinned_background(tmp_path):
    report=native(tmp_path)
    assert check(tmp_path,report)==report['resize_background']


@pytest.mark.parametrize('fault',['source_alpha','artwork_alpha','duplicate','nested','font','wrong_total'])
def test_preflight_rejects_incompatible_template_before_number_exports(tmp_path,fault):
    report=native(tmp_path)
    if fault.endswith('_alpha'):
        name='preflight-original.png' if fault=='source_alpha' else 'preflight-artwork.png'
        Image.new('RGBA',(2835,2004),(31,72,111,222)).save(tmp_path/name)
    elif fault=='duplicate':report['inspection']['layers'].append(deepcopy(report['inspection']['layers'][0]))
    elif fault=='nested':report['inspection']['layers'][0]['path'].append({'name':'nested'})
    elif fault=='font':report['inspection']['layers'][0]['fonts'][0]['installed']=False
    else:report['inspection']['layers'][0]['text']='001 / 200'
    with pytest.raises(ValueError):check(tmp_path,report)


def test_resize_proof_rejects_painting_and_the_demonstrated_222_alpha(tmp_path):
    native(tmp_path)
    for name in ('resize-original.png','original.png','master.png'):
        Image.new('RGB',(2835,2004),(31,72,111)).save(tmp_path/name)
    assert verify_resize(tmp_path)['native_pixels_exact']
    Image.new('RGBA',(2835,2004),(31,72,111,222)).save(tmp_path/'master.png')
    with pytest.raises(ValueError,match='222-222'):verify_resize(tmp_path)
    Image.new('RGB',(2835,2004),(31,72,112)).save(tmp_path/'resize-original.png')
    with pytest.raises(ValueError,match='native artwork pixels'):verify_resize(tmp_path)


@pytest.mark.parametrize('status,attempts,reconnects,waits',[(422,1,0,[]),(429,3,2,[1,2]),(503,3,2,[1,2])])
def test_only_transient_uploads_retry_with_bounded_backoff(tmp_path,status,attempts,reconnects,waits):
    import requests
    from tests.test_auto_editions_preparation_host import local
    archive=tmp_path/'prepared.zip';archive.write_bytes(b'verified intermediate')
    row=dict(folder=tmp_path,grant={'base_url':'https://sandbox.invalid','ticket':'test','secret':'test'},
             context={'automatic':True},status='Working')
    response=Mock(status_code=status)
    error=requests.HTTPError(f'HTTP {status}',response=response)
    with patch.object(local,'JOBS',{'job':row}),patch.object(local,'cancellation_check',return_value=False),\
         patch('requests.post',side_effect=error) as post,patch.object(local,'reconnect',return_value=None) as reconnect,\
         patch.object(local.HOST_STOP,'wait',return_value=False) as wait,patch.object(local,'report_failure'),\
         patch.object(local,'release_verified_temporary_files') as cleanup:
        local.upload_prepared('job',archive)
    assert post.call_count==attempts and reconnect.call_count==reconnects
    assert [c.args[0] for c in wait.call_args_list]==waits
    assert row['status']==('Blocked' if status==422 else 'Recovering')
    assert archive.read_bytes()==b'verified intermediate'
    cleanup.assert_not_called()
    assert json.loads((tmp_path/'failure-detail.json').read_text())['stage']=='Uploading'


def test_upload_validation_reason_remains_actionable_and_scoped(tmp_path):
    import requests
    from tests.test_auto_editions_preparation_host import local
    response=Mock(status_code=422)
    response.json.return_value={'error':'Source revision changed: secret-capability-123'}
    error=requests.HTTPError('422 validation failed',response=response)
    row=dict(folder=tmp_path,grant={'secret':'secret-capability-123'},context={})
    detail=local.failure_detail(row,'Uploading',error)
    assert 'Source revision changed' in detail and 'capability-123' not in detail
    assert row['diagnostic']['code']=='SOURCE_CHANGED'


def test_stage_error_history_preserves_cause_and_redacts_capabilities(tmp_path):
    from tests.test_auto_editions_preparation_host import local
    row=dict(folder=tmp_path,grant={'secret':'secret-capability-123'},context={'lease_token':'lease-capability-123'})
    try:raise ValueError('non-opaque alpha (222-255) secret-capability-123 lease-capability-123')
    except ValueError as error:local.failure_detail(row,'Preparation',error)
    detail=json.loads((tmp_path/'failure-detail.json').read_text())
    assert 'ValueError' in detail['traceback'] and '222-255' in detail['message']
    assert 'capability-123' not in json.dumps(detail)
    assert row['diagnostic']['code']=='ARTWORK_ALPHA' and row['diagnostic']['stage']=='Preparing'
    assert len((tmp_path/'failure-history.jsonl').read_text().splitlines())==1
