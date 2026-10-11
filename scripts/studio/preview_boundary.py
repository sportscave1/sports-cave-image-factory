"""Repeatable inert Docker security preflight; never starts Sports Cave OS."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

import drafts
import studio

def docker(*args, timeout=60, check=True):
    result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError("Docker command failed: " + result.stderr.strip()[:1000])
    return result

def hardened(image, name, task):
    return ["--name", name, "--label", "sports-cave-studio.task="+task,
            "--network", "none", "--read-only", "--user", "65532:65532",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
            "--pids-limit", "64", "--memory", "256m", "--cpus", "1",
            "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=16777216,uid=65532,gid=65532,mode=700",
            "--env", "HOME=/tmp", "--env", "HTTP_PROXY=", "--env", "HTTPS_PROXY=",
            "--env", "ALL_PROXY=", "--env", "NO_PROXY=", "--env", "http_proxy=",
            "--env", "https_proxy=", "--env", "all_proxy=", "--env", "no_proxy=", image]

def validate(config, image, task):
    h, c = config["HostConfig"], config["Config"]
    checks = {
        "image_pinned": config["Image"] == image,
        "network_none": h["NetworkMode"] == "none",
        "read_only": h["ReadonlyRootfs"] is True,
        "non_root": c["User"] == "65532:65532",
        "cap_drop_all": h["CapDrop"] == ["ALL"] and not h.get("CapAdd"),
        "no_new_privileges": any(x in ("no-new-privileges", "no-new-privileges:true") for x in h["SecurityOpt"]),
        "default_seccomp": not any("unconfined" in x for x in h["SecurityOpt"]),
        "not_privileged": not h["Privileged"],
        "private_pid_ipc": not h["PidMode"] and h["IpcMode"] == "private",
        "no_bind_or_volume_mounts": not config["Mounts"] and not h.get("Binds"),
        "no_devices": not h.get("Devices") and not h.get("DeviceRequests"),
        "no_published_ports": not h.get("PortBindings") and not h.get("PublishAllPorts"),
        "no_extra_hosts": not h.get("ExtraHosts"),
        "bounded_resources": h["PidsLimit"] == 64 and h["Memory"] == 268435456 and h["NanoCpus"] == 1000000000,
        "ownership_label": c["Labels"].get("sports-cave-studio.task") == task,
        "tmpfs_only": list(h.get("Tmpfs", {})) == ["/tmp"],
    }
    allowed = {"PATH","LANG","PYTHON_VERSION","PYTHON_SHA256","GPG_KEY","HOME",
               "HTTP_PROXY","HTTPS_PROXY","ALL_PROXY","NO_PROXY",
               "http_proxy","https_proxy","all_proxy","no_proxy"}
    entries = dict(e.split("=",1) for e in c["Env"])
    checks["environment_allowlist"] = not (entries.keys() - allowed)
    checks["proxies_empty"] = all(not v for k,v in entries.items() if k.lower().endswith("_proxy"))
    if not all(checks.values()):
        raise RuntimeError("Container policy rejected: " + ", ".join(k for k,v in checks.items() if not v))
    return checks

def run(home, task, owner):
    with studio.locked(home) as file:
        drafts.assigned(studio.read(file),task,owner)
    context = json.loads(docker("context","inspect").stdout)[0]
    endpoint = context["Endpoints"]["docker"]["Host"]
    if not endpoint.startswith("npipe://") or docker("info","--format","{{.OSType}}").stdout.strip() != "linux":
        raise RuntimeError("Only the verified local Windows Linux-container daemon is allowed.")
    image = json.loads(docker("image","inspect","sports-cave-studio-probe:"+task).stdout)[0]["Id"]
    prefix = "sc-studio-probe-" + uuid.uuid4().hex[:12]
    owned = []
    started = time.monotonic()
    try:
        # Inert off-runtime positive control, no host port or file mounts.
        canary = prefix+"-canary"
        docker("create","--name",canary,"--label","sports-cave-studio.task="+task,
               "--network","bridge","--read-only","--cap-drop","ALL",
               "--security-opt","no-new-privileges:true","--pids-limit","32",
               "--memory","64m","--entrypoint","python",image,
               "-B","-m","http.server","8123","--bind","0.0.0.0","--directory","/tmp")
        owned.append(canary)
        docker("start",canary)
        info=json.loads(docker("inspect",canary).stdout)[0]
        address=info["NetworkSettings"]["Networks"]["bridge"]["IPAddress"]
        control = prefix+"-control"
        docker("create","--name",control,"--label","sports-cave-studio.task="+task,
               "--network","bridge","--read-only","--cap-drop","ALL",
               "--security-opt","no-new-privileges:true","--entrypoint","python",image,
               "-B","-c","import urllib.request; assert urllib.request.urlopen('http://"+address+":8123',timeout=3).status == 200; print('positive-control-passed')")
        owned.append(control)
        positive=docker("start","-a",control)
        if "positive-control-passed" not in positive.stdout:
            raise RuntimeError("Off-runtime canary was not reachable by the positive control.")
        results=[]
        for i in range(2):
            name=prefix+"-"+str(i)
            docker("create",*hardened(image,name,task),address)
            owned.append(name)
            policy=validate(json.loads(docker("inspect",name).stdout)[0],image,task)
            result=docker("start","-a",name,timeout=90,check=False)
            if not result.stdout.strip():
                raise RuntimeError("Probe failed before producing evidence: " + result.stderr[:2000])
            probe=json.loads(result.stdout)
            results.append({"policy":policy,"probe":probe,"exit_code":result.returncode})
            if not probe["passed"] or result.returncode:
                raise RuntimeError("Isolation negative probe failed: "+json.dumps(probe))
        evidence={"task":task,"owner":owner,"image":image,"positive_control":True,
                  "results":results,"seconds":round(time.monotonic()-started,3),
                  "application_started":False,"phase2_verified":False,
                  "probe_sha256":hashlib.sha256((Path(__file__).parent/"isolation/probe.py").read_bytes()).hexdigest()}
        studio.atomic(Path(home)/".studio"/"phase2-container-probes.json",evidence)
        return evidence
    finally:
        # Only exact containers created by this invocation; never prune.
        for name in reversed(owned):
            result=docker("inspect",name,check=False)
            if result.returncode==0 and json.loads(result.stdout)[0]["Config"]["Labels"].get("sports-cave-studio.task")==task:
                docker("rm","-f",name)

if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--home",type=Path,default=studio.DEFAULT_HOME)
    p.add_argument("--id",required=True)
    p.add_argument("--owner",required=True)
    a=p.parse_args()
    print(json.dumps(run(a.home,a.id,a.owner),indent=2))
