"""Fail-closed per-task Docker runtime; host only relays bounded raster/input JSON."""
import hashlib
import json
from pathlib import Path
import subprocess
import time
import uuid
import re
import preview_boundary as boundary
import preview_export
import studio
import drafts

PROFILE=Path(__file__).parent/"isolation/chromium-seccomp.json"
PROFILE_SHA256="4540a0c176f2bdd83936ef958c0b306dc6ab6ea4310608149d11ac0803c68022"

def profile_digest():
    # Git may normalise CRLF on checkout. Pin identical LF policy bytes.
    return hashlib.sha256(PROFILE.read_bytes().replace(b"\r\n",b"\n")).hexdigest()
IMAGE_TAG="sha256:d74525e5ce7bd49a602399f6ac1e16476b9158bfaab00bb00703b42a85815baa"
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
        self.container_id=None
        self.docker_context=None
        self.relay=None
        self.last_frame=None

    def _docker(self,*args,**kwargs):
        target_args=[self.container_id if self.container_id and arg==self.name else arg for arg in args]
        return boundary.docker(*target_args,context=self.docker_context,**kwargs)

    def _scope(self):
        with studio.locked(self.home) as file:
            registry=studio.read(file)
            drafts.assigned(registry,self.task,self.owner)
            if self.container_id:
                lease=registry.get('preview_leases',{}).get(self.task,{})
                if lease.get('id')!=self.lease or lease.get('owner')!=self.owner or lease.get('container_id')!=self.container_id:
                    raise RuntimeError('Preview lease or container ownership changed.')

    def start(self):
        if self.name:
            self._scope()
            if self.container_id and not self.event({'action':'health'}).get('alive'):
                raise RuntimeError('Preview runtime is unavailable. Use the explicit Restart control.')
            return dict(self.last_frame) if self.last_frame else self.event({'action':'frame'})
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
        self.docker_context=context['Name']
        image=json.loads(self._docker("image","inspect",IMAGE_TAG).stdout)[0]["Id"]
        name="sc-studio-preview-"+uuid.uuid4().hex[:12]
        self._docker("create",*options(image,name,self.task),"sleep","900")
        self.name=name
        with studio.locked(self.home) as file:
            registry=studio.read(file)
            lease=registry.get("preview_leases",{}).get(self.task,{})
            if lease.get("id")!=self.lease:
                raise RuntimeError("Preview lease changed during startup.")
            lease["container"]=name
            studio.atomic(file,registry)
        try:
            config=json.loads(self._docker("inspect",name).stdout)[0]
            policy=validate_runtime(config,image,self.task)
            if not re.fullmatch('[a-f0-9]{64}',config.get('Id','')):
                raise RuntimeError('Immutable container identity missing.')
            self.container_id=config['Id']
            with studio.locked(self.home) as file:
                registry=studio.read(file)
                lease=registry.get('preview_leases',{}).get(self.task,{})
                if lease.get('id')!=self.lease:raise RuntimeError('Preview lease changed.')
                lease['container_id']=self.container_id
                studio.atomic(file,registry)
            self._docker("start",name)
            probe_result=self._docker("exec",name,"python","-B","/opt/studio/probe.py","192.0.2.1",timeout=90,check=False)
            if not probe_result.stdout.strip():
                raise RuntimeError("Runtime probe failed: "+probe_result.stderr[:1000])
            probe=json.loads(probe_result.stdout)
            browser=json.loads(self._docker("exec",name,"python","-B","/opt/studio/browser_probe.py",timeout=60).stdout)
            if not probe["passed"] or not browser["passed"]:
                raise RuntimeError("Runtime negative probes did not pass.")
            self.evidence={"image":image,"policy":policy,"probe":probe,"browser":browser,
                           "profile_sha256":profile_digest()}
            # Copy a generated tar only after the exact runtime passes probes.
            cp=subprocess.run(["docker","--context",self.docker_context,"exec","-i",self.container_id,"python","-B","-c",
                "import sys,tarfile; tarfile.open(fileobj=sys.stdin.buffer,mode='r|').extractall('/tmp',filter='data')"],input=archive,capture_output=True,timeout=30, **studio.quiet_process())
            if cp.returncode: raise RuntimeError("Source transfer failed: "+cp.stderr.decode()[:500])
            self._docker("exec","-d",name,"sh","-c",
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
            log=self._docker("exec",name,"cat","/tmp/controller.log",check=False).stdout
            raise RuntimeError("Preview startup failed: "+log[-2500:]+"\n"+last[:200])
        except Exception:
            self.stop()
            raise

    def event(self,data):
        if not self.name: raise RuntimeError("Preview is stopped.")
        self._scope()
        if not self.container_id:
            config=json.loads(self._docker("inspect",self.name).stdout)[0]
            if config["Config"]["Labels"].get("sports-cave-studio.task")!=self.task:
                raise RuntimeError("Container ownership mismatch.")
        allowed={"frame","health","reload-source","login-synthetic","click","inspect","text","key","scroll","size","viewport","refresh","navigate","input-batch"}
        if not isinstance(data,dict) or data.get("action") not in allowed:raise ValueError("Unsupported preview event")
        if data.get('action')=='input-batch':
            from preview_input import validate_batch
            data={'action':'input-batch','page':data.get('page'),'events':validate_batch(data)}
        if data.get('action')=='viewport':
            w,h=data.get('width'),data.get('height')
            if type(w) is not int or type(h) is not int or not 320<=w<=1920 or not 480<=h<=1440:raise ValueError('Unsupported viewport bounds')
            if self.last_frame and (w,h)==(self.last_frame['width'],self.last_frame['height']):return dict(self.last_frame)
        if data.get("action")=="size" and data.get("mode") not in {"desktop","tablet","mobile"}:raise ValueError("Unsupported viewport")
        if data.get('action')=='size' and self.last_frame and self.last_frame.get('width')=={'desktop':1280,'tablet':820,'mobile':390}[data['mode']]:
            return dict(self.last_frame)
        if data.get("action")=="navigate":
            import page_catalog
            with studio.locked(self.home) as file:_,root=drafts.assigned(studio.read(file),self.task,self.owner)
            selected=next((p for p in page_catalog.pages(root) if p["key"]==data.get("page")),None)
            if not selected:raise ValueError("Unknown OS page")
            data={"action":"navigate","page":selected["key"]}
        body=json.dumps(data).encode()
        if len(body)>11000: raise ValueError("Event is too large.")
        if self.container_id:
            from preview_relay import Relay, RelayTransportError
            if self.relay is None:self.relay=Relay(self.container_id,self.docker_context)
            try:result=self.relay.request(data)
            except RelayTransportError:
                self.relay.close();self.relay=None
                raise
        else:
            r=subprocess.run(["docker",*(["--context",self.docker_context] if self.docker_context else []),"exec","-i",self.container_id or self.name,"python","-B","-c",RELAY],
                             input=body,capture_output=True,timeout=20, **studio.quiet_process())
            if r.returncode: raise RuntimeError("Preview relay exit "+str(r.returncode)+": "+(r.stderr or r.stdout).decode()[-600:])
            result=json.loads(r.stdout)
        if len(result.get("image",""))>1500000: raise RuntimeError("Oversized preview frame.")
        if data.get("action")=="inspect":
            import editor
            metadata=result.get("inspection",{})
            key=metadata.get("component")
            if metadata.get("supported"):
                if key not in editor.MAPPINGS:raise RuntimeError("Unknown inspection mapping")
                with studio.locked(self.home) as file:
                    registry=studio.read(file);draft=next(d for d in registry["drafts"] if d["task_id"]==self.task)
                try:
                    opened=editor.open_file(self.home,draft["id"],self.owner)
                    exported=next(f["sha256"] for f in self.manifest["files"] if f["path"]==editor.VISUAL_FILE)
                    root=Path(draft["worktree_path"])
                    if hashlib.sha256(preview_export.source_bytes(root,editor.VISUAL_FILE)[0]).hexdigest()!=exported:raise ValueError("Preview is behind source; restart before inspection")
                    metadata["location"]=opened["locations"].get(key)
                except (ValueError,RuntimeError):
                    metadata.update(supported=False,reason="Source mapping changed; read-only inspection")
        if result.get('image'):self.last_frame=result
        return result

    def refresh_source(self,paths=None):
        """Re-export checked source inside the existing boundary; retain synthetic DB."""
        if not self.name: raise RuntimeError("Preview is stopped.")
        self._scope()
        archive,manifest=(self.source_provider() if self.source_provider else preview_export.capture_delta(self.home,self.task,self.owner,paths,self.manifest) if paths else preview_export.capture(self.home,self.task,self.owner))
        config=json.loads(self._docker("inspect",self.name).stdout)[0]
        validate_runtime(config,self.evidence["image"],self.task)
        result=subprocess.run(["docker",*(["--context",self.docker_context] if self.docker_context else []),"exec","-i",self.container_id or self.name,"python","-B","-c",
            "import sys,tarfile; tarfile.open(fileobj=sys.stdin.buffer,mode='r|').extractall('/tmp',filter='data')"],
            input=archive,capture_output=True,timeout=30, **studio.quiet_process())
        if result.returncode: raise RuntimeError("Source refresh transfer failed.")
        frame=self.event({"action":"reload-source","changed_files":list(paths or [])})
        self.manifest=manifest
        return frame

    def stop(self):
        if self.relay:
            self.relay.close();self.relay=None
        if self.name:
            name=self.name
            config=json.loads(self._docker("inspect",name).stdout)[0]
            if config["Config"]["Labels"].get("sports-cave-studio.task")!=self.task:
                raise RuntimeError("Refusing to stop a different task's container.")
            self._docker("rm","-f",name)
            self.name=None
            self.container_id=None
            self.last_frame=None
        if self.lease:
            with studio.locked(self.home) as file:
                registry=studio.read(file)
                leases=registry.get("preview_leases",{})
                if leases.get(self.task,{}).get("id")==self.lease:
                    del leases[self.task]
                    studio.atomic(file,registry)
            self.lease=None
