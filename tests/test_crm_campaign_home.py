"""Offline home/navigation projections; transports are forbidden."""
from copy import deepcopy
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import Mock,patch
import os
import threading
import unittest
from streamlit.testing.v1 import AppTest
from crm_campaign_home import _job,kpis,row_html
from crm_campaign_home_data import summary,rows,top_identity,invalidate
from tests.test_crm_simple_editor import document

ID='47bb53bc-9a37-4f99-a840-e775073dbce5'


def record():
    return dict(id=ID,name='Real fixture campaign',version=1,draft_status='DRAFT',status='DRAFT',archived_at=None,
      last_tested_at=None,deletable=True,market='NZ',subject='Verified fixture subject',thumbnail='https://cdn.shopify.com/s/files/fixture.jpg',
      updated_at='2026-10-02T06:40:00Z',sent_at=None,delivery_status=None,recipients=None,delivered=None,opens=None,
      clicks=None,orders=0,revenue={},delivery_rate=None,open_rate=None,click_rate=None,in_page=True)


SCRIPT='''
import streamlit as st
from copy import deepcopy
from concurrent.futures import Future
from unittest.mock import Mock,patch
from crm_campaign_page import campaign_workspace
from tests.test_crm import ADMIN
from tests.test_crm_campaign_home import record,ID
from tests.test_crm_simple_editor import document
from crm_campaign_content import settings
store=Mock();store.connect=None;store.render_settings.return_value=settings({})
store.setting.return_value={'value':{'smart_hours':16}}
store.default_sections.return_value=[];store.q.return_value=None
draft={'id':ID,'version':1,'name':'Real fixture campaign','status':'DRAFT','archived_at':None,'document':document()}
store.draft.return_value=draft;store.duplicate.return_value={**draft,'id':None,'name':'Real fixture campaign — copy'}
actions=Mock();actions.user=ADMIN
st.session_state['load_stages']=[]
def job(state,store,key,load):
 st.session_state['load_stages'].append(key[0])
 f=Future();state.setdefault('campaign_home_cache',{})[(store.connect,key)]=(None,f)
 if st.session_state.get('pending'):return f
 if key[0] in ('counts','delivery','attribution') and st.session_state.get('stats_error'):
  from crm_store import StoreUnavailable
  f.set_exception(StoreUnavailable('Private diagnostic fixture'));return f
 if key[0] in ('counts','delivery','attribution'):f.set_result({'all_count':st.session_state.get('fixture_count',1),'drafts':1,'active':0,'sent':0,'archived':0,'sent_emails':0,'revenue':{},'orders':0,'click_rate':None,'bounce_rate':None})
 else:f.set_result([record()])
 return f
def composer(*args,**kwargs):
 if 'campaign_editor' not in st.session_state:st.session_state['campaign_editor']=deepcopy(draft)
 st.caption('Existing composer: '+st.session_state['campaign_editor']['name'])
 for label in ('Settings','Editor','Templates'):st.caption(label)
 for label in ('Save draft','Send test','Send now'):st.button(label)
with patch('crm_campaign_page.CampaignStore',return_value=store),patch('crm_campaign_home._job',side_effect=job),patch('crm_campaign_page._selected_campaign',side_effect=composer),patch('crm_campaign_page.activate'),patch('crm_campaign_page.recent_campaigns',side_effect=AssertionError('Never append history')),patch('requests.sessions.Session.request',side_effect=AssertionError('No HTTP')):
 campaign_workspace(Mock(),Mock(),actions)
st.session_state['duplicate_calls']=store.duplicate.call_count
st.session_state['draft_calls']=store.draft.call_args_list
'''


class HomeTests(unittest.TestCase):
    def test_resolved_cards_and_rows_remain_during_refresh(self):
        app=AppTest.from_string(SCRIPT).run()
        before=' '.join(e.proto.body for e in app.get('html'))
        self.assertIn('Real fixture campaign',before)
        app.session_state['pending']=True;app.run()
        self.assertFalse(app.exception)
        after=' '.join(e.proto.body for e in app.get('html'))
        self.assertIn('Real fixture campaign',after)
        self.assertNotIn('sc-home-unresolved"',after)
        self.assertIn('Refreshing campaigns…',[c.value for c in app.caption])

    def test_failed_refresh_retains_resolved_totals(self):
        app=AppTest.from_string(SCRIPT).run()
        app.session_state['stats_error']=True;app.run()
        self.assertFalse(app.exception)
        html=' '.join(e.proto.body for e in app.get('html'))
        self.assertIn('Real fixture campaign',html)
        self.assertNotIn('sc-home-unresolved"',html)
        self.assertNotIn('Private diagnostic',html)

    def test_tabs_are_text_controls_with_gold_active_style_and_no_large_rail(self):
        app=AppTest.from_string(SCRIPT).run()
        self.assertFalse(app.radio)
        app.get('button_group')[0].set_value('Sent').run()
        self.assertFalse(app.exception)
        self.assertEqual(app.get('button_group')[0].value,'Sent')
        app.session_state['fixture_count']=2;app.run()
        self.assertEqual(app.get('button_group')[0].value,'Sent')
        app.get('button_group')[0].set_value(None).run()
        self.assertEqual(app.get('button_group')[0].value,'Sent')
        source=Path('crm_campaign_home.py').read_text(encoding='utf-8')
        self.assertIn('segmented_controlActive',source)
        self.assertNotIn('top_identity(',source)
        self.assertNotIn('Turn collectors into lifelong fans',source)
        self.assertNotIn('min-width:1045px',source)
        self.assertNotIn('height=240',source)

    def test_refresh_controller_is_single_owned_and_waits_for_render_completion(self):
        import ast
        source=Path('crm_campaign_home.py').read_text(encoding='utf-8')
        functions={n.name:n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)}
        poll=ast.get_source_segment(source,functions['arm_home_poll'])
        self.assertIn("if st.session_state.get('campaign_home_rendering'): return",poll)
        self.assertIn('uuid4().hex',poll)
        self.assertNotIn('st.rerun(',poll)
        self.assertNotIn('.empty(',poll)
        self.assertEqual(source.count("key='crm-home-poll_tick'"),1)

    def test_home_default_real_rows_no_editor(self):
        app=AppTest.from_string(SCRIPT).run();self.assertFalse(app.exception)
        self.assertEqual(app.session_state['campaign_view'],'CAMPAIGNS_HOME')
        html=' '.join(e.proto.body for e in app.get('html'))
        self.assertIn('Real fixture campaign',html);self.assertIn('Verified fixture subject',html)
        self.assertNotIn('Existing composer:',str([c.value for c in app.caption]))
        self.assertNotIn('Send now',[b.label for b in app.button])
        self.assertEqual(app.get('button_group')[0].value,'All campaigns')

    def test_new_existing_editor_and_back_are_exclusive(self):
        app=AppTest.from_string(SCRIPT).run()
        next(b for b in app.button if b.label=='+ New campaign').click().run()
        self.assertFalse(app.exception);self.assertEqual(app.session_state['campaign_view'],'CAMPAIGN_EDITOR')
        self.assertIn('Existing composer: Untitled campaign',[c.value for c in app.caption])
        for label in ('Save draft','Send test','Send now'):self.assertIn(label,[b.label for b in app.button])
        self.assertFalse(app.radio);self.assertNotIn('home_new',[b.key for b in app.button])
        next(b for b in app.button if b.label=='← Campaigns').click().run()
        self.assertFalse(app.exception);self.assertEqual(app.session_state['campaign_view'],'CAMPAIGNS_HOME')
        self.assertFalse(app.query_params.get('campaign'))

    def test_open_and_duplicate_target_exact_id(self):
        for label in ('Edit','Duplicate'):
            app=AppTest.from_string(SCRIPT).run()
            next(b for b in app.button if b.label==label).click().run()
            self.assertFalse(app.exception);self.assertEqual(app.session_state['campaign_view'],'CAMPAIGN_EDITOR')
            self.assertEqual(app.session_state['campaign_editor']['name'],'Real fixture campaign'+(' — copy' if label=='Duplicate' else ''))
            if label=='Edit':self.assertEqual(str(app.session_state['campaign_editor']['id']),ID)

    def test_pending_shell_has_controls_before_data(self):
        app=AppTest.from_string(SCRIPT);app.session_state['pending']=True;app.run()
        self.assertFalse(app.exception)
        self.assertIn('+ New campaign',[b.label for b in app.button])
        self.assertEqual(app.session_state['load_stages'],['counts','delivery','attribution','table'])
        html=' '.join(e.proto.body for e in app.get('html'))
        for label in ('Campaigns','RECIPIENTS','Bounce rate (30 days)','sc-home-kpis'):self.assertIn(label,html)
        self.assertNotIn('sc-email-loading',html)

    def test_failed_totals_keep_cards_and_do_not_block_campaign_rows(self):
        app=AppTest.from_string(SCRIPT);app.session_state['stats_error']=True;app.run()
        self.assertFalse(app.exception)
        html=' '.join(e.proto.body for e in app.get('html'))
        self.assertIn('sc-home-kpis',html);self.assertIn('Real fixture campaign',html)
        self.assertNotIn('Private diagnostic',html)
        self.assertIn('Some totals are temporarily unavailable · last resolved values retained.',[c.value for c in app.caption])

    def test_templates_enters_existing_templates_tab(self):
        app=AppTest.from_string(SCRIPT).run()
        next(b for b in app.button if b.label=='View email templates').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state[app.session_state['campaign_edit_key']+'panel'],'Templates')

    def test_back_protects_dirty_editor_cancel_and_discard(self):
        for choice in ('Cancel','Discard and leave'):
            app=AppTest.from_string(SCRIPT).run()
            next(b for b in app.button if b.label=='+ New campaign').click().run()
            app.session_state['campaign_editor']['name']='Unsaved change'
            next(b for b in app.button if b.label=='← Campaigns').click().run()
            self.assertFalse(app.exception)
            self.assertIn('Save draft and leave',[b.label for b in app.button])
            next(b for b in app.button if b.label==choice).click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['campaign_view'],'CAMPAIGN_EDITOR' if choice=='Cancel' else 'CAMPAIGNS_HOME')
            if choice=='Cancel':self.assertEqual(app.session_state['campaign_editor']['name'],'Unsaved change')

    def test_async_reads_coalesce_inflight_and_cache_invalidation(self):
        gate=threading.Event();store=Mock();store.connect=None;state={};calls=[]
        def read():calls.append(1);gate.wait(3);return {'count':1}
        first=_job(state,store,('fixture',),read)
        try:self.assertIs(_job(state,store,('fixture',),read),first)
        finally:gate.set()
        self.assertEqual(first.result(3),{'count':1})
        self.assertIs(_job(state,store,('fixture',),read),first);self.assertEqual(len(calls),1)
        invalidate(state);second=_job(state,store,('fixture',),lambda:{'count':2})
        self.assertEqual(second.result(3),{'count':2});self.assertIsNot(first,second)

    def test_display_escape_thumbnail_currency_and_breakpoints(self):
        row=record();row['name']='<script>bad</script>';row['revenue']={'NZD':'10','AUD':'20'}
        html=row_html(row)
        self.assertNotIn('<script>',html);self.assertIn('&lt;script&gt;',html)
        self.assertIn('width=80',html);self.assertIn('loading="lazy"',html)
        self.assertNotIn('NZ$10.00',html);self.assertNotIn('A$20.00',html)
        self.assertIn('—',kpis({'click_rate':None,'bounce_rate':None}))
        source=Path('crm_campaign_home.py').read_text(encoding='utf-8')
        for width in (1500,1200,700):self.assertIn('max-width:'+str(width)+'px',source)
        for mock in ('8,432','$3,280','4.8%'):self.assertNotIn(mock,source)

    def test_summary_queries_bounded_and_no_payload_or_n_plus_one(self):
        store=Mock();store.q.side_effect=[{},{},{},None,[]]
        summary(store);top_identity(store);rows(store)
        self.assertEqual(store.q.call_count,5)
        sql=' '.join(c.args[0] for c in store.q.call_args_list)
        for forbidden in ('d.*','document AS','custom_html','audience_snapshot','template.content'):self.assertNotIn(forbidden,sql)
        self.assertIn('LIMIT %s OFFSET %s',sql);self.assertIn('NOT s.test_send',sql)
        self.assertIn('delivered AND clicked',sql);self.assertIn('a.eligible',sql)

    def test_explicit_url_enters_editor_and_sent_boundary_is_preserved(self):
        app=AppTest.from_string(SCRIPT);app.query_params['campaign']=ID;app.run()
        self.assertFalse(app.exception);self.assertEqual(app.session_state['campaign_view'],'CAMPAIGN_EDITOR')
        page=Path('crm_campaign_page.py').read_text(encoding='utf-8').split('def _selected_campaign')[1]
        self.assertLess(page.index('if delivery:'),page.index('send_control('))
        self.assertIn('operational_view(',page.split('if delivery:')[1].split('from crm_campaign_markets')[0])

    def test_sidebar_entry_home_preserves_browser_history_deep_link_and_dirty_guard(self):
        from crm_navigation import navigation_allowed
        state={'campaign_view':'CAMPAIGN_EDITOR','campaign_editor':{'name':'dirty'},'campaign_saved':{'name':'saved'}}
        self.assertFalse(navigation_allowed(state,'CRM Campaigns','CRM Campaigns'))
        self.assertEqual(state.pop('campaign_pending_open'),'home')
        self.assertTrue(navigation_allowed(state,'Orders','CRM Campaigns',source='browser-history'))
        self.assertNotIn('campaign_pending_open',state)
        self.assertTrue(navigation_allowed(state,'Orders','CRM Campaigns'))
        self.assertEqual(state['campaign_pending_open'],'home')


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable local SQL required')
class HomeSQLTests(unittest.TestCase):
    def test_home_templates_button_opens_real_existing_templates_controls(self):
        from tests.test_crm_ui import SCRIPT as REAL_SCRIPT
        app=AppTest.from_string(REAL_SCRIPT)
        app.session_state['route']='CRM Campaigns';app.session_state['campaign_view']='CAMPAIGNS_HOME'
        app.run(timeout=20);self.assertFalse(app.exception)
        next(b for b in app.button if b.label=='View email templates').click().run(timeout=20)
        self.assertFalse(app.exception)
        self.assertEqual([t.label for t in app.tabs],['Settings','Editor','Templates'])
        self.assertEqual(app.session_state[app.session_state['campaign_edit_key']+'panel'],'Templates')
        self.assertTrue(any('template' in b.label.lower() for b in app.button))

    def test_real_metadata_metrics_match_existing_reporting_and_grouped_queries(self):
        import uuid
        from crm_campaign_store import CampaignStore
        from tests.crm_db_fixture import connect
        from tests.test_crm_send_flow import SendFlowTests,LIVE
        from tests.test_crm import ADMIN
        from tests.test_crm_campaign_v2 import authority,profile
        from crm_campaign_send import review,queue_campaign
        from crm_campaign_analytics import sent_page
        flow=SendFlowTests('test_real_queue_once_and_existing_worker_delivers_snapshot_with_mock_provider')
        flow.setUp();self.addCleanup(flow.doCleanups)
        flow.shop=authority([profile(i) for i in range(99701,99705)])
        doc=flow.editor()['document'];doc.update(market_audience=True,market='AU')
        from crm_campaign_markets import audience
        doc['audience']=audience('AU')
        from tests.test_crm_resend_marketing import ENV
        editor=flow.store.save(ADMIN,'Home SQL fixture '+uuid.uuid4().hex,doc,env=ENV)
        with patch.dict(os.environ,LIVE):
            result=review(flow.shop,flow.store,editor,LIVE)
            receipt=queue_campaign(flow.shop,flow.store,ADMIN,editor,str(uuid.uuid4()),env=LIVE,snapshot_id=result['snapshot_id'])
        identity=str(receipt['id'])
        flow.store.q("UPDATE crm_marketing_sends SET status='ACCEPTED',first_submitted_at=now() WHERE campaign_id=%s",(identity,))
        flow.store.q("UPDATE crm_campaigns SET status='SENT',sent_at=now() WHERE id=%s",(identity,))
        send=flow.store.q('SELECT id FROM crm_marketing_sends WHERE campaign_id=%s LIMIT 1',(identity,),True)
        for event in ('email.delivered','email.opened','email.clicked'):
            for _ in range(2):flow.store.q('INSERT INTO crm_delivery_events(event_id,provider_id,event_type,occurred_at,send_id) VALUES(%s,%s,%s,now(),%s)',(str(uuid.uuid4()),str(uuid.uuid4()),event,send['id']))
        for amount,eligible,age in (('125',True,0),('5',True,40),('500',False,0)):
            flow.store.q('''INSERT INTO crm_order_attribution(shopify_order_id,campaign_id,campaign_key,
              order_created_at,visit_at,amount,currency,eligible) VALUES(%s,%s,%s,
              now()-(%s*interval '1 day'),now(),%s,'NZD',%s)''',
              ('gid://shopify/Order/'+str(uuid.uuid4()),identity,editor['document']['campaign_key'],age,amount,eligible))
        store=CampaignStore(connect)
        with patch.object(store,'q',wraps=store.q) as query:
            totals=summary(store);top=top_identity(store);items=rows(store,search=editor['name'],top=top)
            self.assertEqual(query.call_count,5)
        row=next(r for r in items if str(r['id'])==identity)
        old=next(r for r in sent_page(store,limit=200) if str(r['id'])==identity)
        for field in ('recipients','delivered','opens','clicks','orders','delivery_rate','open_rate','click_rate'):
            self.assertEqual(row[field],old[field],field)
        self.assertEqual(row['delivered'],1);self.assertEqual(row['clicks'],1)
        from decimal import Decimal
        self.assertEqual(row['orders'],2);self.assertNotIn('revenue',row)
        self.assertIsNotNone(top)
        outside=rows(store,search='no matching campaign name',detail=identity)
        self.assertEqual(len(outside),1);self.assertFalse(outside[0]['in_page'])
        self.assertEqual(str(outside[0]['id']),identity)
        self.assertGreaterEqual(totals['sent_emails'],4)
        self.assertNotIn('document',row);flow.provider.post.assert_not_called()


if __name__=='__main__':unittest.main()
