"""Automation authoring; immutable publications reuse template version storage."""
from copy import deepcopy
from datetime import timedelta
import json
import uuid
from crm_campaign_store import CampaignStore
from crm_navigation import require
from crm_automation_definition import FORMAT, new_flow, validate, native, status, production_document
from crm_logic import now, date


class AutomationStore(CampaignStore):
    email_mode='automation'
    step_id=None

    def flow(self, identity):
        row=self.get('automations',str(uuid.UUID(str(identity))))
        if not row or not native(row) or row['config'].get('deleted_at'): raise ValueError('Automation is unavailable.')
        return row

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
        return self.q("""INSERT INTO crm_automations(id,automation_key,name,trigger_type,config)
          VALUES(%s,%s,%s,%s,%s::jsonb) RETURNING *""",(identity,'native:'+identity,name or TRIGGERS[trigger][0],trigger,json.dumps(cfg)),True)

    def save_flow(self,user,identity,name,flow,revision):
        from crm_checkout_migration import migrate_flow
        require(user,'crm_automations_manage');flow=migrate_flow(flow);validate(flow)
        if not isinstance(name,str) or not name.strip() or len(name)>150: raise ValueError('Use an automation name of 1–150 characters.')
        with self.db() as conn:
            old=conn.execute('SELECT * FROM crm_automations WHERE id=%s FOR UPDATE',(identity,)).fetchone()
            if not old or not native(old) or old['config'].get('deleted_at') or status(old)=='ARCHIVED': raise ValueError('Automation is not editable.')
            cfg=deepcopy(old['config'])
            if cfg['draft']==flow and old['name']==name: return old
            if cfg['revision']!=revision: raise ValueError('A newer draft exists. Your local edits are retained; reload before saving.')
            cfg.update(draft=deepcopy(flow),revision=revision+1)
            return conn.execute('UPDATE crm_automations SET name=%s,config=%s::jsonb,updated_at=now() WHERE id=%s RETURNING *',(name,json.dumps(cfg),identity)).fetchone()

    def publish(self,user,identity,revision,*,env=None):
        require(user,'crm_automations_manage')
        from crm_campaign_send import production_checks, validate_tracking
        from crm_campaign_sections import with_email_defaults
        from crm_email_size import validate_rendered_email
        cfg=self.render_settings(env)
        with self.db() as conn:
            row=conn.execute('SELECT * FROM crm_automations WHERE id=%s FOR UPDATE',(identity,)).fetchone()
            if not row or not native(row) or status(row)=='ARCHIVED' or row['config'].get('deleted_at'): raise ValueError('Automation is not publishable.')
            config=deepcopy(row['config'])
            if config['revision']!=revision: raise ValueError('Automation changed. Save and review again.')
            from crm_checkout_migration import migrate_flow
            flow=validate(migrate_flow(config['draft']));config['draft']=deepcopy(flow)
            version=config['published_version']+1;steps=[]
            from crm_automation_capabilities import require as require_trigger
            require_trigger(self,flow['trigger'])
            for index,step in enumerate(flow['emails']):
                doc=with_email_defaults(production_document(step['document']),cfg)
                from crm_abandoned_checkout import publication_document
                validation_doc=publication_document(doc,flow['trigger'])
                failures=[k for k,v in production_checks(validation_doc,cfg,env,reviewed_audience=True).items() if not v]
                if failures: raise ValueError('Email '+str(index+1)+' blocked: '+'; '.join(failures))
                validate_rendered_email(validate_tracking(validation_doc,cfg,str(uuid.uuid5(uuid.UUID(str(identity)),step['step_id']))))
                template_id=str(uuid.uuid5(uuid.UUID(str(identity)),step['step_id']))
                content={'format':'automation_delivery_v1','document':doc,'render_settings':cfg,
                         'automation_id':str(identity),'automation_version':version,'step_id':step['step_id'],
                         'trigger':flow['trigger'],'rules':flow['rules']}
                if flow.get('review_request'):
                    from reviews_submission import MARKER
                    if MARKER not in json.dumps(doc):raise ValueError('Add the review request link before publishing.')
                    content['review_request']=deepcopy(flow['review_request'])
                conn.execute("""INSERT INTO crm_templates(id,template_key,name,kind,version,content)
                  VALUES(%s,%s,%s,'Automation',%s,%s::jsonb) ON CONFLICT(id) DO UPDATE SET
                  version=excluded.version,content=excluded.content,updated_at=now()""",
                  (template_id,'automation-email:'+template_id,row['name']+' · Email '+str(index+1),version,json.dumps(content)))
                conn.execute('INSERT INTO crm_template_versions(template_id,version,content) VALUES(%s,%s,%s::jsonb)',(template_id,version,json.dumps(content)))
                steps.append({'type':'send','step_id':step['step_id'],'delay_seconds':step['delay_seconds'],
                              'template_id':template_id,'template_version':version,
                              'automation_version':version,'trigger':flow['trigger'],'rules':flow['rules']})
            # The immutable email versions / enrollment steps own content. The
            # entry policy only needs rules and re-entry, never the email bodies.
            config.update(published_version=version,published={k:deepcopy(flow[k]) for k in ('trigger','rules','reentry_days')},published_at=now().isoformat())
            config['published']['abandonment_seconds']=flow.get('abandonment_seconds',3600)
            if config.get('paused_at'):
                self._resume_due(conn,identity,config['paused_at'],now())
            config.pop('paused_at',None)
            return conn.execute("UPDATE crm_automations SET config=%s::jsonb,steps=%s::jsonb,trigger_type=%s,status='ACTIVE',activated_at=now(),updated_at=now() WHERE id=%s RETURNING *",
                (json.dumps(config),json.dumps(steps),flow['trigger'],identity)).fetchone()

    def lifecycle(self,user,identity,action):
        require(user,'crm_automations_manage')
        with self.db() as conn:
            row=conn.execute('SELECT * FROM crm_automations WHERE id=%s FOR UPDATE',(identity,)).fetchone()
            if not row or row['config'].get('deleted_at'): raise ValueError('Automation unavailable.')
            cfg=deepcopy(row['config']);current=status(row);target=row['status'];at=now()
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

    def draft(self,identity):
        row=self.flow(identity)
        step=next((s for s in row['config']['draft']['emails'] if s['step_id']==self.step_id),None)
        if not step: raise ValueError('Email step changed. Reopen it.')
        from crm_checkout_migration import migrate
        doc=migrate(step['document']) if row['config']['draft']['trigger']=='abandoned' else deepcopy(step['document'])
        return {'id':str(row['id']),'version':row['config']['revision'],'name':row['name'],
                'document':doc,'archived_at':row['config'].get('archived_at')}

    def preview_document(self,doc):
        from crm_abandoned_checkout import preview_context
        from crm_checkout_preview import needs_checkout,document,sample
        self.preview_warning=''
        if not needs_checkout(doc):return doc,''
        import streamlit as st
        data,note=preview_context(st.session_state,self.preview_shop,auto_refresh=False,slot='_automation_checkout_pin')
        if not data:data=sample(doc)
        from crm_automation_preview_cache import digest
        token=digest([doc,data])
        entries=st.session_state.get('_automation_hydrations',{})
        cached=entries.get(token)
        if cached is None:
            style_warnings=[]
            rendered,detected=document(doc,data,preview_warnings=style_warnings)
            cached={'token':token,'document':rendered,'legacy':detected,'style_warnings':style_warnings}
            entries={**entries,token:cached}
            if len(entries)>4:entries.pop(next(iter(entries)))
            st.session_state['_automation_hydrations']=entries
        rendered,detected=cached['document'],cached['legacy']
        if detected:self.preview_warning='Legacy checkout block needs migration · replace it with the native checkout products block before publishing.'
        if cached.get('style_warnings'):
            self.preview_warning+=' '+ ' '.join(cached['style_warnings'])
        label='Previewing: Sample abandoned checkout' if data.get('preview_only') else 'Previewing: '+data['label']+' · '+('cached latest abandoned checkout' if note else 'latest abandoned checkout')
        return rendered,label

    def test_document(self,doc,operation_id):
        from crm_abandoned_checkout import latest
        from crm_checkout_preview import needs_checkout,document,sample
        if not needs_checkout(doc):return doc
        if self.flow(self.draft_identity)['config']['draft']['trigger']!='abandoned':raise ValueError('Checkout abandoned trigger required.')
        if getattr(self,'_checkout_test_operation',None)!=operation_id:
            from crm_shopify import Shopify
            try:data=latest(getattr(self,'preview_shop',None) or Shopify())
            except Exception:data=None
            if not data:data=sample(doc)
            self._checkout_test_data=data;self._checkout_test_operation=operation_id
        return document(doc,self._checkout_test_data,test=True)[0]

    def save(self,user,name,document,identity=None,version=None,**_):
        row=self.flow(identity);flow=deepcopy(row['config']['draft'])
        step=next(s for s in flow['emails'] if s['step_id']==self.step_id);step['document']=deepcopy(document)
        self.save_flow(user,identity,name,flow,version)
        return self.draft(identity)

    def _history(self,*args,**kwargs):
        # The shared test receipt itself is the immutable automation test audit.
        return None
