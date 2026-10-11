"""Opt-in real editor acceptance. Restores only its own tested edits through history."""
import base64
import hashlib
import json
from pathlib import Path
import threading
import time
import draft_ui
import editor
import studio
from verify_preview_runtime import HOME, OWNER, request, query

def main():
    server=draft_ui.DraftServer(HOME,'20261011-c24ca137',OWNER,idle_seconds=300)
    root=Path(server.state()['task']['worktree_path'])
    files=['app.py',editor.CODE_FILES[0]]
    baseline={p:(root/p).read_bytes() for p in files}
    report={'phase3_verified':False,'started_at':studio.now()}
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    cleanup=[]
    def opened(path='app.py'):return request(server,'editor-open',path=path)
    def save(state,**values):
        return request(server,'editor-save',path=state['path'],expected_hash=state['hash'],expected_revision=state['revision'],**values)
    try:
        request(server,'start-preview')
        container=server.preview_runtime.name
        query(container,"INSERT INTO studio_marker VALUES ('editor-refresh-retains-data')")
        first=opened()
        t=time.monotonic()
        result=save(first,component='title',changes={'text':'Studio verification draft','properties':{'color':'#1264B4'}})
        report['save_to_preview_seconds']=round(time.monotonic()-t,3)
        changed=opened(); change=changed['history'][-1]
        cleanup.append(('app.py',change['id']))
        assert 'preview_error' not in result,result.get('preview_error')
        assert 'Studio verification draft' in result['frame']['text'],result['frame']['text']
        assert container==server.preview_runtime.name
        assert ['editor-refresh-retains-data'] in query(container,'SELECT label FROM studio_marker')
        (HOME/'.studio/phase3-edited-preview.jpg').write_bytes(base64.b64decode(result['frame']['image']))
        assert 'Studio verification draft' in request(server,'editor-diff',path='app.py')['diff']
        try:save(first,component='title',changes={'text':'stale'})
        except RuntimeError:report['http_conflict_denied']=True
        else:raise AssertionError('Stale save accepted')
        for path in ['../app.py','.env','sc_auth.py','scripts/studio/editor.py']:
            try:request(server,'editor-open',path=path)
            except RuntimeError:pass
            else:raise AssertionError('File allowlist bypass')
        report['http_file_restrictions']=True
        save(changed,restore={'id':change['id'],'side':'before'})
        assert (root/'app.py').read_bytes()==baseline['app.py']
        result=save(opened(),restore={'id':change['id'],'side':'after'})
        assert 'Studio verification draft' in result['frame']['text']
        save(opened(),restore={'id':change['id'],'side':'before'})
        cleanup.pop()
        code=opened(files[1])
        result=save(code,source=code['source']+'\n<!-- Studio source editor verification -->\n')
        current=opened(files[1]);change=current['history'][-1];cleanup.append((files[1],change['id']))
        assert 'preview_error' not in result,result.get('preview_error')
        from preview_boundary import docker
        received=docker('exec',container,'python','-B','-c',"import hashlib;print(hashlib.sha256(open('/tmp/source/"+files[1]+"','rb').read()).hexdigest())").stdout.strip()
        assert received==current['hash']
        save(current,restore={'id':change['id'],'side':'before'});cleanup.pop()
        assert all((root/p).read_bytes()==data for p,data in baseline.items())
        report.update({'visual_edit_rendered':True,'source_edit_transferred':True,'save_reopen':True,
          'undo_restore':True,'synthetic_data_retained_on_edit':True,'application_source_restored':True,
          'runtime_safety':server.preview_runtime.evidence,'editor_runtime_checks_passed':True})
    finally:
        for path,revision in reversed(cleanup):
            save(opened(path),restore={'id':revision,'side':'before'})
        server.stopping=True;thread.join(10)
        studio.atomic(HOME/'.studio/phase3-editor-acceptance.json',report)
        print(json.dumps({k:v for k,v in report.items() if k!='runtime_safety'},indent=2))
if __name__=='__main__':main()
