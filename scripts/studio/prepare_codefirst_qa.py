"""Isolated synthetic acceptance copy of the actual existing draft. No active companion operations."""
import ast, io, json, re, tarfile, hashlib
from pathlib import Path
import studio, drafts, preview_export, application_drafts

source=Path(__file__).resolve().parents[2]
session=source.parents[1]
home=session/'qa-code'
real_git=studio.git
studio.git=lambda repo,*args:real_git(repo,'-c','core.longpaths=true',*args)
original_home=Path('C:/Users/hello/.codex/visualizations/2026/10/12/01a12f62-716b-7020-bd5c-ca5719a94467/v8')
registry=studio.read(original_home/'.studio/registry.json')
original=next(d for d in registry['drafts'] if d['id']=='9ca4a85e-b3f4-4c85-b61e-4eb5551d2740')
base=studio.git(original['worktree_path'],'rev-parse','HEAD')
owner='codex/v9-codefirst-01a13216';task='v9-code-qa'
if not (home/'.studio/registry.json').exists():
    studio.initialize(home,Path(registry['original_repo']),base,'Acceptance copy of current authorised draft, synthetic export only; no Live attestation.',owner)
    assigned=studio.create_task(home,'QA','CORE',owner,task)
else:raise RuntimeError('QA copy already exists. Reuse its receipt; source will not be overwritten.')
root=Path(assigned['worktree_path'])
archive,manifest=preview_export.capture(original_home,original['task_id'],original['owner'])
with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
    for member in tar.getmembers():
        assert member.isfile() and member.name.startswith('source/')
        relative=member.name.removeprefix('source/');assert preview_export.allowed(relative)
        target=root/relative;assert target.resolve().is_relative_to(root.resolve());target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(tar.extractfile(member).read())
app=root/'app.py';text=app.read_text(encoding='utf-8-sig')
start=text.index('        st.markdown(\n            """\n            <div class="sc-login-wrap">',text.index('def render_login_gate():'));end=text.index('        auth_notice =',start)
new=ast.parse((source/'app.py').read_text(encoding='utf-8')).body
gate=next(n for n in new if isinstance(n,ast.FunctionDef) and n.name=='render_login_gate')
newlines=(source/'app.py').read_text(encoding='utf-8').splitlines(True)
prefix=text[:text.index('def render_login_gate():')];suffix=text[end:]
newtext=(source/'app.py').read_text(encoding='utf-8');begin=newtext.index('def render_login_gate():');stop=newtext.index('        auth_notice =',begin)
text=prefix+newtext[begin:stop]+suffix
style_start=text.index('        .sc-login-wrap {');style_end=text.index('        .sc-section-title {',style_start)
text=text[:style_start]+'        {signin_presentation_css}\n\n'+text[style_end:]
start=text.index('def inject_styles():');end=text.index('    from table_design',start)
part=text[start:end].replace('def inject_styles():\n','def inject_styles():\n    signin_presentation_css = (Path(__file__).resolve().parent / "components/sign_in/presentation.css").read_text(encoding="utf-8")\n')
part=part.replace('        """,\n        unsafe_allow_html=True,','        """.replace("{signin_presentation_css}", signin_presentation_css),\n        unsafe_allow_html=True,')
text=text[:start]+part+text[end:];ast.parse(text);app.write_text(text,encoding='utf-8')
for path in ('signin_presentation.py','components/sign_in/presentation.html','components/sign_in/presentation.css'):
    target=root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((source/path).read_bytes())
draft=next((d for d in studio.read(home/'.studio/registry.json').get('drafts',[]) if d['task_id']==task),None)
if not draft:draft=drafts.new(home,task,owner,'Code-first acceptance copy ONLY')
with studio.locked(home) as file:
    registry=studio.read(file);d=next(d for d in registry['drafts'] if d['id']==draft['id'])
    d['kind']='application';d['production_base']={'service_id':application_drafts.SERVICE,'repository':application_drafts.REPOSITORY,'status':'live','deployment_id':'test-only-current-draft-copy','evidence':'Synthetic acceptance copy, not a verified Live receipt','revision':base};studio.atomic(file,registry)
application_drafts.remember_selection(home,draft['id'],owner)
(source/'docs').mkdir(exist_ok=True)
receipt={'home':str(home),'root':str(root),'owner':owner,'task':task,'draft_id':draft['id'],'original_revision':original['revision'],'original_commit':base,'copy_manifest':manifest}
(source/'docs/codefirst-qa-copy.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps({k:v for k,v in receipt.items() if k!='copy_manifest'}))
