"""Small server-only marketing control store. No Shopify profile/content mirrors."""
import json
import uuid
from contextlib import contextmanager

TABLES={'segments':'crm_segment_definitions','templates':'crm_templates','automations':'crm_automations','campaigns':'crm_campaigns'}

class StoreUnavailable(RuntimeError):pass

class Store:
    def __init__(self, connect=None):self.connect=connect
    @contextmanager
    def db(self):
        try:
            if self.connect:conn=self.connect()
            else:
                from supabase_backend import connect
                conn=connect()
            with conn:
                yield conn
        except (ValueError,PermissionError):raise
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning('crm_control_store_unavailable type=%s',type(exc).__name__)
            code = getattr(exc, 'sqlstate', '') or ''
            if code in ('42P01', '42703'):
                detail = 'Required CRM tables or columns are missing. An administrator must verify and apply the reviewed CRM migrations to the configured database.'
            elif code == '42501':
                detail = 'The configured database account cannot access CRM storage. An administrator must check its permissions.'
            else:
                detail = 'The configured database could not complete this operation. Retry or ask an administrator to check connectivity and the CRM schema.'
            raise StoreUnavailable('CRM persistence is unavailable. ' + detail + ' No successful save is confirmed.') from None
    def q(self,sql,args=(),one=False):
        with self.db() as conn:
            cur=conn.execute(sql,args)
            if cur.description:
                return cur.fetchone() if one else cur.fetchall()
            return None
    def list(self,kind):
        where=" WHERE content->>'format' IS DISTINCT FROM 'campaign_brand_section_v1' AND content->>'format' IS DISTINCT FROM 'campaign_delivery_v1'" if kind=='templates' else ''
        return self.q('SELECT * FROM '+TABLES[kind]+where+' ORDER BY name LIMIT 500')
    def get(self,kind,object_id):return self.q('SELECT * FROM '+TABLES[kind]+' WHERE id=%s',(object_id,),True)
    def state(self,key):
        row=self.q('SELECT value FROM crm_runtime_state WHERE key=%s',(key,),True)
        return row['value'] if row else {}
    def set_state(self,key,value):
        self.q('INSERT INTO crm_runtime_state(key,value) VALUES(%s,%s::jsonb) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=now()',(key,json.dumps(value)))
    def invalidate(self):self.set_state('cache_version',{'version':str(uuid.uuid4())})
    def seed(self):
        from crm_logic import segment_seeds,automation_seeds
        from crm_templates import seeds
        with self.db() as conn:
            for row in segment_seeds():
                conn.execute('INSERT INTO crm_segment_definitions(system_key,name,rules) VALUES(%s,%s,%s::jsonb) ON CONFLICT(system_key) DO NOTHING',(row['system_key'],row['name'],json.dumps(row['rules'])))
            for row in seeds():
                template=conn.execute('INSERT INTO crm_templates(template_key,name,kind,content) VALUES(%s,%s,%s,%s::jsonb) ON CONFLICT(template_key) DO UPDATE SET template_key=excluded.template_key RETURNING id,version,content',(row['template_key'],row['name'],row['kind'],json.dumps(row['content']))).fetchone()
                conn.execute('INSERT INTO crm_template_versions(template_id,version,content) VALUES(%s,%s,%s::jsonb) ON CONFLICT DO NOTHING',(template['id'],template['version'],json.dumps(template['content'])))
            for row in automation_seeds():
                conn.execute('INSERT INTO crm_automations(automation_key,name,trigger_type,config,steps) VALUES(%s,%s,%s,%s::jsonb,%s::jsonb) ON CONFLICT(automation_key) DO NOTHING',(row['automation_key'],row['name'],row['trigger_type'],json.dumps(row['config']),json.dumps(row['steps'])))
    def save_segment(self,name,rules,actor,object_id=None):
        from crm_logic import validate_rules
        validate_rules(rules)
        return self.q('INSERT INTO crm_segment_definitions(id,name,rules,created_by) VALUES(%s,%s,%s::jsonb,%s) ON CONFLICT(id) DO UPDATE SET name=excluded.name,rules=excluded.rules,updated_at=now() RETURNING *',(object_id or str(uuid.uuid4()),name[:150],json.dumps(rules),str(actor)),True)
    def save_template(self,object_id,name,content):
        from crm_templates import validate
        validate(content)
        with self.db() as conn:
            row=conn.execute('UPDATE crm_templates SET name=%s,content=%s::jsonb,version=version+1,updated_at=now() WHERE id=%s RETURNING *',(name[:150],json.dumps(content),object_id)).fetchone()
            if not row:raise ValueError('Template not found.')
            conn.execute('INSERT INTO crm_template_versions(template_id,version,content) VALUES(%s,%s,%s::jsonb)',(row['id'],row['version'],json.dumps(content)))
            return row
    def template(self,object_id,version):return self.q('SELECT content FROM crm_template_versions WHERE template_id=%s AND version=%s',(object_id,version),True)['content']
    def save_automation(self,object_id,steps,config,status):
        from crm_logic import validate_steps
        validate_steps(steps)
        if status not in {'DRAFT','PAUSED','ACTIVE'}:raise ValueError('Invalid status.')
        self.q("UPDATE crm_automations SET steps=%s::jsonb,config=%s::jsonb,status=%s,activated_at=CASE WHEN %s='ACTIVE' AND activated_at IS NULL THEN now() ELSE activated_at END,updated_at=now() WHERE id=%s",(json.dumps(steps),json.dumps(config),status,status,object_id))
    def save_campaign(self,name,template,segment_id=None,definition_id=None):
        return self.q('INSERT INTO crm_campaigns(name,template_id,template_version,shopify_segment_id,segment_definition_id) VALUES(%s,%s,%s,%s,%s) RETURNING *',(name[:150],template['id'],template['version'],segment_id,definition_id),True)
    def schedule(self,object_id,at):
        return self.q("UPDATE crm_campaigns SET status='SCHEDULED',scheduled_at=%s,updated_at=now() WHERE id=%s AND status='DRAFT' RETURNING *",(at,object_id),True)
    def pause_campaign(self,object_id):self.q("UPDATE crm_campaigns SET resume_status=status,status='PAUSED',updated_at=now() WHERE id=%s AND status IN ('SCHEDULED','BUILDING','SENDING')",(object_id,))
    def resume_campaign(self,object_id):self.q("UPDATE crm_campaigns SET status=resume_status,resume_status=NULL,updated_at=now() WHERE id=%s AND status='PAUSED' AND resume_status IN ('SCHEDULED','BUILDING','SENDING')",(object_id,))
    def suppressed(self,customer_id,hashed):
        return bool(self.q('SELECT 1 FROM crm_suppressions WHERE recipient_hash=%s OR shopify_customer_id=%s LIMIT 1',(hashed,customer_id),True))
    def suppress(self,hashed,customer_id,reason,source,address=None):
        self.q('''INSERT INTO crm_suppressions(recipient_hash,shopify_customer_id,reason,source,email_for_provider)
         VALUES(%s,%s,%s,%s,%s) ON CONFLICT(recipient_hash) DO UPDATE SET reason=excluded.reason,
         source=excluded.source,email_for_provider=COALESCE(excluded.email_for_provider,crm_suppressions.email_for_provider),provider_synced=false,shopify_sync_state='PENDING',active=true,updated_at=now()''',(hashed,customer_id,reason,source,address))
        if customer_id:self.q("UPDATE crm_automation_enrollments SET status='STOPPED',stop_reason='suppressed',updated_at=now() WHERE shopify_customer_id=%s AND status='ACTIVE'",(customer_id,))
    def editions(self,customer_id,address=''):
        return self.q('''SELECT edition_number,edition_total,product_title,variant_title,certificate_file_url,shopify_order_name
         FROM edition_orders WHERE shopify_customer_id IN (%s,%s) OR (customer_email<>'' AND lower(customer_email)=lower(%s))
         ORDER BY id DESC LIMIT 100''',(customer_id,customer_id.rsplit('/',1)[-1],address))
    def history(self,customer_id):
        return self.q('''SELECT s.id,s.status,s.created_at,s.provider_email_id,c.name AS campaign,a.name AS automation
         FROM crm_marketing_sends s LEFT JOIN crm_campaigns c ON c.id=s.campaign_id
         LEFT JOIN crm_automation_enrollments e ON e.id=s.enrollment_id LEFT JOIN crm_automations a ON a.id=e.automation_id
         WHERE s.shopify_customer_id=%s ORDER BY s.created_at DESC LIMIT 100''',(customer_id,))
    def enroll(self,automation,customer_id,trigger_id,trigger_key,at):
        return self.q('''INSERT INTO crm_automation_enrollments(automation_id,shopify_customer_id,trigger_shopify_id,trigger_key,trigger_at,steps,next_due_at)
         VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s) ON CONFLICT(automation_id,trigger_key) DO NOTHING RETURNING *''',
         (automation['id'],customer_id,trigger_id,trigger_key,at,json.dumps(automation['steps']),at),True)
    def enqueue(self,key,customer_id,hashed,template,campaign_id=None,enrollment_id=None,step_index=None,test_recipient=None):
        return self.q('''INSERT INTO crm_marketing_sends(idempotency_key,shopify_customer_id,recipient_hash,template_id,template_version,campaign_id,enrollment_id,step_index,test_send,test_recipient)
         VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING *''',
         (key,customer_id,hashed,template['id'],template['version'],campaign_id,enrollment_id,step_index,bool(test_recipient),test_recipient),True)
    def claim_send(self,allow_customer=True,allow_test=True):
        # A crash after submission is never automatically replayed outside provider protection.
        self.q("UPDATE crm_marketing_sends SET status='UNCERTAIN',error_code='interrupted_submission',updated_at=now() WHERE status='SUBMITTING' AND lease_until<now()")
        return self.q('''WITH due AS (SELECT s.id FROM crm_marketing_sends s
         LEFT JOIN crm_campaigns c ON c.id=s.campaign_id LEFT JOIN crm_automation_enrollments e ON e.id=s.enrollment_id
         LEFT JOIN crm_automations a ON a.id=e.automation_id
         WHERE (s.status='PENDING' OR (s.status='CLAIMED' AND s.lease_until<now())) AND s.due_at<=now()
         AND ((s.test_send AND %s) OR (NOT s.test_send AND %s))
         AND (s.campaign_id IS NULL OR c.status='SENDING') AND (s.enrollment_id IS NULL OR (e.status='ACTIVE' AND a.status='ACTIVE'))
         ORDER BY s.due_at FOR UPDATE OF s SKIP LOCKED LIMIT 1)
         UPDATE crm_marketing_sends s SET status='CLAIMED',lease_token=gen_random_uuid(),lease_until=now()+interval '5 minutes',attempts=attempts+1
         FROM due WHERE s.id=due.id RETURNING s.*''',(allow_test,allow_customer),one=True)
    def begin_send(self,row,request_hash,hashed):
        return self.q("""UPDATE crm_marketing_sends SET status='SUBMITTING',request_hash=%s,recipient_hash=%s,first_submitted_at=now(),updated_at=now()
         WHERE id=%s AND status='CLAIMED' AND lease_token=%s AND lease_until>now()
         AND (campaign_id IS NULL OR EXISTS(SELECT 1 FROM crm_campaigns c WHERE c.id=campaign_id AND c.status='SENDING'))
         AND (enrollment_id IS NULL OR EXISTS(SELECT 1 FROM crm_automation_enrollments e JOIN crm_automations a ON a.id=e.automation_id
              WHERE e.id=enrollment_id AND e.status='ACTIVE' AND a.status='ACTIVE')) RETURNING *""",(request_hash,hashed,row['id'],row['lease_token']),True)
    def finish_send(self,row,status,code='',provider_id=None):
        result=self.q('''UPDATE crm_marketing_sends SET status=%s,error_code=%s,provider_email_id=%s,updated_at=now(),lease_until=NULL
         WHERE id=%s AND lease_token=%s RETURNING *''',(status,code,provider_id,row['id'],row['lease_token']),True)
        if status=='ACCEPTED' and provider_id:
            try:
                from crm_workspace_store import WorkspaceRecords
                WorkspaceRecords(self.connect).reconcile_events(provider_id)
            except Exception:
                # Acceptance is durable. Event processing must never cause a resend.
                import logging
                logging.getLogger(__name__).warning('crm_event_reconciliation_deferred')
        return result
    def defer_send(self,row):
        self.q("UPDATE crm_marketing_sends SET status=CASE WHEN attempts>=5 THEN 'FAILED' ELSE 'PENDING' END,error_code='revalidation_unavailable',due_at=now()+interval '5 minutes',lease_until=NULL WHERE id=%s AND lease_token=%s AND status='CLAIMED'",(row['id'],row['lease_token']))
    def receipt(self,send_id):return self.q('SELECT * FROM crm_marketing_sends WHERE id=%s',(send_id,),True)
    def lease(self,owner):
        return bool(self.q('''INSERT INTO crm_runtime_state(key,value) VALUES('worker_lease',jsonb_build_object('owner',%s::text,'until',extract(epoch from now())+300))
         ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=now() WHERE
         (crm_runtime_state.value->>'until')::numeric<extract(epoch from now()) OR crm_runtime_state.value->>'owner'=%s RETURNING key''',(owner,owner),True))
    def release(self,owner):self.q("DELETE FROM crm_runtime_state WHERE key='worker_lease' AND value->>'owner'=%s",(owner,))
    def webhook(self,provider,event_id,topic,object_id,customer_id,at):
        row=self.q('''INSERT INTO crm_webhook_events(provider,event_id,topic,object_id,related_customer_id,occurred_at)
          VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING event_id''',(provider,event_id,topic,object_id,customer_id,at),True)
        self.invalidate();return bool(row)
    def event(self,event_id,provider_id,event_type,hashed,at):
        return self.q('''INSERT INTO crm_marketing_events(event_id,provider_email_id,event_type,recipient_hash,occurred_at)
         VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING event_id''',(event_id,provider_id,event_type,hashed,at),True)
    def reports(self):
        summary=self.q('''SELECT (SELECT count(*) FROM crm_marketing_sends WHERE status='ACCEPTED' AND NOT test_send) AS sends,
         count(DISTINCT provider_email_id) FILTER(WHERE event_type='email.delivered') AS delivered,
         count(DISTINCT provider_email_id) FILTER(WHERE event_type='email.opened') AS opened,
         count(DISTINCT provider_email_id) FILTER(WHERE event_type='email.clicked') AS clicked,
         count(DISTINCT provider_email_id) FILTER(WHERE event_type='email.bounced') AS bounces,
         count(DISTINCT provider_email_id) FILTER(WHERE event_type='email.complained') AS complaints,
         (SELECT count(*) FROM crm_suppressions WHERE active=true AND reason IN ('unsubscribe','manual_unsubscribe','provider_unsubscribe')) AS unsubscribes
         FROM crm_marketing_events WHERE provider_email_id IN (SELECT provider_email_id FROM crm_marketing_sends WHERE NOT test_send)''',one=True)
        campaigns=self.q('''SELECT c.name,count(DISTINCT s.id) AS recipients,count(DISTINCT s.id) FILTER(WHERE s.status='ACCEPTED') AS sent,
         count(DISTINCT s.id) FILTER(WHERE v.event_type='email.delivered') AS delivered,count(DISTINCT s.id) FILTER(WHERE v.event_type='email.opened') AS opened,
         count(DISTINCT s.id) FILTER(WHERE v.event_type='email.clicked') AS clicked FROM crm_campaigns c
         LEFT JOIN crm_marketing_sends s ON s.campaign_id=c.id AND NOT s.test_send LEFT JOIN crm_marketing_events v ON v.provider_email_id=s.provider_email_id GROUP BY c.id,c.name''')
        automations=self.q('''SELECT a.name,count(DISTINCT e.id) AS entered,count(DISTINCT s.id) FILTER(WHERE s.status='ACCEPTED') AS sent,
         count(DISTINCT s.id) FILTER(WHERE v.event_type='email.delivered') AS delivered,count(DISTINCT s.id) FILTER(WHERE v.event_type='email.opened') AS opened,
         count(DISTINCT s.id) FILTER(WHERE v.event_type='email.clicked') AS clicked,count(DISTINCT e.id) FILTER(WHERE e.status='RECOVERED') AS recovered,
         count(DISTINCT e.id) FILTER(WHERE e.status='COMPLETED') AS completed FROM crm_automations a LEFT JOIN crm_automation_enrollments e ON e.automation_id=a.id
         LEFT JOIN crm_marketing_sends s ON s.enrollment_id=e.id AND NOT s.test_send LEFT JOIN crm_marketing_events v ON v.provider_email_id=s.provider_email_id GROUP BY a.id,a.name''')
        return summary,campaigns,automations
