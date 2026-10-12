"""Fail-closed per-task Docker runtime; host only relays bounded raster/input JSON."""
import hashlib
import json
from pathlib import Path
import subprocess
import time
import uuid
import preview_boundary as boundary
import preview_export
import studio
import drafts

PROFILE=Path(__file__).parent/"isolation/chromium-seccomp.json"
PROFILE_SHA256="4540a0c176f2bdd83936ef958c0b306dc6ab6ea4310608149d11ac0803c68022"

def profile_digest():
    # Git may normalise CRLF on checkout. Pin identical LF policy bytes.
    return hashlib.sha256(PROFILE.read_bytes().replace(b"\r\n",b"\n")).hexdigest()
IMAGE_TAG="sports-cave-studio-runtime:phase4d-login-369a5c73"
RELAY="""import sys,urllib.request,urllib.error
data=sys.stdin.buffer.read(12000)
try:
    r=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8877',data=data,headers={'Content-Type':'application/json'}),timeout=15)
    sys.stdout.buffer.write(r.read(2000000))
except urllib.error.HTTPError as error:
    sys.stderr.buffer.write(error.read(2000))
    sys.exit(1)
"""

def options(image,name,task):
    if profile_digest()!=PROFILE_SHA256:
        raise RuntimeError("Unreviewed preview seccomp policy.")
    args=boundary.hardened(image,name,task)
    args[args.index("256m")]="1g"
    args[args.index("64")]="192"
    args[args.index("/tmp:rw,noexec,nosuid,nodev,size=16777216,uid=65532,gid=65532,mode=700")]=\
        "/tmp:rw,noexec,nosuid,nodev,size=536870912,uid=65532,gid=65532,mode=700"
    args[-1:-1]=["--security-opt","seccomp="+str(PROFILE.resolve())]
    return args

def validate_runtime(config,image,task):
    # Reuse core checks without accepting unbounded resource overrides.
    import copy
    h=config["HostConfig"]
    if h["Memory"]!=1073741824 or h["PidsLimit"]!=192:
        raise RuntimeError("Preview resource policy changed.")
    if h.get("Tmpfs")!={"/tmp":"rw,noexec,nosuid,nodev,size=536870912,uid=65532,gid=65532,mode=700"}:
        raise RuntimeError("Preview storage policy changed.")
    seccomp=[s[len("seccomp="):] for s in h["SecurityOpt"] if s.startswith("seccomp=")]
    if len(seccomp)!=1 or json.loads(seccomp[0])!=json.loads(PROFILE.read_text(encoding="utf-8-sig")):
        raise RuntimeError("Preview seccomp profile changed.")
    expected=json.loads(PROFILE.read_text(encoding="utf-8-sig"))
    if expected["defaultAction"]!="SCMP_ACT_ERRNO":
        raise RuntimeError("Preview seccomp must deny by default.")
    checked=copy.deepcopy(config)
    checked["HostConfig"]["Memory"]=268435456
    checked["HostConfig"]["PidsLimit"]=64
    checked["Config"]["Env"]=[v for v in checked["Config"]["Env"] if v=="PLAYWRIGHT_BROWSERS_PATH=/opt/browsers" or not v.startswith("PLAYWRIGHT_BROWSERS_PATH=")]
    checked["Config"]["Env"].remove("PLAYWRIGHT_BROWSERS_PATH=/opt/browsers")
    return boundary.validate(checked,image,task)

class Preview:
    def __init__(self,home,task,owner,source_provider=None):
        self.home,self.task,self.owner=home,task,owner
        self.source_provider=source_provider
        self.name=None
        self.manifest=None
        self.evidence=None
        self.lease=None

    def start(self):
        with studio.locked(self.home) as file:
            registry=studio.read(file)
            drafts.assigned(registry,self.task,self.owner)
            leases=registry.setdefault("preview_leases",{})
            if self.task in leases:
                raise RuntimeError("This worktree already has a preview lease. Stop its owning session first.")
            self.lease=uuid.uuid4().hex
            leases[self.task]={"id":self.lease,"owner":self.owner,"created_at":studio.now(),"pid":__import__("os").getpid()}
            studio.atomic(file,registry)
        try:
            return self._start()
        except Exception:
            self.stop()
            raise

    def _start(self):
        if self.name: raise RuntimeError("Preview already running.")
        archive,manifest=(self.source_provider() if self.source_provider else preview_export.capture(self.home,self.task,self.owner))
        context=json.loads(boundary.docker("context","inspect").stdout)[0]
        if not context["Endpoints"]["docker"]["Host"].startswith("npipe://"):
            raise RuntimeError("Remote Docker contexts are forbidden.")
        image=json.loads(boundary.docker("image","inspect",IMAGE_TAG).stdout)[0]["Id"]
        name="sc-studio-preview-"+uuid.uuid4().hex[:12]
        boundary.docker("create",*options(image,name,self.task),"sleep","900")
        self.name=name
        with studio.locked(self.home) as file:
            registry=studio.read(file)
            lease=registry.get("preview_leases",{}).get(self.task,{})
            if lease.get("id")!=self.lease:
                raise RuntimeError("Preview lease changed during startup.")
            lease["container"]=name
            studio.atomic(file,registry)
        try:
            config=json.loads(boundary.docker("inspect",name).stdout)[0]
            policy=validate_runtime(config,image,self.task)
            boundary.docker("start",name)
            probe_result=boundary.docker("exec",name,"python","-B","/opt/studio/probe.py","192.0.2.1",timeout=90,check=False)
            if not probe_result.stdout.strip():
                raise RuntimeError("Runtime probe failed: "+probe_result.stderr[:1000])
            probe=json.loads(probe_result.stdout)
            browser=json.loads(boundary.docker("exec",name,"python","-B","/opt/studio/browser_probe.py",timeout=60).stdout)
            if not probe["passed"] or not browser["passed"]:
                raise RuntimeError("Runtime negative probes did not pass.")
            self.evidence={"image":image,"policy":policy,"probe":probe,"browser":browser,
                           "profile_sha256":profile_digest()}
            # Copy a generated tar only after the exact runtime passes probes.
            cp=subprocess.run(["docker","exec","-i",name,"python","-B","-c",
                "import sys,tarfile; tarfile.open(fileobj=sys.stdin.buffer,mode='r|').extractall('/tmp',filter='data')"],input=archive,capture_output=True,timeout=30)
            if cp.returncode: raise RuntimeError("Source transfer failed: "+cp.stderr.decode()[:500])
            boundary.docker("exec","-d",name,"sh","-c",
                "exec python -B /opt/studio/controller.py > /tmp/controller.log 2>&1")
            deadline=time.monotonic()+45
            last=""
            while time.monotonic()<deadline:
                try:
                    frame=self.event({"action":"frame"})
                    self.manifest=manifest
                    return frame
                except RuntimeError as e:
                    last=str(e)
                    time.sleep(.25)
            log=boundary.docker("exec",name,"cat","/tmp/controller.log",check=False).stdout
            raise RuntimeError("Preview startup failed: "+log[-2500:]+"\n"+last[:200])
        except Exception:
            self.stop()
            raise

    def event(self,data):
        if not self.name: raise RuntimeError("Preview is stopped.")
        with studio.locked(self.home) as file:
            drafts.assigned(studio.read(file),self.task,self.owner)
        config=json.loads(boundary.docker("inspect",self.name).stdout)[0]
        if config["Config"]["Labels"].get("sports-cave-studio.task")!=self.task:
            raise RuntimeError("Container ownership mismatch.")
        body=json.dumps(data).encode()
        if len(body)>11000: raise ValueError("Event is too large.")
        r=subprocess.run(["docker","exec","-i",self.name,"python","-B","-c",RELAY],
                         input=body,capture_output=True,timeout=20)
        if r.returncode: raise RuntimeError("Preview relay exit "+str(r.returncode)+": "+(r.stderr or r.stdout).decode()[-600:])
        result=json.loads(r.stdout)
        if len(result.get("image",""))>1500000: raise RuntimeError("Oversized preview frame.")
        return result

    def refresh_source(self):
        """Re-export checked source inside the existing boundary; retain synthetic DB."""
        if not self.name: raise RuntimeError("Preview is stopped.")
        archive,manifest=(self.source_provider() if self.source_provider else preview_export.capture(self.home,self.task,self.owner))
        config=json.loads(boundary.docker("inspect",self.name).stdout)[0]
        validate_runtime(config,self.evidence["image"],self.task)
        result=subprocess.run(["docker","exec","-i",self.name,"python","-B","-c",
            "import sys,tarfile; tarfile.open(fileobj=sys.stdin.buffer,mode='r|').extractall('/tmp',filter='data')"],
            input=archive,capture_output=True,timeout=30)
        if result.returncode: raise RuntimeError("Source refresh transfer failed.")
        frame=self.event({"action":"reload-source"})
        self.manifest=manifest
        return frame

    def stop(self):
        if self.name:
            name=self.name
            config=json.loads(boundary.docker("inspect",name).stdout)[0]
            if config["Config"]["Labels"].get("sports-cave-studio.task")!=self.task:
                raise RuntimeError("Refusing to stop a different task's container.")
            boundary.docker("rm","-f",name)
            self.name=None
        if self.lease:
            with studio.locked(self.home) as file:
                registry=studio.read(file)
                leases=registry.get("preview_leases",{})
                if leases.get(self.task,{}).get("id")==self.lease:
                    del leases[self.task]
                    studio.atomic(file,registry)
            self.lease=None
