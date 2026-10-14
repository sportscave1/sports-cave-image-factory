"""Opt-in hidden Windows supervisor. No OS configuration changes from this module."""
import argparse
import contextlib
import json
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
import studio
from device_trust import protect, digest
from draft_ui import DraftServer

@contextlib.contextmanager
def instance_lock(path):
    import msvcrt
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b", buffering=0) as handle:
        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b"0"); handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError("Companion already running; use Open, not another process.")
        try:
            yield
        finally:
            handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

def paths(home, task, owner):
    root = home / ".studio" / "companions" / digest(task+owner)
    root.mkdir(parents=True, exist_ok=True)
    return root

def validate(home, task, owner):
    with studio.locked(home) as file:
        registry = studio.read(file)
        assigned = studio.task_by_id(registry, task, owner)
        studio.identity(registry, assigned)
    return assigned

def config(home, task, owner):
    validate(home, task, owner)
    root = paths(home, task, owner)
    # Allocate once under registry lock; never reuse another task's fixed port.
    with studio.locked(home):
        file = root / "config.json"
        if file.exists():
            result = json.loads(file.read_text())
            if result["task"] != task or result["owner"] != owner:
                raise ValueError("Companion assignment changed.")
            return root, result
        import socket
        used = {json.loads(p.read_text())["port"] for p in (home/".studio"/"companions").glob("*/config.json")}
        for port in range(18761, 18861):
            if port in used:
                continue
            try:
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            result = {"task": task, "owner": owner, "port": port}
            studio.atomic(file, result)
            return root, result
        raise RuntimeError("No free companion port; no configuration replaced.")

def worker(home, task, owner):
    root, cfg = config(home, task, owner)
    server = DraftServer(home, task, owner, persistent=True, port=cfg["port"])
    studio.atomic(root/"session.json", {"protected": protect(server.token.encode()).hex(), "pid": os.getpid(), "parent_pid": os.getppid()})
    import auto_editions_local
    auto_editions_local.restore_host()
    try:
        server.run()
    finally:
        # Normal Stop is distinct from a crash; supervisor must not resurrect it.
        if server.stopping:
            (root/"stopped").touch()

def recover_previews(home, owner, exited_pid):
    # Only the exact exited child process's leases may be recovered. No task-wide rm.
    import preview_boundary as boundary
    with studio.locked(home) as file:
        registry=studio.read(file)
        leases=registry.get("preview_leases",{})
        targets=[(task,dict(lease)) for task,lease in leases.items() if lease.get("pid")==exited_pid and lease.get("owner")==owner]
    for task,lease in targets:
        validate(home,task,owner)
        name=lease.get("container")
        if name:
            context=json.loads(boundary.docker("context","inspect").stdout)[0]
            if not context["Endpoints"]["docker"]["Host"].startswith("npipe://"):
                raise RuntimeError("Remote Docker recovery forbidden.")
            info=json.loads(boundary.docker("inspect",name).stdout)[0]
            if info["Config"]["Labels"].get("sports-cave-studio.task")!=task:
                raise RuntimeError("Recovery container identity mismatch.")
            boundary.docker("rm","-f",name)
        with studio.locked(home) as file:
            registry=studio.read(file)
            current=registry.get("preview_leases",{}).get(task,{})
            if current.get("id")==lease["id"] and current.get("pid")==exited_pid:
                del registry["preview_leases"][task]
                studio.atomic(file,registry)

def existing_worker(root, cfg, task):
    """Adopt only a responding worker proving the current DPAPI bootstrap."""
    import ctypes
    import urllib.request
    from ctypes import wintypes
    record_path=root/"session.json"
    if not record_path.exists():return None
    record=json.loads(record_path.read_text())
    kernel=ctypes.WinDLL("kernel32",use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    kernel.WaitForSingleObject.restype=wintypes.DWORD
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.OpenProcess(0x00100000,False,record["pid"])
    if not handle:return None
    try:
        if kernel.WaitForSingleObject(handle,0)!=258:return None
        token=protect(bytes.fromhex(record["protected"]),True).decode()
        req=urllib.request.Request("http://127.0.0.1:"+str(cfg["port"])+"/api/state",headers={"X-Studio-Token":token})
        with urllib.request.urlopen(req,timeout=3) as response:
            if json.load(response)["task"]["id"]!=task:return None
        class Adopted:
            pid=record["pid"]
            def wait(self):
                try:
                    if kernel.WaitForSingleObject(handle,0xffffffff)!=0:raise RuntimeError("Worker wait failed.")
                    return 1 # A clean stop is identified by the local stopped marker.
                finally:kernel.CloseHandle(handle)
        adopted=Adopted()
        handle_owned=True
        return adopted
    except (OSError,ValueError):return None
    finally:
        if not locals().get("handle_owned"):kernel.CloseHandle(handle)

def supervise(home, task, owner):
    root, cfg = config(home, task, owner)
    with instance_lock(root/"instance.lock"):
        (root/"stopped").unlink(missing_ok=True)
        failures = 0
        while failures < 5:
            started = time.monotonic()
            child = existing_worker(root, cfg, task)
            if child is None:
                child = subprocess.Popen([sys.executable, "-B", str(Path(__file__).resolve()), "worker", "--home", str(home), "--id", task, "--owner", owner],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW)
            code = child.wait()
            record=json.loads((root/"session.json").read_text()) if (root/"session.json").exists() else {}
            actual_pid=record.get("pid") if record.get("parent_pid")==child.pid or record.get("pid")==child.pid else child.pid
            recover_previews(home, owner, actual_pid)
            if (root/"stopped").exists():
                return
            failures = 1 if time.monotonic()-started > 60 else failures+1
            studio.atomic(root/"recovery.json", {"exit_code":code,"consecutive_failures":failures,"at":studio.now()})
            time.sleep(min(2**failures,30))
        raise RuntimeError("Repeated startup failure; inspect port/registry/ownership. No forced takeover.")

def browser_command(browser):
    """Resolve only the two explicitly supported Windows browser applications."""
    import winreg
    name={"chrome":"chrome.exe","edge":"msedge.exe"}.get(browser)
    if not name:raise ValueError("Choose Chrome or Edge.")
    key=r"Software\Microsoft\Windows\CurrentVersion\App Paths"+chr(92)+name
    for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY,winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive,key,0,winreg.KEY_READ|view) as opened:
                    value=winreg.QueryValueEx(opened,None)[0]
                executable=Path(value.strip('"'))
                if executable.is_file() and executable.name.lower()==name:return str(executable)
            except OSError:pass
    raise RuntimeError(browser.title()+" is not registered on this Windows computer. No browser installed or replaced.")

def main():
    global error_path
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["start","resume","supervise","watch","worker","open","workspace","status"])
    p.add_argument("--home",type=Path,default=studio.DEFAULT_HOME)
    p.add_argument("--id",required=True);p.add_argument("--owner",required=True)
    p.add_argument("--browser",choices=["default","chrome","edge"],default="default")
    p.add_argument("--profile",choices=["Default"],default="Default")
    p.add_argument("--intent",choices=["open","edit","preview","changes"],default="edit")
    p.add_argument("--os-origin",default="https://sports-cave-image-factory.onrender.com")
    args=p.parse_args()
    if os.name != "nt":
        raise RuntimeError("Windows companion requires Windows.")
    root,cfg=config(args.home,args.id,args.owner)
    error_path=root/"last-error.json"
    if args.action == "resume":
        (root/"stopped").unlink(missing_ok=True)
        return
    if args.action == "worker": return worker(args.home,args.id,args.owner)
    if args.action == "supervise": return supervise(args.home,args.id,args.owner)
    if args.action == "watch":
        if not (root/"stopped").exists():return supervise(args.home,args.id,args.owner)
        return
    if args.action == "start":
        # Child holds the lock for its entire lifetime; duplicate launches exit harmlessly.
        subprocess.Popen([sys.executable,"-B",str(Path(__file__).resolve()),"supervise","--home",str(args.home),"--id",args.id,"--owner",args.owner],
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    elif args.action in {"open","workspace"}:
        import urllib.request
        record=json.loads((root/"session.json").read_text())
        token=protect(bytes.fromhex(record["protected"]),True).decode()
        origin="http://127.0.0.1:"+str(cfg["port"])
        request=urllib.request.Request(origin+"/api/state",headers={"X-Studio-Token":token})
        with urllib.request.urlopen(request,timeout=3) as response:
            state=json.load(response)
            if state["task"]["id"] != args.id or state["task"]["owner"] != args.owner: raise RuntimeError("Wrong local task or owner.")
        # Credentials stay on localhost; workspace opening never repeats device pairing.
        if args.action=="workspace":
            if not state.get("draft"):raise RuntimeError("Create a registered draft before opening its editor.")
            request=urllib.request.Request(origin+"/api/action",
                data=json.dumps({"action":"handoff","draft_id":state["draft"]["id"],"intent":args.intent}).encode(),
                headers={"Content-Type":"application/json","Origin":origin,"X-Studio-Token":token})
            with urllib.request.urlopen(request,timeout=3) as response:result=json.load(response)
            if result["task_id"]!=args.id or result["draft_id"]!=state["draft"]["id"]:raise RuntimeError("Wrong workspace handoff.")
            url=result["url"]
            if not url.startswith(origin+"/workspace#token="):raise RuntimeError("Unsafe workspace target.")
        else:
            request=urllib.request.Request(origin+"/api/device",
                data=json.dumps({"operation":"prepare","origin":args.os_origin}).encode(),
                headers={"Content-Type":"application/json","Origin":origin,"X-Studio-Local":"1","X-Studio-Token":token})
            with urllib.request.urlopen(request,timeout=3) as response:url=json.load(response)["url"]
            if not url.startswith(origin+"/pair/setup/"):raise RuntimeError("Unsafe local setup URL.")
        if args.browser=="default":webbrowser.open(url)
        else:subprocess.Popen([browser_command(args.browser),"--profile-directory="+args.profile,"--new-window",url],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    status="Starting" if args.action=="start" else "Approval opened" if args.action=="open" else "Workspace opened" if args.action=="workspace" else "Offline"
    if args.action=="status":
        try:
            import urllib.request
            record=json.loads((root/"session.json").read_text())
            token=protect(bytes.fromhex(record["protected"]),True).decode()
            req=urllib.request.Request("http://127.0.0.1:"+str(cfg["port"])+"/api/ping",headers={"X-Studio-Token":token})
            with urllib.request.urlopen(req,timeout=2) as response:
                status="Connected" if json.load(response).get("connected") else "Offline"
        except (OSError,ValueError):
            status="Offline"
    print(json.dumps({"task":args.id,"owner":args.owner,"origin":"http://127.0.0.1:"+str(cfg["port"]),"action":args.action,"status":status}))

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        if "error_path" in globals():
            studio.atomic(error_path, {"at":studio.now(),"error_type":type(exc).__name__,"message":str(exc)[:500]})
        raise
