"""Loopback-only actual Product Upload UI, read-only PSD and isolated providers.

Reuses the existing credential-free Streamlit/PGlite harness. No deployment
server, original writes, Shopify calls or Companion jobs are permitted.
"""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))


def application(original, mbps=0,baseline=False):
    import product_upload_mockups_preview as preview
    app=preview.application()
    store,sql,provider=preview.STATE['env'];patch=preview.STATE['patch']
    import io,time
    import image_factory,tempfile
    patch.setenv(image_factory.TEMP_ROOT_ENV,tempfile.mkdtemp(prefix='sc-product-ui-'))
    from PIL import Image
    from tests.test_product_upload_dropbox import provider_fixture
    from auto_editions import file_hash
    import product_upload_api as api,files_upload_api as files
    from starlette.routing import Route
    from starlette.responses import JSONResponse
    original=Path(original)
    add=provider_fixture(provider)
    meta=add('id:u1tYiAa2O-AAAAAAAABw6w',original.name,'0165e251a26bf2f000000036d367e13')
    meta.update(size=original.stat().st_size,content_hash=file_hash(original,dropbox=True))
    assert meta['size']==285917118 and meta['content_hash']=='c5c9b3192d5cb6a5c42a70ef465f02cae5fcc1d8a2a14fd7fa4b964ec74da72e'
    provider.files[meta['id']]=meta;provider.files[meta['path_display']]=meta
    measurements=dict(downloads=0,download_bytes=0,metadata_calls=0);fault={'next':False}
    import product_upload_artwork as artwork
    cached=artwork.cached
    patch.setattr(artwork,'cached',lambda row,settings:None if fault['next'] else cached(row,settings))
    lookup=provider.metadata_if_present
    def metadata(key):
        measurements['metadata_calls']+=1
        return lookup(key)
    provider.metadata_if_present=metadata
    def download(selected,destination,*,progress=None):
        assert selected['id']==meta['id'] and selected['rev']==meta['rev']
        measurements['downloads']+=1;total=0
        if fault['next']:
            fault['next']=False
            raise __import__('requests').ReadTimeout('Isolated retry fixture')
        with original.open('rb') as source,Path(destination).open('xb') as target:
            while chunk:=source.read(1024*1024):
                if mbps:time.sleep(len(chunk)/(mbps*1024*1024))
                target.write(chunk);total+=len(chunk);measurements['download_bytes']+=len(chunk)
                if progress:progress(total,selected['size'])
    provider.download=download
    def directory(token,path,**kwargs):
        rows=[m for k,m in provider.files.items() if k.startswith('id:') and Path(m.get('path_display','')).parent.as_posix()==path]
        return dict(entries=rows,has_more=False,page_token='')
    patch.setattr(files,'_directory_page',directory)
    with Image.open(original) as image:
        image.thumbnail((160,120));buffer=io.BytesIO();image.convert('RGB').save(buffer,format='JPEG')
    provider.api.get_psd_thumbnail_bytes.return_value=buffer.getvalue()
    from unittest.mock import Mock
    patch.setattr('product_upload_render.Renders.claim',Mock(side_effect=AssertionError('Companion prohibited')))
    patch.setattr('product_upload_render.Renders.request',Mock(side_effect=AssertionError('Companion prohibited')))
    async def metrics(request):return JSONResponse(dict(measurements,source_unchanged=file_hash(original,dropbox=True)==meta['content_hash']))
    async def fail_next(request):fault['next']=True;return JSONResponse({'isolated_failure_armed':True})
    from streamlit.web.server.starlette import App
    if baseline:
        import ast,product_upload_artwork as artwork,product_upload_mockups_ui as ui
        before=ROOT/'output/product-upload-responsive/before'
        for module,name,functions in ((artwork,'product_upload_artwork.py',{'prepare','ready','ensure_ready'}),
                                       (api,'product_upload_api.py',{'action','source_preview'})):
            tree=ast.parse((before/name).read_text(encoding='utf-8'))
            nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in functions]
            exec(compile(ast.Module(body=nodes,type_ignores=[]),str(before/name),'exec'),module.__dict__)
        ui.__file__=str(before/'product_upload_mockups_ui.py')
        exec(compile(Path(ui.__file__).read_text(encoding='utf-8'),ui.__file__,'exec'),ui.__dict__)
        async def baseline_script(request):
            from starlette.responses import Response
            return Response((before/'components/product_uploads/app.js').read_text(encoding='utf-8'),media_type='application/javascript')
    routes=[]
    for route in preview.STATE['local'].routes:
        if route.path=='/':continue
        if route.path=='/api/product-uploads/{action}':route=Route(route.path,api.action,methods=['POST'])
        elif route.path=='/api/product-uploads/source-preview':route=Route(route.path,api.source_preview,methods=['GET'])
        elif baseline and route.path=='/product-uploads.js':route=Route(route.path,baseline_script,methods=['GET'])
        routes.append(route)
    return App(str(ROOT/'tests/fixtures/product_upload_responsive.py'),routes=[*routes,Route('/__test/responsive-metrics',metrics),Route('/__test/fail-next-preparation',fail_next,methods=['POST'])])


if __name__=='__main__':
    import argparse,uvicorn
    parser=argparse.ArgumentParser();parser.add_argument('--psd',required=True);parser.add_argument('--port',type=int,default=8691);parser.add_argument('--download-mbps',type=float,default=0);parser.add_argument('--baseline',action='store_true')
    args=parser.parse_args()
    app=application(args.psd,args.download_mbps,args.baseline)
    try:uvicorn.run(app,host='127.0.0.1',port=args.port,access_log=False)
    finally:
        import product_upload_mockups_preview as preview
        db,patch,_=preview.STATE['local'].state.fixture;patch.undo();db.close()
