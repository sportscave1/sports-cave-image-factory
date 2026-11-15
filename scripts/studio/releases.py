"""Local-only candidate planning and mock release executor. No Git writes or providers.
All candidate content is read from approved Git objects, never task working files.
"""
import ast
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import uuid
import drafts
import studio

POLICY = "release-dry-run-v1"
SERVICES = {"sports-cave-os":"srv-d8kl4on7f7vs73dvavv0",
            "sports-cave-os-webhooks":"srv-d9146onlk1mc739nrm7g",
            "sports-cave-seo-worker":"srv-d9ujm9navr4c73amurgg",
            "sports-cave-seo-daily-sync":"crn-d9ujqvvqj5pc73fpe0ag"}
REQUIRED = {"static", "isolated_preview", "combined_runtime"}

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",", ":")).encode()).hexdigest()

def revision(value):
    if not isinstance(value,str) or not re.fullmatch(r"[0-9a-f]{40}",value):
        raise ValueError("An exact immutable 40-character Git revision is required.")
    return value

def safe_name(name):
    p=PurePosixPath(name)
    if (not isinstance(name,str) or not name or p.is_absolute() or "\\" in name or ":" in name
        or any(x in {"", ".", ".."} for x in name.split("/"))
        or any(x.casefold() in {".git", ".env", ".aws", ".ssh", "secrets.toml"} for x in p.parts)
        or p.suffix.casefold() in {".pem", ".key", ".db", ".sqlite", ".sqlite3"}
        or any(x.casefold().startswith(".env.") for x in p.parts)):
        raise ValueError("Sensitive or unsafe candidate path.")
    return name

class GitObjects:
    """Read-only Git interface: no commit, merge, fetch, checkout or shell command."""
    def __init__(self,root):self.root=Path(root)
    def run(self,*args):
        p=subprocess.run(["git","-C",str(self.root),*args],capture_output=True,timeout=30,check=True, **studio.quiet_process())
        return p.stdout
    def tree(self,sha):
        revision(sha)
        if self.run("cat-file","-t",sha).strip()!=b"commit":raise ValueError("Not a commit.")
        entries={}
        for record in self.run("ls-tree","-r","-z",sha).split(b"\0"):
            if not record:continue
            info,name=record.split(b"\t",1);mode,kind,oid=info.decode().split()
            entries[name.decode("utf-8")]=[mode,kind,oid]
        return entries
    def blob(self,entry):
        mode,kind,oid=entry
        if mode not in {"100644","100755"} or kind!="blob":raise ValueError("Links/submodules are not candidate source.")
        revision(oid)
        size=int(self.run("cat-file","-s",oid))
        if size>5*1024*1024:raise ValueError("Candidate file exceeds 5 MiB.")
        return self.run("cat-file","blob",oid)
    def blobs(self,entries):
        ids=[]
        for mode,kind,oid in entries:
            if mode not in {"100644","100755"} or kind!="blob":raise ValueError("Unsafe source object type.")
            ids.append(revision(oid))
        query=("\n".join(ids)+"\n").encode()
        sizes=subprocess.run(["git","-C",str(self.root),"cat-file","--batch-check"],input=query,capture_output=True,check=True,timeout=30, **studio.quiet_process()).stdout.splitlines()
        lengths=[int(line.split()[2]) for line in sizes]
        if len(lengths)!=len(ids) or any(n>5*1024*1024 for n in lengths) or sum(lengths)>50*1024*1024:raise ValueError("Candidate source size limit.")
        data=subprocess.run(["git","-C",str(self.root),"cat-file","--batch"],input=query,capture_output=True,check=True,timeout=30, **studio.quiet_process()).stdout
        out=[];offset=0
        for oid,length in zip(ids,lengths):
            end=data.index(b"\n",offset);header=data[offset:end].decode().split()
            if header!=[oid,"blob",str(length)]:raise ValueError("Object export mismatch.")
            start=end+1;out.append(data[start:start+length]);offset=start+length+1
        return out
    def ancestor(self,base,head):
        revision(base);revision(head)
        p=subprocess.run(["git","-C",str(self.root),"merge-base","--is-ancestor",base,head],capture_output=True,timeout=30, **studio.quiet_process())
        if p.returncode not in {0,1}:raise ValueError("Cannot verify revision ancestry.")
        return p.returncode==0

def assemble(repo,base,selections):
    """Conservative three-way file composition; overlapping unequal edits block."""
    revision(base)
    if not selections:raise ValueError("Select at least one approved task revision.")
    if len(selections)>20 or len({s["task_id"] for s in selections})!=len(selections):raise ValueError("Duplicate or excessive selections.")
    original=repo.tree(base);tree=copy.deepcopy(original);conflicts=[];included=[]
    for s in sorted(selections,key=lambda x:x["task_id"]):
        before=repo.tree(revision(s["base_commit"]));after=repo.tree(revision(s["commit"]))
        if not repo.ancestor(s["base_commit"],s["commit"]) or not repo.ancestor(s["base_commit"],base):
            raise ValueError("Selected task has no verified shared integration ancestry.")
        # Ancestors of the approved base are already integrated, not reverse-applied.
        if repo.ancestor(s["commit"],base):included.append(s["task_id"]);continue
        for name in sorted(set(before)|set(after)):
            if before.get(name)==after.get(name):continue
            safe_name(name)
            if after.get(name):repo.blob(after[name])  # reject symlinks and oversized blobs
            current=tree.get(name)
            if current not in (before.get(name),after.get(name)):
                conflicts.append(name);continue
            if name in after:tree[name]=after[name]
            else:tree.pop(name,None)
    if conflicts:raise ValueError("Conflicting/uncertain integration; manual review required: "+", ".join(sorted(set(conflicts))))
    changed=[n for n in sorted(set(original)|set(tree)) if original.get(n)!=tree.get(n)]
    exact=base if tree==original else next((s["commit"] for s in selections if repo.tree(s["commit"])==tree),None)
    risks=[]
    if any("migration" in n.casefold() or n.lower().endswith(".sql") for n in changed):risks.append("database_migration")
    if any("worker" in n.casefold() or "webhook" in n.casefold() or n in {"render.yaml","sports_cave_server.py","requirements.txt"} for n in changed):risks.append("worker_or_deployment_compatibility")
    return {"base_commit":base,"selections":selections,"tree":tree,"tree_hash":digest(tree),
            "candidate_commit":exact,"changed_files":changed,"already_in_base":included,"risks":risks,"policy":POLICY}

def fingerprint(plan):
    return digest({k:plan[k] for k in ("base_commit","selections","tree_hash","candidate_commit","changed_files","risks","policy")})

def audit(record,event,detail):
    history=record.setdefault("history",[])
    item={"event":event,"detail":detail,"at":studio.now(),"previous":history[-1]["hash"] if history else ""}
    item["hash"]=digest(item);history.append(item)

def intact(record):
    if record["tree_hash"]!=digest(record["tree"]) or record["fingerprint"]!=fingerprint(record):raise ValueError("Candidate identity changed; prepare again.")
    previous=""
    for item in record.get("history",[]):
        body={k:v for k,v in item.items() if k!="hash"}
        if item.get("previous")!=previous or digest(body)!=item.get("hash"):raise ValueError("Audit history integrity failed.")
        previous=item["hash"]

def tested(record):
    intact(record)
    checks=record.get("checks",{})
    if set(checks)!=REQUIRED or any(not checks[n].get("passed") or checks[n].get("fingerprint")!=record["fingerprint"] for n in REQUIRED):
        raise ValueError("All required checks must pass against this exact candidate.")
    if not record["candidate_commit"]:raise ValueError("Combined candidate needs a separately authorised immutable Git commit; no commit is created here.")
    if record["risks"]:raise ValueError("Separate migration backup/recovery or worker compatibility review is required; automatic approval is blocked.")

def review(record,owner,confirmation):
    tested(record)
    if record["owner"]!=owner or confirmation!="REVIEW "+record["candidate_commit"]:raise ValueError("Exact owner review confirmation required.")
    record["review"]={"owner":owner,"fingerprint":record["fingerprint"],"at":studio.now()}
    audit(record,"reviewed",record["review"])

def approve(record,owner,confirmation):
    tested(record)
    if record["status"] in {"Simulating","Simulation verified","Simulation recovered"} or any(h["event"]=="simulation_verified" for h in record.get("history",[])):raise ValueError("Candidate already published in simulation; duplicate approval blocked.")
    if record["owner"]!=owner:raise ValueError("Only the assigned release owner may approve.")
    if (record.get("review") or {}).get("fingerprint")!=record["fingerprint"]:raise ValueError("Review this exact tested candidate before approval.")
    if confirmation!="APPROVE "+record["candidate_commit"]:raise ValueError("Confirm the exact candidate SHA.")
    record["approval"]={"owner":owner,"commit":record["candidate_commit"],"fingerprint":record["fingerprint"],"at":studio.now()}
    record["status"]="Approved for simulation"
    audit(record,"approved",record["approval"])

class MockExecutor:
    """No network, credentials or subprocess calls. Never changes real Live state."""
    def deploy(self,sha,scenario="success"):
        revision(sha)
        if scenario not in {"success","service_failure","revision_mismatch","unhealthy"}:raise ValueError("Unknown mock scenario.")
        services={name:{"id":sid,"revision":sha,"status":"succeeded","healthy":True} for name,sid in SERVICES.items()}
        if scenario=="service_failure":services["sports-cave-seo-worker"]["status"]="failed"
        if scenario=="revision_mismatch":services["sports-cave-seo-worker"]["revision"]="0"*40
        if scenario=="unhealthy":services["sports-cave-os"]["healthy"]=False
        return {"simulation":True,"github":{"branch":"main","revision":sha},"services":services,"at":studio.now()}

def verify_receipt(receipt,sha):
    revision(sha)
    if receipt.get("simulation") is not True:raise ValueError("Only simulated provider evidence is accepted by this build.")
    if receipt.get("github")!={"branch":"main","revision":sha}:raise ValueError("GitHub revision/branch mismatch.")
    if set(receipt.get("services",{}))!=set(SERVICES):raise ValueError("Missing application/worker results.")
    for name,sid in SERVICES.items():
        row=receipt["services"][name]
        if row.get("id")!=sid or row.get("revision")!=sha or row.get("status")!="succeeded" or row.get("healthy") is not True:
            raise ValueError("Deployment or health verification failed: "+name)
    return True

def simulate(record,owner,confirmation,scenario="success",previous=None):
    tested(record)
    approval=record.get("approval") or {}
    if record["owner"]!=owner or approval.get("owner")!=owner or approval.get("fingerprint")!=record["fingerprint"] or approval.get("commit")!=record["candidate_commit"]:
        raise ValueError("Exact owner approval required.")
    if confirmation!="SIMULATE "+record["candidate_commit"]:raise ValueError("Final exact-revision simulation confirmation required.")
    if record["status"]!="Approved for simulation":raise ValueError("Duplicate or concurrent publication attempt blocked.")
    record["status"]="Simulating";audit(record,"simulation_started",record["candidate_commit"])
    receipt=MockExecutor().deploy(record["candidate_commit"],scenario)
    record["last_simulation"]=receipt
    try:verify_receipt(receipt,record["candidate_commit"])
    except ValueError as exc:
        record["status"]="Simulation failed";record["failure"]=str(exc);record["approval"]=None
        audit(record,"simulation_failed",str(exc));return
    record.pop("failure",None)
    record["status"]="Simulation verified";record["previous_verified_simulation"]=previous
    audit(record,"simulation_verified",receipt)

def recover(record,owner,confirmation):
    intact(record)
    if record["owner"]!=owner or record["status"] not in {"Simulation verified","Simulation failed"}:raise ValueError("No recoverable owned simulation.")
    if record["risks"]:raise ValueError("Code rollback does not undo database migrations; separate recovery plan required.")
    previous=record.get("previous_verified_simulation")
    if not previous:raise ValueError("No previous verified simulation to recover. Never guess a rollback SHA.")
    sha=previous["github"]["revision"];verify_receipt(previous,sha)
    if confirmation!="RECOVER "+sha:raise ValueError("Confirm the previous verified SHA.")
    receipt=MockExecutor().deploy(sha);verify_receipt(receipt,sha)
    record["status"]="Simulation recovered";record["recovery"]=receipt;audit(record,"simulation_recovered",receipt)

def eligible(registry,task,repo,full=False):
    if task.get("status")!="Approved" or not task.get("integration_readiness"):raise ValueError("Task is unfinished or not approved.")
    root=studio.identity(registry,task);current=studio.git(root,"rev-parse","HEAD")
    if studio.git(root,"status","--porcelain"):raise ValueError("Task contains uncommitted/untracked changes.")
    if task.get("current_commit")!=current:raise ValueError("Recorded approved revision is stale.")
    test=task.get("last_verified_test") or {};verification=task.get("verification") or {}
    if not test.get("passed") or not verification.get("passed"):raise ValueError("Passing test/verification evidence required.")
    expected=test.get("snapshot")
    if not expected or expected!=verification.get("snapshot") or expected.get("commit")!=current or expected.get("status"):
        raise ValueError("Tests do not identify a clean immutable approved revision.")
    if full and studio.snapshot(root)!=expected:raise ValueError("Approved content no longer matches its test evidence.")
    repo.tree(current)
    return {"task_id":task["id"],"name":task["name"],"owner":task["owner"],"category":task["category"],"base_commit":task["base_commit"],"commit":current,"test_snapshot":expected}

def live_status():
    return {"verified":False,"revision":None,"github_branch":None,"health":"Unverified","release_timestamp":None,
            "services":{n:{"id":sid,"status":"Unverified","revision":None} for n,sid in SERVICES.items()},
            "history":[],"previous_verified_release":None,"reason":"No trusted live provider verification connected. Simulations never populate Live."}

def state_path(home):return drafts.plain_path(Path(home)/".studio"/"release-manager.json")
def load(home):
    path=state_path(home)
    if not path.exists():return {"schema":1,"records":[],"last_verified_simulation":None}
    state=json.loads(path.read_text(encoding="utf-8"))
    for record in state["records"]:intact(record)
    return state

def authority(home,taskid,owner):
    registry=studio.read(Path(home)/".studio/registry.json")
    task,root=drafts.assigned(registry,taskid,owner)
    if task["category"]!="RELEASE":raise ValueError("Release operations require an assigned RELEASE task owner.")
    return registry,task,root

def public(record):
    return {k:v for k,v in record.items() if k not in {"tree"}}

def catalog(home,taskid,owner):
    with studio.locked(home):
        registry,task,root=authority(home,taskid,owner);state=load(home);repo=GitObjects(root);options=[]
        for source in registry["tasks"]:
            row={k:source.get(k) for k in ("id","name","category","owner","status")}
            try:row.update(eligible(registry,source,repo));row["eligible"]=True
            except (ValueError,RuntimeError,subprocess.SubprocessError) as exc:row.update(eligible=False,reason=str(exc))
            options.append(row)
        return {"live":live_status(),"base":registry["approved_base"],"options":options,"records":[public(r) for r in state["records"] if r["release_task"]==taskid and r["owner"]==owner],"publishing_enabled":False}

def static_checks(repo,record):
    failures=[]
    for name in record["changed_files"]:
        entry=record["tree"].get(name)
        if not entry:continue
        try:
            data=repo.blob(entry);safe_name(name)
            if name.endswith(".py"):ast.parse(data,filename=name)
            if b"\0" not in data and studio.secret_findings(data.decode("utf-8",errors="replace")):raise ValueError("Potential secret")
        except (ValueError,SyntaxError) as exc:failures.append(name+": "+str(exc))
    return {"passed":not failures,"failures":failures,"fingerprint":record["fingerprint"],"at":studio.now(),"scope":"Changed-source syntax, sensitive paths and secret patterns; runtime checks separate"}

def action(home,taskid,owner,data):
    op=data.get("operation")
    if op=="publish":raise ValueError("Production publishing is disabled in this build; mock executor only.")
    with studio.locked(home):
        registry,task,root=authority(home,taskid,owner);repo=GitObjects(root);state=load(home)
        if op=="prepare":
            ids=data.get("task_ids")
            if not isinstance(ids,list) or not ids or not all(isinstance(x,str) for x in ids):raise ValueError("Select approved task IDs.")
            selections=[eligible(registry,studio.task_by_id(registry,i),repo,True) for i in ids]
            base=registry["approved_base"]["commit"]
            if base!=task["base_commit"]:raise ValueError("Assigned release base changed. Reallocate safely; do not reset this task.")
            plan=assemble(repo,base,selections);key=fingerprint(plan)
            if any(r["fingerprint"]==key and r["release_task"]==taskid for r in state["records"]):raise ValueError("This exact candidate already exists. Reopen it.")
            record={**plan,"id":str(uuid.uuid4()),"owner":owner,"release_task":taskid,"fingerprint":key,"version":1,"status":"Prepared" if plan["candidate_commit"] else "Awaiting authorised candidate commit","created_at":studio.now(),"checks":{},"approval":None}
            audit(record,"prepared",{"selected":ids,"candidate":plan["candidate_commit"]});state["records"].append(record)
        else:
            record=next((r for r in state["records"] if r["id"]==data.get("id") and r["owner"]==owner and r["release_task"]==taskid),None)
            if not record:raise ValueError("Unknown or differently owned release candidate.")
            if data.get("version")!=record["version"]:raise ValueError("Stale release view; refresh before acting.")
            intact(record)
            if op in {"review","approve","simulate"}:
                if registry["approved_base"]["commit"]!=record["base_commit"]:raise ValueError("Approved integration base changed; prepare again.")
                if not record["candidate_commit"] or repo.tree(record["candidate_commit"])!=record["tree"]:raise ValueError("Exact committed candidate tree required.")
                for selection in record["selections"]:
                    current=eligible(registry,studio.task_by_id(registry,selection["task_id"]),repo,True)
                    if current!=selection:raise ValueError("Selected task approval changed.")
            if op=="test":
                record["checks"]["static"]=static_checks(repo,record);record["approval"]=None;record["review"]=None
                record["status"]="Checks incomplete";audit(record,"static_checked",record["checks"]["static"])
            elif op=="review":review(record,owner,data.get("confirmation"))
            elif op=="approve":approve(record,owner,data.get("confirmation"))
            elif op=="simulate":
                record["previous_verified_simulation"]=state.get("last_verified_simulation")
                simulate(record,owner,data.get("confirmation"),data.get("scenario","success"),state.get("last_verified_simulation"))
                if record["status"]=="Simulation verified":state["last_verified_simulation"]=record["last_simulation"]
            elif op=="recover":
                recover(record,owner,data.get("confirmation"));state["last_verified_simulation"]=record["recovery"]
            else:raise ValueError("Unsupported release operation.")
            record["version"]+=1
        studio.atomic(state_path(home),state)
        return public(record)

def read_candidate(home,taskid,owner,candidate_id):
    with studio.locked(home):
        registry,task,root=authority(home,taskid,owner);state=load(home)
        record=next((r for r in state["records"] if r["id"]==candidate_id and r["owner"]==owner and r["release_task"]==taskid),None)
        if not record:raise ValueError("Unknown candidate.")
        intact(record)
        return copy.deepcopy(record),root

def runtime_result(home,taskid,owner,candidate_id,expected,checks,evidence=None):
    with studio.locked(home):
        authority(home,taskid,owner);state=load(home)
        record=next(r for r in state["records"] if r["id"]==candidate_id and r["owner"]==owner and r["release_task"]==taskid)
        if record["fingerprint"]!=expected:raise ValueError("Preview identity changed.")
        for key in ("isolated_preview","combined_runtime"):
            record["checks"][key]={"passed":checks[key],"fingerprint":expected,"at":studio.now(),"scope":"Mandatory Docker probes and synthetic application startup/login; not production or worker execution"}
        if evidence is not None:record["runtime_evidence"]=evidence
        record["approval"]=None;record["review"]=None;record["status"]="Runtime checked";record["version"]+=1;audit(record,"runtime_checked",record["checks"])
        studio.atomic(state_path(home),state)
        return public(record)
