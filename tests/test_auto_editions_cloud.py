from copy import deepcopy
import shutil
from unittest.mock import patch

import pytest
from PIL import Image
import auto_editions as ae
import auto_editions_cloud as cloud
from test_auto_editions import package


def prepared(tmp_path):
    manifest=package(tmp_path)
    approval=dict(actor_id='admin',pixel_exact=True,visual_approved=True,preparation_hash=ae.fingerprint(manifest))
    unit=dict(id=42,allocation_valid=True,identity_enforced=True,status='completed',
              edition_number=2,edition_total=2,allocation_index=1,shopify_variant_id='variant-1',
              shopify_order_id='order-1',shopify_line_item_id='line-1',shopify_product_gid='gid://shopify/Product/123')
    mapping=dict(verified=True,state='Linked',dropbox_file_id='id:example')
    metadata=dict(id='id:example',rev='abc123',content_hash='a'*64)
    return unit,mapping,metadata,dict(manifest=manifest,approval=approval,variant_ids=['variant-1'])


def test_completed_allocation_uses_existing_identity_without_mutation(tmp_path):
    inputs=prepared(tmp_path); before=deepcopy(inputs)
    job=cloud.confirmed_job(*inputs)
    assert job['number']==2 and inputs==before
    assert cloud.confirmed_job(*inputs)['id']==job['id']


@pytest.mark.parametrize('field,value',[('allocation_valid',False),('identity_enforced',False),
    ('edition_number',True),('edition_number',3),('edition_total',3),('invalidated_at','date'),
    ('cancelled_at','date'),('shopify_variant_id','different'),('status','cancelled')])
def test_rejects_invalid_or_wrong_variant_allocation(tmp_path,field,value):
    inputs=prepared(tmp_path); inputs[0][field]=value
    with pytest.raises(ValueError):cloud.confirmed_job(*inputs)


def test_changed_revision_or_mapping_requires_new_preparation(tmp_path):
    inputs=prepared(tmp_path);inputs[2]['rev']='fff'
    with pytest.raises(ValueError,match='revision changed'):cloud.confirmed_job(*inputs)
    inputs=prepared(tmp_path);inputs[1]['dropbox_file_id']='id:different'
    with pytest.raises(ValueError):cloud.confirmed_job(*inputs)


def test_worker_fetches_only_master_and_requested_patch(tmp_path):
    job=cloud.confirmed_job(*prepared(tmp_path))
    class Storage:
        fetched=[]
        def fetch(self,digest,asset,destination):
            self.fetched.append(asset['name']);shutil.copyfile(tmp_path/asset['name'],destination)
        def publish_output(self,job,path):
            with Image.open(path) as im:assert im.size==(200,100)
            return dict(sha256=ae.file_hash(path))
    storage=Storage(); result=cloud.execute(job,storage)
    assert storage.fetched==['master.png','number-2.png']
    assert result['test_only'] is True and result['print_ready'] is False


def test_job_tampering_or_memory_limit_stops_before_storage(tmp_path):
    job=cloud.confirmed_job(*prepared(tmp_path))
    with pytest.raises(ValueError,match='memory budget'):cloud.execute(job,None,max_pixels=1)
    job['number']=1
    with pytest.raises(ValueError,match='edition changed'):cloud.execute(job,None)


def test_cloud_roles_need_no_dev_studio_permission():
    worker=dict(id='va',role='worker',is_active=True)
    with patch('os_accounts.can_access_page',side_effect=lambda actor,page:page in ('Files','Orders')):
        assert cloud.require_access(worker)=='va'
        with pytest.raises(PermissionError):cloud.require_access(worker,setup=True)
    with patch('os_accounts.can_access_page',return_value=False):
        with pytest.raises(PermissionError):cloud.require_access(worker)


def test_private_paths_never_accept_psds_or_escape():
    with pytest.raises(ValueError):cloud.DropboxAssets.path('a'*64,'source.psd')
    with pytest.raises(ValueError):cloud.DropboxAssets.path('a'*64,'../source.png')
    assert '/Masters/' in cloud.DropboxAssets.path('a'*64,'master.png')
    assert '/Cache/' in cloud.DropboxAssets.path('a'*64,'output.jpg',cache=True)


def test_dropbox_preparation_resumes_without_overwriting_existing_assets(tmp_path):
    manifest=package(tmp_path)
    class Integration:
        records={}
        writes=[]
        def ensure_folder_path(self,*args,**kwargs):pass
        def get_metadata_if_exists(self,token,path):return self.records.get(path)
        def psd_open_metadata(self,token,file_id,include_preview=False):return self.records.get(file_id)
        def upload_local_file(self,token,path,local,conflict):
            assert conflict=='cancel' and path.endswith('.png') and '/Masters/' in path
            self.writes.append(path)
            self.records[path]=dict(id='id:file',rev='123',size=local.stat().st_size,
                                    content_hash=ae.file_hash(local,dropbox=True))
            return self.records[path]
    integration=Integration();storage=cloud.DropboxAssets('test-token',integration)
    first=storage.publish_preparation(manifest,tmp_path)
    assert len(first['assets'])==3 and len(integration.writes)==3
    assert storage.publish_preparation(manifest,tmp_path)==first
    assert len(integration.writes)==3
    integration.records[integration.writes[0]]['content_hash']='b'*64
    with pytest.raises(ValueError,match='not overwritten'):storage.publish_preparation(manifest,tmp_path)
    assert len(integration.writes)==3


def test_dropbox_download_closes_stream_on_checksum_failure(tmp_path):
    from unittest.mock import Mock
    stream=Mock();stream.iter_content.return_value=[b'wrong']
    integration=Mock();integration.get_file_response.return_value=({'size':5},stream)
    storage=cloud.DropboxAssets('test-token',integration)
    with pytest.raises(ValueError,match='checksum'):
        storage.fetch('a'*64,dict(name='master.png',sha256='b'*64),tmp_path/'input.png')
    stream.close.assert_called_once()


def test_archive_idempotency_revision_checks_and_master_history(tmp_path):
    job=cloud.confirmed_job(*prepared(tmp_path))
    job['archive_labels']=dict(order_name='#SC3287',product_title='Kostecki & Hazelwood',variant_title='Unframed / XL')
    path=tmp_path/'output.jpg';ae.render_jpg(job['manifest'],tmp_path,2,path)
    class Integration:
        records={};writes=[]
        def ensure_folder_path(self,*args,**kwargs):pass
        def get_metadata_if_exists(self,token,path):return self.records.get(path)
        def psd_open_metadata(self,token,file_id,include_preview=False):return self.records.get(file_id)
        def upload_local_file(self,token,destination,path,conflict,simple_limit):
            assert conflict=='cancel'
            assert simple_limit==cloud.MAX_OUTPUT_BYTES
            meta=dict(id='id:'+str(len(self.writes)),rev='123',path_display=destination,size=path.stat().st_size,content_hash=ae.file_hash(path,dropbox=True))
            self.records[destination]=self.records[meta['id']]=meta;self.writes.append(destination)
            return meta
    integration=Integration();storage=cloud.DropboxAssets('test',integration)
    first=storage.publish_output(job,path)
    assert first['path'].rsplit('/',1)[1].startswith('002-of-2 - ')
    assert '/Generated JPGs/SC3287/TEST/' in first['path']
    assert storage.publish_output(job,path)==first and len(integration.writes)==1
    changed=deepcopy(job);changed['id']='f'*64;changed['preparation_hash']='e'*64
    other=storage.publish_output(changed,path)
    assert other['file_id']!=first['file_id'] and len(integration.writes)==2
    storage.discard_cache(job['id'],first)
    integration.records[first['file_id']]['rev']='456'
    with pytest.raises(ValueError,match='unavailable or changed'):storage.verify_output(first)
    integration.records[first['file_id']]['content_hash']='b'*64
    with pytest.raises(ValueError,match='nothing was overwritten'):storage.publish_output(job,path)


def test_encoded_jpg_has_actual_pixels_and_300_ppi(tmp_path):
    manifest=package(tmp_path);result=ae.render_jpg(manifest,tmp_path,2,tmp_path/'out.jpg')
    with Image.open(tmp_path/'out.jpg') as im:
        assert im.size==(200,100) and im.info['dpi']==(300,300)
    assert result['colour_profile']=='Unspecified' and result['print_ready'] is False


def test_archive_download_uses_supported_revision_path():
    from unittest.mock import Mock
    integration=Mock();raw=object();stream=Mock()
    integration.team_space_client.return_value.files_download.return_value=(raw,stream)
    integration._metadata_to_dict.return_value={'id':'id:exact','rev':'abc123'}
    assets=cloud.DropboxAssets('test',integration)
    assert assets.output_response({'revision':'abc123'})==({'id':'id:exact','rev':'abc123'},stream)
    integration.team_space_client.return_value.files_download.assert_called_once_with('rev:abc123')
    with pytest.raises(ValueError):assets.output_response({'revision':'../../bad'})
