"""Explicit, opt-in local acceptance run. Starts only registered synthetic previews."""
import base64
import http.client
import json
from pathlib import Path
import threading
import time
import draft_ui
import drafts
import studio
from preview_boundary import docker

HOME=Path("C:/Dev/SportsCaveWorktrees")
TASKS=["20261011-c24ca137","20261011-preview-check"]
OWNER="me/phase2"

def request(server,action,**values):
    conn=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=100)
    data=json.dumps({"action":action,**values})
    conn.request("POST","/api/action",data,{"X-Studio-Token":server.token,"Content-Type":"application/json"})
    response=conn.getresponse()
    body=json.loads(response.read())
    conn.close()
    if response.status!=200:
        raise RuntimeError(str(body))
    return body

def query(name,sql):
    code="import psycopg,json; c=psycopg.connect('postgresql://studio@127.0.0.1:55432/studio?sslmode=disable'); q=c.execute("+repr(sql)+"); print(json.dumps(q.fetchall() if q.description else [])); c.commit()"
    return json.loads(docker("exec",name,"python","-B","-c",code).stdout)

def main():
    if not any(d["task_id"]==TASKS[1] for d in drafts.listing(HOME,OWNER)):
        drafts.new(HOME,TASKS[1],OWNER,"Synthetic preview acceptance")
    servers=[draft_ui.DraftServer(HOME,t,OWNER,idle_seconds=300) for t in TASKS]
    threads=[]
    report={"phase2_verified":False,"application_started":True,"started_at":studio.now()}
    before=[studio.snapshot(Path(s.state()["task"]["worktree_path"])) for s in servers]
    try:
        for s in servers:
            th=threading.Thread(target=s.run,daemon=True)
            th.start(); threads.append(th)
        report["independent_ports"]=[s.server_port for s in servers]
        assert len(set(report["independent_ports"]))==2
        starts=[]
        for i,s in enumerate(servers):
            t=time.monotonic()
            request(s,"start-preview")
            starts.append(round(time.monotonic()-t,3))
            frame=request(s,"preview-event",event={"action":"login-synthetic"})
            frame=request(s,"preview-event",event={"action":"frame"})
            assert "Synthetic Preview Admin" in frame["text"] and "Traceback:" not in frame["text"],frame["text"][:1500]
            (HOME/".studio"/("phase2-preview-"+str(i)+".jpg")).write_bytes(base64.b64decode(frame["image"]))
        report["start_seconds"]=starts
        a,b=[s.preview_runtime.name for s in servers]
        query(a,"INSERT INTO studio_marker VALUES ('first-preview-only')")
        assert query(b,"SELECT label FROM studio_marker")==[["synthetic-only"]]
        report["synthetic_databases_independent"]=True
        report["image_policy_probes"]=[s.preview_runtime.evidence for s in servers]
        # No application worker/migration imports or Python child jobs permitted.
        code="""import pathlib,sys,json,importlib,subprocess
source=pathlib.Path('/opt/studio/entry.py').read_text(encoding="utf-8-sig").rsplit('runpy.run_path(',1)[0]
exec(compile(source,'preview-guards','exec'))
checks={}
for name in ['run_migrations','sports_cave_server','support_email_worker','support_email_idle','webhooks']:
    try: importlib.import_module(name); checks[name]=False
    except ImportError: checks[name]=True
try: subprocess.run(['python','-c','print(1)']); checks['application_child_job']=False
except RuntimeError: checks['application_child_job']=True
import requests
checks['shopify_read_mock']=requests.get('https://synthetic.myshopify.com/products.json').json()['synthetic']
checks['meta_read_mock']=requests.get('https://graph.facebook.com/ads').json()['synthetic']
checks['resend_read_mock']=requests.get('https://api.resend.com/emails').json()['synthetic']
for url in ['https://synthetic.myshopify.com/products.json','https://graph.facebook.com/ads','https://api.resend.com/emails','https://unknown.invalid/write']:
    try: requests.post(url,json={}); checks[url]=False
    except RuntimeError: checks[url]=True
print(json.dumps(checks))
"""
        guards=json.loads(docker("exec",a,"python","-B","-c",code).stdout)
        assert all(guards.values()),guards
        report["worker_and_provider_guards"]=guards
        from preview_runtime import Preview
        try:
            Preview(HOME,TASKS[0],OWNER).start()
        except RuntimeError:
            report["duplicate_workspace_denied"]=True
        else: raise AssertionError("Duplicate preview started.")
        try:
            Preview(HOME,TASKS[0],"other-owner").start()
        except RuntimeError:
            report["wrong_owner_denied"]=True
        else: raise AssertionError("Wrong owner started preview.")
        mobile=request(servers[0],"preview-event",event={"action":"size","mode":"mobile"})
        assert mobile["width"]==390
        (HOME/".studio/phase2-mobile.jpg").write_bytes(base64.b64decode(mobile["image"]))
        report["mobile_frame"]=True
        report["container_stats"]=docker("stats","--no-stream","--format","{{.Name}} {{.MemUsage}} {{.PIDs}}",a,b).stdout
        request(servers[0],"restart-preview")
        assert servers[0].preview_runtime.name!=a
        assert query(servers[0].preview_runtime.name,"SELECT label FROM studio_marker")==[["synthetic-only"]]
        report["restart_resets_only_synthetic_runtime"]=True
        assert "Synthetic Preview Admin" in request(servers[1],"preview-event",event={"action":"frame"})["text"]
        servers[0].idle_seconds=.1
        threads[0].join(5)
        assert not threads[0].is_alive() and servers[0].preview_runtime.name is None
        report["idle_shutdown"]=True
        request(servers[1],"stop-preview")
        assert servers[1].preview_runtime.name is None
        report["stop"]=True
        after=[studio.snapshot(Path(s.state()["task"]["worktree_path"])) for s in servers]
        assert before==after
        report["worktree_contents_preserved"]=True
        report["functional_checks_passed"]=True
        report["phase2_verified"]=True
        report["scope"]="Actual Docker-contained Streamlit app with synthetic database and raster-only browser; module-specific populated fixtures and production route parity are not claimed."
    except Exception as e:
        report["failure"]=str(e)
        raise
    finally:
        for s in servers:
            s.stopping=True
        for th in threads:
            th.join(10)
        studio.atomic(HOME/".studio/phase2-preview-acceptance.json",report)
        print(json.dumps(report,indent=2))
if __name__=="__main__":
    main()
