"""Immutable container controller: synthetic PostgreSQL, Streamlit, raster-only browser."""
import base64
import json
import os
import re
from pathlib import Path
import subprocess
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from playwright.sync_api import sync_playwright
import psycopg
from inspection import INSPECT, TARGETS
from page_catalog import pages

def synthetic_cookie_cleanup(route):
    """Plain Streamlit lacks the OS cookie router; emulate only its empty cleanup.

    The actual application still validates credentials and creates its own cookie.
    This handler is confined to the network-isolated browser's exact loopback URL.
    """
    if route.request.url != "http://127.0.0.1:8501/api/os/auth/clear-cookie" or route.request.method != "POST":
        route.abort()
        return
    route.fulfill(status=204, headers={"Cache-Control": "no-store"}, body="")

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
        "--server.fileWatcherType=none","--browser.gatherUsageStats=false",
        "--server.disconnectedSessionTTL=10"],
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
    context.route("http://127.0.0.1:8501/api/os/auth/clear-cookie", synthetic_cookie_cleanup)
    page=context.new_page()
    page.goto("http://127.0.0.1:8501")
    page.wait_for_function("() => !!document.querySelector('.sc-login-title')",timeout=20000)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            try:
                length=int(self.headers.get("Content-Length","0"))
                if not 0<length<12000: raise ValueError("Oversized event")
                data=json.loads(self.rfile.read(length))
                op=data.get("action");inspection=None
                if op=='health':
                    body=json.dumps({'alive':app.poll() is None and not page.is_closed(),'synthetic':True}).encode()
                    self.send_response(200);self.send_header('Content-Length',str(len(body)))
                    self.end_headers();self.wfile.write(body)
                    return
                if op=="reload-source":
                    # New Streamlit session re-executes entry.py/runpy against updated source.
                    # Keep the verified process, browser, synthetic DB and authentication cookies.
                    page.evaluate("() => document.activeElement?.blur()")
                    page.keyboard.press("r")
                    page.locator('[data-testid="stAppViewContainer"]').wait_for(timeout=10000)
                elif op=="navigate":
                    from urllib.parse import quote
                    selected=next((p for p in pages(Path("/tmp/source")) if p["key"]==data.get("page")),None)
                    if not selected:raise ValueError("Unknown OS page")
                    if selected["key"]=="__signin__":context.clear_cookies()
                    elif page.get_by_placeholder("Username or email",exact=True).is_visible():
                        page.get_by_placeholder("Username or email",exact=True).fill("preview@example.invalid")
                        page.get_by_placeholder("Password",exact=True).fill("StudioOnly-2026")
                        page.get_by_role("button",name="Sign in",exact=True).click()
                        page.get_by_placeholder("Username or email",exact=True).wait_for(state="hidden",timeout=10000)
                    page.goto("http://127.0.0.1:8501/?page="+quote(selected["route"]),wait_until="domcontentloaded")
                    page.locator('[data-testid="stAppViewContainer"]').wait_for(timeout=10000)
                elif op=="inspect":
                    x,y=data.get("x"),data.get("y")
                    if type(x) is not int or type(y) is not int or not 0<=x<page.viewport_size["width"] or not 0<=y<page.viewport_size["height"]:raise ValueError("Coordinates")
                    inspection=page.evaluate(INSPECT,{"x":x,"y":y})
                elif op=="login-synthetic":
                    page.get_by_placeholder("Username or email",exact=True).fill("preview@example.invalid")
                    page.get_by_placeholder("Password",exact=True).fill("StudioOnly-2026")
                    page.get_by_role("button",name="Sign in",exact=True).click()
                    page.get_by_placeholder("Username or email",exact=True).wait_for(state="hidden",timeout=10000)
                    page.get_by_text(re.compile(r"^Synthetic Preview Admin(?:\s*\u00b7\s*Admin)?$")).wait_for(timeout=10000)
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
                    widths={"desktop":1280,"tablet":820,"mobile":390}
                    if data.get("mode") not in widths:raise ValueError("Viewport")
                    page.set_viewport_size({"width":widths[data["mode"]],"height":900})
                elif op=="refresh":
                    page.reload()
                elif op!="frame":
                    raise ValueError("Unknown event")
                # Bounded event settling; no unattended screenshot loop.
                page.wait_for_timeout(200)
                if op in {"frame","reload-source","navigate","login-synthetic","refresh"}:
                    # Cookie restoration may schedule a second Streamlit rerun. Wait for
                    # bounded, stable content instead of returning a half-rendered frame.
                    previous=None;stable=0
                    for _ in range(24):
                        text=page.locator("body").inner_text()
                        ready=bool(text.strip()) and page.locator('[data-testid="stMainBlockContainer"]').count()>0
                        running=page.locator('[data-testid="stStatusWidget"]').filter(has_text="Running").count()>0
                        stable=stable+1 if ready and not running and text==previous else 0
                        if stable>=3:break
                        previous=text;page.wait_for_timeout(200)
                    if stable<3:raise RuntimeError("OS screen is still loading. Refresh the preview; no source was discarded.")
                result={"image":base64.b64encode(page.screenshot(type="jpeg",quality=80)).decode(),
                        "text":("\n".join(f.locator("body").inner_text(timeout=1500)[:5000] for f in page.frames if f.url.startswith(("http://127.0.0.1:8501","about:srcdoc"))))[:12000],
                        "width":page.viewport_size["width"],"height":page.viewport_size["height"],
                        "login_visible":page.get_by_placeholder("Username or email",exact=True).is_visible(),
                        "synthetic":True,"inspect_targets":page.evaluate(TARGETS)}
                if inspection is not None:result["inspection"]=inspection
                body=json.dumps(result).encode()
                self.send_response(200)
            except Exception as exc:
                body=json.dumps({"error":str(exc)[:1000]}).encode()
                self.send_response(400)
            self.send_header("Content-Length",str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    HTTPServer(("127.0.0.1",8877),Handler).serve_forever()
