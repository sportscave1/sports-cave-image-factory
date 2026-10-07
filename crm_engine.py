"""DB-driven delivery: frozen native campaigns and fresh automation validation."""
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
        automation=self.store.get('automations',enrollment['automation_id']) if enrollment else None
        checkout_flow=bool(automation and automation['trigger_type']=='abandoned')
        if checkout_flow and not (c or {}).get('email'):return c,context,'missing_email'
        if not ok and not checkout_flow:return c,context,reason
        if enrollment:
            a=automation
            if not a:return c,context,'automation_unavailable'
            kind=a['trigger_type'];trigger=enrollment['trigger_shopify_id']
            if a['status']!='ACTIVE':return c,context,'automation_paused'
            frozen=enrollment['steps'][0] if enrollment.get('steps') else {}
            if frozen.get('automation_version'):
                current=enrollment['steps'][enrollment['current_step']] if enrollment['current_step']<len(enrollment['steps']) else None
                if not current or not any(s.get('step_id')==current['step_id'] for s in a['steps']):return c,context,'automation_step_removed'
                from crm_automation_definition import qualifies
                kind=frozen['trigger']
                from crm_automation_capabilities import require as require_trigger
                require_trigger(self.store,kind)
                identity_rules=[r for r in frozen['rules'] if r['field'] in ('market','customer_country')]
                if not qualifies({'rules':identity_rules},c):return c,context,'automation_rules_changed'
            if kind=='abandoned':
                if enrollment.get('checkout_key'):
                    state=self.store.q('SELECT status FROM crm_shopify_checkouts WHERE checkout_key=%s',(enrollment['checkout_key'],),True)
                    if not state or state['status']=='RECOVERED':return c,context,'recovered'
                checkout=self.shop.checkout(trigger,fresh=True)
                if not checkout:raise ValueError('Checkout verification unavailable')
                if date(checkout.get('completedAt')):
                    if enrollment.get('checkout_key'):
                        self.store.q("UPDATE crm_shopify_checkouts SET analytics=analytics||%s::jsonb WHERE checkout_key=%s",(json.dumps({'completed_at':checkout['completedAt']}),enrollment['checkout_key']))
                    return c,context,'recovered'
                if (checkout.get('customer') or {}).get('id')!=c['id']:
                    from crm_checkout_identity import recipient
                    ledger=self.store.q('SELECT * FROM crm_shopify_checkouts WHERE checkout_key=%s',(enrollment.get('checkout_key'),),True)
                    verified=recipient(self.shop,self.store,checkout,ledger or {})
                    if not verified or verified['id']!=c['id']:return c,context,'checkout_customer_changed'
                    checkout={**checkout,'customer':c}
                if enrollment.get('checkout_key'):
                    from crm_shopify_automation_events import key_from_recovery_url
                    import os
                    if key_from_recovery_url(checkout.get('abandonedCheckoutUrl'),os.getenv('SHOPIFY_STORE_DOMAIN',''))!=enrollment['checkout_key']:
                        return c,context,'checkout_identity_changed'
                if not safe_url(checkout.get('abandonedCheckoutUrl')) or not checkout['lineItems']['nodes']:return c,context,'invalid_checkout'
                # Any newer order stops reminders, including payment-pending orders.
                # Customer.lastOrder is authoritative and avoids scanning order history.
                if not enrollment.get('checkout_key'):
                    latest=c.get('lastOrder') or {}
                    if date(latest.get('createdAt')) and date(latest['createdAt'])>=date(checkout['createdAt']):return c,context,'recovered'
                    recent=self.shop.orders(c['id'],fresh=True)['nodes']
                    if any(not o.get('cancelledAt') and date(o['createdAt'])>=date(checkout['createdAt']) for o in recent):return c,context,'recovered'
                from crm_checkout_eligibility import recovery_eligibility,policy
                ok,reason=recovery_eligibility(checkout,c,policy(self.store),suppressed=self.store.suppressed(c['id'],recipient_hash(c.get('email'))))
                if not ok:return c,context,reason
                context['checkout_url']=checkout['abandonedCheckoutUrl']
                context['_checkout']=checkout;context['_checkout_id']=trigger
                context['products']=[{'title':p['title'],'quantity':p['quantity'],'price':p.get('originalUnitPriceSet',{}).get('shopMoney',{}).get('amount','')} for p in checkout['lineItems']['nodes']]
                if frozen.get('automation_version'):
                    from crm_automation_rule_facts import checkout_facts
                    if not qualifies({'rules':frozen['rules']},c,checkout_facts(checkout)):return c,context,'automation_rules_changed'
            elif kind in ('post_purchase','fulfilled'):
                order=self.shop.order(trigger,fresh=True)
                if not order or order.get('cancelledAt') or (kind=='post_purchase' and not order.get('fullyPaid')) or (order.get('customer') or {}).get('id')!=c['id']:return c,context,'order_ineligible'
                if kind=='fulfilled' and order.get('displayFulfillmentStatus')!='FULFILLED':return c,context,'order_not_fulfilled'
                context['order_name']=order['name']
                if frozen.get('automation_version'):
                    from crm_automation_rule_facts import order_facts
                    if not qualifies({'rules':frozen['rules']},c,order_facts(self.shop,order,frozen['rules'])):return c,context,'automation_rules_changed'
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
                if reason=='automation_paused':
                    self.store.release_paused_send(row);return True
                self.store.finish_send(row,'BLOCKED',reason);return True
            if not row['test_send']:
                from crm_native_unsubscribe import native_unsubscribe_url
                unsubscribe=native_unsubscribe_url(c,recovery=bool(context.get('_checkout')))
                if not unsubscribe:
                    self.store.finish_send(row,'BLOCKED','missing_shopify_marketing_unsubscribe_url');return True
            if self.delivery().suppressed(address):
                self.store.suppress(recipient_hash(address),row['shopify_customer_id'],'suppressed','resend',address)
                self.store.finish_send(row,'BLOCKED','provider_suppression');return True
            content=self.store.template(row['template_id'],row['template_version'])
            if content.get('format')=='automation_delivery_v1':
                if row['test_send'] or recipient_hash(address)!=row['recipient_hash']:
                    self.store.finish_send(row,'BLOCKED','recipient_changed');return True
                from crm_automation_runtime import render as render_automation
                if content.get('review_request'):
                    from reviews_submission import prepare_email
                    from reviews_store import ReviewsStore
                    content=prepare_email(content,row,enrollment,self.shop,ReviewsStore(self.store.connect))
                from crm_abandoned_checkout import dynamic,complete
                if dynamic(content['document']):context['_checkout']=complete(self.shop,context.get('_checkout'))
                message=render_automation(content,row,unsubscribe,context)
            elif content.get('format')=='campaign_delivery_v1':
                from crm_campaign_schedule import overdue_reason
                late=overdue_reason(content,row,self.clock())
                if late:
                    self.store.finish_send(row,'BLOCKED',late);return True
                if content['document'].get('market_audience') and not content.get('audience_snapshot_id'):
                    from crm_campaign_markets import country,COUNTRIES
                    market=content['document']['market']
                    if market!='Global' and country(c)!=COUNTRIES[market]:
                        self.store.finish_send(row,'BLOCKED','market_changed');return True
                from crm_campaign_send import production_checks
                from crm_campaign_content import render_campaign
                if row['test_send'] or recipient_hash(address)!=row['recipient_hash']:
                    self.store.finish_send(row,'BLOCKED','recipient_changed');return True
                if not all(production_checks(content['document'],content['render_settings'],reviewed_audience=bool(content.get('audience_snapshot_id'))).values()):
                    self.store.finish_send(row,'BLOCKED','production_readiness');return True
                campaign=self.store.q('SELECT campaign_send_id FROM crm_campaigns WHERE id=%s',(row['campaign_id'],),True)
                if not campaign:raise ValueError('Campaign send identity missing.')
                message=render_campaign(content['document'],content['render_settings'],unsubscribe_url=unsubscribe,production=True,
                                        campaign_id=str(row['campaign_id']),send_id=str(campaign['campaign_send_id']))
                from crm_email_size import validate_rendered_email
                try:validate_rendered_email(message)
                except ValueError:
                    self.store.finish_send(row,'BLOCKED','email_size_limit');return True
                message['unsubscribe_url']=unsubscribe
            else:
                optout=self.config.test_unsubscribe_url() if row['test_send'] else unsubscribe
                message=render(content,context,optout,self.config.logo_url,row['idempotency_key'])
            message['unsubscribe_one_click']=False  # Shopify documents navigation, not RFC 8058 POST.
            digest=hashlib.sha256(json.dumps({'to':address,**message},sort_keys=True).encode()).hexdigest()
            # Recheck local suppressions immediately before committing the submission claim.
            if self.store.suppressed(row['shopify_customer_id'],recipient_hash(address)):
                self.store.finish_send(row,'BLOCKED','local_suppression');return True
            if not row['test_send']:
                from crm_workspace_store import WorkspaceRecords
                records=WorkspaceRecords(self.store.connect)
                hours=content['document']['smart_hours'] if content.get('format') in ('campaign_delivery_v1','automation_delivery_v1') else records.setting('sending')['value']['smart_hours']
                if records.frequency_blocked(recipient_hash(address),hours):
                    self.store.finish_send(row,'BLOCKED','smart_sending');return True
            self.hold_lease()
            if not self.store.begin_send(row,digest,recipient_hash(address)):
                if row.get('enrollment_id'):self.store.release_paused_send(row)
                return True
            submitting=True
            provider_id=self.delivery().send(address,message,row['idempotency_key'],row['test_send'])
            self.store.finish_send(row,'ACCEPTED',provider_id=provider_id)
            if enrollment and enrollment.get('checkout_key'):
                try:self.store.set_state('checkout-send-attempt:'+str(row['id'])+':'+str(row['attempts']),{'status':'ACCEPTED','at':self.clock().isoformat(),'enrollment_id':str(enrollment['id'])})
                except Exception:logging.getLogger(__name__).warning('checkout_send_audit_deferred send_id=%s',row['id'])
        except MarketingDisabled:
            self.store.defer_send(row)
        except Exception as exc:
            if submitting:
                # No automatic replay after potentially accepted submission, including process crashes.
                from email_service import EmailDeliveryError
                known_rejection=isinstance(exc,EmailDeliveryError) and exc.status_code in (400,401,403,404,405,422,429)
                if known_rejection and exc.status_code==429 and enrollment and enrollment.get('checkout_key') and row['attempts']<5:
                    self.store.q("UPDATE crm_marketing_sends SET status='PENDING',error_code='provider_rate_limited',due_at=now()+interval '5 minutes',lease_until=NULL WHERE id=%s AND lease_token=%s AND status='SUBMITTING'",(row['id'],row['lease_token']))
                else:self.store.finish_send(row,'FAILED' if known_rejection else 'UNCERTAIN','provider_rejected' if known_rejection else 'submission_uncertain')
                if enrollment and enrollment.get('checkout_key'):
                    self.store.set_state('checkout-send-attempt:'+str(row['id'])+':'+str(row['attempts']),{'status':'REJECTED' if known_rejection else 'UNCERTAIN','at':self.clock().isoformat(),'enrollment_id':str(enrollment['id']),'http_status':getattr(exc,'status_code',None)})
            else:self.store.defer_send(row)
            logging.getLogger(__name__).warning('crm_send_held phase=%s type=%s','submission' if submitting else 'revalidation',type(exc).__name__)
        return True
    def stop(self,enrollment,reason):
        status='RECOVERED' if reason=='recovered' else 'STOPPED'
        if reason=='recovered' and enrollment.get('checkout_key'):
            from crm_shopify_automation_events import recover
            self.store.q("UPDATE crm_shopify_checkouts SET status='RECOVERED',updated_at=now() WHERE checkout_key=%s",(enrollment['checkout_key'],))
            recover(self.store,enrollment['checkout_key']);return
        self.store.q('UPDATE crm_automation_enrollments SET status=%s,stop_reason=%s,last_checked_at=now(),updated_at=now() WHERE id=%s',(status,reason,enrollment['id']))
        if enrollment.get('steps') and enrollment['steps'][0].get('automation_version'):
            logging.getLogger(__name__).info('automation_exit automation_id=%s journey_id=%s journey_status=%s exit_reason=%s',enrollment['automation_id'],enrollment['id'],status,reason)
    def advance(self,enrollment):
        if enrollment.get('steps') and enrollment['steps'][0].get('automation_version'):
            from crm_automation_runtime import advance
            return advance(self,enrollment)
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
        from time import perf_counter
        start=perf_counter()
        try:return self._process_event(event)
        finally:
            import re
            identity=event.get('event_id','')
            safe=identity if isinstance(identity,str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}',identity) else 'invalid'
            logging.getLogger(__name__).info('shopify_automation_processed shopify_topic=%s shopify_event_id=%s processing_ms=%.1f',event['topic'],safe,(perf_counter()-start)*1000)
    def _process_event(self,event):
        topic=event['topic'];customer_id=event['related_customer_id'];at=date(event['occurred_at'])
        if topic in ('customers/delete','customers/redact'):
            if customer_id:self.store.suppress(hashlib.sha256(customer_id.encode()).hexdigest(),customer_id,'redacted','shopify')
            # New private analytics projection must honor existing redaction.
            if customer_id:self.store.q("UPDATE crm_shopify_checkouts SET analytics='{}' WHERE customer_id=%s",(customer_id,))
            return
        active=getattr(type(self.store),'active_automations',None)
        automations=[a for a in (active(self.store) if active else self.store.list('automations')) if a['status']=='ACTIVE' and date(a['activated_at'])<=at]
        from crm_automation_definition import native
        from crm_automation_runtime import process_event
        process_event(self,event,automations)
        automations=[a for a in automations if not native(a)]
        if topic=='customers_email_marketing_consent/update':
            c=self.shop.customer(customer_id,fresh=True)
            if consent(c)!='SUBSCRIBED':
                self.store.q("UPDATE crm_automation_enrollments SET status='STOPPED',stop_reason='consent_changed',updated_at=now() WHERE shopify_customer_id=%s AND status='ACTIVE' AND (steps->0->>'trigger' IS DISTINCT FROM 'abandoned') AND automation_id NOT IN (SELECT id FROM crm_automations WHERE trigger_type='abandoned')",(customer_id,));return
            changed=date(c['emailMarketingConsent'].get('consentUpdatedAt'))
            if not changed or abs((changed-at).total_seconds())>300:return
            for a in automations:
                if a['trigger_type']=='welcome':self.store.enroll(a,c['id'],c['id'],c['id']+':'+changed.isoformat(),changed)
        elif topic.startswith('orders/'):
            from crm_campaign_attribution import schedule_order
            schedule_order(self.store,event['object_id'])
            # The signed existing order event expedites the bounded attribution
            # scan. Order/automation processing keeps its existing semantics.
            scan=self.store.state('email_attribution_scan');scan.pop('next_at',None)
            self.store.set_state('email_attribution_scan',scan)
            order=self.shop.order(event['object_id'],fresh=True)
            if order and not order.get('cancelledAt') and order.get('customer'):
                customer_id=order['customer']['id']
                self.store.q("UPDATE crm_automation_enrollments e SET status='RECOVERED',stop_reason='paid_order',updated_at=now() FROM crm_automations a WHERE e.automation_id=a.id AND e.checkout_key IS NULL AND COALESCE(e.steps->0->>'trigger',a.trigger_type)='abandoned' AND e.shopify_customer_id=%s AND e.trigger_at<=%s AND e.status='ACTIVE'",(customer_id,order['createdAt']))
                for a in automations:
                    if a['trigger_type']=='post_purchase' and order.get('fullyPaid') and date(order['createdAt'])>=date(a['activated_at']):self.store.enroll(a,customer_id,order['id'],order['id'],at)
        elif topic.startswith('checkouts/'):
            # Events merely expedite reconciliation; only abandonedCheckouts is eligibility authority.
            self.store.set_state('reconcile:abandoned',{})
    def reconcile(self,automation):
        from crm_automation_definition import native
        if native(automation):
            from crm_automation_runtime import reconcile
            return reconcile(self,automation)
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
    def advance_due(self):
        due=self.store.q("SELECT e.* FROM crm_automation_enrollments e JOIN crm_automations a ON a.id=e.automation_id WHERE e.status='ACTIVE' AND a.status='ACTIVE' AND e.next_due_at<=now() AND (e.retry_after IS NULL OR e.retry_after<=now()) ORDER BY e.next_due_at LIMIT 20")
        logging.getLogger(__name__).info('crm_due_batch count=%s',len(due))
        for e in due:
            self.hold_lease()
            try:self.advance(e)
            except Exception as exc:
                self.store.q("UPDATE crm_automation_enrollments SET retry_after=now()+interval '5 minutes',stop_reason='verification_unavailable' WHERE id=%s",(e['id'],))
                logging.getLogger(__name__).warning('checkout_advance_held enrollment_id=%s checkout_key=%s error_class=%s',e['id'],e.get('checkout_key'),type(exc).__name__)

    def tick(self,owner):
        if not self.store.lease(owner):return {'leader':False}
        self.owner=owner
        from time import perf_counter
        started=perf_counter();completed=False
        logging.getLogger(__name__).info('crm_worker_run_start')
        try:
            from crm_automation_capabilities import verify as verify_automation,refresh_due
            if refresh_due(self.store.state('shopify_automation_capabilities'),self.clock()):
                try:verify_automation(self.shop,self.store)
                except Exception:logging.getLogger(__name__).warning('automation_capability_check_unavailable')
            # One durable publication per leased cycle, independent of mail gates.
            try:
                from crm_automation_publication import tick as publication_tick
                from crm_automation_store import AutomationStore
                publication_tick(AutomationStore(self.store.connect),owner)
            except Exception as exc:
                logging.getLogger(__name__).warning('automation_publication_cycle_failed error_class=%s',type(exc).__name__)
            from crm_campaign_schedule import schedule_gate
            schedule_gate(self.store,self.config.enabled,self.clock())
            events=self.store.q("SELECT * FROM crm_webhook_events WHERE status='PENDING' AND provider<>'resend' ORDER BY received_at LIMIT 10")
            for event in events:
                if not self.store.lease(owner):return {'leader':False}
                try:
                    self.process_event(event)
                    self.store.q("UPDATE crm_webhook_events SET status='DONE',processed_at=now() WHERE provider=%s AND event_id=%s",(event['provider'],event['event_id']))
                except Exception:
                    self.store.q("UPDATE crm_webhook_events SET attempts=attempts+1,status=CASE WHEN attempts>=4 THEN 'FAILED' ELSE 'PENDING' END,error_code='source_unavailable' WHERE provider=%s AND event_id=%s",(event['provider'],event['event_id']))
            # Due work runs before catalogue refreshes or source reconciliation.
            # The queue and claims remain shared with the existing worker.
            if self.config.enabled:
                self.advance_due()
            for _ in range(5):
                if not self.store.lease(owner) or not self.send_one():break
            try:
                from crm_checkout_analytics import sync_cache
                sync_cache(self.shop,self.store,self.clock())
            except Exception as exc:logging.getLogger(__name__).warning('checkout_cache_sync_failed type=%s',type(exc).__name__)
            if self.config.enabled:
                active=getattr(type(self.store),'active_automations',None)
                for a in (active(self.store) if active else self.store.list('automations')):
                    if a['status']=='ACTIVE':
                        self.hold_lease()
                        from crm_automation_definition import native
                        if native(a):
                            try:self.reconcile(a)
                            except Exception as exc:
                                # An unavailable trigger source holds this flow;
                                # it must not prevent unrelated Campaign dispatch.
                                logging.getLogger(__name__).warning('automation_source_held automation_id=%s exception_type=%s',a['id'],type(exc).__name__)
                        else:self.reconcile(a)
                self.store.q("UPDATE crm_campaigns SET status='SENDING',sending_started_at=now(),updated_at=now() WHERE status='SCHEDULED' AND audience_snapshot_id IS NOT NULL AND scheduled_at<=now()")
                campaigns=self.store.q("SELECT * FROM crm_campaigns WHERE audience_snapshot_id IS NULL AND (status='BUILDING' OR (status='SCHEDULED' AND scheduled_at<=now())) ORDER BY created_at LIMIT 1")
                for campaign in campaigns:self.hold_lease();self.campaign_page(campaign)
            # Native reviewed campaigns consume the frozen delivery snapshot in
            # batches. Automation/legacy template tests retain their own path.
            from crm_campaign_dispatch import dispatch
            dispatch(self)
            self.store.q("""UPDATE crm_campaigns c SET status='SENT',sent_at=now(),updated_at=now(),
              final_recipient_count=(SELECT count(*) FROM crm_marketing_sends s WHERE s.campaign_id=c.id AND s.status='ACCEPTED' AND s.provider_email_id IS NOT NULL)
              WHERE status='SENDING' AND NOT EXISTS(SELECT 1 FROM crm_marketing_sends s WHERE s.campaign_id=c.id AND s.status IN ('PENDING','CLAIMED','SUBMITTING','UNCERTAIN'))""")
            # Read-side analytics continues with marketing OFF and cannot submit
            # email. A Shopify outage must not interrupt delivery/consent handling.
            try:
                self.hold_lease()
                from crm_campaign_attribution import reconcile as reconcile_attribution
                reconcile_attribution(self.store,self.shop,self.clock)
            except Exception as exc:
                logging.getLogger(__name__).warning('crm_attribution_delayed type=%s',type(exc).__name__)
                state=self.store.state('email_attribution_scan')
                state.update(next_at=(self.clock()+timedelta(minutes=5)).isoformat(),error='source_unavailable')
                self.store.set_state('email_attribution_scan',state)
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
            self.store.set_state('worker_health',{'checked_at':self.clock().isoformat(),'status':'ok','marketing_enabled':self.config.enabled,'provider_configured':bool(self.config.api_key),'sender_configured':bool(self.config.sender and self.config.reply_to)})
            completed=True
            return {'leader':True}
        finally:
            logging.getLogger(__name__).info('crm_worker_run_end completed=%s duration_ms=%.1f',completed,(perf_counter()-started)*1000)
            self.store.release(owner);self.owner=None
