"""Market/template/schedule regressions: disposable SQL, never external delivery."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import os
import unittest
import uuid
from unittest.mock import Mock, patch
from crm_campaign_markets import calculate,country,audience
from crm_campaign_schedule import resolve,due,plan,schedule_gate,overdue_reason
from crm_campaign_content import validate_document,settings
from crm_campaign_library import save_template,insert_template,template_html
from crm_campaign_store import CampaignStore
from crm_campaign_send import final_audience,queue_campaign
from crm_resend import MarketingDisabled
from crm_store import Store
from tests.crm_db_fixture import connect
from tests.test_crm import ADMIN
from tests.test_crm_simple_editor import document
from tests.test_crm_send_flow import LIVE,CFG
from crm_logic import recipient_hash, date

def profile(i,code='AU',state='NSW',consent='SUBSCRIBED',address=None):
    return {'id':f'gid://shopify/Customer/{i}','email':f'p{i}@example.test','validEmailAddress':True,
      'emailMarketingConsent':{'marketingState':consent},'defaultAddress':address or {'countryCodeV2':code,'provinceCode':state}}

def authority(rows):
    from tests.crm_fixtures import native_customer
    shop=Mock();shop.campaign_subscribers.return_value={'nodes':[native_customer(c) for c in rows],'pageInfo':{'hasNextPage':False}}
    return shop

class MarketAndTimezoneTests(unittest.TestCase):
    def test_countries_counts_exclusions_and_final_audience_share_logic(self):
        rows=[profile(1),profile(2,'US','NY'),profile(3,'GB',''),profile(4,'NZ',''),profile(5,consent='UNSUBSCRIBED'),profile(6),profile(7),profile(8)]
        rows[5]['email']=rows[0]['email'];rows[6]['validEmailAddress']=False
        store=Mock();store.active_suppression_hashes.return_value=({recipient_hash(rows[7]['email'])},set());store.recent_marketing_hashes.return_value=set()
        shop=authority(rows);result=calculate(shop,store)
        self.assertEqual({m:r['eligible'] for m,r in result.items()},{'AU':1,'US':1,'UK':1,'Global':4})
        self.assertEqual(sum(result['AU']['excluded'].values()),4)
        doc=document();doc.update(market_audience=True,market='US',audience=audience('US'))
        self.assertEqual(final_audience(shop,store,doc)['recipients'],result['US']['recipients'])
        for value,expected in [('Australia','AU'),('USA','US'),('United Kingdom','GB'),('UK','GB')]:
            self.assertEqual(country({'defaultAddress':{'country':value}}),expected)
    def test_conflicting_consent_outside_market_and_frequency(self):
        rows=[profile(1),profile(2,'US',consent='UNSUBSCRIBED'),profile(3)]
        rows[1]['email']=rows[0]['email']
        store=Mock();store.active_suppression_hashes.return_value=(set(),set());store.recent_marketing_hashes.return_value={recipient_hash(rows[2]['email'])}
        result=calculate(authority(rows),store)['AU']
        self.assertEqual(result['eligible'],0);self.assertEqual(result['excluded'],{'smart_sending':1,'conflicting_consent':1})
    def test_timezone_priority_states_and_fallback(self):
        for code,state,zone in [('AU','NSW','Australia/Sydney'),('AU','QLD','Australia/Brisbane'),('AU','SA','Australia/Adelaide'),('AU','WA','Australia/Perth'),('US','NY','America/New_York'),('US','IL','America/Chicago'),('US','CO','America/Denver'),('US','CA','America/Los_Angeles'),('GB','','Europe/London')]:
            self.assertEqual(resolve(profile(1,code,state))[0],zone)
        self.assertEqual(resolve(profile(1,address={'timeZone':'America/Chicago'})),('America/Chicago','address_timezone'))
        self.assertEqual(resolve(profile(1,'US','')),('America/New_York','country_fallback'))
        self.assertEqual(resolve(profile(1,'NZ','')),('UTC','global_utc_fallback'))
    def test_dst_offsets_gap_and_fold(self):
        timing=lambda date,time='07:00':{'mode':'schedule','date':date,'time':time}
        self.assertEqual(due(timing('2026-07-01'),'America/New_York').hour,11)
        self.assertEqual(due(timing('2026-12-01'),'America/New_York').hour,12)
        self.assertEqual(due(timing('2026-07-01'),'Europe/London').hour,6)
        self.assertEqual(due(timing('2026-12-01'),'Europe/London').hour,7)
        self.assertEqual(due(timing('2026-12-01'),'Australia/Adelaide').minute,30)
        with self.assertRaisesRegex(ValueError,'does not exist'):due(timing('2026-03-08','02:30'),'America/New_York')
        self.assertEqual(due(timing('2026-11-01','01:30'),'America/New_York').hour,5)
    def test_seven_am_local_for_every_required_zone(self):
        timing={'mode':'schedule','date':'2026-10-05','time':'07:00'}
        for zone,expected in {'Australia/Sydney':'2026-10-04T20:00:00+00:00',
          'Australia/Brisbane':'2026-10-04T21:00:00+00:00','Australia/Adelaide':'2026-10-04T20:30:00+00:00',
          'Australia/Perth':'2026-10-04T23:00:00+00:00','America/New_York':'2026-10-05T11:00:00+00:00',
          'America/Chicago':'2026-10-05T12:00:00+00:00','America/Denver':'2026-10-05T13:00:00+00:00',
          'America/Los_Angeles':'2026-10-05T14:00:00+00:00','Europe/London':'2026-10-05T06:00:00+00:00'}.items():
            with self.subTest(zone=zone):self.assertEqual(due(timing,zone).isoformat(),expected)
    def test_worker_kill_switch_cannot_claim_or_send(self):
        from crm_engine import Engine
        from crm_resend import Config
        store=Mock();provider=Mock()
        engine=Engine(store,Mock(),provider,Config({'CRM_MARKETING_ENABLED':'false','CRM_MARKETING_SEND_ENABLED':'true'}))
        self.assertFalse(engine.send_one());store.claim_send.assert_not_called();provider.send.assert_not_called()
    def test_invalid_and_past_schedule_fail_closed(self):
        doc=document();doc['send_timing']={'mode':'schedule','date':'2020-01-01','time':'07:00'}
        state={'recipients':[{'id':'1','hash':'x'}],'profiles':{'1':profile(1)}}
        with self.assertRaisesRegex(ValueError,'reschedule'):plan(doc,state,datetime.now(timezone.utc))
        doc['send_timing']['time']='invalid'
        with self.assertRaises(ValueError):validate_document(doc)
    def test_backend_policy_defaults_do_not_invent_sender(self):
        cfg=settings({});self.assertEqual(cfg['privacy'],'https://www.sportscaveshop.com/policies/privacy-policy')
        self.assertEqual(cfg['refund'],'https://www.sportscaveshop.com/policies/refund-policy');self.assertEqual(cfg['contact'],'')

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class PersistenceAndSchedulingTests(unittest.TestCase):
    def setUp(self):
        self.store=CampaignStore(connect)
        self.guard=patch('requests.sessions.Session.request',side_effect=AssertionError('External I/O forbidden'));self.guard.start();self.addCleanup(self.guard.stop)
    def test_template_create_edit_rename_archive_and_independent_campaign_snapshot(self):
        name='Template '+uuid.uuid4().hex;row=save_template(self.store,ADMIN,name,'<p>Original</p>')
        self.assertEqual(template_html(self.store,row),'<p>Original</p>')
        doc=document();original=doc['custom_html'];insert_template(doc,template_html(self.store,row),row)
        self.assertEqual(doc['custom_html'],original);self.assertEqual(len(doc['middle_sections']),2)
        campaign=self.store.save(ADMIN,name,doc)
        edited=save_template(self.store,ADMIN,name+' renamed','<p>Changed</p>',row)
        self.assertEqual(edited['version'],row['version']+1)
        self.store.archive_design(ADMIN,edited['id'],edited['version'])
        self.assertEqual(self.store.draft(campaign['id'])['document'],doc)
        self.assertNotIn(row['id'],[r['id'] for r in self.store.templates()])
        blank=document();blank['custom_html']='';insert_template(blank,'<p>Start</p>',row)
        self.assertEqual(blank['custom_html'],'<p>Start</p>');self.assertEqual(len(blank['middle_sections']),1)
    def test_library_excludes_automation_owned_templates(self):
        import json
        row=save_template(self.store,ADMIN,'Flow-owned '+uuid.uuid4().hex,'<p>Flow snapshot</p>')
        self.store.seed()
        flow=self.store.list('automations')[0]
        self.store.q('UPDATE crm_automations SET steps=%s::jsonb WHERE id=%s',(json.dumps([{'type':'send','template':row['template_key']}]),flow['id']))
        try:self.assertNotIn(row['id'],[r['id'] for r in self.store.html_library()])
        finally:self.store.q('UPDATE crm_automations SET steps=%s::jsonb WHERE id=%s',(json.dumps(flow['steps']),flow['id']))
    def queued(self):
        doc=document();doc.update(market_audience=True,market='US',audience=audience('US'),send_timing={'mode':'schedule','date':'2099-10-05','time':'07:00'})
        saved=self.store.save(ADMIN,'Scheduled '+uuid.uuid4().hex,doc)
        shop=authority([profile(5001,'US','NY'),profile(5002,'US','CA')])
        with patch.object(self.store,'render_settings',return_value=CFG),patch.object(self.store,'active_suppression_hashes',return_value=(set(),set())),patch.object(self.store,'recent_marketing_hashes',return_value=set()):
            result=queue_campaign(shop,self.store,ADMIN,saved,str(uuid.uuid4()),env={**LIVE,'CRM_MARKET_REVIEW_VERIFIED':'US'})
        return saved,result
    def test_schedule_durable_different_timezones_idempotent_and_delete_guard(self):
        saved,result=self.queued();rows=self.store.q('SELECT * FROM crm_marketing_sends WHERE campaign_id=%s ORDER BY due_at',(saved['id'],))
        self.assertEqual(len(rows),2);self.assertEqual((date(rows[1]['due_at'])-date(rows[0]['due_at'])).total_seconds(),10800)
        snapshot=Store(connect).template(rows[0]['template_id'],1)
        self.assertEqual(len(snapshot['schedule']),2);self.assertEqual(self.store.draft(saved['id'])['document']['send_timing']['time'],'07:00')
        with self.assertRaises(ValueError):self.store.delete_draft(ADMIN,saved['id'],saved['version'],confirmed=True,confirmed_name=saved['name'])
        again=queue_campaign(Mock(),self.store,ADMIN,saved,str(uuid.uuid4()),env=LIVE)
        self.assertTrue(again['already_started'])
        with self.assertRaises(ValueError):self.store.save(ADMIN,saved['name'],saved['document'],saved['id'],saved['version'])
    def test_off_then_on_never_catches_up_but_future_job_remains(self):
        saved,_=self.queued();rows=self.store.q('SELECT * FROM crm_marketing_sends WHERE campaign_id=%s ORDER BY due_at',(saved['id'],))
        at=date(rows[0]['due_at'])+timedelta(seconds=1);store=Store(connect)
        schedule_gate(store,False,at)
        row=store.receipt(rows[0]['id']);self.assertEqual((row['status'],row['error_code']),('BLOCKED','marketing_off_schedule'))
        schedule_gate(store,True,at+timedelta(seconds=1))
        self.assertEqual(store.receipt(row['id'])['error_code'],'schedule_missed')
        self.assertEqual(store.receipt(rows[1]['id'])['status'],'PENDING')
        self.assertEqual(self.store.list_drafts(search=saved['name'])[0]['schedule_error'],'schedule_missed')
    def test_healthy_due_job_survives_but_worker_outage_misses(self):
        saved,_=self.queued();row=self.store.q('SELECT * FROM crm_marketing_sends WHERE campaign_id=%s ORDER BY due_at LIMIT 1',(saved['id'],),True);store=Store(connect)
        schedule_gate(store,True,date(row['due_at'])-timedelta(seconds=10))
        schedule_gate(store,True,date(row['due_at'])+timedelta(seconds=1))
        self.assertEqual(store.receipt(row['id'])['status'],'PENDING')
        schedule_gate(store,True,date(row['due_at'])+timedelta(minutes=10))
        self.assertEqual(store.receipt(row['id'])['error_code'],'schedule_missed')
    def test_off_blocks_scheduled_queue_before_any_write(self):
        store=Mock();doc=document();doc['send_timing']={'mode':'schedule','date':'2099-01-01','time':'07:00'}
        with self.assertRaises(MarketingDisabled):queue_campaign(Mock(),store,ADMIN,{'document':doc},str(uuid.uuid4()),env={'CRM_MARKETING_ENABLED':'false'})
        store.q.assert_not_called();store.db.assert_not_called()
    def test_draft_delete_preserves_history(self):
        row=self.store.save(ADMIN,'Delete '+uuid.uuid4().hex,document())
        with self.assertRaises(ValueError):self.store.delete_draft(ADMIN,row['id'],row['version'])
        with patch('activity_log.record_activity_log',return_value=True):self.store.delete_draft(ADMIN,row['id'],row['version'],confirmed=True,confirmed_name=row['name'])
        self.assertTrue(self.store.draft(row['id'])['archived_at']);self.assertGreaterEqual(len(self.store.history(row['id'])),2)
        self.assertFalse(self.store.list_drafts(search=row['name']))

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class SimplifiedUiTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        from tests.test_crm_ui import SCRIPT
        at=AppTest.from_string(SCRIPT.replace("'role':'worker'","'role':'admin'"));at.session_state['route']='CRM Campaigns'
        return at
    def test_tabs_no_infrastructure_templates_lazy_counts_cached(self):
        at=self.app()
        with patch('crm_segment_counts.COUNTS.display',return_value={'counts':{},'pending':True,'error':False}),patch.object(CampaignStore,'html_library',side_effect=AssertionError('Library must be lazy')),patch('crm_settings_page.campaign_settings_panel',side_effect=AssertionError('Removed settings must not load')):
            at.run(timeout=20);self.assertFalse(at.exception)
            self.assertEqual([t.label for t in at.tabs],['Campaign Settings','Editor','Templates'])
            calls=len(at.session_state['wire'].calls)
            next(t for t in at.text_input if t.label=='Subject').set_value('Typing').run(timeout=20)
            self.assertEqual(len(at.session_state['wire'].calls),calls)
            self.assertTrue({'Audience','Templates','More','Test','Campaign settings'}.isdisjoint({e.label for e in at.expander}))
            self.assertFalse(any('Smart Sending' in n.label for n in at.number_input))
    def test_market_and_timing_save_reload_and_no_hidden_copy_confirmation(self):
        at=self.app();at.run(timeout=20)
        market=next(s for s in at.selectbox if s.label=='Segment')
        self.assertEqual([s.split(' · ')[0] for s in market.options],['AUSTRALIA','USA','UK','ALL SUBSCRIBERS'])
        market.set_value('US').run(timeout=20)
        next(r for r in at.radio if r.label=='Send timing').set_value('Schedule').run(timeout=20)
        self.assertEqual(len(at.date_input),1);self.assertEqual(len(at.time_input),1)
        next(b for b in at.button if b.label=='Save draft').click().run(timeout=20)
        self.assertFalse(at.exception)
        row=CampaignStore(connect).draft(at.session_state['campaign_editor']['id'])
        self.assertEqual(row['document']['audience'],audience('US'))
        self.assertEqual(row['document']['send_timing']['mode'],'schedule')
        self.assertFalse(any(c.label in ('Copy and subject reviewed','One approved internal mailbox only') for c in at.checkbox))
    def test_counts_failure_keeps_composer_available(self):
        at=self.app()
        with patch('crm_segment_counts.COUNTS.display',return_value={'counts':{},'pending':False,'error':True}):
            at.run(timeout=20)
            self.assertFalse(at.exception)
            self.assertEqual(next(s for s in at.selectbox if s.label=='Segment').options,['AUSTRALIA · —','USA · —','UK · —','ALL SUBSCRIBERS · —'])
            self.assertTrue(any('counts unavailable' in c.value for c in at.caption))
            self.assertFalse(any('SECRET' in c.value for c in at.caption))
