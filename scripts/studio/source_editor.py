"""Code-only permissions and journalled multi-file editing. Never executes application code."""
import ast
import difflib
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from html.parser import HTMLParser
from pathlib import Path

import drafts, editor, studio, page_catalog, dev_sources

PRESENTATION = ('components/sign_in/presentation.html', 'components/sign_in/presentation.css', 'signin_presentation.py')
EDITABLE = (*editor.CODE_FILES, *PRESENTATION)
MAX_BATCH = 8 * 1024 * 1024
_paths_cache={}

def protected(path):
    return path not in EDITABLE and path!='app.py' and bool(re.search(r'auth|account|password|credential|secret|database|(?:^|_)db|payment|allocation|edition|config',Path(path).stem,re.I))

def paths(root):
    """Only actual statically verified page modules; no arbitrary directory access."""
    meta,data=drafts.read_source(root,'app.py')
    key=(str(root),meta['sha256'])
    if key in _paths_cache: return _paths_cache[key]
    result = {'app.py', 'top_bar.py', *EDITABLE}
    for node in ast.walk(ast.parse(data.decode('utf-8-sig'))):
        if isinstance(node,ast.ImportFrom) and node.level==0 and node.module and node.module.isidentifier(): result.add(node.module+'.py')
        if isinstance(node,ast.Import):
            result.update(a.name+'.py' for a in node.names if a.name.isidentifier())
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) and node.func.value.id=='importlib' and node.func.attr=='import_module' and node.args and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str) and node.args[0].value.isidentifier(): result.add(node.args[0].value+'.py')
    _paths_cache.clear();_paths_cache[key]=result
    return result

def read_scope(registry, draft_id, owner, path):
    draft, task, root = drafts.draft_by_id(registry, draft_id, owner)
    if not isinstance(path,str) or path not in paths(root):
        raise ValueError('Source is not a verified application UI reference.')
    if protected(path): raise ValueError('Sensitive backend source is not authorised for complete-source export.')
    return draft, root, drafts.safe_file(root, path)

def files(home, draft_id, owner):
    with studio.locked(home) as file:
        registry = studio.read(file)
        draft, task, root = drafts.draft_by_id(registry, draft_id, owner)
        finish_batch(home, file, registry, draft, root)
        rows = []
        for path in sorted(paths(root)):
            row = {'path': path, 'mode': 'source', 'available': True, 'editable': path in EDITABLE}
            try:
                if not drafts.safe_file(root,path).exists(): continue
                if protected(path): raise ValueError('Sensitive backend source withheld; requires separate source-export authorisation.')
                drafts.read_source(root, path)
            except (ValueError, OSError) as exc:
                row.update(available=False, reason=str(exc))
            rows.append(row)
        return {'draft_id': draft_id, 'task_id': task['id'], 'files': rows}

def open_file(home, draft_id, owner, path):
    with studio.locked(home) as file:
        registry = studio.read(file)
        draft, root, _ = read_scope(registry, draft_id, owner, path)
        finish_batch(home, file, registry, draft, root)
        editor.finish_pending(home, file, registry, draft, root)
        meta, data = drafts.read_source(root, path)
        return {'path': path, 'hash': meta['sha256'], 'revision': draft['revision'],
                'source': data.decode('utf-8-sig'), 'complete': True, 'editable': path in EDITABLE,
                'language': Path(path).suffix.lstrip('.'),
                'restriction': '' if path in EDITABLE else 'Read-only: application logic is not authorised for source replacement.',
                'history': [h for h in draft.get('editor_history', []) if h['path'] == path]}

def history_source(home,draft_id,owner,path,entry_id,side):
    if side not in ('before','after'): raise ValueError('Invalid source history side.')
    with studio.locked(home) as file:
        registry=studio.read(file);draft,root,_=read_scope(registry,draft_id,owner,path)
        finish_batch(home,file,registry,draft,root)
        entry=next((h for h in draft.get('editor_history',[]) if h['id']==entry_id and h['path']==path),None)
        if not entry: raise ValueError('Unknown file revision.')
        data=editor.content(home,entry[side]);text=data.decode('utf-8-sig')
        if studio.secret_findings(text): raise ValueError('Sensitive history source withheld.')
        return {'path':path,'source':text,'complete':True}

class Scripts(HTMLParser):
    def __init__(self):
        super().__init__(); self.scripts=[]; self.current=None
    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            attrs=dict(attrs)
            self.current=[] if not attrs.get('src') and attrs.get('type','') not in ('application/json','application/ld+json') else None
    def handle_data(self, data):
        if self.current is not None: self.current.append(data)
    def handle_endtag(self, tag):
        if tag == 'script' and self.current is not None:
            self.scripts.append(''.join(self.current)); self.current=None

def js_check(source):
    node=shutil.which('node')
    if not node: raise ValueError('Node syntax checker unavailable; JavaScript save refused.')
    result=subprocess.run([node, '--input-type=module', '--check'], input=source, text=True,
                          capture_output=True, timeout=10, **studio.quiet_process())
    if result.returncode: raise ValueError('JavaScript syntax check failed: '+result.stderr[-1000:])

def validate_source(path, source):
    if not isinstance(source,str): raise ValueError('Expected complete source text.')
    data=source.encode('utf-8')
    if len(data)>drafts.MAX_FILE or '\x00' in source or studio.secret_findings(source):
        raise ValueError('Binary, oversized or potentially sensitive source refused.')
    if path == 'signin_presentation.py':
        try: tree=ast.parse(source)
        except SyntaxError as exc: raise ValueError('Presentation Python syntax error at line '+str(exc.lineno)+': '+str(exc.msg)) from exc
        values={}
        for node in tree.body:
            if isinstance(node,ast.Expr) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str): continue
            if not isinstance(node,ast.Assign) or len(node.targets)!=1 or not isinstance(node.targets[0],ast.Name):
                raise ValueError('Presentation Python permits literal data assignments only, no executable statements.')
            name=node.targets[0].id
            if name not in {'TITLE','DESCRIPTION','BRAND','COLUMNS'} or name in values: raise ValueError('Unsupported presentation setting.')
            values[name]=ast.literal_eval(node.value)
        if set(values)!={'TITLE','DESCRIPTION','BRAND','COLUMNS'}: raise ValueError('Required presentation settings missing.')
        for name in ('TITLE','DESCRIPTION','BRAND'):
            if not isinstance(values[name],str) or len(values[name])>500: raise ValueError('Presentation text must be a short literal string.')
        widths=values['COLUMNS']
        if not isinstance(widths,(list,tuple)) or len(widths)!=3 or any(type(w) not in (int,float) or not .1<=w<=5 for w in widths):
            raise ValueError('Three bounded presentation column widths required.')
    elif path.endswith('.html'):
        parser=Scripts();parser.feed(source);parser.close()
        for script in parser.scripts: js_check(script)
    elif path.endswith(('.js','.mjs','.cjs')): js_check(source)
    elif path.endswith('.css'):
        # Lexically balance CSS outside comments/quoted strings. No source execution.
        stack=[]; quote=None; comment=False; i=0
        while i<len(source):
            c=source[i]; pair=source[i:i+2]
            if comment:
                if pair=='*/': comment=False;i+=1
            elif quote:
                if c=='\\': i+=1
                elif c==quote: quote=None
            elif pair=='/*': comment=True;i+=1
            elif c in ('"',"'"): quote=c
            elif c in '{([': stack.append(c)
            elif c in '})]':
                if not stack or stack.pop()!='{(['['})]'.index(c)]: raise ValueError('Unbalanced CSS delimiters.')
            i+=1
        if stack or quote or comment: raise ValueError('Incomplete CSS rule/string/comment.')
    return data

def replace(target, data):
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent,prefix='.studio-edit-',delete=False) as f:
            temporary=Path(f.name);f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(temporary,target);temporary=None
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)

def finish_batch(home, file, registry, draft, root):
    pending=draft.get('editor_batch_pending')
    if not pending: return
    # Validate EVERY target before rollback or finalisation, retaining foreign edits.
    targets=[]
    for entry in pending['changes']:
        if entry['path'] not in EDITABLE: raise RuntimeError('Invalid journal source permission.')
        target=drafts.safe_file(root,entry['path']);current=editor.digest(target.read_bytes())
        if current not in (entry['before'],entry['after']):
            raise RuntimeError('Interrupted batch conflicts with source; all recovery preimages retained.')
        targets.append((entry,target,current))
    if pending['phase']=='committed':
        if any(current!=entry['after'] for entry,_,current in targets): raise RuntimeError('Committed batch source changed; recovery retained.')
        if draft['revision']!=pending['base_revision']: raise RuntimeError('Interrupted batch revision changed.')
        previous={f['path']:f for f in draft['revisions'][-1]['files']} if draft['revisions'] else {}
        draft['revision']+=1
        for entry,_,_ in targets:
            draft.setdefault('editor_history',[]).append({**entry,'batch_id':pending['id'],'revision':draft['revision']})
            previous[entry['path']]={'path':entry['path'],'sha256':entry['after'],'size':len(editor.content(home,entry['after']))}
        draft['revisions'].append({'number':draft['revision'],'commit':studio.git(root,'rev-parse','HEAD'),
            'saved_at':studio.now(),'files':list(previous.values()),'scope':'coherent authorised UI-source batch','batch_id':pending['id']})
        draft['editing_status']='Saved locally';draft['release_eligible']=False
    else:
        for entry,target,current in targets:
            if current!=entry['before']: replace(target,editor.content(home,entry['before']))
    del draft['editor_batch_pending'];draft['updated_at']=registry['updated_at']=studio.now();studio.atomic(file,registry)

def write_all(home, draft_id, owner, expected_revision, changes):
    if not isinstance(changes,list) or not 1<=len(changes)<=32: raise ValueError('Save All requires 1-32 authorised files.')
    if type(expected_revision) is not int: raise ValueError('Expected draft revision required.')
    with studio.locked(home) as file:
        registry=studio.read(file);draft,_,root=drafts.draft_by_id(registry,draft_id,owner)
        finish_batch(home,file,registry,draft,root);editor.finish_pending(home,file,registry,draft,root)
        if draft['revision']!=expected_revision: raise RuntimeError('Concurrent draft revision; buffers retained. Reopen and compare.')
        seen=set();entries=[];total=0;diffs=[]
        for row in changes:
            if not isinstance(row,dict) or set(row)-{'path','expected_hash','source','restore'}: raise ValueError('Unsupported source batch fields.')
            path=row.get('path')
            if path not in EDITABLE or path in seen: raise ValueError('Duplicate or unauthorised editable source.')
            seen.add(path);target=drafts.safe_file(root,path);_,before=drafts.read_source(root,path)
            if editor.digest(before)!=row.get('expected_hash'): raise RuntimeError('Concurrent source modification: '+path)
            restore=row.get('restore');undo_of=None
            if restore is not None:
                if set(restore)!={'id','side'} or restore['side'] not in ('before','after'): raise ValueError('Invalid history restoration.')
                hit=next((h for h in draft.get('editor_history',[]) if h['id']==restore['id'] and h['path']==path),None)
                if not hit: raise ValueError('Unknown file history entry.')
                after=validate_source(path,editor.content(home,hit[restore['side']]).decode('utf-8'))
                if restore['side']=='before': undo_of=hit['id']
            else: after=validate_source(path,row.get('source'))
            total+=len(after)
            if total>MAX_BATCH: raise ValueError('Source batch exceeds 8 MiB.')
            if before==after: continue
            entries.append({'id':str(uuid.uuid4()),'path':path,'before':editor.blob(home,before),'after':editor.blob(home,after),
                            'saved_at':studio.now(),'operation':'undo' if undo_of else 'restore' if restore else 'edit','undo_of':undo_of})
            diffs.append(''.join(difflib.unified_diff(before.decode('utf-8-sig').splitlines(True),after.decode('utf-8').splitlines(True),fromfile=path,tofile=path)))
        if not entries: return {'changed':False,'revision':draft['revision'],'paths':[],'diff':''}
        pending={'id':str(uuid.uuid4()),'phase':'prepared','base_revision':expected_revision,'changes':entries}
        draft['editor_batch_pending']=pending;studio.atomic(file,registry)
        try:
            for entry in entries:
                target=drafts.safe_file(root,entry['path'])
                if editor.digest(target.read_bytes())!=entry['before']: raise RuntimeError('Source changed during batch save.')
                replace(target,editor.content(home,entry['after']))
            pending['phase']='committed';studio.atomic(file,registry)
        except Exception:
            pending['phase']='prepared';finish_batch(home,file,registry,draft,root);raise
        finish_batch(home,file,registry,draft,root)
        return {'changed':True,'revision':draft['revision'],'paths':[e['path'] for e in entries],'batch_id':pending['id'],'diff':'\n'.join(diffs)[:100000]}
