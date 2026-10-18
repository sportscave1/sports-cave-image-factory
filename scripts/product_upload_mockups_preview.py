"""Isolated combined UI harness. Reuses the credential-free intake test server.

Actual Streamlit/components/Mockups generation; Photoshop and cloud boundaries
are doubles. Never imports the deployment server or installed Companion.
"""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(Path(__file__).parent))


def application():
    # The disposable PGlite HTTP transport has a short idle keep-alive. Close
    # an idle socket before its next query; no production transport is changed.
    import http.client,time
    original_connection=http.client.HTTPConnection
    class PreviewConnection(original_connection):
        last_request=0
        def request(self,*args,**kwargs):
            now=time.monotonic()
            if now-self.last_request>2:self.close()
            self.last_request=now
            return super().request(*args,**kwargs)
    http.client.HTTPConnection=PreviewConnection
    from product_upload_local_preview import application as intake_application
    local=intake_application()
    import os,tempfile,image_factory
    # Private fixture resources, with room for Windows lifestyle staging paths.
    os.environ[image_factory.TEMP_ROOT_ENV]=str(Path(tempfile.gettempdir())/'sc-pu-4b18037e')
    db,patch,env=local.state.fixture
    store,sql,provider=env
    import product_upload_api as api
    import shutil
    def download(meta,path):
        if meta['id'].startswith('id:render:'):
            shutil.copyfile(provider.root/(meta['id'].split(':')[-1]+'.png'),path)
        else:
            shutil.copyfile(provider.sessions[meta['id'].removeprefix('id:')],path)
    provider.download=download
    def save_render(key,path):
        from auto_editions import file_hash
        target=provider.root/(key+'.png');shutil.copyfile(path,target)
        return dict(id='id:render:'+key,rev='r1',content_hash=file_hash(target,dropbox=True))
    provider.save_render=save_render
    patch.setattr(api,'Dropbox',lambda:provider)
    from unittest.mock import Mock
    provider.api=Mock();provider.token='synthetic'
    provider.api.sanitize_path_component.side_effect=lambda s,**kw:s.strip()
    provider.api.join_upload_path.side_effect=lambda a,b:a.rstrip('/')+'/'+b
    provider.api.get_metadata_if_exists.return_value=None
    provider.api.numbered_path.side_effect=lambda a,b:b+' (2)'
    global STATE
    STATE=dict(local=local,env=env,patch=patch)
    from streamlit.web.server.starlette import App
    routes=[r for r in local.routes if r.path!='/']
    return App(str(ROOT/'tests/fixtures/product_upload_mockups.py'),routes=routes)


if __name__=='__main__':
    sys.modules['product_upload_mockups_preview']=sys.modules[__name__]
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8683);args=parser.parse_args()
    app=application()
    import uvicorn
    try:uvicorn.run(app,host='127.0.0.1',port=args.port,access_log=False)
    finally:
        db,patch,_=STATE['local'].state.fixture;patch.undo();db.close()
