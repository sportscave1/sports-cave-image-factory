import asyncio,json,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path.cwd()))
import files_upload_api as files,psd_directory as psd,edition_test_api
from starlette.requests import Request
from urllib.parse import quote
async def measure():
    async def receive():return {'type':'http.request','body':b'{"action":"openPhotoshop"}','more_body':False}
    req=Request({'type':'http','method':'POST','scheme':'http','server':('test',80),'path':'/api/files-psd-open','headers':[(b'origin',b'http://test')],'query_string':('product_gid='+quote('gid://shopify/Product/1',safe='')).encode()},receive)
    meta={'.tag':'file','id':'id:1','name':'Fixture.psd','path_display':psd.ROOT+'/Fixture.psd','size':10,'rev':'rev','content_hash':'a'*64}
    staff=dict(id='fixture-va',role='worker',is_active=True,page_permissions=['files','orders'])
    with patch.object(files,'_request_user',return_value=staff),patch.object(files,'_dropbox_context',return_value=dict(root_path='/Sportscave Team Folder',access_token='TEST')),patch.object(psd,'directory',return_value={'gid://shopify/Product/1':dict(verified=True,state='Linked',dropbox_file_id='id:1')}),patch.object(files.dropbox_integration,'psd_open_metadata',return_value=meta):
        native=await files.open_product_psd(req)
        pilot=await edition_test_api.page(req)
        print(json.dumps(dict(staff_psd_native_grant_http=native.status_code,staff_photoshop_pilot_page_http=pilot.status_code)))
asyncio.run(measure())
