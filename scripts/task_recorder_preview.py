"""Isolated full OS + real recorder routes, account auth and local PostgreSQL.
No production server entry point, workers, provider credentials or external I/O.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--port",type=int,default=18961)
    p.add_argument("--serve",action="store_true")
    args=p.parse_args()
    root=args.root.resolve();root.mkdir(parents=True,exist_ok=True)
    repo=Path(__file__).resolve().parents[1]
    if not args.serve:
        allowed={"PATH","SYSTEMROOT","WINDIR","COMSPEC","PATHEXT","USERPROFILE","APPDATA","LOCALAPPDATA","PROGRAMFILES","PROGRAMFILES(X86)"}
        env={k:v for k,v in os.environ.items() if k.upper() in allowed}
        env.update({"PYTHONDONTWRITEBYTECODE":"1","DATABASE_URL":"postgresql://postgres:synthetic-recorder-only@127.0.0.1:55439/recorder?sslmode=disable",
            "SPORTS_CAVE_AUTH_SECRET":"synthetic-recorder-preview-64cdf0b0-only",
            "SPORTS_CAVE_ADMIN_EMAIL":"recorder-preview@example.invalid","SPORTS_CAVE_ADMIN_PASSWORD":"RecorderPreview-Only-2026",
            "SPORTS_CAVE_ADMIN_NAME":"Recorder preview admin","SPORTS_CAVE_DB_PATH":str(root/"synthetic.db"),
            "STREAMLIT_BROWSER_GATHER_USAGE_STATS":"false","STREAMLIT_SERVER_FILE_WATCHER_TYPE":"none",
            "TEMP":str(root),"TMP":str(root),"PYTHONPATH":str(repo)})
        return subprocess.call([sys.executable,str(Path(__file__).resolve()),"--serve","--root",str(root),"--port",str(args.port)],cwd=repo,env=env)
    from urllib.parse import urlsplit
    dsn=urlsplit(os.environ.get("DATABASE_URL",""))
    if dsn.hostname!="127.0.0.1" or dsn.port!=55439 or dsn.path!="/recorder":
        raise SystemExit("Preview requires the isolated recorder database.")
    import dotenv
    dotenv.load_dotenv=lambda *a,**k:False
    import socket
    original=socket.socket.connect
    def local_connect(sock,address):
        if isinstance(address,tuple) and address[0] not in {"127.0.0.1","localhost","::1"}:
            raise RuntimeError("External I/O is disabled in the recorder preview.")
        return original(sock,address)
    socket.socket.connect=local_connect
    def audit(event,items):
        if event in {"subprocess.Popen","os.system","os.posix_spawn","os.fork"}:
            raise RuntimeError("Background jobs are disabled in the recorder preview.")
        if event=="open" and isinstance(items[0],(str,bytes)):
            mode=items[1] or ""
            flags=items[2] if len(items)>2 else 0
            if any(c in str(mode) for c in "wax+") or (isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT)):
                path=Path(os.fsdecode(items[0])).resolve()
                if path!=root and root not in path.parents and str(path).lower() not in {"nul",os.devnull.lower()}:
                    raise RuntimeError("Preview writes must stay in isolated storage.")
    sys.addaudithook(audit)
    import psycopg
    from psycopg.rows import dict_row
    def connect():return psycopg.connect(os.environ["DATABASE_URL"],row_factory=dict_row)
    with connect() as conn:
        conn.execute((repo/"supabase/migrations/20261020001929_task_recorder_device_relay.sql").read_text())
    import os_accounts
    accounts=os_accounts.DEFAULT_STORE
    accounts.ensure_schema()
    user=accounts.find_user_by_login("recorder-preview@example.invalid")
    if not user:
        user=accounts.create_user(username="recorder-preview",email="recorder-preview@example.invalid",
            display_name="Recorder preview admin",password_hash=os_accounts.hash_password("RecorderPreview-Only-2026"),role="admin")
    from starlette.routing import Route
    from streamlit.web.server.starlette import App
    from task_recorder.hosted_api import ROUTES
    from auth_cookie_cleanup import ROUTES as CLEANUP
    app=App(str(repo/"app.py"),routes=[Route(path,fn,methods=list(methods)) for path,fn,methods in (*ROUTES,*CLEANUP)])
    # Real app.py sign-in/sidebar/page and exact production API handlers.
    import uvicorn
    print("Isolated OS recorder preview: http://127.0.0.1:"+str(args.port)+"/?page=task_recorder",flush=True)
    uvicorn.run(app,host="127.0.0.1",port=args.port,log_level="warning",access_log=False)

if __name__=="__main__":raise SystemExit(main())
