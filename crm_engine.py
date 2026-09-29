"""DB-driven marketing execution. Uses fresh Shopify state before every send."""
import hashlib
import json
import logging
import uuid
from datetime import timedelta
from crm_logic import now,date,email,consent,eligibility,recipient_hash,LiveFacts,matches,safe_url
from crm_resend import Config,Resend,MarketingDisabled
from crm_templates import render

class Engine:
    def __init__(self,store,shop,provider=None,config=None,clock=now):
        self.store,self.shop,self.config,self.clock=store,shop,config or Config(),clock
        self.provider=provider;self.owner=None
    def hold_lease(self):
        if self.owner and not self.store.lease(self.owner):raise RuntimeError('CRM worker lease changed.')
    def delivery(self):
        if self.provider is None:self.provider=Resend(self.config)
        return self.provider
    def validate(self,customer_id,enrollment=None):
        c=self.shop.customer(customer_id,fresh=True)
        ok,reason=eligibility(c,self.store.suppressed(customer_id,recipient_hash((c or {}).get('email'))))
        context={'first_name':(c or {}).get('firstName') or 'there','store_url':'https://www.sportscaveshop.com'}
        if not ok:return c,context,reason
        if enrollment:
            a=self.store.get('automations',enrollment['automation_id'])
            kind=a['trigger_type'];trigger=enrollment['trigger_shopify_id']
            if a['status']!='ACTIVE':return c,context,'automation_paused'
            if kind=='abandoned':
                checkout=self.shop.checkout(trigger,fresh=True)
                if not checkout or checkout.get('completedAt'):return c,context,'recovered'
                if (checkout.get('customer') or {}).get('id')!=c['id']:return c,context,'checkout_customer_changed'
                if not safe_url(checkout.get('abandonedCheckoutUrl')) or not checkout['lineItems']['nodes']:return c,context,'invalid_checkout'
                # Any newer order stops reminders, including payment-pending orders.
                # Customer.lastOrder is authoritative and avoids scanning order history.
                latest=c.get('lastOrder') or {}
                if date(latest.get('createdAt')) and date(latest['createdAt'])>=date(checkout['createdAt']):return c,context,'recovered'
                recent=self.shop.orders(c['id'],fresh=True)['nodes']
                if any(not o.get('cancelledAt') and date(o['createdAt'])>=date(checkout['createdAt']) for o in recent):return c,context,'recovered'
                context['checkout_url']=checkout['abandonedCheckoutUrl']
                context['products']=[{'title':p['title'],'quantity':p['quantity'],'price':p.get('originalUnitPriceSet',{}).get('shopMoney',{}).get('amount','')} for p in checkout['lineItems']['nodes']]
            elif kind=='post_purchase':
                order=self.shop.order(trigger,fresh=True)
                if not order or order.get('cancelledAt') or not order.get('fullyPaid') or (order.get('customer') or {}).get('id')!=c['id']:return c,context,'order_ineligible'
                context['order_name']=order['name']
            elif kind=='win_back':
                last=date((c.get('lastOrder') or {}).get('createdAt'))
                if not last or int(c['numberOfOrders'])<1 or last>self.clock()-timedelta(days=int(a['config'].get('days',180))):return c,context,'recent_purchase'
        return c,context,''
    def send_one(self):
        if not (self.config.enabled or self.config.tests_enabled):return False
        row=self.store.claim_send(allow_customer=self.config.enabled,allow_test=self.config.tests_enabled)
        if not row:return False
        submitting=False
        try:
            self.config.require_send(row['test_send'])
            enrollment=self.store.q('SELECT * FROM crm_automation_enrollments WHERE id=%s',(row['enrollment_id'],),True) if row['enrollment_id'] else None
            if row['test_send']:
                address=email(row['test_recipient']);context={'first_name':'Collector','store_url':'https://www.sportscaveshop.com','checkout_url':'https://www.sportscaveshop.com','order_name':'Preview'};reason=''
                if self.store.suppressed(None,recipient_hash(address)):reason='local_suppression'
            else:
                c,context,reason=self.validate(row['shopify_customer_id'],enrollment)
                address=email((c or {}).get('email'))
            if reason:
                self.store.finish_send(row,'BLOCKED',reason);return True
            if self.delivery().suppressed(address):
                self.store.suppress(recipient_hash(address),row['shopify_customer_id'],'suppressed','resend',address)
                self.store.finish_send(row,'BLOCKED','provider_suppression');return True
            content=self.store.template(row['template_id'],row['template_version'])
            if content.get('format')=='campaign_delivery_v1':
                from crm_campaign_schedule import overdue_reason
                late=overdue_reason(content,row,self.clock())
                if late:
                    self.store.finish_send(row,'BLOCKED',late);return True
                if content['document'].get('market_audience'):
                    from crm_campaign_markets import country,COUNTRIES
                    market=content['document']['market']
                    if market!='Global' and country(c)!=COUNTRIES[market]:
                        self.store.finish_send(row,'BLOCKED','market_changed');return True
                from crm_campaign_send import production_checks
                from crm_campaign_content import render_campaign
                if row['test_send'] or recipient_hash(address)!=row['recipient_hash']:
                    self.store.finish_send(row,'BLOCKED','recipient_changed');return True
                if not all(production_checks(content['document'],content['render_settings']).values()):
                    self.store.finish_send(row,'BLOCKED','production_readiness');return True
                unsubscribe=self.config.unsubscribe_url(row['id'])
                message=render_campaign(content['document'],content['render_settings'],unsubscribe_url=unsubscribe,production=True)
                message['unsubscribe_url']=unsubscribe
            else:
                optout=self.config.test_unsubscribe_url() if row['test_send'] else self.config.unsubscribe_url(row['id'])
                message=render(content,context,optout,self.config.logo_url,row['idempotency_key'])
            digest=hashlib.sha256(json.dumps({'to':address,**message},sort_keys=True).encode()).hexdigest()
            # Recheck local suppressions immediately before committing the submission claim.
            if self.store.suppressed(row['shopify_customer_id'],recipient_hash(address)):
                self.store.finish_send(row,'BLOCKED','local_suppression');return True
            if not row['test_send']:
                from crm_workspace_store import WorkspaceRecords
                records=WorkspaceRecords(self.store.connect)
                hours=content['document']['smart_hours'] if content.get('format')=='campaign_delivery_v1' else records.setting('sending')['value']['smart_hours']
                if records.frequency_blocked(recipient_hash(address),hours):
                    self.store.finish_send(row,'BLOCKED','smart_sending');return True
            self.hold_lease()
            if not self.store.begin_send(row,digest,recipient_hash(address)):return True
            submitting=True
            provider_id=self.delivery().send(address,message,row['idempotency_key'],row['test_send'])
            self.store.finish_send(row,'ACCEPTED',provider_id=provider_id)
        except MarketingDisabled:
            self.store.defer_send(row)
        except Exception as exc:
            if submitting:
                # No automatic replay after potentially accepted submission, including process crashes.
                from email_service import EmailDeliveryError
                known_rejection=isinstance(exc,EmailDeliveryError) and exc.status_code in (400,401,403,404,405,422,429)
                self.store.finish_send(row,'FAILED' if known_rejection else 'UNCERTAIN','provider_rejected' if known_rejection else 'submission_uncertain')
            else:self.store.defer_send(row)
            logging.getLogger(__name__).warning('crm_send_held phase=%s type=%s','submission' if submitting else 'revalidation',type(exc).__name__)
        return True
    def stop(self,enrollment,reason):
        status='RECOVERED' if reason=='recovered' else 'STOPPED'
        self.store.q('UPDATE crm_automation_enrollments SET status=%s,stop_reason=%s,last_checked_at=now(),updated_at=now() WHERE id=%s',(status,reason,enrollment['id']))
    def advance(self,enrollment):
        steps=enrollment['steps'];index=enrollment['current_step'];at=self.clock()
        if index>=len(steps):
            self.store.q("UPDATE crm_automation_enrollments SET status='COMPLETED',updated_at=now() WHERE id=%s",(enrollment['id'],));return
        step=steps[index];due=at
        if step['type']=='delay':due=(date(enrollment['trigger_at']) if index==0 else at)+timedelta(hours=float(step['hours']))
        elif step['type']=='stop':
            self.store.q("UPDATE crm_automation_enrollments SET status='COMPLETED',updated_at=now() WHERE id=%s",(enrollment['id'],));return
        else:
            c,_,reason=self.validate(enrollment['shopify_customer_id'],enrollment)
            if reason:self.stop(enrollment,reason);return
            if step['type']=='send':
                key='automation:'+str(enrollment['id'])+':'+str(index)
                receipt=self.store.q('SELECT * FROM crm_marketing_sends WHERE idempotency_key=%s',(key,),True)
                if not receipt:
                    template=self.store.q('SELECT * FROM crm_templates WHERE template_key=%s',(step['template'],),True)
                    if not template:raise ValueError('Workflow template missing.')
                    self.store.enqueue(key,c['id'],recipient_hash(c['email']),template,enrollment_id=enrollment['id'],step_index=index)
                    return
                if receipt['status'] in ('PENDING','CLAIMED','SUBMITTING'):return
                if receipt['status']!='ACCEPTED':self.stop(enrollment,receipt['error_code'] or 'send_held');return
        self.store.q('UPDATE crm_automation_enrollments SET current_step=%s,next_due_at=%s,last_checked_at=%s,updated_at=now() WHERE id=%s AND current_step=%s',(index+1,due,at,enrollment['id'],index))
    def campaign_page(self,campaign):
        if campaign['shopify_segment_id']:
            page=self.shop.members(campaign['shopify_segment_id'],after=campaign['recipient_cursor'],fresh=True);rules=None
        else:
            rules=self.store.get('segments',campaign['segment_definition_id'])['rules']
            page=self.shop.customers(after=campaign['recipient_cursor'],fresh=True)
        template={'id':campaign['template_id'],'version':campaign['template_version']}
        for c in page['nodes']:
            self.hold_lease()
            if rules and not matches(rules,LiveFacts(self.shop,c,self.store.editions,fresh=True),self.clock()):continue
            hashed=recipient_hash(c.get('email'))
            if not eligibility(c,self.store.suppressed(c['id'],hashed))[0]:continue
            self.store.enqueue('campaign:'+str(campaign['id'])+':'+c['id'],c['id'],hashed,template,campaign_id=campaign['id'])
        self.hold_lease()
        more=page['pageInfo'].get('hasNextPage',False)
        self.store.q("UPDATE crm_campaigns SET status=%s,recipient_cursor=%s,snapshot_at=COALESCE(snapshot_at,now()),updated_at=now() WHERE id=%s AND status IN ('BUILDING','SCHEDULED')",('BUILDING' if more else 'SENDING',page['pageInfo'].get('endCursor'),campaign['id']))
    def process_event(self,event):
        topic=event['topic'];customer_id=event['related_customer_id'];at=date(event['occurred_at'])
        if topic in ('customers/delete','customers/redact'):
            if customer_id:self.store.suppress(hashlib.sha256(customer_id.encode()).hexdigest(),customer_id,'redacted','shopify')
            return
        automations=[a for a in self.store.list('automations') if a['status']=='ACTIVE' and date(a['activated_at'])<=at]
        if topic=='customers_email_marketing_consent/update':
            c=self.shop.customer(customer_id,fresh=True)
            if consent(c)!='SUBSCRIBED':
                self.store.q("UPDATE crm_automation_enrollments SET status='STOPPED',stop_reason='consent_changed',updated_at=now() WHERE shopify_customer_id=%s AND status='ACTIVE'",(customer_id,));return
            changed=date(c['emailMarketingConsent'].get('consentUpdatedAt'))
            if not changed or abs((changed-at).total_seconds())>300:return
            for a in automations:
                if a['trigger_type']=='welcome':self.store.enroll(a,c['id'],c['id'],c['id']+':'+changed.isoformat(),changed)
        elif topic.startswith('orders/'):
            order=self.shop.order(event['object_id'],fresh=True)
            if order and not order.get('cancelledAt') and order.get('customer'):
                customer_id=order['customer']['id']
                self.store.q("UPDATE crm_automation_enrollments e SET status='RECOVERED',stop_reason='paid_order',updated_at=now() FROM crm_automations a WHERE e.automation_id=a.id AND a.trigger_type='abandoned' AND e.shopify_customer_id=%s AND e.trigger_at<=%s AND e.status='ACTIVE'",(customer_id,order['createdAt']))
                for a in automations:
                    if a['trigger_type']=='post_purchase' and order.get('fullyPaid') and date(order['createdAt'])>=date(a['activated_at']):self.store.enroll(a,customer_id,order['id'],order['id'],at)
        elif topic.startswith('checkouts/'):
            # Events merely expedite reconciliation; only abandonedCheckouts is eligibility authority.
            self.store.set_state('reconcile:abandoned',{})
    def reconcile(self,automation):
        kind=automation['trigger_type']
        if kind not in ('abandoned','win_back'):return
        key='reconcile:'+kind;state=self.store.state(key)
        if date(state.get('after_time')) and date(state['after_time'])>self.clock():return
        cursor=state.get('cursor')
        if kind=='abandoned':
            page=self.shop.checkouts(cursor,fresh=True)
            for checkout in page['nodes']:
                c=checkout.get('customer');created=date(checkout['updatedAt'])
                if c and not checkout.get('completedAt') and created>=date(automation['activated_at']) and created<=self.clock()-timedelta(hours=1):
                    self.store.enroll(automation,c['id'],checkout['id'],checkout['id'],created)
        else:
            page=self.shop.customers(cursor,fresh=True)
            for c in page['nodes']:
                last=date((c.get('lastOrder') or {}).get('createdAt'))
                if consent(c)=='SUBSCRIBED' and int(c.get('numberOfOrders',0))>0 and last and last<=self.clock()-timedelta(days=int(automation['config'].get('days',180))):
                    trigger=(c.get('lastOrder') or {})['id']
                    self.store.enroll(automation,c['id'],trigger,c['id']+':'+trigger,self.clock())
        more=page['pageInfo'].get('hasNextPage')
        self.store.set_state(key,{'cursor':page['pageInfo'].get('endCursor') if more else None,'after_time':(self.clock()+timedelta(seconds=2 if more else 300)).isoformat()})
    def tick(self,owner):
        if not self.store.lease(owner):return {'leader':False}
        self.owner=owner
        try:
            from crm_campaign_schedule import schedule_gate
            schedule_gate(self.store,self.config.enabled,self.clock())
            events=self.store.q("SELECT * FROM crm_webhook_events WHERE status='PENDING' ORDER BY received_at LIMIT 10")
            for event in events:
                if not self.store.lease(owner):return {'leader':False}
                try:
                    self.process_event(event)
                    self.store.q("UPDATE crm_webhook_events SET status='DONE',processed_at=now() WHERE provider=%s AND event_id=%s",(event['provider'],event['event_id']))
                except Exception:
                    self.store.q("UPDATE crm_webhook_events SET attempts=attempts+1,status=CASE WHEN attempts>=4 THEN 'FAILED' ELSE 'PENDING' END,error_code='source_unavailable' WHERE provider=%s AND event_id=%s",(event['provider'],event['event_id']))
            if self.config.enabled:
                for a in self.store.list('automations'):
                    if a['status']=='ACTIVE':
                        self.hold_lease();self.reconcile(a)
                campaigns=self.store.q("SELECT * FROM crm_campaigns WHERE status='BUILDING' OR (status='SCHEDULED' AND scheduled_at<=now()) ORDER BY created_at LIMIT 1")
                for campaign in campaigns:self.hold_lease();self.campaign_page(campaign)
                due=self.store.q("SELECT e.* FROM crm_automation_enrollments e JOIN crm_automations a ON a.id=e.automation_id WHERE e.status='ACTIVE' AND a.status='ACTIVE' AND e.next_due_at<=now() ORDER BY e.next_due_at LIMIT 20")
                for e in due:
                    self.hold_lease()
                    try:self.advance(e)
                    except Exception:self.store.q("UPDATE crm_automation_enrollments SET next_due_at=now()+interval '5 minutes' WHERE id=%s",(e['id'],))
            for _ in range(5):
                if not self.store.lease(owner) or not self.send_one():break
            self.store.q("UPDATE crm_campaigns c SET status='SENT',updated_at=now() WHERE status='SENDING' AND NOT EXISTS(SELECT 1 FROM crm_marketing_sends s WHERE s.campaign_id=c.id AND s.status IN ('PENDING','CLAIMED','SUBMITTING','UNCERTAIN'))")
            # Provider suppression writes are separate from send permissions; local stop-state already applies.
            from crm_consent_sync import reconcile_pending
            reconcile_pending(self.store,self.shop)
            if self.config.api_key:
                pending=self.store.q("SELECT p.*,s.provider_email_id FROM crm_suppressions p LEFT JOIN LATERAL (SELECT provider_email_id FROM crm_marketing_sends WHERE recipient_hash=p.recipient_hash AND provider_email_id IS NOT NULL ORDER BY created_at DESC LIMIT 1) s ON true WHERE NOT p.provider_synced AND (p.email_for_provider IS NOT NULL OR s.provider_email_id IS NOT NULL) ORDER BY p.updated_at LIMIT 5")
                for row in pending:
                    try:
                        address=row['email_for_provider']
                        if not address:address=self.delivery().recipient_for(row['provider_email_id'],row['recipient_hash'])
                        if not address:continue
                        self.delivery().suppress(address)
                        self.store.q('UPDATE crm_suppressions SET provider_synced=true,email_for_provider=NULL WHERE recipient_hash=%s',(row['recipient_hash'],))
                    except Exception:break
            self.store.set_state('worker_health',{'checked_at':self.clock().isoformat(),'status':'ok'})
            return {'leader':True}
        finally:
            self.store.release(owner);self.owner=None
