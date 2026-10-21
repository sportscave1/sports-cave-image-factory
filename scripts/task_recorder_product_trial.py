"""Real Product Uploads components with disposable PostgreSQL and synthetic pixels.

No original artwork, installed Companion, Shopify or external providers. This
is a UI/provider acceptance fixture, not evidence of native recorder playback.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--port", type=int, default=18975)
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    installed = Path(os.environ["LOCALAPPDATA"]) / "SportsCaveOS"
    if root == ROOT or ROOT in root.parents or root == installed or installed in root.parents:
        raise SystemExit("Use an isolated synthetic runtime outside source and installed helper data.")
    root.mkdir(parents=True, exist_ok=True)
    if not args.serve:
        allowed = {"PATH","SYSTEMROOT","WINDIR","COMSPEC","PATHEXT","USERPROFILE","APPDATA","LOCALAPPDATA","PROGRAMFILES","PROGRAMFILES(X86)"}
        env = {key:value for key,value in os.environ.items() if key.upper() in allowed}
        temporary = root / "tmp"
        temporary.mkdir(exist_ok=True)
        env.update(TEMP=str(temporary), TMP=str(temporary), PYTHONDONTWRITEBYTECODE="1",
                   STREAMLIT_BROWSER_GATHER_USAGE_STATS="false", STREAMLIT_SERVER_FILE_WATCHER_TYPE="none")
        return subprocess.call([sys.executable,"-B",str(Path(__file__).resolve()),"--serve","--root",str(root),"--port",str(args.port)],cwd=ROOT,env=env)
    import dotenv
    dotenv.load_dotenv = lambda *a,**k:False
    import socket
    connect_socket = socket.socket.connect
    def loopback(sock, address):
        if isinstance(address,tuple) and address[0] not in {"127.0.0.1","localhost","::1"}:
            raise RuntimeError("Synthetic Product Uploads fixture permits loopback connections only.")
        return connect_socket(sock,address)
    socket.socket.connect = loopback
    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row
    database = "recorder_product_trial_" + uuid.uuid4().hex
    base = "host=127.0.0.1 port=55439 user=postgres password=synthetic-recorder-only"
    with psycopg.connect(base + " dbname=postgres",autocommit=True) as admin:
        for role in ("anon","authenticated","service_role"):
            if not admin.execute("SELECT 1 FROM pg_roles WHERE rolname=%s",(role,)).fetchone():
                admin.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    dsn = base + " dbname=" + database
    (root / "synthetic-product-trial.json").write_text(json.dumps(dict(database=database,port=args.port,purpose="Synthetic Product Uploads component acceptance"),indent=2))
    from contextvars import ContextVar
    current_connection = ContextVar("recorder-synthetic-sql",default=None)
    class Connection:
        def __enter__(self):
            self.conn = current_connection.get()
            self.owned = self.conn is None
            if self.owned:self.conn = psycopg.connect(dsn,row_factory=dict_row)
            self.scope = current_connection.set(self.conn)
            self.transaction = self.conn.transaction()
            self.transaction.__enter__()
            return self
        def cursor(self):return self.conn.cursor()
        def __exit__(self,*error):
            try:return self.transaction.__exit__(*error)
            finally:
                current_connection.reset(self.scope)
                if self.owned:self.conn.close()
    def database_fixture():
        from auto_editions_jobs import Jobs
        setup = psycopg.connect(dsn,autocommit=True,row_factory=dict_row)
        try:
            setup.execute((ROOT/"migrations/20261014004209_auto_editions_v6.sql").read_text())
            yield Jobs(Connection),setup.cursor()
        finally:setup.close()
    import tests.test_product_upload_intake as intake_fixture
    from types import SimpleNamespace
    intake_fixture.database = SimpleNamespace(__wrapped__=database_fixture)
    import product_upload_mockups_preview as preview
    app = preview.application()
    store,_,provider = preview.STATE["env"]
    patch = preview.STATE["patch"]
    import image_factory as factory
    patch.setenv(factory.TEMP_ROOT_ENV,str(root / "images"))
    from PIL import Image, ImageCms, ImageDraw
    import struct
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    resource = b"8BIM" + struct.pack(">H",1039) + b"\0\0" + struct.pack(">I",len(profile)) + profile + b"\0" * (len(profile)%2)
    width,height = 96,64
    source = root / "Recorder Synthetic Art.psd"
    source.write_bytes(b"8BPS\0\1"+b"\0"*6+struct.pack(">HIIHH",3,height,width,8,3)+struct.pack(">I",0)+
        struct.pack(">I",len(resource))+resource+struct.pack(">I",0)+b"\0\0"+
        bytes([25])*(width*height)+bytes([85])*(width*height)+bytes([130])*(width*height))
    from tests.test_product_upload_dropbox import provider_fixture
    from tests.test_product_upload_intake import ADMIN
    import auto_editions as ae
    add = provider_fixture(provider)
    meta = add("id:recorderSyntheticArt21",source.name,"a1")
    meta.update(size=source.stat().st_size,content_hash=ae.file_hash(source,dropbox=True))
    provider.files[meta["id"]] = meta
    provider.files[meta["path_display"]] = meta
    import shutil
    def download(selected, destination, **kwargs):
        if selected["id"] != meta["id"]:raise ValueError("Only the synthetic PSD is available.")
        shutil.copyfile(source,destination)
        if kwargs.get("progress"):kwargs["progress"](meta["size"],meta["size"])
    provider.download = download
    from tests.fixtures.product_upload_outputs_provider import Outputs
    cloud = Outputs()
    provider.api = cloud
    metadata = cloud.get_metadata_if_exists
    cloud.get_metadata_if_exists = lambda token,key:metadata(token,key) or next((dict(row) for row in cloud.files.values() if row.get("id")==key),None)
    import dropbox_integration as dropbox
    patch.setattr(dropbox,"get_metadata_if_exists",cloud.get_metadata_if_exists)
    patch.setattr(dropbox,"list_folder_page",lambda token,parent,**kw:dict(entries=cloud.entries(token,parent),has_more=False))
    calls=[]
    def generate(name,sport,artwork,*,output_root,asset_completed_callback=None,**kwargs):
        import time
        calls.append(dict(kind="generate",name=name,sport=sport))
        folder = Path(output_root) / ("synthetic-"+uuid.uuid4().hex)
        folder.mkdir(parents=True)
        assets=[]
        for spec in factory.PRODUCT_IMAGE_SLOT_SPECS:
            if spec.get("prompt_filename"):continue
            image=Image.new("RGB",(320,240),(25,70,110))
            ImageDraw.Draw(image).text((20,110),"SYNTHETIC "+spec["display_label"],fill="white")
            png=folder/(spec["slot_id"]+".png");webp=folder/(spec["slot_id"]+".webp")
            image.save(png);image.save(webp)
            asset=factory.build_asset_record(spec["asset_key"],spec["display_label"],review_path=png,preview_path=png,webp_path=webp,
                zip_group=spec["zip_group"],export_to_socials=False)
            assets.append(asset)
            if asset_completed_callback:asset_completed_callback(asset,None,run_dir=folder)
            time.sleep(.15)
        return dict(product_name=name,product_slug=factory.slugify(name),sport_category=sport,sport_slug=factory.slugify(sport),
                    run_dir=folder,assets=assets,lifestyle_mockup_paths={},final_prompt_items=kwargs.get("final_prompt_items",[]))
    patch.setattr(factory,"generate_product_images",generate)
    from product_upload_dropbox import select
    row=select(store.connect,provider,str(uuid.uuid4()),ADMIN["id"],"DRAFT",meta["id"],meta["rev"])
    from product_upload_artwork import prepare as prepare_artwork
    row=prepare_artwork(store.connect,provider,str(row["id"]),ADMIN["id"])
    from unittest.mock import Mock
    patch.setattr("product_upload_render.Renders.request",Mock(side_effect=AssertionError("Installed Companion jobs prohibited in recorder fixture")))
    patch.setattr("product_upload_render.Renders.claim",Mock(side_effect=AssertionError("Installed Companion jobs prohibited in recorder fixture")))
    from product_upload_prompts import build
    def configure(module):
        module._files_directory_entries=cloud.entries
    preview.STATE["configure_outputs"] = configure
    preview.STATE["recorder_trial_origin"] = "http://127.0.0.1:" + str(args.port)
    import product_upload_gallery as gallery
    render_gallery = gallery.render
    def observed_gallery(**kwargs):
        if kwargs.get("mode") == "actions" and kwargs.get("prompt"):
            (root/"expected-gallery-prompt.txt").write_bytes(kwargs["prompt"].encode("utf-8"))
            (root/"expected-gallery-context.json").write_text(json.dumps(dict(intake_id=str(row["id"]))))
        return render_gallery(**kwargs)
    patch.setattr(gallery,"render",observed_gallery)
    if "product_upload_outputs_ui" in sys.modules:
        patch.setattr(sys.modules["product_upload_outputs_ui"],"render",observed_gallery)
    from starlette.routing import Route
    from starlette.responses import JSONResponse,HTMLResponse
    async def metrics(request):
        import hashlib
        from product_upload_compact import context_from_row
        from product_upload_source import current_source
        latest=store.read(str(row["id"]),ADMIN["id"])
        expected=None
        if latest["data"].get("mockups_exported"):
            source_info=current_source(latest)
            expected=build(latest["mode"],latest["data"]["name"],source=source_info,metadata=context_from_row(latest))
            (root/"expected-copy.txt").write_bytes(expected.encode("utf-8"))
        return JSONResponse(dict(generate_calls=calls,output_calls=cloud.calls,source_unchanged=ae.file_hash(source,dropbox=True)==meta["content_hash"],
            expected_copy_sha256=hashlib.sha256(expected.encode()).hexdigest() if expected else None,
            expected_copy_length=len(expected) if expected else None,exported=bool(latest["data"].get("mockups_exported"))))
    async def copy_check(request):
        return HTMLResponse('''<!doctype html><title>Recorder synthetic clipboard check</title>
<style>body{font:18px system-ui;max-width:720px;margin:32px}textarea{width:100%;height:180px}button{font:inherit;padding:10px}</style>
<h1>Recorder synthetic clipboard check</h1><p>After copying the synthetic Product Uploads prompt, paste it below and choose Verify. Only its hash, length and match result are retained.</p>
<label for="copied">Copied synthetic prompt</label><textarea id="copied"></textarea><button id="verify">Verify</button><p id="result" role="status"></p>
<script>document.getElementById('verify').onclick=async()=>{const field=document.getElementById('copied');const reply=await fetch('/__test/verify-copy',{method:'POST',headers:{'Content-Type':'text/plain'},body:field.value});const data=await reply.json();document.getElementById('result').textContent=data.exact?'Exact match':(data.error||'Clipboard mismatch');field.value='';};</script>''')
    async def verify_copy(request):
        if request.headers.get("origin") != preview.STATE["recorder_trial_origin"]:
            return JSONResponse(dict(error="Use the local clipboard check page."),status_code=403)
        if int(request.headers.get("content-length","0")) > 1024*1024:
            return JSONResponse(dict(error="Test paste exceeds the supported size."),status_code=413)
        value=await request.body()
        if len(value)>1024*1024:return JSONResponse(dict(error="Test paste exceeds the supported size."),status_code=413)
        expected_path=root/"expected-gallery-prompt.txt"
        context_path=root/"expected-gallery-context.json"
        if (not expected_path.exists() or not context_path.exists() or
                json.loads(context_path.read_text()).get("intake_id")!=str(row["id"])):
            return JSONResponse(dict(error="Prepare the current synthetic prompt first."),status_code=409)
        import hashlib
        expected=expected_path.read_bytes()
        result=dict(intake_id=str(row["id"]),exact=value==expected,bytes=len(value),sha256=hashlib.sha256(value).hexdigest(),expected_sha256=hashlib.sha256(expected).hexdigest())
        (root/"paste-copy-verification.json").write_text(json.dumps(result,indent=2))
        return JSONResponse(result)
    from streamlit.web.server.starlette import App
    app=App(str(ROOT/"tests/fixtures/task_recorder_product_trial_ui.py"),routes=[*app._user_routes,
        Route("/__test/recorder-product",metrics),Route("/__test/copy-check",copy_check),Route("/__test/verify-copy",verify_copy,methods=["POST"])])
    (root/"ready.json").write_text(json.dumps(dict(url="http://127.0.0.1:"+str(args.port)+"/?upload="+str(row["id"]),pid=os.getpid()),indent=2))
    import uvicorn
    try:uvicorn.run(app,host="127.0.0.1",port=args.port,access_log=False)
    finally:
        db,patch,_=preview.STATE["local"].state.fixture
        patch.undo()
        try:next(db)
        except StopIteration:pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
