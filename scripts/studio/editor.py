"""Explicit source mappings, compare-and-save and recoverable draft edit revisions."""
import ast
import difflib
import hashlib
import html
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

import drafts
import studio

CODE_FILES=("components/sports_cave_top_bar/index.html","mockups_page.css","orders_page.css",
            "components/session_recovery.js")
VISUAL_FILE="app.py"
MAPPINGS={
 "title":{"label":"Sign-in heading","selector":".sc-login-title","text_class":"sc-login-title"},
 "description":{"label":"Sign-in description","selector":".sc-login-copy","text_class":"sc-login-copy"},
 "brand":{"label":"Sign-in label","selector":".sc-login-kicker","text_class":"sc-login-kicker"},
 "panel":{"label":"Sign-in panel","selector":".sc-login-wrap"},
 "mobile_panel":{"label":"Sign-in panel · mobile","selector":".sc-login-wrap","occurrence":1},
 "submit":{"label":"Form submit buttons · shared","selector":'div[data-testid="stFormSubmitButton"] > button',"button":True},
}
PROPERTIES=("color","background","font-family","font-size","font-weight","line-height",
 "margin","margin-top","margin-bottom","padding","gap","border","border-radius",
 "width","max-width","text-align","display","flex-direction")

def digest(data): return hashlib.sha256(data).hexdigest()

def blob(home,data):
    h=digest(data); p=drafts.blob_path(home,h)
    p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists():
        if digest(p.read_bytes())!=h: raise RuntimeError("Revision content is corrupt.")
    else:
        with p.open("xb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
    return h

def content(home,h):
    p=drafts.blob_path(home,h); data=p.read_bytes()
    if digest(data)!=h: raise RuntimeError("Revision content is corrupt.")
    return data

def mapped_css(text,mapping):
    pattern=re.compile(re.escape(mapping["selector"])+r"\s*\{([^{}]*)\}")
    hits=list(pattern.finditer(text))
    index=mapping.get("occurrence",0)
    if index>=len(hits):
        if mapping.get("button"): return None
        raise ValueError("Component mapping changed; visual edit refused.")
    return hits[index]

def visual_values(text):
    result={}
    for key,m in MAPPINGS.items():
        match=mapped_css(text,m)
        properties=dict(re.findall(r"([\w-]+)\s*:\s*([^;]+);",match.group(1))) if match else {}
        value={"label":m["label"],"properties":{p:properties.get(p,"") for p in PROPERTIES}}
        if m.get("text_class"):
            hits=re.findall(r'<div class="'+m["text_class"]+r'">([^<>]*)</div>',text)
            if len(hits)!=1: raise ValueError("Text mapping changed; visual edit refused.")
            value["text"]=html.unescape(hits[0])
        if m.get("button"):
            hit=re.search(r'submitted = st\.form_submit_button\(("(?:[^"\\]|\\.)*"), type="primary"',text)
            if not hit: raise ValueError("Submit mapping changed; visual edit refused.")
            value["text"]=json.loads(hit.group(1))
        result[key]=value
    return result

def validate_property(key,value):
    if key not in PROPERTIES or not isinstance(value,str) or len(value)>100:
        raise ValueError("Unsupported visual property.")
    # Literal values only: no URLs, CSS functions, declarations, escapes or expressions.
    clean=value.replace(" !important","").strip()
    if not clean: return ""
    if key in {"color","background"}:
        valid=bool(re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?",clean))
    elif key=="font-family": valid=clean in {"Segoe UI","Arial","Georgia","inherit"}
    elif key=="font-weight": valid=clean in {"normal","bold","400","500","600","700","800","900"}
    elif key=="text-align": valid=clean in {"left","center","right"}
    elif key=="display": valid=clean in {"block","flex"}
    elif key=="flex-direction": valid=clean in {"row","column"}
    elif key=="border": valid=bool(re.fullmatch(r"(?:0|[0-9]{1,2}px solid #[0-9a-fA-F]{6})",clean))
    else:
        valid=bool(re.fullmatch(r"(?:0|auto|[0-9]{1,3}(?:\.[0-9]{1,2})?(?:px|rem|em|%|vh|vw)?)(?: (?:0|auto|[0-9]{1,3}(?:\.[0-9]{1,2})?(?:px|rem|em|%|vh|vw)?)){0,3}",clean))
    if not valid: raise ValueError("Unsupported literal value for "+key)
    return clean

def transform(text,component,changes):
    if component not in MAPPINGS or not isinstance(changes,dict):
        raise ValueError("Unsupported component.")
    m=MAPPINGS[component]
    if "text" in changes:
        value=changes["text"]
        if not isinstance(value,str) or len(value)>200 or any(ord(c)<32 for c in value):
            raise ValueError("Text requires at most 200 printable characters.")
        if m.get("text_class"):
            pattern=r'(<div class="'+m["text_class"]+r'">)[^<>]*(</div>)'
            escaped=html.escape(value).replace("\\","\\\\")
            text,count=re.subn(pattern,lambda h:h[1]+escaped+h[2],text)
            if count!=1: raise ValueError("Text mapping no longer unique.")
        elif m.get("button"):
            pattern=r'(submitted = st\.form_submit_button\()"(?:[^"\\]|\\.)*"'
            text,count=re.subn(pattern,lambda h:h[1]+json.dumps(value),text)
            if count!=1: raise ValueError("Button mapping no longer unique.")
        else: raise ValueError("This component has no editable text.")
    values=changes.get("properties",{})
    if not isinstance(values,dict): raise ValueError("Expected property map.")
    if values:
        match=mapped_css(text,m)
        body=match.group(1) if match else "\n"
        for key,value in values.items():
            value=validate_property(key,value)
            declaration=r"(?m)^\s*"+re.escape(key)+r"\s*:[^;]*;"
            body=re.sub(declaration,"",body)
            if value: body+="\n            "+key+": "+value+";"
        rule=m["selector"]+" {"+body+"\n        }"
        if match: text=text[:match.start()]+rule+text[match.end():]
        else:
            anchors=list(re.finditer(r"\.sc-login-title\s*\{",text))
            if len(anchors)!=1: raise ValueError("Style insertion anchor changed.")
            position=anchors[0].start()
            text=text[:position]+rule+"\n\n        "+text[position:]
    ast.parse(text)
    return text

def scope(registry,draft_id,owner,path):
    if path not in (VISUAL_FILE,*CODE_FILES): raise ValueError("File is not editor-allowlisted.")
    draft,task,root=drafts.draft_by_id(registry,draft_id,owner)
    return draft,root,drafts.safe_file(root,path)

def finish_pending(home,file,registry,draft,root):
    pending=draft.get("editor_pending")
    if not pending: return
    path=pending["path"]
    _,_,target=scope(registry,draft["id"],draft["owner"],path)
    current=digest(target.read_bytes())
    if current==pending["after"]:
        draft.setdefault("editor_history",[]).append(pending)
        draft["revision"]+=1
        previous=draft["revisions"][-1]["files"] if draft["revisions"] else []
        files=[x for x in previous if x["path"]!=path]
        data=content(home,pending["after"])
        files.append({"path":path,"sha256":pending["after"],"size":len(data)})
        draft["revisions"].append({"number":draft["revision"],"commit":studio.git(root,"rev-parse","HEAD"),
          "saved_at":studio.now(),"files":files,"scope":"explicit selected files, not a complete application export"})
        draft["editing_status"]="Saved locally" if draft.get("kind")=="application" else "Implemented Locally"
        draft["release_eligible"]=False
    elif current!=pending["before"]:
        raise RuntimeError("Interrupted edit conflicts with source. Recovery blobs retained; manual review required.")
    del draft["editor_pending"]
    draft["updated_at"]=registry["updated_at"]=studio.now()
    studio.atomic(file,registry)

def locations(text):
    result={}
    for key,mapping in MAPPINGS.items():
        hit=mapped_css(text,mapping)
        if mapping.get("text_class"):
            found=re.search(r'<div class="'+mapping["text_class"]+r'">',text)
            if found:hit=found
        if mapping.get("button"):
            hit=re.search(r'submitted = st\.form_submit_button\(',text) or hit
        if hit:
            line=text.count("\n",0,hit.start())+1
            lines=text.splitlines()
            result[key]={"path":VISUAL_FILE,"line":line,"excerpt":"\n".join(lines[max(0,line-2):line+3])}
    return result


def files(home,draft_id,owner):
    """List only explicit editor mappings, never browse arbitrary filesystem paths."""
    with studio.locked(home) as file:
        registry=studio.read(file)
        draft,task,root=drafts.draft_by_id(registry,draft_id,owner)
        result=[]
        for path in (VISUAL_FILE,*CODE_FILES):
            item={"path":path,"mode":"visual" if path==VISUAL_FILE else "source","available":False}
            try:
                _,data=drafts.read_source(root,path)
                if path==VISUAL_FILE:visual_values(data.decode("utf-8-sig"))
                item["available"]=True
            except (ValueError,RuntimeError,OSError) as exc:
                item["reason"]=str(exc)
            result.append(item)
        return {"draft_id":draft["id"],"task_id":task["id"],"files":result}


def open_file(home,draft_id,owner,path=VISUAL_FILE):
    with studio.locked(home) as file:
        registry=studio.read(file)
        draft,root,target=scope(registry,draft_id,owner,path)
        finish_pending(home,file,registry,draft,root)
        meta,data=drafts.read_source(root,path)
        text=data.decode("utf-8-sig")
        return {"path":path,"hash":meta["sha256"],"revision":draft["revision"],
          "visual":visual_values(text) if path==VISUAL_FILE else None,
          "locations":locations(text) if path==VISUAL_FILE else {},
          "source":None if path==VISUAL_FILE else text,"code_files":CODE_FILES,
          "history":[h for h in draft.get("editor_history",[]) if h["path"]==path]}

def write(home,draft_id,owner,path,expected_hash,expected_revision,*,source=None,component=None,changes=None,restore=None):
    with studio.locked(home) as file:
        registry=studio.read(file)
        draft,root,target=scope(registry,draft_id,owner,path)
        finish_pending(home,file,registry,draft,root)
        before=target.read_bytes()
        if digest(before)!=expected_hash or draft["revision"]!=expected_revision:
            raise RuntimeError("Concurrent edit detected. Reopen and compare; no source was changed.")
        if restore is not None:
            if not isinstance(restore,dict): raise ValueError("Expected a saved revision object.")
            hit=next((h for h in draft.get("editor_history",[]) if h["id"]==restore.get("id") and h["path"]==path),None)
            if not hit or restore.get("side") not in {"before","after"}: raise ValueError("Unknown file revision.")
            after=content(home,hit[restore["side"]])
        elif path==VISUAL_FILE:
            if source is not None: raise ValueError("Python source editing is not authorised.")
            after=transform(before.decode("utf-8-sig"),component,changes).encode("utf-8")
        else:
            if not isinstance(source,str): raise ValueError("Expected source text.")
            after=source.encode("utf-8")
        if len(after)>drafts.MAX_FILE or b"\x00" in after or studio.secret_findings(after.decode("utf-8-sig")):
            raise ValueError("Binary, oversized or potentially sensitive editor content refused.")
        if after==before: return {"changed":False,"revision":draft["revision"]}
        pending={"id":str(uuid.uuid4()),"path":path,"before":blob(home,before),"after":blob(home,after),
                 "saved_at":studio.now(),"operation":("undo" if restore["side"]=="before" else "restore") if restore else "edit",
                 "undo_of":restore["id"] if restore and restore["side"]=="before" else None}
        draft["editor_pending"]=pending
        studio.atomic(file,registry)  # Durable preimage + intent before touching source.
        temp=None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent,prefix=".studio-edit-",delete=False) as f:
                temp=Path(f.name); f.write(after); f.flush(); os.fsync(f.fileno())
            if digest(target.read_bytes())!=expected_hash: raise RuntimeError("Source changed during save.")
            os.replace(temp,target); temp=None
            finish_pending(home,file,registry,draft,root)
        finally:
            if temp is not None: temp.unlink(missing_ok=True)
        return {"changed":True,"revision":draft["revision"],"hash":digest(after),
                "diff":"".join(difflib.unified_diff(before.decode("utf-8-sig").splitlines(True),
                       after.decode("utf-8-sig").splitlines(True),fromfile=path,tofile=path))[:50000]}

def view_changes(home,draft_id,owner,path):
    opened=open_file(home,draft_id,owner,path)
    if not opened["history"]: return {"diff":"No editor revisions for this file."}
    first=opened["history"][0]
    with studio.locked(home) as file:
        registry=studio.read(file)
        _,_,target=scope(registry,draft_id,owner,path)
        before=content(home,first["before"]).decode("utf-8-sig")
        after=target.read_text(encoding="utf-8-sig")
    return {"diff":"".join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=path,tofile=path))[:50000]}
