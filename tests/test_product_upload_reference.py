from copy import deepcopy
from pathlib import Path
import hashlib

import pytest
from PIL import Image


def fixture(tmp_path):
    from auto_editions import file_hash
    path=tmp_path/'black.webp'
    Image.new('RGB',(120,80),'navy').save(path,format='WEBP',lossless=True)
    source={'id':'id:psd','rev':'R1'}
    row={'id':'upload','data':{'source':source}}
    result={'run_dir':str(tmp_path),'_product_upload_actor_id':'actor','_product_upload_intake':'upload',
            'assets':[{'key':'black','webp_path':path}],
            'product_image_manifest':[{'slot_id':'black-frame','output_filename':'black.webp'}]}
    meta={'id':'id:black','rev':'R2','size':path.stat().st_size,'content_hash':file_hash(path,dropbox=True)}
    receipt={'successes':[{'relative_path':'WEBP/black.webp','metadata':meta}]}
    return path,row,result,receipt


def test_exact_saved_webp_is_exposed_through_actor_bound_os_route(tmp_path,monkeypatch):
    from product_upload_reference import attachment
    from product_upload_gallery import resolve
    from urllib.parse import urlparse,parse_qs
    import mockup_storage
    monkeypatch.setattr(mockup_storage,'safe_temp_path',lambda value:Path(value))
    path,row,result,receipt=fixture(tmp_path)
    item=attachment(result,row,receipt)
    assert item['sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
    assert item['size']==path.stat().st_size and item['name']=='black.webp'
    assert item['content_hash']==receipt['successes'][0]['metadata']['content_hash']
    token=parse_qs(urlparse(item['url']).query)['token'][0]
    assert resolve(token,'actor',lambda *a:row)==path
    with pytest.raises(ValueError):resolve(token,'other',lambda *a:row)
    row['data']['staff_full_restart']='reset'
    with pytest.raises(ValueError,match='earlier reset'):resolve(token,'actor',lambda *a:row)


@pytest.mark.parametrize('field,value',[('size',2),('content_hash','0'*64)])
def test_mismatched_original_cannot_be_attached(tmp_path,field,value):
    from product_upload_reference import attachment
    path,row,result,receipt=fixture(tmp_path)
    receipt=deepcopy(receipt)
    receipt['successes'][0]['metadata'][field]=value
    with pytest.raises(ValueError,match='differs'):
        attachment(result,row,receipt)
