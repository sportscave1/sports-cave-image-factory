"""All seven source types and confirmed source inspection against the exact existing image."""
import json,time
from pathlib import Path
import studio,source_editor,draft_ui

source=Path(__file__).resolve().parents[2];r=json.loads((source/'docs/codefirst-qa-copy.json').read_text())
home=Path(r['home']);root=Path(r['root']);owner=r['owner'];draft=r['draft_id']
server=draft_ui.DraftServer(home,r['task'],owner,persistent=True)
paths=list(source_editor.EDITABLE);before={p:(root/p).read_bytes() for p in paths};report={}
try:
    frame=server.action({'action':'start-preview'});container=server.preview_runtime.container_id
    rows=[]
    for path in paths:
        opened=source_editor.open_file(home,draft,owner,path);value=opened['source']
        if path.endswith('.py'):value=value.replace('Welcome back','Data-only all-seven title')
        else:value+= '\n<!-- all-seven verification -->\n' if path.endswith('.html') else '\n/* all-seven verification */\n'
        rows.append({'path':path,'expected_hash':opened['hash'],'source':value})
    revision=studio.read(home/'.studio/registry.json')['drafts'][0]['revision'];start=time.perf_counter()
    result=server.action({'action':'editor-save-all','expected_revision':revision,'files':rows})
    assert result['revision']==revision+1 and set(result['paths'])==set(paths)
    assert result.get('frame') and not result.get('preview_error'),result.get('preview_error')
    assert 'Data-only all-seven title' in result['frame']['text']
    report['all_seven_single_revision_and_rendered']=True;report['all_seven_save_seconds']=time.perf_counter()-start
    target=next(t for t in result['frame']['inspect_targets'] if t['component']=='title')
    inspected=server.preview_runtime.event({'action':'inspect','x':target['x'],'y':target['y']})
    assert inspected['inspection']['supported'] and inspected['inspection']['location']['path']=='signin_presentation.py'
    report['confirmed_signin_source_inspection']=True
    assert server.preview_runtime.container_id==container;report['same_container']=True
    report['isolation_evidence']=server.preview_runtime.evidence
finally:
    rows=[]
    for path,data in before.items():
        opened=source_editor.open_file(home,draft,owner,path)
        if (root/path).read_bytes()!=data:rows.append({'path':path,'expected_hash':opened['hash'],'source':data.decode('utf-8')})
    if rows:source_editor.write_all(home,draft,owner,studio.read(home/'.studio/registry.json')['drafts'][0]['revision'],rows)
    assert all((root/path).read_bytes()==data for path,data in before.items())
    if server.preview_runtime:server.preview_runtime.stop()
    server.server_close();report['source_restored']=True
    (source/'docs/codefirst-runtime-check.json').write_text(json.dumps(report,indent=2))
print(json.dumps({k:v for k,v in report.items() if k!='isolation_evidence'},indent=2))
