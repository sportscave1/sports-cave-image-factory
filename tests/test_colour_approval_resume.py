import json
from unittest.mock import patch,Mock
import pytest
import auto_editions as ae
from auto_editions_colour_policy import propose,fingerprint,approve
from auto_editions_colour_store import approve_and_resume,resume_existing,configuration
from tests.test_auto_editions_colour import icc,source,psd
from tests.test_colour_workflow_reuse import E,SCOPE
from tests.test_auto_editions_discovery import database,store,pglite_database,register,tick,asset,PID


def blocked(store):
    d,sql=store;register(store);tick(store,[asset()]);job=d.queue.claim('host')
    identity=source()
    d.queue.checkpoint(PID,str(job['lease_token']),'host','Blocked','Colour policy awaiting approval',source=identity)
    sql.execute("UPDATE auto_edition_onboarding SET lease_until=now()-interval '1 second' WHERE product_gid=%s",(PID,))
    return d,sql,identity


def test_approval_resume_is_atomic_pinned_audited_duplicate_safe(store):
    d,sql,s=blocked(store)
    p=propose('owner-interpretation',icc(),[dict(source=s,provenance=E)],[E],[E])
    body=dict(proposal=p,reviewed_hash=fingerprint(p));read=lambda _:dict(id=s['file_id'],rev=s['revision'],content_hash=s['content_hash'])
    with patch('auto_editions_colour_review.registry',return_value=[]):
        first=approve_and_resume(d.queue,PID,body,'owner',read);assert first['resumed']
        second=approve_and_resume(d.queue,PID,body,'owner',read);assert second['already_requested']
        sql.execute("SELECT event,count(*) n FROM auto_edition_onboarding_audit WHERE event IN ('colour_retry','colour_policy_approved') GROUP BY event")
        assert {r['event']:r['n'] for r in sql.fetchall()}==dict(colour_retry=1,colour_policy_approved=1)
        assert len(configuration(d.connect)['policies'])==1
        sql.execute('SELECT status,priority,source FROM auto_edition_onboarding WHERE product_gid=%s',(PID,));row=sql.fetchone()
        assert row['status']=='Awaiting preparation' and row['source']==s and row['priority']==job_priority(sql,PID)
        with pytest.raises(ValueError,match='Provider source changed'):
            approve_and_resume(d.queue,PID,body,'owner',lambda _:dict(id=s['file_id'],rev='a2',content_hash='b'*64))


def job_priority(sql,pid):
    sql.execute('SELECT priority FROM auto_edition_onboarding WHERE product_gid=%s',(pid,));return sql.fetchone()['priority']


def test_stale_mapping_and_noncolour_failures_never_activate_policy(store):
    d,sql,s=blocked(store);p=propose('owner',icc(),[dict(source=s,provenance=E)],[E],[E]);body=dict(proposal=p,reviewed_hash=fingerprint(p))
    read=lambda _:dict(id=s['file_id'],rev=s['revision'],content_hash=s['content_hash'])
    with patch('auto_editions_colour_review.registry',return_value=[]):
        sql.execute("UPDATE auto_edition_onboarding SET reason='Missing number layer'")
        with pytest.raises(ValueError,match='separate inspection'):approve_and_resume(d.queue,PID,body,'owner',read)
        sql.execute("SELECT count(*) n FROM auto_edition_onboarding_audit WHERE event IN ('colour_retry','colour_policy_approved')");assert sql.fetchone()['n']==0
        sql.execute("UPDATE product_psd_mappings SET dropbox_file_id='id:changed'")
        with pytest.raises(ValueError,match='mapping changed'):approve_and_resume(d.queue,PID,body,'owner',read)


def test_verified_upload_receipt_reuses_workflow_only_after_actual_bytes_match(store,tmp_path):
    from auto_editions_colour_upload import capture,finish
    d,sql=store;file=psd(tmp_path/'upload.psd');s={**source(),'file_id':'id:new','content_hash':ae.file_hash(file,dropbox=True)}
    p=propose('workflow',icc(),[dict(source=source(),provenance=E)],[E],[E],scope=SCOPE);policy=approve(p,'owner',fingerprint(p))
    state=dict(path=str(tmp_path/'capture.psd'),offset=0,policy=policy,provenance=[E],actor='admin',content_hash=s['content_hash'])
    capture(state,0,file.read_bytes())
    meta=dict(id=s['file_id'],rev=s['revision'],content_hash=s['content_hash'])
    r=finish(state,meta,d.connect);assert r['status']=='verified' and not PathExists(state['path'])
    with patch('auto_editions_colour_review.registry',return_value=[policy]),patch.dict('os.environ',{'AUTO_EDITIONS_UNTAGGED_RGB_DEFAULT':'workflow'}):
        c=configuration(d.connect)
        from auto_editions_colour_policy import resolve
        assert resolve(s,**c)[1]['group']=='workflow'
    state={**state,'path':str(tmp_path/'wrong.psd'),'offset':0};capture(state,0,file.read_bytes())
    with pytest.raises(ValueError):finish(state,{**meta,'content_hash':'f'*64},d.connect)


def PathExists(path):
    from pathlib import Path
    return Path(path).exists()


def test_backend_and_companion_resolve_same_audited_policy(monkeypatch):
    from auto_editions_colour_policy import resolve
    p=propose('exact',icc(),[dict(source=source(),provenance=E)],[E],[E]);p=approve(p,'owner',fingerprint(p))
    monkeypatch.setenv('AUTO_EDITIONS_COLOUR_POLICY_BACKEND','audit')
    with patch('auto_editions_colour_store.configuration',return_value=dict(policies=[p],memberships=[],default_group='')):
        assert resolve(source())[1]==resolve(source(),[p])[1]


def test_upload_provenance_failure_preserves_completed_artwork_upload(tmp_path):
    import files_upload_api as files
    from tests.test_files_upload_api import DropboxChunkUploadManagerTests
    case=DropboxChunkUploadManagerTests();case.setUp();record=case.start_upload(size=3)
    internal=case.manager._record(record['upload_id'],record['upload_secret'])
    internal.colour_workflow=dict(path=str(tmp_path/'capture.psd'),offset=0)
    with patch.object(files.dropbox_integration,'start_upload_session',return_value='session'),patch.object(files.dropbox_integration,'finish_upload_session',return_value={'id':'id:actual','rev':'a1'}),patch('auto_editions_colour_upload.finish',side_effect=ValueError('not verified')):
        result=case.manager.append(record['upload_id'],record['upload_secret'],0,b'abc',final=True)
    assert result['state']=='completed' and result['offset']==3 and result['metadata']['colour_workflow']['status']=='needs_verification'
