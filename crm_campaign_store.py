"""Versioned authoring only. Never writes legacy sends/campaign queues or profiles."""
from copy import deepcopy
import json
import uuid
from crm_workspace_store import WorkspaceRecords
from crm_navigation import require
from crm_campaign_content import new_document, validate_document, preflight, settings, fingerprint, render_campaign


class CampaignStore(WorkspaceRecords):
    def list_drafts(self, archived=False, *, search='', status='All', market='All', offset=0, limit=100):
        return self.q("SELECT * FROM crm_campaign_drafts WHERE (archived_at IS NOT NULL)=%s AND position(lower(%s) in lower(name))>0 AND (%s='All' OR status=%s) AND (%s='All' OR document->>'market'=%s) ORDER BY updated_at DESC,id LIMIT %s OFFSET %s",(archived,search,status,status,market,market,min(200,max(1,int(limit))),max(0,int(offset))))

    def draft(self, identity):
        row=self.q('SELECT * FROM crm_campaign_drafts WHERE id=%s',(identity,),True)
        if not row: raise ValueError('Campaign not found.')
        return row

    def history(self, identity):
        return self.q('SELECT action,actor,version,created_at FROM crm_campaign_history WHERE campaign_id=%s ORDER BY id DESC LIMIT 50',(identity,))

    def save(self, user, name, document, identity=None, version=None, *, requested_status='DRAFT', env=None, duplicate_of=None):
        document=deepcopy(document)
        if isinstance(document,dict) and isinstance(document.get('html_sections'),dict) and isinstance(document['html_sections'].get('footer'),str):
            from crm_campaign_footer import prepare_footer
            document['html_sections']['footer']=prepare_footer(document['html_sections']['footer'])
        document.setdefault('campaign_key','sc_'+uuid.uuid4().hex)
        require(user,'crm_campaigns_manage'); validate_document(document)
        if not name.strip() or len(name)>150: raise ValueError('Use a campaign name of 1–150 characters.')
        requested_status={'NEEDS REVIEW':'NEEDS_REVIEW','TEST READY':'TEST_READY','CANCELED':'ARCHIVED'}.get(requested_status,requested_status)
        if requested_status not in ('DRAFT','NEEDS_REVIEW','TEST_READY'): raise ValueError('Production campaign states are unavailable.')
        checks=preflight(document,env)
        status=requested_status
        if status=='TEST_READY' and not checks['test_ready']: status='NEEDS_REVIEW'
        actor=str(user.get('id') or user.get('username') or '')
        with self.db() as conn:
            old={}
            if identity:
                old=conn.execute('SELECT * FROM crm_campaign_drafts WHERE id=%s FOR UPDATE',(identity,)).fetchone()
                if not old or old['version']!=version: raise ValueError('Campaign changed elsewhere. Reload before saving.')
                if old['archived_at']: raise ValueError('Archived campaigns are read-only. Duplicate to edit.')
                row=conn.execute('UPDATE crm_campaign_drafts SET name=%s,document=%s::jsonb,status=%s,version=version+1,updated_at=now(),tested_version=NULL WHERE id=%s RETURNING *',(name,json.dumps(document),status,identity)).fetchone()
            else:
                row=conn.execute('INSERT INTO crm_campaign_drafts(name,document,status,created_by) VALUES(%s,%s::jsonb,%s,%s) RETURNING *',(name,json.dumps(document),status,actor)).fetchone()
            actions=['campaign_duplicated' if duplicate_of else 'campaign_edited' if old else 'campaign_created']
            if old and old['document']['audience']!=document['audience']: actions.append('segment_changed')
            if old and any(old['document'].get(field)!=document.get(field) for field in ('content','blocks','custom_html','content_mode','html_sections')): actions.append('content_changed')
            if old and old['status']!=status: actions.append('compliance_status_changed')
            for action in actions:
                self._history(conn,row,action,actor,old)
            return row

    def _history(self,conn,row,action,actor,before):
        # Campaign content/config only. No credentials or resolved audience membership.
        conn.execute('INSERT INTO crm_campaign_history(campaign_id,version,action,actor,before_value,after_value) VALUES(%s,%s,%s,%s,%s::jsonb,%s::jsonb)',
                     (row['id'],row['version'],action,actor,json.dumps(before,default=str),json.dumps(row,default=str)))

    def duplicate(self,user,identity):
        row=self.draft(identity); doc=deepcopy(row['document']); doc['counts']={}; doc['copy_reviewed']=False
        doc['campaign_key']='sc_'+uuid.uuid4().hex
        return self.save(user,(row['name']+' — copy')[:150],doc,duplicate_of=str(identity))

    def archive(self,user,identity,version):
        require(user,'crm_campaigns_manage')
        with self.db() as conn:
            before=conn.execute('SELECT * FROM crm_campaign_drafts WHERE id=%s FOR UPDATE',(identity,)).fetchone()
            if not before or before['version']!=version: raise ValueError('Campaign changed elsewhere. Reload before archiving.')
            row=conn.execute("UPDATE crm_campaign_drafts SET archived_at=now(),status='ARCHIVED',version=version+1,updated_at=now() WHERE id=%s RETURNING *",(identity,)).fetchone()
            self._history(conn,row,'campaign_archived',str(user.get('id','')),before)

    def delete_draft(self,user,identity,version,*,confirmed=False,confirmed_name=''):
        """Delete only untouched authoring history; every delivery/reference fails closed."""
        require(user,'crm_campaigns_manage')
        if confirmed is not True:raise ValueError('Explicit draft deletion confirmation is required.')
        with self.db() as conn:
            row=conn.execute('SELECT * FROM crm_campaign_drafts WHERE id=%s FOR UPDATE',(identity,)).fetchone()
            if not row or row['version']!=version or row['name']!=confirmed_name:
                raise ValueError('Campaign changed. Reopen the deletion confirmation.')
            if row['status']!='DRAFT' or row['archived_at'] or row['last_tested_at'] or row['last_test_resend_id']:
                raise ValueError('Only an unsent DRAFT can be deleted. Archive this campaign instead.')
            for table,column in (('crm_internal_tests','campaign_id'),('crm_suppressions','campaign_reference'),
                                 ('crm_order_attribution','campaign_id'),('crm_marketing_sends','campaign_id')):
                if conn.execute(f'SELECT 1 FROM {table} WHERE {column}=%s LIMIT 1',(identity,)).fetchone():
                    raise ValueError('This campaign has retained test, delivery or compliance history. Archive it instead.')
            if conn.execute('SELECT 1 FROM crm_website_events WHERE campaign_key=%s LIMIT 1',(row['document'].get('campaign_key',''),)).fetchone():
                raise ValueError('This campaign has attribution events. Archive it instead.')
            # Restrictive foreign keys also protect concurrent/new reference types.
            conn.execute('DELETE FROM crm_campaign_history WHERE campaign_id=%s',(identity,))
            conn.execute('DELETE FROM crm_campaign_drafts WHERE id=%s',(identity,))
        from activity_log import record_activity_log
        receipt=record_activity_log(action_type='crm_draft_deleted',page='CRM & Marketing',
            message='Draft deleted: '+row['name'],entity_type='crm_campaign_draft',entity_id=str(identity),
            metadata={'name':row['name'],'version':row['version']},actor=str(user.get('id','')))
        return {'deleted':True,'audit_saved':bool(receipt)}

    def test_campaign(self, user, identity, version, *, recipient, confirmed, operation_id, env=None, session=None):
        require(user,'crm_campaigns_manage')
        import os_accounts
        from crm_resend_marketing import _send_admin_email, single_email, DeliveryError
        if not os_accounts.is_admin(user): raise PermissionError('Only an administrator can send a campaign test.')
        row=self.draft(identity)
        if not single_email(recipient):raise DeliveryError('invalid_recipient')
        allowlist=self.setting('sending')['value']['internal_recipients']
        if recipient.casefold() not in {v.casefold() for v in allowlist}:raise ValueError('Recipient is not in the configured internal-test allowlist. Ask an administrator to configure it in Settings.')
        if confirmed is not True:raise DeliveryError('confirmation_required')
        operation=str(uuid.UUID(str(operation_id)))
        if row['version']!=version or row['archived_at']: raise ValueError('Reload the current editable campaign before testing.')
        cfg=self.render_settings(env)
        if not preflight(row['document'],env,cfg)['test_ready']: raise ValueError('Resolve the test preflight items first.')
        rendered=render_campaign(row['document'],cfg);digest=fingerprint(row['document'],cfg)
        from crm_resend_marketing import get_resend_marketing_config_status
        delivery=get_resend_marketing_config_status(env)
        if not delivery['configured']:raise DeliveryError('configuration_missing')
        if delivery['marketing_enabled']:raise DeliveryError('stage_one_only')
        with self.db() as conn:
            attempt=conn.execute("INSERT INTO crm_internal_tests(id,campaign_id,campaign_version,render_hash,recipient,sender,actor,status) VALUES(%s,%s,%s,%s,%s,%s,%s,'REQUESTED') ON CONFLICT DO NOTHING RETURNING id",(operation,identity,version,digest,recipient.casefold(),delivery['sender'],str(user.get('id','')))).fetchone()
            if not attempt:
                prior=conn.execute('SELECT * FROM crm_internal_tests WHERE id=%s',(operation,)).fetchone()
                if str(prior['campaign_id'])!=str(identity) or prior['campaign_version']!=version or prior['render_hash']!=digest or prior['recipient']!=recipient.casefold():raise ValueError('Test operation already belongs to another saved request.')
                if prior['status']=='ACCEPTED':return {'message':'Test email accepted by Resend','message_id':prior['provider_id'],'accepted_at':str(prior['accepted_at']),'audit_saved':True}
                raise ValueError('This test was already attempted. Check its receipt; uncertain tests are never retried automatically.')
        try:
            result=_send_admin_email(user=user,recipient=recipient,confirmed=confirmed,operation_id=operation,
                                    env=env,session=session,message=rendered,
                                    campaign={'id':str(identity),'version':version,'render_hash':digest})
        except DeliveryError as exc:
            self.q('UPDATE crm_internal_tests SET status=%s,error_category=%s WHERE id=%s',('UNCERTAIN' if exc.category=='resend_unavailable' else 'FAILED',exc.category,operation))
            raise
        # Provider I/O is outside the lock. A concurrent edit cannot inherit TESTED.
        try:
            with self.db() as conn:
                conn.execute("UPDATE crm_internal_tests SET status='ACCEPTED',provider_id=%s,accepted_at=%s WHERE id=%s",(result['message_id'],result['accepted_at'],operation))
                current=conn.execute('SELECT * FROM crm_campaign_drafts WHERE id=%s FOR UPDATE',(identity,)).fetchone()
                same=current['version']==version and not current['archived_at']
                updated=conn.execute("UPDATE crm_campaign_drafts SET last_tested_at=%s,last_test_resend_id=%s,tested_version=%s,status=CASE WHEN %s THEN 'TESTED' ELSE status END WHERE id=%s RETURNING *",
                                     (result['accepted_at'],result['message_id'],version if same else None,same,identity)).fetchone()
                receipt={**updated,'test_receipt':result,'test_footer':cfg,'tested_document_version':version}
                self._history(conn,receipt,'campaign_test_sent',str(user.get('id','')),current)
            self.reconcile_events(result['message_id'])
        except Exception:
            result['audit_saved']=False
        return result

    def restore(self,user,identity,version):
        require(user,'crm_campaigns_manage')
        with self.db() as conn:
            before=conn.execute('SELECT * FROM crm_campaign_drafts WHERE id=%s FOR UPDATE',(identity,)).fetchone()
            if not before or before['version']!=version:raise ValueError('Campaign changed elsewhere. Reload first.')
            row=conn.execute("UPDATE crm_campaign_drafts SET archived_at=NULL,status='DRAFT',version=version+1,tested_version=NULL,updated_at=now() WHERE id=%s RETURNING *",(identity,)).fetchone()
            self._history(conn,row,'campaign_restored',str(user.get('id','')),before)
            return row
