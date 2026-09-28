"""Persistent workspace records on existing server-only CRM database connection."""
from copy import deepcopy
from datetime import timedelta
import json
import re
import uuid
from crm_store import Store
from crm_navigation import require
from crm_campaign_content import settings, validate_document, new_document
from crm_email_blocks import legacy_blocks, PURPOSES
from crm_resend_marketing import single_email
from crm_tracking import asset_url, public_https
from crm_logic import now

DEFAULTS={'branding':{'logo':'','accent':'#b49450','font':'Arial','button_style':'Solid black','social_links':[]},
          'compliance':{'business':'Sports Cave','postal':'','postal_verified':False,'website':'https://www.sportscaveshop.com','privacy':'','contact':'','identity_confirmed':False},
          'sending':{'internal_recipients':[],'smart_hours':16},
          'prompts':{'default':'Premium collector-focused copy. Concise and truthful.'}}


def admin(user):
    import os_accounts
    if not os_accounts.is_admin(user):raise PermissionError('Only an active administrator can change delivery settings.')


def validate_setting(key,value):
    if key not in DEFAULTS or not isinstance(value,dict):raise ValueError('Unknown workspace setting.')
    if key=='prompts':
        if set(value)-({'default'}|set(PURPOSES)) or not all(isinstance(v,str) and len(v)<=6000 for v in value.values()):raise ValueError('Invalid prompt guidance.')
    elif set(value)!=set(DEFAULTS[key]):raise ValueError('Only non-secret workspace settings can be saved.')
    elif key=='sending':
        recipients=value['internal_recipients']
        if not isinstance(recipients,list) or len(recipients)>20 or any(not single_email(v) for v in recipients):raise ValueError('Enter at most 20 valid internal mailbox addresses.')
        if len(set(v.casefold() for v in recipients))!=len(recipients):raise ValueError('Remove duplicate internal recipients.')
        if type(value['smart_hours']) is not int or not 1<=value['smart_hours']<=168:raise ValueError('Smart Sending must be 1–168 hours.')
    elif key=='branding':
        if value['logo'] and not asset_url(value['logo']):raise ValueError('Use a durable public JPEG or PNG logo URL.')
        if not re.fullmatch(r'#[a-fA-F0-9]{6}',value['accent']) or value['font'] not in ('Arial','Georgia') or value['button_style'] not in ('Solid black','Outlined black'):raise ValueError('Use an approved email colour, font and button preset.')
        if not isinstance(value['social_links'],list) or len(value['social_links'])>5 or any(not public_https(v) for v in value['social_links']):raise ValueError('Use up to five confirmed HTTPS social links.')
    elif key=='compliance':
        if any(type(value[k]) is not bool for k in ('postal_verified','identity_confirmed')):raise ValueError('Confirm business identity explicitly.')
        for k in ('business','postal','website','privacy','contact'):
            if not isinstance(value[k],str) or len(value[k])>1000 or any(ord(c)<32 for c in value[k]):raise ValueError('Use short single-line business details.')
        if value['website'] and not public_https(value['website']):raise ValueError('Use a public HTTPS website.')
        if value['privacy'] and not public_https(value['privacy']):raise ValueError('Use a confirmed public HTTPS privacy page.')
        if value['contact'] and not single_email(value['contact']):raise ValueError('Use one valid business contact mailbox.')
    if len(json.dumps(value))>45000:raise ValueError('Setting too large.')


class WorkspaceRecords(Store):
    def setting(self,key):
        if key not in DEFAULTS:raise ValueError('Unknown setting.')
        row=self.q('SELECT * FROM crm_workspace_settings WHERE key=%s',(key,),True)
        if row:
            row['value']={**deepcopy(DEFAULTS[key]),**row['value']}
            return row
        return {'key':key,'value':deepcopy(DEFAULTS[key]),'version':0}

    def save_setting(self,user,key,value,version):
        admin(user);validate_setting(key,value)
        actor=str(user.get('id',''))
        with self.db() as conn:
            if version==0:
                row=conn.execute('INSERT INTO crm_workspace_settings(key,value,updated_by) VALUES(%s,%s::jsonb,%s) ON CONFLICT DO NOTHING RETURNING *',(key,json.dumps(value),actor)).fetchone()
            else:
                row=conn.execute('UPDATE crm_workspace_settings SET value=%s::jsonb,version=version+1,updated_by=%s,updated_at=now() WHERE key=%s AND version=%s RETURNING *',(json.dumps(value),actor,key,version)).fetchone()
            if not row:raise ValueError('Settings changed elsewhere. Reload before saving.')
            conn.execute('INSERT INTO crm_settings_history(key,version,value,actor) VALUES(%s,%s,%s::jsonb,%s)',(key,row['version'],json.dumps(value),actor))
            return row

    def render_settings(self,env=None):
        cfg=settings(env)
        business=self.setting('compliance')
        if business['version']:cfg.update(business['value'])
        cfg.update(self.setting('branding')['value'])
        return cfg

    def templates(self,archived=False):
        return self.q('SELECT * FROM crm_templates WHERE (archived_at IS NOT NULL)=%s ORDER BY updated_at DESC LIMIT 200',(archived,))

    def template_document(self,row):
        if row['content'].get('format')=='campaign_blocks_v1':return deepcopy(row['content']['document'])
        # Legacy template rows and versions are preserved, usable as explicit snapshots.
        doc=new_document();c=row['content']
        doc['content'].update({k:str(c.get(k,'')) for k in ('subject','headline','body','cta_label','cta_url')})
        doc['content']['preheader']=str(c.get('preview',''))
        doc['blocks']=legacy_blocks(doc['content']);doc['type']='Custom'
        return doc

    def save_design(self,user,name,document,identity=None,version=None):
        require(user,'crm_templates_manage');validate_document(document)
        if not name.strip() or len(name)>150:raise ValueError('Use a template name of 1–150 characters.')
        doc=new_document();doc['type']=document['type'];doc['market']=document['market']
        doc['content']=deepcopy(document['content']);doc['blocks']=deepcopy(document.get('blocks') or legacy_blocks(document['content']))
        content={'format':'campaign_blocks_v1','document':doc}
        with self.db() as conn:
            if identity:
                row=conn.execute('UPDATE crm_templates SET name=%s,content=%s::jsonb,version=version+1,updated_at=now() WHERE id=%s AND version=%s AND archived_at IS NULL RETURNING *',(name,json.dumps(content),identity,version)).fetchone()
            else:row=conn.execute("INSERT INTO crm_templates(template_key,name,kind,content) VALUES(%s,%s,'Campaign',%s::jsonb) RETURNING *",('design_'+uuid.uuid4().hex,name,json.dumps(content))).fetchone()
            if not row:raise ValueError('Template changed elsewhere or was archived. Reload before editing.')
            conn.execute('INSERT INTO crm_template_versions(template_id,version,content) VALUES(%s,%s,%s::jsonb)',(row['id'],row['version'],json.dumps(content)))
            return row

    def archive_design(self,user,identity,version):
        require(user,'crm_templates_manage')
        if not self.q('UPDATE crm_templates SET archived_at=now(),updated_at=now(),version=version+1 WHERE id=%s AND version=%s AND archived_at IS NULL RETURNING id',(identity,version),True):raise ValueError('Template changed elsewhere.')

    def recent_marketing_hashes(self,hours=16):
        # OS-only marketing receipts, including future campaign/flow dispatches.
        # Admin tests have their own table and legacy test sends are explicitly excluded.
        rows=self.q("SELECT DISTINCT recipient_hash FROM crm_marketing_sends WHERE test_send=false AND status='ACCEPTED' AND provider_email_id IS NOT NULL AND first_submitted_at>=%s",(now()-timedelta(hours=hours),))
        return {r['recipient_hash'] for r in rows}

    def frequency_blocked(self,hashed,hours=16):
        return bool(self.q("SELECT 1 FROM crm_marketing_sends WHERE recipient_hash=%s AND test_send=false AND status IN ('ACCEPTED','SUBMITTING','UNCERTAIN') AND first_submitted_at>=%s LIMIT 1",(hashed,now()-timedelta(hours=hours)),True))

    def active_suppression_hashes(self):
        rows=self.q('SELECT recipient_hash,shopify_customer_id FROM crm_suppressions WHERE active=true LIMIT 100001')
        if len(rows)>100000:raise ValueError('Suppression set exceeds interactive limit; production worker review required.')
        return {r['recipient_hash'] for r in rows},{r['shopify_customer_id'] for r in rows if r['shopify_customer_id']}

    def manual_suppression(self,user,address,reason='manual_unsubscribe'):
        admin(user)
        if not single_email(address) or reason not in ('manual_unsubscribe','admin_suppression'):raise ValueError('Enter one valid mailbox and suppression reason.')
        from crm_logic import recipient_hash
        self.suppress(recipient_hash(address),None,reason,'manual_support_action:'+str(user.get('id','')),address)
        self.set_state('last_manual_suppression',{'at':now().isoformat(),'actor':str(user.get('id','')),'reason':reason})

    def test_history(self,identity=None):
        where='WHERE t.campaign_id=%s' if identity else ''
        return self.q('SELECT t.*, EXISTS(SELECT 1 FROM crm_delivery_events e WHERE e.test_id=t.id AND e.event_type=\'email.delivered\') AS delivered FROM crm_internal_tests t '+where+' ORDER BY created_at DESC LIMIT 100',(identity,) if identity else ())

    def delivery_report(self,identity=None):
        tests=self.test_history(identity)
        args=(identity,) if identity else ()
        where=' WHERE t.campaign_id=%s' if identity else ''
        events=self.q('SELECT e.event_type,count(DISTINCT e.test_id) AS total FROM crm_delivery_events e JOIN crm_internal_tests t ON t.id=e.test_id'+where+' GROUP BY e.event_type',args)
        totals={r['event_type']:r['total'] for r in events}
        attempted=self.q('SELECT count(*) AS total,count(*) FILTER(WHERE status=\'ACCEPTED\') AS accepted,count(*) FILTER(WHERE status=\'FAILED\') AS failed FROM crm_internal_tests t'+where,args,True)
        return {'tests':tests,'events':totals,'counts':attempted}

    def reconcile_events(self,provider_id):
        # Early signed callbacks may predate the accepted response. Associate by stored
        # provider ID only, never provider-supplied campaign/recipient tags.
        with self.db() as conn:
            conn.execute('UPDATE crm_delivery_events e SET test_id=t.id FROM crm_internal_tests t WHERE e.provider_id=%s AND t.provider_id=e.provider_id AND e.send_id IS NULL',(provider_id,))
            conn.execute('UPDATE crm_delivery_events e SET send_id=s.id FROM crm_marketing_sends s WHERE e.provider_id=%s AND s.provider_email_id=e.provider_id AND s.test_send=false AND e.test_id IS NULL',(provider_id,))
            conn.execute('INSERT INTO crm_marketing_events(event_id,provider_email_id,event_type,recipient_hash,occurred_at) SELECT e.event_id,e.provider_id,e.event_type,s.recipient_hash,e.occurred_at FROM crm_delivery_events e JOIN crm_marketing_sends s ON s.id=e.send_id WHERE e.provider_id=%s ON CONFLICT DO NOTHING',(provider_id,))
            rows=conn.execute("SELECT s.recipient_hash,s.shopify_customer_id,e.event_type,e.hard_bounce FROM crm_delivery_events e JOIN crm_marketing_sends s ON s.id=e.send_id WHERE e.provider_id=%s AND (e.event_type='email.complained' OR e.hard_bounce)",(provider_id,)).fetchall()
        for row in rows:self.suppress(row['recipient_hash'],row['shopify_customer_id'],'spam_complaint' if row['event_type']=='email.complained' else 'hard_bounce','resend_verified')
