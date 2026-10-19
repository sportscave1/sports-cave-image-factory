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
    import hashlib, json, subprocess, sys
    from PIL import Image,ImageDraw
    from starlette.applications import Starlette
    from starlette.responses import HTMLResponse,JSONResponse
    from starlette.routing import Route
    from tests.test_product_upload_package import saved_row
    from tests.benchmark_product_upload_transfer import local_client
    import product_upload_api as api, product_upload_prompts, files_upload_api as native_files, os_accounts
    root=Path(__file__).resolve().parents[2];row=saved_row()
    row['data'].update(basic_validated=True,state='Ready',name='Fixture artwork.psd')
    files=row['data']['upload_operation']['output']['files'];images={};requests=[]
    for i,f in enumerate(files):
        im=Image.new('RGB',(1024,1024),(228-i*9,223-i*7,205+i*4));d=ImageDraw.Draw(im);d.rectangle((140,160,884,864),fill='#252930');d.rectangle((160,180,864,844),fill='#b18a3c');d.text((250,470),f['metadata']['name'],fill='white',font_size=32)
        b=BytesIO();im.save(b,format='WEBP');original=b.getvalue();im.thumbnail((128,128));b=BytesIO();im.save(b,format='JPEG');images[f['metadata']['id']]=(original,b.getvalue())
        f['metadata']['size']=len(original)
        f['metadata']['content_hash']=hashlib.sha256(hashlib.sha256(original).digest()).hexdigest()
        f['metadata']['.tag']='file'
    class Store:
        def __init__(self,*_):pass
        def read(self,*_):return row
        @contextmanager
        def locked(self,*_):yield row,None
        def copied(self,*_):return row
        def change_mode(self,key,uid,mode):row['mode']=mode;return row
    meta={f['metadata']['id']:f['metadata'] for f in files}
    folder=row['data']['upload_operation']['output']['folder']+'/WEBP'
    folder_meta={'.tag':'folder','id':'id:webpfolder','name':'WEBP','path_display':folder}
    def metadata(key):
        if key in (folder,'id:webpfolder'):return folder_meta
        return meta.get(key) or next((m for m in meta.values() if m['path_display']==key),None)
    def listing(token,path,cursor='',**kw):
        assert path=='id:webpfolder'
        requests.append('listing '+str(cursor))
        values=list(meta.values())
        return dict(entries=values[4:] if cursor else values[:4],has_more=not bool(cursor),cursor='page2' if not cursor else '')
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
    async def evidence(request):
        import product_upload_clipboard as clipboard
        return JSONResponse(dict(requests=requests,sessions=[{k:r[k] for k in ('state','count','sequence','copy_ms')} for r in clipboard.REQUESTS.records.values()]))
    async def shell(request):
        return HTMLResponse('''<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0;font:14px/1.4 "Segoe UI",sans-serif;background:#faf9f5}header{background:#171814;color:#cfaa49;padding:16px}main{max-width:1080px;margin:auto;padding:20px}iframe{border:0;width:100%;height:450px}button,select{padding:8px;font:inherit}.save{display:flex;gap:12px;align-items:center}.save span{color:#278244}</style><header>Sports Cave OS · Isolated saved WebP fixture</header><main><h2>Product Uploads</h2><p>Saving to: Motorsport Wall Art / fixture-artwork (2)</p><div class="save"><button disabled>Save all</button><span>✓ Saved</span></div><iframe id="component" src="/component" title="Saved package"></iframe><label>Fixture width <select id="width" onchange="document.querySelector('main').style.maxWidth=this.value+'px'"><option value="1080">Desktop</option><option value="640">Narrow desktop</option></select></label> <label>Fixture scale <select id="scale" onchange="document.querySelector('iframe').contentDocument.body.style.zoom=this.value"><option value="1">100%</option><option value="1.5">150%</option><option value="2">200%</option></select></label><p>Fixture thumbnails only. No real product or cloud data.</p></main><script>const f=document.querySelector('iframe');f.onload=()=>f.contentWindow.postMessage({type:'streamlit:render',args:{section:'handoff',id:'KEY',mode:'DRAFT',package_version:'saved'}},location.origin);addEventListener('message',e=>{if(e.source===f.contentWindow&&e.data.type==='sports-cave-product-upload-height')f.style.height=e.data.height+'px';});</script>'''.replace('KEY',str(row['id'])))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(api,'actor',actor);patch.setattr(api,'Intakes',Store)
        patch.setattr(api,'Dropbox',lambda:SimpleNamespace(token='fixture',metadata_if_present=metadata,api=SimpleNamespace(get_thumbnail_bytes=thumbnail,get_psd_file_response=original,list_folder_page=listing)))
        patch.setattr(os_accounts,'can_access_page',lambda *a:True)
        patch.setattr(native_files,'_dropbox_context',lambda:dict(access_token='fixture',root_path='/Team'))
        patch.setattr(native_files.dropbox_integration,'get_file_metadata',lambda token,key:metadata(key))
        patch.setattr(native_files.dropbox_integration,'get_psd_file_response',original)
        patch.setattr(product_upload_prompts,'build',lambda mode,name:'Fixture '+mode+' prompt for '+name)
        helper=None;processes=[]
        if '--native' in sys.argv:
            from tests.test_desktop_helper import DesktopWindowsBuildTests
            helper=DesktopWindowsBuildTests();helper.setUp();helper._compile()
        async def launch(request):
            result=await api.clipboard_launch(request)
            if helper and result.status_code==200:
                payload=json.loads(result.body)
                processes.append(subprocess.Popen([str(helper.executable),payload['url']],creationflags=subprocess.CREATE_NO_WINDOW,
                    env={**os.environ,'SPORTS_CAVE_FILE_CACHE':str(helper.base/'cache'),'SPORTS_CAVE_DESKTOP_INSTANCE':'webp-fixture'}))
                # Do not invoke or replace the globally installed protocol handler.
                payload['url']='#isolated-helper-started'
                return JSONResponse(payload)
            return result
        app=Starlette(routes=[Route('/',shell),Route('/component',component),Route('/fixture/evidence',evidence),
            Route('/api/product-uploads/clipboard-launch',launch,methods=['POST']),
            Route('/api/product-uploads/state',state),Route('/api/product-uploads/mapping-status',mapping),
            *[Route(p,e,methods=list(m)) for p,e,m in native_files.FILES_UPLOAD_ROUTES if p.startswith('/api/files-native-transfer/')],
            *[Route(p,e,methods=list(m)) for p,e,m in api.ROUTES]])
        with local_client(app) as client:
            if helper:
                (helper.base/'config.json').write_text(json.dumps(dict(AppUrl=client.base,AllowedOrigins=[client.base],RootPath='')),encoding='utf-8')
                print('Isolated helper: '+str(helper.executable),flush=True)
            print(client.base,flush=True);input('Fixture ready; Enter stops.\n')
            for process in processes:
                if process.poll() is None:process.terminate();process.wait(timeout=10)
            if helper:helper.tearDown()


if __name__=='__main__':main()
