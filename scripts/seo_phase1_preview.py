"""Run actual authenticated app.py with isolated Postgres and offline Google transport.
The production server launcher, provider secrets, workers and subprocesses are excluded.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--port',type=int,default=18977)
    parser.add_argument('--serve',action='store_true')
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[1]
    root=args.root.resolve();root.mkdir(parents=True,exist_ok=True)
    if not args.serve:
        allowed={'PATH','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','USERPROFILE','APPDATA','LOCALAPPDATA','PROGRAMFILES','PROGRAMFILES(X86)'}
        env={k:v for k,v in os.environ.items() if k.upper() in allowed}
        env.update({'DATABASE_URL':'postgresql://postgres:synthetic-seo-preview-only@127.0.0.1:55447/seo_phase1?sslmode=disable',
            'SEO_PHASE1_MODE':'shared','SPORTS_CAVE_AUTH_SECRET':'synthetic-seo-full-app-preview-only',
            'SPORTS_CAVE_ADMIN_EMAIL':'seo-preview@example.invalid','SPORTS_CAVE_ADMIN_PASSWORD':'SeoPreview-Only-2026',
            'SPORTS_CAVE_ADMIN_NAME':'SEO preview admin','SPORTS_CAVE_DB_PATH':str(root/'app.db'),
            'PYTHONDONTWRITEBYTECODE':'1','STREAMLIT_BROWSER_GATHER_USAGE_STATS':'false',
            'STREAMLIT_SERVER_FILE_WATCHER_TYPE':'none','TEMP':str(root),'TMP':str(root),
            'PYTHONPATH':str(repo)+os.pathsep+str(repo/'.local/python-deps')})
        return subprocess.call([sys.executable,str(Path(__file__).resolve()),'--serve','--root',str(root),'--port',str(args.port)],cwd=repo,env=env)
    (root/'secrets.toml').write_text('# Empty synthetic preview secrets only\n',encoding='utf-8')
    import streamlit.config as streamlit_config
    streamlit_config.set_option('secrets.files',[str(root/'secrets.toml')])
    import dotenv
    dotenv.load_dotenv=lambda *a,**k:False
    from scripts.seo_phase1_devdata import connect,prepare,DevelopmentGoogleClient
    connect().close() # exact host/port/database validation precedes any schema writes
    import socket
    original_connect=socket.socket.connect
    def local_connect(sock,address):
        if isinstance(address,tuple) and address[0] not in {'127.0.0.1','localhost','::1'}:
            raise RuntimeError('External network is disabled in the SEO development preview.')
        return original_connect(sock,address)
    socket.socket.connect=local_connect
    def audit(event,items):
        if event in {'subprocess.Popen','os.system','os.posix_spawn','os.fork'}:
            raise RuntimeError('Background processes are disabled in the SEO development preview.')
        if event=='open' and isinstance(items[0],(str,bytes)):
            path=Path(os.fsdecode(items[0])).resolve()
            if path.name=='.env' or (path.name=='secrets.toml' and root not in path.parents):
                raise RuntimeError('Provider credential files are disabled in the SEO preview.')
            mode=items[1] or '';flags=items[2] if len(items)>2 else 0
            if any(c in str(mode) for c in 'wax+') or (isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT)):
                if path!=root and root not in path.parents and str(path).lower() not in {'nul',os.devnull.lower()}:
                    raise RuntimeError('SEO preview writes must stay inside its isolated runtime directory.')
    sys.addaudithook(audit)
    prepare(repo)
    import os_accounts
    accounts=os_accounts.DEFAULT_STORE;accounts.ensure_schema()
    admin=accounts.find_user_by_login('seo-preview@example.invalid')
    if not admin:
        admin=accounts.create_user(username='seo-preview',email='seo-preview@example.invalid',display_name='SEO development admin',password_hash=os_accounts.hash_password('SeoPreview-Only-2026'),role='admin')
    from google_direct_reporting import GoogleReports
    def development_client(self,connection):
        if connection.get('ga4_property_id')!='properties/57995487' or connection.get('gsc_site_url')!='sc-domain:seo-preview.invalid':
            raise RuntimeError('Only the synthetic development Google property is permitted.')
        return DevelopmentGoogleClient()
    GoogleReports.client=development_client
    with connect() as conn:
        conn.execute((repo/'supabase/migrations/20261020001929_task_recorder_device_relay.sql').read_text())
    from starlette.routing import Route
    from streamlit.web.server.starlette import App
    from auth_cookie_cleanup import ROUTES as CLEANUP
    from top_bar_api import TOP_BAR_ROUTE_HANDLERS
    from daily_planner import DAILY_PLANNER_ROUTE_HANDLERS
    from task_recorder.hosted_api import ROUTES as RECORDER
    app=App(str(repo/'app.py'),routes=[Route(path,fn,methods=list(methods)) for path,fn,methods in (*CLEANUP,*TOP_BAR_ROUTE_HANDLERS,*DAILY_PLANNER_ROUTE_HANDLERS,*RECORDER)])
    import uvicorn
    print(f'Isolated authenticated SEO app: http://127.0.0.1:{args.port}/?page=seo',flush=True)
    uvicorn.run(app,host='127.0.0.1',port=args.port,access_log=False,log_level='warning')

if __name__=='__main__':raise SystemExit(main())
