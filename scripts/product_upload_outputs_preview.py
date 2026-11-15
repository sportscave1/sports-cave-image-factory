"""Actual Product Upload UI; isolated SQL/provider, original read-only, no external writes."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))


def application(psd):
    import product_upload_responsive_preview as responsive
    app=responsive.application(psd)
    import product_upload_mockups_preview as preview
    from tests.fixtures.product_upload_outputs_provider import Outputs
    cloud=Outputs()
    cloud.delay=.08 # Isolated transfer latency makes real byte progress observable.
    patch=preview.STATE['patch'];provider=preview.STATE['env'][2]
    # Selection fixture and export fixture use one synthetic account context.
    provider.api=cloud
    # Picker/source thumbnail method is read only synthetic data.
    from PIL import Image
    import io
    with Image.open(psd) as image:
        image.thumbnail((160,120));data=io.BytesIO();image.convert('RGB').save(data,format='JPEG')
    cloud.get_psd_thumbnail_bytes=lambda *a,**kw:data.getvalue()
    from unittest.mock import Mock
    patch.setattr('prompt_store._load_prompts_from_supabase',Mock(return_value=[]))
    def configure(module):
        import ast
        tree=ast.parse((ROOT/'app.py').read_text(encoding='utf-8'))
        picker=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_render_mockup_folder_picker')
        exec(compile(ast.Module(body=[picker],type_ignores=[]),str(ROOT/'app.py'),'exec'),module.__dict__)
        module._files_directory_entries=cloud.entries
        module.dropbox_integration.ensure_folder_path=lambda *a,**kw:None # existing fixture tree only
    preview.STATE['configure_outputs']=configure
    from starlette.routing import Route
    from starlette.responses import JSONResponse
    async def metrics(request):return JSONResponse(dict(calls=cloud.calls,paths=list(cloud.files)))
    async def fail(request):
        cloud.fail_once=request.query_params.get('name');return JSONResponse(dict(armed=True))
    from streamlit.web.server.starlette import App
    return App(str(ROOT/'tests/fixtures/product_upload_responsive.py'),routes=[*app._user_routes,
        Route('/__test/outputs',metrics),Route('/__test/fail-save',fail,methods=['POST'])])


if __name__=='__main__':
    import argparse,uvicorn
    parser=argparse.ArgumentParser();parser.add_argument('--psd',required=True);parser.add_argument('--port',type=int,default=8692)
    args=parser.parse_args();app=application(args.psd)
    try:uvicorn.run(app,host='127.0.0.1',port=args.port,access_log=False)
    finally:
        import product_upload_mockups_preview as preview
        db,patch,_=preview.STATE['local'].state.fixture;patch.undo();db.close()
