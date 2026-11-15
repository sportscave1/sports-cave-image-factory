"""Reviewed source-class export; no Git metadata, runtime data or host configuration."""
import ast
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import tarfile

import drafts
import studio

ASSETS = {"assets/sports-cave-os-app-icon.webp",
          "assets/sports-cave-logo-landscape-gold-transparent.webp",
          "assets/sports-cave-sc-gold-favicon.svg"}
STUDIO_UI = {"scripts/studio/ui/"+name for name in ("workspace.js","workspace.css","editor.js","editor.css","code-editor.js")}
DEVELOPMENT_ADDITIONS = STUDIO_UI | {"developer_studio_page.py", "components/developer_studio/panel.html",
                         "components/developer_studio/panel.css", "components/developer_studio/panel.js",
                         "signin_presentation.py", "components/sign_in/presentation.html", "components/sign_in/presentation.css"}
SOURCE_DIRS = {"components", "ui_components"}
DENIED_MODULES = {"run_migrations.py", "sports_cave_server.py"}
SYNTHETIC_PASSWORD = "StudioOnly-2026"

def allowed(name):
    p=PurePosixPath(name)
    if name in DENIED_MODULES or any(s.startswith(".") for s in p.parts):
        return False
    if "worker" in p.stem or "webhook" in p.stem:
        return False
    return (name == "design_studio_prompts/SPORTS-CAVE-HIGH-QUALITY-IMAGE-SEARCH-PROMPT-V2.txt" or len(p.parts)==1 and p.suffix in {".py",".css",".js"} or
            p.parts[0] in SOURCE_DIRS and p.suffix in {".html",".css",".js"} or name in ASSETS or name in STUDIO_UI)

def raw_source(root, name):
    path=drafts.plain_path(root/name)
    if not path.resolve().is_relative_to(root.resolve()) or not path.is_file() or path.stat().st_nlink>1:
        raise ValueError("Unsafe source path: "+name)
    return path.read_bytes()

def source_bytes(root, name):
    return sanitise_source(name,raw_source(root,name))

def sanitise_source(name,data):
    if len(data)>5*1024*1024:
        raise ValueError("Oversized export source: "+name)
    if name in ASSETS:
        return data,False
    text=data.decode("utf-8-sig")
    redacted=False
    if name=="sc_auth.py":
        tree=ast.parse(text)
        nodes=[n for n in tree.body if isinstance(n,ast.Assign) and
               any(isinstance(t,ast.Name) and t.id=="DEFAULT_APP_PASSWORD" for t in n.targets)]
        if len(nodes)!=1 or not isinstance(nodes[0].value,ast.Constant):
            raise ValueError("Unrecognized authentication default; export refused.")
        node=nodes[0]
        lines=text.splitlines(keepends=True)
        lines[node.lineno-1:node.end_lineno]=["DEFAULT_APP_PASSWORD = "+repr(SYNTHETIC_PASSWORD)+"\n"]
        text="".join(lines)
        redacted=True
    if studio.secret_findings(text):
        raise ValueError("Potential credential in source; export refused (value withheld): "+name)
    # Flag literal secret assignments, including short human passwords.
    if name.endswith(".py"):
        for node in ast.walk(ast.parse(text)):
            if not isinstance(node,ast.Assign) or not isinstance(node.value,ast.Constant):
                continue
            value=node.value.value
            names=[t.id for t in node.targets if isinstance(t,ast.Name)]
            if isinstance(value,str) and len(value)>=8 and any(
                re.search(r"(?:PASSWORD|SECRET|ACCESS_TOKEN|API_KEY)$",n,re.I) for n in names):
                safe=(name=="sc_auth.py" and names==["DEFAULT_APP_PASSWORD"] and value==SYNTHETIC_PASSWORD
                      or name=="shared_credentials.py" and names in (["MASKED_PASSWORD"],["FIELD_PASSWORD"]))
                if not safe:
                    raise ValueError("Unreviewed credential-like literal: "+name+":"+str(node.lineno))
    return text.encode(),redacted

def capture(home,task_id,owner):
    with studio.locked(home) as file:
        task,root=drafts.assigned(studio.read(file),task_id,owner)
        before=studio.git(root,"rev-parse","HEAD")
        names=sorted({n for n in studio.git(root,"ls-files").splitlines() if allowed(n)} |
                     {n for n in DEVELOPMENT_ADDITIONS if (root/n).exists() and allowed(n)})
        if "app.py" not in names or "sc_auth.py" not in names:
            raise ValueError("Required application source missing.")
        fingerprints={};captured=[]
        for name in names:
            original=raw_source(root,name)
            fingerprints[name]=hashlib.sha256(original).digest()
            captured.append((name,*sanitise_source(name,original)))
        if sum(len(data) for _,data,_ in captured)>50*1024*1024:
            raise ValueError("Export exceeds 50 MiB.")
        for name,data,redacted in captured:
            if hashlib.sha256(raw_source(root,name)).digest()!=fingerprints[name]:
                raise RuntimeError("Source changed during export.")
        if studio.git(root,"rev-parse","HEAD")!=before:
            raise RuntimeError("Commit changed during export.")
        manifest={"task":task_id,"owner":owner,"commit":before,
                  "files":[{"path":n,"sha256":hashlib.sha256(data).hexdigest(),"synthetic_override":r}
                           for n,data,r in captured]}
        buffer=io.BytesIO()
        with tarfile.open(fileobj=buffer,mode="w") as tar:
            for name,data,_ in captured:
                info=tarfile.TarInfo("source/"+name)
                info.size=len(data); info.uid=info.gid=65532; info.mode=0o644
                tar.addfile(info,io.BytesIO(data))
        return buffer.getvalue(),manifest


def capture_objects(repo,record):
    """Export the locked approved object composition, not any host working tree."""
    import releases
    releases.intact(record)
    names=sorted(n for n in record["tree"] if allowed(n))
    if "app.py" not in names or "sc_auth.py" not in names:raise ValueError("Candidate lacks the application entry point.")
    for n in names:releases.safe_name(n)
    entries=[record["tree"][n] for n in names]
    raw=repo.blobs(entries)
    captured=[(n,*sanitise_source(n,data)) for n,data in zip(names,raw)]
    if sum(len(data) for _,data,_ in captured)>50*1024*1024:raise ValueError("Candidate export exceeds 50 MiB.")
    manifest={"candidate_id":record["id"],"fingerprint":record["fingerprint"],"commit":record["candidate_commit"],
              "files":[{"path":n,"sha256":hashlib.sha256(data).hexdigest(),"synthetic_override":r} for n,data,r in captured]}
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode="w") as tar:
        for name,data,_ in captured:
            info=tarfile.TarInfo("source/"+name);info.size=len(data);info.uid=info.gid=65532;info.mode=0o644
            tar.addfile(info,io.BytesIO(data))
    return buffer.getvalue(),manifest


def capture_delta(home,task_id,owner,paths,previous):
    """Refresh only a verified editor save; full refresh remains available for external edits."""
    import editor, source_editor
    if not paths or len(paths)>32 or any(p not in (editor.VISUAL_FILE,*source_editor.EDITABLE) for p in paths):raise ValueError("Unapproved incremental source")
    with studio.locked(home) as file:
        _,root=drafts.assigned(studio.read(file),task_id,owner)
        if studio.git(root,"rev-parse","HEAD")!=previous["commit"]:raise ValueError("Draft commit changed; restart or fully refresh preview")
        entries=[];buffer=io.BytesIO()
        with tarfile.open(fileobj=buffer,mode="w") as tar:
            for name in paths:
                original=raw_source(root,name)
                data,redacted=sanitise_source(name,original)
                if raw_source(root,name)!=original:raise RuntimeError("Source changed during refresh")
                info=tarfile.TarInfo("source/"+name);info.size=len(data);info.uid=info.gid=65532;info.mode=0o644
                tar.addfile(info,io.BytesIO(data))
                entries.append({"path":name,"sha256":hashlib.sha256(data).hexdigest(),"synthetic_override":redacted})
        manifest={**previous,"files":[f for f in previous["files"] if f["path"] not in paths]+entries,"refresh_scope":"editor-saved files; full refresh for external changes"}
        return buffer.getvalue(),manifest
