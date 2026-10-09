"""Versioned authoring only. Never writes legacy sends/campaign queues or profiles."""
from copy import deepcopy
import json
import uuid
from crm_workspace_store import WorkspaceRecords
from crm_navigation import require
from crm_campaign_delete import VISIBLE
from crm_campaign_content import new_document, validate_document, preflight, settings, fingerprint, render_campaign


class CampaignStore(WorkspaceRecords):
    def history_counts(self):
        """One local aggregate for history badges; never reads audience/provider data."""
        return self.q("""SELECT count(*) FILTER(WHERE c.status IS DISTINCT FROM 'SENT') AS active,
          count(*) FILTER(WHERE c.status='SENT') AS sent,
          COALESCE(bool_or(c.status IN ('BUILDING','SENDING') OR
            (c.status='SCHEDULED' AND c.scheduled_at<=now()+interval '1 minute')),false) AS polling_active
          FROM crm_campaign_drafts d LEFT JOIN crm_campaigns c ON c.id=d.id
          WHERE d.archived_at IS NULL AND """+VISIBLE,one=True)

    def render_settings(self,env=None):
        cfg=super().render_settings(env)
        cfg['email_defaults']=self.default_sections(cfg)
        return cfg

    def list_drafts(self, archived=False, *, search='', status='All', market='All', offset=0, limit=100, metadata=False, working=False):
        fields="d.id,d.name,d.version,d.status,d.archived_at,d.updated_at,d.last_tested_at,jsonb_build_object('market',d.document->'market','send_timing',d.document->'send_timing') AS document" if metadata else 'd.*'
        return self.q("""SELECT """+fields+""",c.status AS delivery_status,
          GREATEST(d.updated_at,c.updated_at) AS activity_at,
          (SELECT s.error_code FROM crm_marketing_sends s WHERE s.campaign_id=d.id
           AND s.error_code IN ('schedule_missed','marketing_off_schedule') LIMIT 1) AS schedule_error
          FROM crm_campaign_drafts d LEFT JOIN crm_campaigns c ON c.id=d.id
          WHERE """+VISIBLE+""" AND (d.archived_at IS NOT NULL)=%s AND position(lower(%s) in lower(d.name))>0
          AND (%s='All' OR d.status=%s) AND (%s='All' OR d.document->>'market'=%s)
          AND (NOT %s OR c.status IS DISTINCT FROM 'SENT')
          ORDER BY GREATEST(d.updated_at,c.updated_at) DESC,d.id LIMIT %s OFFSET %s""",(archived,search,status,status,market,market,working,min(200,max(1,int(limit))),max(0,int(offset))))

    def draft(self, identity):
        row=self.q('SELECT * FROM crm_campaign_drafts WHERE id=%s',(identity,),True)
        if not row: raise ValueError('Campaign not found.')
        return row

    def history(self, identity):
        return self.q('SELECT action,actor,version,created_at FROM crm_campaign_history WHERE campaign_id=%s ORDER BY id DESC LIMIT 50',(identity,))

    def save(self, user, name, document, identity=None, version=None, *, requested_status='DRAFT', env=None, duplicate_of=None):
        document=deepcopy(document)
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
                if conn.execute('SELECT 1 FROM crm_campaigns WHERE id=%s',(identity,)).fetchone():raise ValueError('A queued or sent campaign is read-only. Duplicate to edit.')
                if old['archived_at']: raise ValueError('Archived campaigns are read-only. Duplicate to edit.')
                if old['name']==name and old['document']==document and old['status']==status:return old
                row=conn.execute('UPDATE crm_campaign_drafts SET name=%s,document=%s::jsonb,status=%s,version=version+1,updated_at=now(),tested_version=NULL WHERE id=%s RETURNING *',(name,json.dumps(document),status,identity)).fetchone()
            else:
                row=conn.execute('INSERT INTO crm_campaign_drafts(name,document,status,created_by) VALUES(%s,%s::jsonb,%s,%s) RETURNING *',(name,json.dumps(document),status,actor)).fetchone()
            actions=['campaign_duplicated' if duplicate_of else 'campaign_edited' if old else 'campaign_created']
            if old and old['document']['audience']!=document['audience']: actions.append('segment_changed')
            if old and any(old['document'].get(field)!=document.get(field) for field in ('content','blocks','custom_html','content_mode','html_sections','middle_sections')): actions.append('content_changed')
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
            if conn.execute("SELECT 1 FROM crm_campaigns WHERE id=%s AND status<>'SENT'",(identity,)).fetchone():
                raise ValueError('A scheduled or sending campaign cannot be archived.')
            row=conn.execute("UPDATE crm_campaign_drafts SET archived_at=now(),status='ARCHIVED',version=version+1,updated_at=now() WHERE id=%s RETURNING *",(identity,)).fetchone()
            self._history(conn,row,'campaign_archived',str(user.get('id','')),before)

    def delete_draft(self,user,identity,version,*,confirmed=False,confirmed_name=''):
        """Soft-delete an unsent draft while retaining every revision and audit record."""
        require(user,'crm_campaigns_manage')
        if confirmed is not True:raise ValueError('Explicit draft deletion confirmation is required.')
        with self.db() as conn:
            row=conn.execute('SELECT * FROM crm_campaign_drafts WHERE id=%s FOR UPDATE',(identity,)).fetchone()
            if not row or row['version']!=version or row['name']!=confirmed_name:
                raise ValueError('Campaign changed. Reopen the deletion confirmation.')
            if row['status']!='DRAFT' or row['archived_at'] or row['last_tested_at'] or row['last_test_resend_id']:
                raise ValueError('Only an unsent DRAFT can be deleted. Archive this campaign instead.')
            for table,column in (('crm_internal_tests','campaign_id'),('crm_suppressions','campaign_reference'),
                                 ('crm_order_attribution','campaign_id'),('crm_marketing_sends','campaign_id'),('crm_campaigns','id')):
                if conn.execute(f'SELECT 1 FROM {table} WHERE {column}=%s LIMIT 1',(identity,)).fetchone():
                    raise ValueError('This campaign has retained test, delivery or compliance history. Archive it instead.')
            if conn.execute('SELECT 1 FROM crm_website_events WHERE campaign_key=%s LIMIT 1',(row['document'].get('campaign_key',''),)).fetchone():
                raise ValueError('This campaign has attribution events. Archive it instead.')
            # Soft deletion retains every revision and audit record.
            deleted=conn.execute("UPDATE crm_campaign_drafts SET archived_at=now(),status='ARCHIVED',version=version+1,updated_at=now() WHERE id=%s RETURNING *",(identity,)).fetchone()
            self._history(conn,deleted,'campaign_deleted',str(user.get('id','')),row)
        from activity_log import record_activity_log
        receipt=record_activity_log(action_type='crm_draft_deleted',page='CRM & Marketing',
            message='Draft deleted: '+row['name'],entity_type='crm_campaign_draft',entity_id=str(identity),
            metadata={'name':row['name'],'version':row['version']},actor=str(user.get('id','')))
        return {'deleted':True,'audit_saved':bool(receipt)}

    def test_campaign(self, user, identity, version, *, recipient, confirmed, operation_id, env=None, session=None, shop=None):
        automation=getattr(self,'email_mode',None)=='automation'
        require(user,'crm_automations_manage' if automation else 'crm_campaigns_manage')
        from crm_resend_marketing import _send_admin_email, single_email, DeliveryError
        row=self.draft(identity)
        if not automation and self.q('SELECT 1 FROM crm_campaigns WHERE id=%s',(identity,),True):raise ValueError('Queued and sent campaigns are read-only. Duplicate to test.')
        if not single_email(recipient):raise DeliveryError('invalid_recipient')
        if confirmed is not True:raise DeliveryError('confirmation_required')
        operation=str(uuid.UUID(str(operation_id)))
        if row['version']!=version or row['archived_at']: raise ValueError('Reload the current editable campaign before testing.')
        cfg=self.render_settings(env)
        render_doc=row['document']
        if automation:
            self.draft_identity=identity;render_doc=self.test_document(render_doc,operation)
        checks=preflight(render_doc,env,cfg)
        if not checks['test_ready']:
            from crm_campaign_issues import CampaignValidationError
            raise CampaignValidationError(checks)
        digest=fingerprint(row['document'],cfg)
        from crm_resend_marketing import get_resend_marketing_config_status
        delivery=get_resend_marketing_config_status(env)
        if not delivery['configured']:raise DeliveryError('configuration_missing')
        # A repeated operation must use its recorded snapshot, never resolve fresh
        # facts and silently issue a second send after prices/counters change.
        catalogue_sections=[s for s in row['document'].get('middle_sections',[]) if s['type']=='catalogue' and s['visible']]
        prior=self.q('SELECT * FROM crm_internal_tests WHERE id=%s',(operation,),True)
        if prior:
            return self._test_receipt(prior,identity,version,digest,recipient,automation_step_id=self.step_id if automation else None)
        if catalogue_sections:
            from crm_catalogue import Catalogue, verify_catalogues
            from crm_shopify import Shopify
            verify_catalogues(row['document'], Catalogue(shop or Shopify()))
        from crm_test_recipient import test_recipient_url
        unsubscribe_url=test_recipient_url(self,recipient,shop=shop)
        rendered=render_campaign(render_doc,cfg,unsubscribe_url=unsubscribe_url,production=True,test_tracking=True)
        if automation:
            from crm_abandoned_checkout import reject_unresolved
            reject_unresolved(rendered['html']);reject_unresolved(rendered['text'])
        # Production-authentic content, still a manual TEST transport and receipt.
        rendered['subject']='[CAMPAIGN TEST] '+rendered['subject']
        rendered['unsubscribe_url']=unsubscribe_url
        with self.db() as conn:
            # Serialize per-user attempts across sessions, preserving receipt replay.
            actor=str(user.get('id',''))
            guard_key='campaign-test-rate:'+actor
            conn.execute("INSERT INTO crm_runtime_state(key,value) VALUES(%s,'{}'::jsonb) ON CONFLICT DO NOTHING",(guard_key,))
            conn.execute('SELECT key FROM crm_runtime_state WHERE key=%s FOR UPDATE',(guard_key,))
            if automation:
                attempt=conn.execute("INSERT INTO crm_internal_tests(id,automation_id,automation_step_id,campaign_version,render_hash,recipient,sender,actor,status) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'REQUESTED') ON CONFLICT DO NOTHING RETURNING id",(operation,identity,self.step_id,version,digest,recipient.casefold(),delivery['sender'],str(user.get('id','')))).fetchone()
            else:
                attempt=conn.execute("INSERT INTO crm_internal_tests(id,campaign_id,campaign_version,render_hash,recipient,sender,actor,status) VALUES(%s,%s,%s,%s,%s,%s,%s,'REQUESTED') ON CONFLICT DO NOTHING RETURNING id",(operation,identity,version,digest,recipient.casefold(),delivery['sender'],str(user.get('id','')))).fetchone()
            if not attempt:
                prior=conn.execute('SELECT * FROM crm_internal_tests WHERE id=%s',(operation,)).fetchone()
                return self._test_receipt(prior,identity,version,digest,recipient,automation_step_id=self.step_id if automation else None)
            recent=conn.execute("SELECT count(*) AS n FROM crm_internal_tests WHERE actor=%s AND created_at>now()-interval '1 hour'",(actor,)).fetchone()
            if recent['n']>60:raise ValueError('Test email limit reached (60 per hour). Please try again later.')
            if catalogue_sections:
                # Retain content/facts without putting a customer unsubscribe token
                # into campaign history. The provider alone receives the live URL.
                from html import escape
                snapshot={k:v.replace(escape(unsubscribe_url,quote=True),'{{UNSUBSCRIBE_URL}}').replace(unsubscribe_url,'{{UNSUBSCRIBE_URL}}')
                          for k,v in rendered.items() if k!='unsubscribe_url'}
                self._history(conn,{**row,'outbound_snapshot':{'operation_id':operation,
                    'rendered':snapshot,'production_unsubscribe_url':True,'sections':deepcopy(row['document']['middle_sections']),
                    'render_hash':digest}},'campaign_test_snapshot',str(user.get('id','')), {})
        try:
            result=_send_admin_email(user=user,recipient=recipient,confirmed=confirmed,operation_id=operation,
                                    env=env,session=session,message=rendered,
                                    campaign={'id':str(identity),'version':version,'render_hash':digest,**({'email_mode':'automation','step_id':str(self.step_id)} if automation else {})})
        except DeliveryError as exc:
            self.q('UPDATE crm_internal_tests SET status=%s,error_category=%s WHERE id=%s',('UNCERTAIN' if exc.category=='resend_unavailable' else 'FAILED',exc.category,operation))
            raise
        # Provider I/O is outside the lock. A concurrent edit cannot inherit TESTED.
        try:
            with self.db() as conn:
                conn.execute("UPDATE crm_internal_tests SET status='ACCEPTED',provider_id=%s,accepted_at=%s WHERE id=%s",(result['message_id'],result['accepted_at'],operation))
                if not automation:
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

    @staticmethod
    def _test_receipt(prior,identity,version,digest,recipient,*,automation_step_id=None):
        source=prior.get('automation_id') if automation_step_id else prior['campaign_id']
        if (str(source)!=str(identity) or (automation_step_id and str(prior.get('automation_step_id'))!=str(automation_step_id)) or prior['campaign_version']!=version
                or prior['render_hash']!=digest or prior['recipient']!=recipient.casefold()):
            raise ValueError('Test operation already belongs to another saved request.')
        if prior['status']=='ACCEPTED':
            return {'message':'Test email accepted by Resend','message_id':prior['provider_id'],
                    'accepted_at':str(prior['accepted_at']),'audit_saved':True}
        raise ValueError('This test was already attempted. Check its receipt; uncertain tests are never retried automatically.')

    def restore(self,user,identity,version):
        require(user,'crm_campaigns_manage')
        with self.db() as conn:
            before=conn.execute('SELECT * FROM crm_campaign_drafts WHERE id=%s FOR UPDATE',(identity,)).fetchone()
            if not before or before['version']!=version:raise ValueError('Campaign changed elsewhere. Reload first.')
            row=conn.execute("UPDATE crm_campaign_drafts SET archived_at=NULL,status='DRAFT',version=version+1,tested_version=NULL,updated_at=now() WHERE id=%s RETURNING *",(identity,)).fetchone()
            self._history(conn,row,'campaign_restored',str(user.get('id','')),before)
            return row
