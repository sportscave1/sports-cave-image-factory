"""Automation authoring; immutable publications reuse template version storage."""
from copy import deepcopy
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import timedelta
import json
import uuid
from crm_campaign_store import CampaignStore
from crm_navigation import require
from crm_automation_definition import FORMAT, new_flow, validate, native, status
from crm_logic import now, date

_DISPLAY_READS = ContextVar('automation_display_reads', default=None)


class AutomationStore(CampaignStore):
    email_mode='automation'
    step_id=None

    @contextmanager
    def display_read_scope(self):
        """Share one definition inside one render only, never across reruns.

        Fragment callbacks run after this context has exited and read fresh data.
        Worker threads have separate contexts. All database operations invalidate
        the memo before executing, including mutations and locked validation.
        """
        token = _DISPLAY_READS.set((self, {}))
        try:
            yield
        finally:
            _DISPLAY_READS.reset(token)

    @contextmanager
    def db(self):
        scope = _DISPLAY_READS.get()
        if scope is not None and scope[0] is self:
            scope[1].clear()
        with super().db() as conn:
            yield conn

    def flow(self, identity,*,row=None):
        identity=str(uuid.UUID(str(identity)))
        scope = _DISPLAY_READS.get()
        memo = scope[1] if scope is not None and scope[0] is self else None
        if row is None:
            row = memo.get(identity) if memo is not None else None
            if row is None: row = self.get('automations',identity)
        if row and str(row['id'])!=identity:raise ValueError('Automation is unavailable.')
        if not row or not native(row) or row['config'].get('deleted_at'): raise ValueError('Automation is unavailable.')
        from crm_automation_timing import single_delay
        row=deepcopy(row)
        row['config']['draft']=single_delay(row['config']['draft'])
        if memo is not None:
            memo.clear()  # One requested flow only; never grow a render-wide catalogue.
            memo[identity] = deepcopy(row)
        return row

    def display_snapshot(self, identity):
        """Reuse a validated row only during the parent's current render.

        Independent fragments have no context and must check freshness. Any DB
        operation clears the scope, so writes cannot reuse an earlier snapshot.
        """
        scope=_DISPLAY_READS.get()
        if scope is None or scope[0] is not self:return None
        return scope[1].get(str(identity))

    def create(self,user,trigger='welcome',name=None):
        require(user,'crm_automations_manage')
        from crm_automation_definition import TRIGGERS
        identity=str(uuid.uuid4())
        cfg={'format':FORMAT,'revision':1,'published_version':0,'draft':new_flow(trigger)}
        from crm_html_workspace import html_document
        from crm_middle_sections import middle_sections,commit_middle
        rendering=self.render_settings()
        doc=html_document(cfg['draft']['emails'][0]['document'])
        doc['html_sections']=self.default_sections(rendering)
        commit_middle(doc,middle_sections(doc))
        cfg['draft']['emails'][0]['document']=doc
        if trigger=='abandoned':
            from crm_automation_definition import email_step
            from crm_abandoned_checkout import apply_template
            from crm_checkout_template import load
            from crm_checkout_section import editable
            apply_template(doc,load(self)['html']);doc=editable(doc)
            cfg['draft']['emails']=[email_step(doc,delay) for delay in (7200,86400,172800)]
            for index,step in enumerate(cfg['draft']['emails']):
                step.update(name=('First Reminder','Second Reminder','Final Reminder')[index],enabled=True)
                step['document']['content']['subject']=('Your Sports Cave checkout','A reminder about your Sports Cave checkout','Your Sports Cave checkout link')[index]
            cfg['draft']['exit_on_purchase']=True
        return self.q("""INSERT INTO crm_automations(id,automation_key,name,trigger_type,config)
          VALUES(%s,%s,%s,%s,%s::jsonb) RETURNING *""",(identity,'native:'+identity,name or TRIGGERS[trigger][0],trigger,json.dumps(cfg)),True)

    def save_flow(self,user,identity,name,flow,revision):
        from crm_checkout_migration import migrate_flow
        from crm_automation_timing import single_delay
        require(user,'crm_automations_manage');flow=single_delay(migrate_flow(flow));validate(flow,draft=True)
        if not isinstance(name,str) or not name.strip() or len(name)>150: raise ValueError('Use an automation name of 1–150 characters.')
        with self.db() as conn:
            old=conn.execute('SELECT * FROM crm_automations WHERE id=%s FOR UPDATE',(identity,)).fetchone()
            if not old or not native(old) or old['config'].get('deleted_at') or status(old)=='ARCHIVED': raise ValueError('Automation is not editable.')
            cfg=deepcopy(old['config'])
            if cfg['draft']==flow and old['name']==name: return old
            if cfg['revision']!=revision: raise ValueError('A newer draft exists. Your local edits are retained; reload before saving.')
            cfg.update(draft=deepcopy(flow),revision=revision+1)
            return conn.execute('UPDATE crm_automations SET name=%s,config=%s::jsonb,updated_at=now() WHERE id=%s RETURNING *',(name,json.dumps(cfg),identity)).fetchone()

    def request_publish(self,user,identity,revision):
        from crm_automation_publication import request
        return request(self,user,identity,revision)

    def retry_delivery(self,user,identity,send_id):
        """Explicit retry of a known rejection, using the same immutable receipt."""
        require(user,'crm_automations_manage')
        with self.db() as conn:
            flow=conn.execute('SELECT * FROM crm_automations WHERE id=%s FOR UPDATE',(identity,)).fetchone()
            if not flow or not native(flow) or status(flow)!='ACTIVE':raise ValueError('Resume the flow before retrying.')
            item=conn.execute('SELECT enrollment_id FROM crm_marketing_sends WHERE id=%s AND NOT test_send',(send_id,)).fetchone()
            if not item:raise ValueError('Send unavailable.')
            journey=conn.execute('SELECT * FROM crm_automation_enrollments WHERE id=%s AND automation_id=%s FOR UPDATE',(item['enrollment_id'],identity)).fetchone()
            send=conn.execute('SELECT * FROM crm_marketing_sends WHERE id=%s FOR UPDATE',(send_id,)).fetchone()
            retryable=('provider_rejected','revalidation_unavailable')
            if not journey or send['status']!='FAILED' or send.get('provider_email_id') or send.get('error_code') not in retryable or send['step_index']!=journey['current_step']:
                raise ValueError('This send cannot be retried safely. Accepted or uncertain sends are never replayed.')
            if journey['status']!='ACTIVE' and not (journey['status']=='STOPPED' and journey['stop_reason'] in retryable):raise ValueError('Recipient has exited the flow.')
            conn.execute("UPDATE crm_automation_enrollments SET status='ACTIVE',retry_after=NULL,next_due_at=now(),stop_reason='' WHERE id=%s",(journey['id'],))
            conn.execute("UPDATE crm_marketing_sends SET status='PENDING',due_at=now(),lease_until=NULL WHERE id=%s",(send_id,))
        return True

    def publish(self,user,identity,revision,*,env=None):
        """Authoritative synchronous executor retained for internal/local callers.

        The editor only calls request_publish; durable jobs use the same validator.
        """
        from crm_automation_publication import publish_direct
        return publish_direct(self,user,identity,revision,env=env)

    def lifecycle(self,user,identity,action):
        require(user,'crm_automations_manage')
        with self.db() as conn:
            row=conn.execute('SELECT *,now() AS transition_at FROM crm_automations WHERE id=%s FOR UPDATE',(identity,)).fetchone()
            if not row or row['config'].get('deleted_at'): raise ValueError('Automation unavailable.')
            # Claims and due timestamps use the same database clock. Host clock
            # skew must not push already-due work into the future on resume.
            cfg=deepcopy(row['config']);current=status(row);target=row['status'];at=date(row['transition_at'])
            if action=='pause' and current=='ACTIVE': target='PAUSED';cfg['paused_at']=at.isoformat()
            elif action=='resume' and current=='PAUSED' and cfg.get('published_version'):
                target='ACTIVE'
                self._resume_due(conn,identity,cfg.get('paused_at') or at,at)
                cfg.pop('paused_at',None)
                conn.execute('UPDATE crm_automations SET activated_at=%s WHERE id=%s',(at,identity))
            elif action=='archive' and current in ('DRAFT','PAUSED'): target='PAUSED';cfg['archived_at']=at.isoformat()
            elif action=='delete' and current in ('DRAFT','ARCHIVED'):
                # Always tombstone: retain publications, journeys, sends and provider events.
                target='PAUSED';cfg['deleted_at']=at.isoformat()
            else: raise ValueError('Pause an active automation before archiving; only drafts and archived flows can be deleted.')
            return conn.execute('UPDATE crm_automations SET status=%s,config=%s::jsonb,updated_at=now() WHERE id=%s RETURNING *',(target,json.dumps(cfg),identity)).fetchone()

    @staticmethod
    def _resume_due(conn,identity,paused_at,at):
        # Preserve remaining wait; publication from paused uses the same semantics.
        shift=max(timedelta(0),at-date(paused_at))
        interval=str(shift.total_seconds())+' seconds'
        conn.execute("UPDATE crm_automation_enrollments SET next_due_at=next_due_at+%s::interval,updated_at=now() WHERE automation_id=%s AND status='ACTIVE'",(interval,identity))
        conn.execute("UPDATE crm_marketing_sends s SET due_at=s.due_at+%s::interval FROM crm_automation_enrollments e WHERE s.enrollment_id=e.id AND e.automation_id=%s AND s.status IN ('PENDING','CLAIMED')",(interval,identity))
        # Spread already-overdue work across normal worker cycles. Future
        # schedules retain their remaining wait instead of being reset.
        conn.execute("""WITH overdue AS (
          SELECT id,row_number() OVER(ORDER BY next_due_at,id)-1 AS position
          FROM crm_automation_enrollments WHERE automation_id=%s AND status='ACTIVE' AND next_due_at<%s)
          UPDATE crm_automation_enrollments e SET next_due_at=%s::timestamptz+(o.position/5)*interval '30 seconds'
          FROM overdue o WHERE e.id=o.id""",(identity,at,at))
        conn.execute("UPDATE crm_marketing_sends s SET due_at=GREATEST(s.due_at,e.next_due_at) FROM crm_automation_enrollments e WHERE s.enrollment_id=e.id AND e.automation_id=%s AND s.status IN ('PENDING','CLAIMED')",(identity,))

    def duplicate(self,user,identity):
        require(user,'crm_automations_manage')
        old=self.get('automations',str(uuid.UUID(str(identity))))
        if not old or old['config'].get('deleted_at'):raise ValueError('Automation unavailable.')
        if not native(old):
            # Legacy duplication stays an unpublished legacy definition; never
            # mutate its original live steps or enrollments.
            copy_id=str(uuid.uuid4())
            cfg=deepcopy(old['config']);cfg.pop('archived_at',None);cfg.pop('deleted_at',None)
            return self.q("INSERT INTO crm_automations(id,automation_key,name,trigger_type,status,steps,config) VALUES(%s,%s,%s,%s,'DRAFT',%s::jsonb,%s::jsonb) RETURNING *",
              (copy_id,'legacy-copy:'+copy_id,old['name']+' copy',old['trigger_type'],json.dumps(old['steps']),json.dumps(cfg)),True)
        row=self.create(user,old['config']['draft']['trigger'],old['name']+' copy')
        flow=deepcopy(old['config']['draft'])
        for step in flow['emails']: step['step_id']=str(uuid.uuid4())
        return self.save_flow(user,row['id'],row['name'],flow,1)

    def adopt(self,user,identity):
        """Explicitly convert an unused legacy draft, never a live journey."""
        require(user,'crm_automations_manage')
        from crm_automation_definition import TRIGGERS,email_step
        from crm_html_workspace import html_document
        with self.db() as conn:
            row=conn.execute('SELECT * FROM crm_automations WHERE id=%s FOR UPDATE',(identity,)).fetchone()
            if not row or row['status']!='DRAFT' or native(row) or row['trigger_type'] not in TRIGGERS:
                raise ValueError('Only an unused supported legacy draft can be converted.')
            if conn.execute('SELECT 1 FROM crm_automation_enrollments WHERE automation_id=%s LIMIT 1',(identity,)).fetchone():
                raise ValueError('This legacy flow has journey history; retain it for audit.')
            emails=[];delay=0
            for step in row['steps']:
                if step['type']=='delay':delay+=int(float(step['hours'])*3600)
                elif step['type']=='send':
                    template=conn.execute('SELECT * FROM crm_templates WHERE template_key=%s',(step['template'],)).fetchone()
                    if not template:raise ValueError('Legacy email template is unavailable.')
                    emails.append(email_step(html_document(self.template_document(template)),delay));delay=0
                elif step['type']!='stop':raise ValueError('Legacy flow contains unsupported steps.')
            flow=new_flow(row['trigger_type']);flow['emails']=emails or flow['emails'];validate(flow)
            cfg={'format':FORMAT,'revision':1,'published_version':0,'draft':flow,'legacy_config':row['config']}
            return conn.execute("UPDATE crm_automations SET config=%s::jsonb,steps='[]'::jsonb,updated_at=now() WHERE id=%s RETURNING *",(json.dumps(cfg),identity)).fetchone()

    def draft(self,identity,*,row=None):
        row=self.flow(identity) if row is None else row
        step=next((s for s in row['config']['draft']['emails'] if s['step_id']==self.step_id),None)
        if not step: raise ValueError('Email step changed. Reopen it.')
        from crm_checkout_migration import migrate
        doc=migrate(step['document']) if row['config']['draft']['trigger']=='abandoned' else deepcopy(step['document'])
        if row['config'].get('published_version') and 'html_sections' not in doc:
            from crm_automation_publish_state import published
            snapshot=published(self,row)
            previous=next((s['document'] for s in snapshot['emails'] if s['step_id']==self.step_id),{})
            if 'html_sections' in previous:doc['html_sections']=deepcopy(previous['html_sections'])
        return {'id':str(row['id']),'version':row['config']['revision'],'name':row['name'],
                'document':doc,'archived_at':row['config'].get('archived_at')}

    def preview_document(self,doc):
        from crm_recovery_discount import substitute
        doc=substitute(doc,preview=True)
        from crm_personalisation import present as has_personalisation,render as personalise,values_from_preview
        from crm_abandoned_checkout import preview_context
        from crm_checkout_preview import needs_checkout,document,sample
        self.preview_warning=''
        personalisation_trigger=getattr(self,'preview_trigger',None)
        if personalisation_trigger is None:
            personalisation_trigger=self.flow(self.draft_identity)['config']['draft']['trigger'] if has_personalisation(doc) else 'abandoned'
        if has_personalisation(doc) and personalisation_trigger!='abandoned' and not needs_checkout(doc):
            return personalise(doc,values_from_preview(None),trigger=personalisation_trigger),'Sample Preview'
        if not needs_checkout(doc):
            if not has_personalisation(doc):return doc,''
            import streamlit as st
            pin=st.session_state.get('_automation_checkout_pin') or {}
            data=preview_context(st.session_state,self.preview_shop,auto_refresh=False,slot='_automation_checkout_pin')[0] if pin else None
            return personalise(doc,values_from_preview(data)),('Selected checkout preview' if data else 'Sample Preview')
        from crm_frame_banner_template import present,resolve
        from crm_lifestyle_images import present as has_lifestyle,resolve as resolve_lifestyle,NO_CONTEXT
        from crm_abandoned_checkout import dynamic
        from crm_checkout_preview import legacy
        if (present(doc) or has_lifestyle(doc)) and not dynamic(doc) and not legacy(doc) and self.flow(self.draft_identity)['config']['draft']['trigger']!='abandoned':
            if has_lifestyle(doc):self.preview_warning=NO_CONTEXT
            return resolve_lifestyle(resolve(doc)),''
        import streamlit as st
        data,note=preview_context(st.session_state,self.preview_shop,auto_refresh=False,slot='_automation_checkout_pin')
        if not data:data=sample(doc)
        if doc.get('recovery_discount') and not data.get('preview_only'):
            from crm_recovery_discount import recovery_url
            data={**data,'recovery_url':recovery_url(data['recovery_url'],doc['recovery_discount']['code'])}
        from crm_automation_preview_cache import digest
        token=digest([doc,data])
        entries=st.session_state.get('_automation_hydrations',{})
        cached=entries.get(token)
        if cached is None:
            style_warnings=[]
            rendered,detected=document(doc,data,preview_warnings=style_warnings,shop=getattr(self,'preview_shop',None))
            cached={'token':token,'document':rendered,'legacy':detected,'style_warnings':style_warnings}
            entries={**entries,token:cached}
            if len(entries)>4:entries.pop(next(iter(entries)))
            st.session_state['_automation_hydrations']=entries
        rendered,detected=cached['document'],cached['legacy']
        if detected:self.preview_warning='Legacy checkout block needs migration · replace it with the native checkout products block before publishing.'
        if cached.get('style_warnings'):
            self.preview_warning+=' '+ ' '.join(cached['style_warnings'])
        if has_lifestyle(doc) and data.get('preview_only'):
            self.preview_warning+=' '+NO_CONTEXT
        label='Previewing: Sample abandoned checkout' if data.get('preview_only') else 'Previewing: '+data['label']+' · '+('cached latest abandoned checkout' if note else 'latest abandoned checkout')
        return (personalise(rendered,values_from_preview(data)) if has_personalisation(rendered) else rendered),label

    def test_document(self,doc,operation_id,*,recipient=None,customer=None,shop=None):
        if recipient is not None and self.flow(self.draft_identity)['config']['draft']['trigger']=='abandoned':
            from crm_test_checkout import document
            from crm_shopify import Shopify
            return document(shop or getattr(self,'preview_shop',None) or Shopify(),doc,recipient,customer)
        from crm_recovery_discount import substitute,selection as discount_selection
        if discount_selection(doc):
            from crm_discount_api import fresh
            from crm_shopify import Shopify
            discount=fresh(getattr(self,'preview_shop',None) or Shopify(),discount_selection(doc))
            if discount['status']!='ACTIVE':raise ValueError('Selected discount is not active. Refresh the offer before sending a test.')
            doc=substitute(doc,discount)
        else:doc=substitute(doc)
        from crm_personalisation import present as has_personalisation,render as personalise,values_from_preview
        from crm_abandoned_checkout import latest
        from crm_checkout_preview import needs_checkout,document,sample
        if not needs_checkout(doc) and not has_personalisation(doc):return doc
        if has_personalisation(doc) and not needs_checkout(doc):
            trigger=self.flow(self.draft_identity)['config']['draft']['trigger']
            if trigger!='abandoned':
                from crm_personalisation import resolve
                return personalise(doc,resolve({},customer,trigger=trigger) if customer else values_from_preview(None),trigger=trigger)
        from crm_frame_banner_template import present,resolve
        from crm_lifestyle_images import present as has_lifestyle,resolve as resolve_lifestyle
        from crm_abandoned_checkout import dynamic
        from crm_checkout_preview import legacy
        if (present(doc) or has_lifestyle(doc)) and not dynamic(doc) and not legacy(doc) and self.flow(self.draft_identity)['config']['draft']['trigger']!='abandoned':return resolve_lifestyle(resolve(doc))
        if self.flow(self.draft_identity)['config']['draft']['trigger']!='abandoned':raise ValueError('Checkout abandoned trigger required.')
        if getattr(self,'_checkout_test_operation',None)!=operation_id:
            from crm_shopify import Shopify
            try:data=latest(getattr(self,'preview_shop',None) or Shopify())
            except Exception:data=None
            if not data:data=sample(doc)
            self._checkout_test_data=data;self._checkout_test_operation=operation_id
        rendered=document(doc,self._checkout_test_data,test=True,shop=getattr(self,'preview_shop',None))[0] if needs_checkout(doc) else doc
        return personalise(rendered,values_from_preview(self._checkout_test_data)) if has_personalisation(rendered) else rendered

    def save(self,user,name,document,identity=None,version=None,**_):
        row=self.flow(identity);flow=deepcopy(row['config']['draft'])
        step=next(s for s in flow['emails'] if s['step_id']==self.step_id);step['document']=deepcopy(document)
        saved=self.save_flow(user,identity,name,flow,version)
        return self.draft(identity,row=saved)

    def _history(self,*args,**kwargs):
        # The shared test receipt itself is the immutable automation test audit.
        return None
