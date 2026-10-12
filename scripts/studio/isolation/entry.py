"""Container-only synthetic startup. Invoked after policy probes pass."""
import importlib.abc
import os
from pathlib import Path
import runpy
import sys

class ForbiddenRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        name=fullname.rsplit(".",1)[-1]
        if "worker" in name or "webhook" in name or name in {"run_migrations","support_email_idle","sports_cave_server"}:
            raise ImportError("Preview blocks worker/webhook/migration module: "+fullname)

sys.meta_path.insert(0,ForbiddenRuntime())
os.chdir("/tmp/source")
sys.path.insert(0,"/tmp/source")
# Supplemental transport adapters; Docker network/filesystem restrictions are the boundary.
import requests
def mock_request(self, method, url, **kwargs):
    from urllib.parse import urlparse
    host=urlparse(str(url)).hostname or ""
    if host in {"127.0.0.1","localhost"}:
        raise RuntimeError("Application HTTP transport is disabled in synthetic preview.")
    if method.upper() in {"GET","HEAD"} and (
        host.endswith(".myshopify.com") or host in {"graph.facebook.com","api.resend.com"}):
        result=requests.Response()
        result.status_code=200
        result._content=b'{"data":[],"products":[],"customers":[],"orders":[],"synthetic":true}'
        result.headers["Content-Type"]="application/json"
        result.url=url
        return result
    raise RuntimeError("External integration action blocked in synthetic preview.")
requests.sessions.Session.request=mock_request

# No application-launched subprocesses; Streamlit/browser/DB started by immutable controller.
def audit(event,args):
    if event in {"subprocess.Popen","os.system","os.posix_spawn","os.fork","os.forkpty","pty.spawn"}:
        raise RuntimeError("Application child jobs disabled in preview.")
sys.addaudithook(audit)
# Preview-only cache invalidation for the explicit frontend editor allowlist.
# These modules stay cached in the long-lived Streamlit process after a browser reload.
# Never change production cache behaviour or clear data/application caches here.
for module_name,function_name in (("top_bar","_component_source"),("session_recovery","_source")):
    module=sys.modules.get(module_name)
    cached=getattr(module,function_name,None) if module else None
    if cached is not None and hasattr(cached,"cache_clear"):
        cached.cache_clear()
runpy.run_path("/tmp/source/app.py",run_name="__main__")
