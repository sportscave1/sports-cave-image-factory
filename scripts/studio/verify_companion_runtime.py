"""Explicit local acceptance: kills ONLY this task's authenticated test companion worker."""
import argparse,json,subprocess,sys,time,urllib.request
from pathlib import Path
import psutil
import companion,studio
from device_trust import protect

def verify(home,task,owner):
    root,cfg=companion.config(home,task,owner)
    origin="http://127.0.0.1:"+str(cfg["port"])
    def session():
        d=json.loads((root/"session.json").read_text())
        return d,protect(bytes.fromhex(d["protected"]),True).decode()
    def request(token,action=None):
        data=json.dumps({"action":action}).encode() if action else None
        req=urllib.request.Request(origin+("/api/action" if action else "/api/state"),data=data,headers={"X-Studio-Token":token,**({"Content-Type":"application/json"} if data else {})})
        with urllib.request.urlopen(req,timeout=4) as r:return json.load(r)
    d,token=session()
    assert request(token)["task"]["id"]==task
    worker=psutil.Process(d["pid"])
    command=worker.cmdline()
    assert "worker" in command and task in command and owner in command and str(Path(companion.__file__).resolve()) in command
    chain=[worker]+worker.parents()
    own=[p for p in chain if task in p.cmdline() and str(Path(companion.__file__).resolve()) in p.cmdline()]
    supervisor=next(p for p in own if "supervise" in p.cmdline())
    before=sum(sum(p.cpu_times()[:2]) for p in own)
    started=time.monotonic();time.sleep(20)
    elapsed=time.monotonic()-started
    cpu=sum(sum(p.cpu_times()[:2]) for p in own)-before
    memory=sum(p.memory_info().rss for p in own)
    # Attempt duplicate start; established listener and process must remain the same.
    subprocess.run([sys.executable,"-B",str(Path(companion.__file__).resolve()),"start","--home",str(home),"--id",task,"--owner",owner],check=True,capture_output=True)
    time.sleep(2)
    assert session()[0]["pid"]==worker.pid
    assert request(token)["task"]["owner"]==owner
    worker.terminate();worker.wait(5)
    recovered=None
    for _ in range(30):
        time.sleep(.5)
        try:
            next_d,next_token=session()
            if next_d["pid"]!=d["pid"] and request(next_token)["task"]["id"]==task:
                recovered=next_d;break
        except (OSError,ValueError):pass
    assert recovered,"Automatic worker restart failed"
    assert next_token!=token
    request(next_token,"close")
    supervisor.wait(8)
    result={"task":task,"owner":owner,"verified_at":studio.now(),"stable_origin":origin,"duplicate_prevented":True,"crash_recovered":True,"bootstrap_rotated":True,"intentional_stop_not_restarted":True,"idle_sample_seconds":elapsed,"cpu_seconds":cpu,"cpu_one_core_percent":100*cpu/elapsed,"combined_rss_bytes":memory,"processes_including_windows_launchers":len(own),"windows_logon_test":"not run; startup not enabled","hosted_browser":"not exercised by this local process check"}
    studio.atomic(home/".studio"/("companion-v5-"+task+".json"),result)
    print(json.dumps(result))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--home",type=Path,default=studio.DEFAULT_HOME);p.add_argument("--id",required=True);p.add_argument("--owner",required=True)
    a=p.parse_args();verify(a.home,a.id,a.owner)
