"""New workflow membership recovery stays bounded/opt-in in disposable SQL."""
import json
from auto_editions_colour_policy import propose,approve,fingerprint
from auto_editions_colour_workflows import verified_membership
from auto_editions_colour_recovery import recover
import auto_editions as ae
from tests.test_colour_workflow_reuse import SCOPE,E
from tests.test_auto_editions_colour import psd,icc,source
from tests.test_auto_editions_discovery import database,store,pglite_database,register,tick,asset,PID


def test_new_workflow_member_can_resume_without_duplicate_profile_approval(store,tmp_path,monkeypatch):
    d,sql=store;register(store);tick(store,[asset()]);job=d.queue.claim('host')
    path=psd(tmp_path/'source.psd');identity={**source(),'content_hash':ae.file_hash(path,dropbox=True)}
    proposal=propose('workflow-default',icc(),[dict(source={**source(),'file_id':'id:seed'},provenance=E)],[E],[E],scope=SCOPE)
    policy=approve(proposal,'synthetic-owner',fingerprint(proposal))
    receipt=verified_membership(policy,path,identity,[E],'synthetic-lineage-verifier')
    receipts=tmp_path/'receipts.json';receipts.write_text(json.dumps([receipt]))
    monkeypatch.setenv('AUTO_EDITIONS_UNTAGGED_RGB_DEFAULT',policy['group']);monkeypatch.setenv('AUTO_EDITIONS_COLOUR_WORKFLOWS_FILE',str(receipts))
    d.queue.checkpoint(PID,str(job['lease_token']),'host','Blocked','Colour policy awaiting approval',source=identity)
    sql.execute("UPDATE auto_edition_onboarding SET lease_until=now()-interval '1 second' WHERE product_gid=%s",(PID,))
    # An earlier mapped source's colour retry must not suppress this source's
    # separately verified recovery. The same current file/content remains once-only.
    with d.connect() as conn,conn.cursor() as cur:
        d.queue.audit(cur,PID,'synthetic-owner','colour_retry',dict(source={**identity,'file_id':'id:old','content_hash':'c'*64}))
    plan=recover(d.queue,'synthetic-owner',policies=[policy]);assert len(plan)==1 and plan[0]['source']==identity
    sql.execute('SELECT status FROM auto_edition_onboarding WHERE product_gid=%s',(PID,));assert sql.fetchone()['status']=='Blocked'
    monkeypatch.setenv('AUTO_EDITIONS_COLOUR_RECOVERY_ENABLED','true')
    assert len(recover(d.queue,'synthetic-owner',policies=[policy],dry_run=False))==1
    assert recover(d.queue,'synthetic-owner',policies=[policy],dry_run=False)==[]
