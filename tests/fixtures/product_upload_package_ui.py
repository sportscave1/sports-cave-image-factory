"""Local synthetic saved-package UI. No production credentials or provider writes."""
import os
from pathlib import Path
from io import BytesIO
from types import SimpleNamespace
from contextlib import contextmanager


def main():
    keep={k:v for k,v in os.environ.items() if k.upper() in ('PATH','SYSTEMROOT','WINDIR','TEMP','TMP','USERPROFILE')}
    os.environ.clear();os.environ.update(keep)
    import pytest
    from PIL import Image,ImageDraw
    from starlette.applications import Starlette
    from starlette.responses import HTMLResponse,JSONResponse
    from starlette.routing import Route
    from tests.test_product_upload_package import saved_row
    from tests.benchmark_product_upload_transfer import local_client
    import product_upload_api as api, product_upload_prompts
    root=Path(__file__).resolve().parents[2];row=saved_row()
    row['data'].update(basic_validated=True,state='Ready',name='Fixture artwork.psd')
    files=row['data']['upload_operation']['output']['files'];images={};requests=[]
    for i,f in enumerate(files):
        im=Image.new('RGB',(1024,1024),(228-i*9,223-i*7,205+i*4));d=ImageDraw.Draw(im);d.rectangle((140,160,884,864),fill='#252930');d.rectangle((160,180,864,844),fill='#b18a3c');d.text((250,470),f['metadata']['name'],fill='white',font_size=32)
        b=BytesIO();im.save(b,format='WEBP');original=b.getvalue();im.thumbnail((128,128));b=BytesIO();im.save(b,format='JPEG');images[f['metadata']['id']]=(original,b.getvalue())
        f['metadata']['size']=len(original)
    class Store:
        def __init__(self,*_):pass
        def read(self,*_):return row
        @contextmanager
        def locked(self,*_):yield row,None
        def copied(self,*_):return row
        def change_mode(self,key,uid,mode):row['mode']=mode;return row
    meta={f['metadata']['id']:f['metadata'] for f in files}
    def thumbnail(token,path,**kw):
        m=next(m for m in meta.values() if m['path_display']==path);requests.append('thumbnail '+m['name']);return images[m['id']][1]
    def original(token,key,rev):
        requests.append('original '+meta[key]['name'])
        return meta[key],SimpleNamespace(iter_content=lambda **_:iter([images[key][0]]),close=lambda:None)
    async def actor(*a,**kw):return {'id':'fixture-owner'}
    async def component(request):return HTMLResponse((root/'components/product_uploads/index.html').read_text())
    async def state(request):
        from product_upload_intake import public
        return JSONResponse(dict(enabled=True,upload=public(row)))
    async def mapping(request):return JSONResponse(dict(mapping=dict(state='Unmapped',label='Unmapped',reason='Synthetic fixture; no live mapping performed.')))
    async def evidence(request):return JSONResponse(dict(requests=requests))
    async def shell(request):
        return HTMLResponse('''<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0;font:14px/1.4 "Segoe UI",sans-serif;background:#faf9f5}header{background:#171814;color:#cfaa49;padding:16px}main{max-width:1080px;margin:auto;padding:20px}iframe{border:0;width:100%;height:450px}button,select{padding:8px;font:inherit}.save{display:flex;gap:12px;align-items:center}.save span{color:#278244}</style><header>Sports Cave OS · Isolated saved WebP fixture</header><main><h2>Product Uploads</h2><p>Saving to: Motorsport Wall Art / fixture-artwork (2)</p><div class="save"><button disabled>Save all</button><span>✓ Saved</span></div><iframe id="component" src="/component" title="Saved package"></iframe><label>Fixture width <select id="width" onchange="document.querySelector('main').style.maxWidth=this.value+'px'"><option value="1080">Desktop</option><option value="640">Narrow desktop</option></select></label> <label>Fixture scale <select id="scale" onchange="document.querySelector('iframe').contentDocument.body.style.zoom=this.value"><option value="1">100%</option><option value="1.5">150%</option><option value="2">200%</option></select></label><p>Fixture thumbnails only. No real product or cloud data.</p></main><script>const f=document.querySelector('iframe');f.onload=()=>f.contentWindow.postMessage({type:'streamlit:render',args:{section:'handoff',id:'KEY',mode:'DRAFT',package_version:'saved'}},location.origin);addEventListener('message',e=>{if(e.source===f.contentWindow&&e.data.type==='sports-cave-product-upload-height')f.style.height=e.data.height+'px';});</script>'''.replace('KEY',str(row['id'])))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(api,'actor',actor);patch.setattr(api,'Intakes',Store)
        patch.setattr(api,'Dropbox',lambda:SimpleNamespace(token='fixture',metadata_if_present=lambda key:meta.get(key),api=SimpleNamespace(get_thumbnail_bytes=thumbnail,get_psd_file_response=original)))
        patch.setattr(product_upload_prompts,'build',lambda mode,name:'Fixture '+mode+' prompt for '+name)
        app=Starlette(routes=[Route('/',shell),Route('/component',component),Route('/fixture/evidence',evidence),
            Route('/api/product-uploads/state',state),Route('/api/product-uploads/mapping-status',mapping),
            *[Route(p,e,methods=list(m)) for p,e,m in api.ROUTES]])
        with local_client(app) as client:
            print(client.base,flush=True);input('Fixture ready; Enter stops.\n')


if __name__=='__main__':main()
