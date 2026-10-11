"""Immutable container controller: synthetic PostgreSQL, Streamlit, raster-only browser."""
import base64
import json
import os
from pathlib import Path
import subprocess
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from playwright.sync_api import sync_playwright
import psycopg

ROOT=Path("/tmp")
os.environ.update({"OPENBLAS_NUM_THREADS":"1","OMP_NUM_THREADS":"1","MKL_NUM_THREADS":"1","HOME":"/tmp","XDG_CACHE_HOME":"/tmp/cache","TMPDIR":"/tmp",
    "DATABASE_URL":"postgresql://studio@127.0.0.1:55432/studio?sslmode=disable",
    "SPORTS_CAVE_ADMIN_EMAIL":"preview@example.invalid","SPORTS_CAVE_ADMIN_PASSWORD":"StudioOnly-2026",
    "SPORTS_CAVE_ADMIN_NAME":"Synthetic Preview Admin","SPORTS_CAVE_AUTH_SECRET":"synthetic-local-only",
    "STREAMLIT_BROWSER_GATHER_USAGE_STATS":"false"})
ROOT.joinpath("cache").mkdir(exist_ok=True)
postgres=next(Path("/usr/lib/postgresql").glob("*/bin"))
subprocess.run([str(postgres/"initdb"),"-D","/tmp/pg","-U","studio","--auth=trust","--no-locale","--encoding=UTF8"],
               check=True,stdout=subprocess.DEVNULL)
db=subprocess.Popen([str(postgres/"postgres"),"-D","/tmp/pg","-p","55432","-k","/tmp",
                     "-c","listen_addresses=127.0.0.1","-c","max_connections=20"],
                    stdout=open("/tmp/postgres.log","w"),stderr=subprocess.STDOUT)
for _ in range(100):
    try:
        with psycopg.connect("postgresql://studio@127.0.0.1:55432/postgres?sslmode=disable",autocommit=True) as conn:
            conn.execute("CREATE DATABASE studio")
        break
    except psycopg.OperationalError:
        time.sleep(.1)
else:
    raise RuntimeError("Synthetic PostgreSQL failed.")
with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    conn.execute("CREATE TABLE studio_marker (label text NOT NULL)")
    conn.execute("INSERT INTO studio_marker VALUES ('synthetic-only')")
import urllib.request
def start_app():
    process=subprocess.Popen(["python","-B","-m","streamlit","run","/opt/studio/entry.py",
        "--server.address=127.0.0.1","--server.port=8501","--server.headless=true",
        "--server.fileWatcherType=none","--browser.gatherUsageStats=false"],
        cwd="/tmp/source",stdout=open("/tmp/application.log","w"),stderr=subprocess.STDOUT)
    for _ in range(100):
        try:
            assert urllib.request.urlopen("http://127.0.0.1:8501/_stcore/health",timeout=1).status==200
            break
        except Exception:
            if process.poll() is not None:
                raise RuntimeError("Preview application startup failed.")
            time.sleep(.1)
    else:
        raise RuntimeError("Preview application startup timed out.")
    return process
app=start_app()
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,chromium_sandbox=True,
        args=["--disable-background-networking","--disable-component-update"])
    context=browser.new_context(viewport={"width":1280,"height":900},accept_downloads=False)
    page=context.new_page()
    page.goto("http://127.0.0.1:8501")
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            try:
                length=int(self.headers.get("Content-Length","0"))
                if not 0<length<12000: raise ValueError("Oversized event")
                data=json.loads(self.rfile.read(length))
                op=data.get("action")
                if op=="reload-source":
                    global app
                    app.terminate()
                    try: app.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        app.kill(); app.wait(timeout=5)
                    app=start_app()
                    page.reload()
                    page.get_by_placeholder("Username or email",exact=True).wait_for(timeout=10000)
                elif op=="login-synthetic":
                    page.get_by_placeholder("Username or email",exact=True).fill("preview@example.invalid")
                    page.get_by_placeholder("Password",exact=True).fill("StudioOnly-2026")
                    page.get_by_role("button",name="Sign in",exact=True).click()
                    page.wait_for_timeout(1000)
                elif op=="click":
                    x,y=int(data["x"]),int(data["y"])
                    if not 0<=x<1600 or not 0<=y<1200: raise ValueError("Coordinates")
                    page.mouse.click(x,y)
                elif op=="text":
                    value=data["text"]
                    if not isinstance(value,str) or len(value)>2000: raise ValueError("Text size")
                    page.keyboard.insert_text(value)
                elif op=="key":
                    key=data["key"]
                    if key not in {"Enter","Tab","Backspace","Escape","ArrowDown","ArrowUp"}: raise ValueError("Key")
                    page.keyboard.press(key)
                elif op=="scroll":
                    page.mouse.wheel(0,max(-900,min(900,int(data["delta"]))))
                elif op=="size":
                    page.set_viewport_size({"width":390 if data["mode"]=="mobile" else 1280,"height":900})
                elif op=="refresh":
                    page.reload()
                elif op!="frame":
                    raise ValueError("Unknown event")
                # Bounded event settling; no unattended screenshot loop.
                page.wait_for_timeout(300)
                result={"image":base64.b64encode(page.screenshot(type="jpeg",quality=80)).decode(),
                        "text":page.locator("body").inner_text()[:12000],
                        "width":page.viewport_size["width"],"height":page.viewport_size["height"],
                        "synthetic":True}
                body=json.dumps(result).encode()
                self.send_response(200)
            except Exception as exc:
                body=json.dumps({"error":str(exc)[:1000]}).encode()
                self.send_response(400)
            self.send_header("Content-Length",str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    HTTPServer(("127.0.0.1",8877),Handler).serve_forever()
