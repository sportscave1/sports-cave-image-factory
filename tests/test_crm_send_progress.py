"""Offline status semantics, UI isolation and disposable-SQL lifecycle evidence."""
from copy import deepcopy
from pathlib import Path
import os
import time
import unittest
import uuid
from unittest.mock import Mock, patch
from streamlit.testing.v1 import AppTest
from crm_campaign_progress import summarize, read_progress, load_progress, track, expire

ID='47bb53bc-9a37-4f99-a840-e775073dbce5'


def row(status='SENDING', **counts):
    return {'id':ID,'name':'Collector edition','status':status,'counts':counts}


STATUS_SCRIPT='''
import streamlit as st
from unittest.mock import Mock,patch
from crm_campaign_progress_ui import status_content
from tests.test_crm_send_progress import ID
store=Mock();store.q.return_value=[st.session_state['row']]
st.session_state.pop('campaign_progress_cache',None)
with patch('requests.sessions.Session.request',side_effect=AssertionError('No HTTP')):
 status_content(store,ID)
st.session_state['query_count']=store.q.call_count
'''

QUEUE_SCRIPT='''
import streamlit as st
from copy import deepcopy
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import Mock,patch
from crm_campaign_send_ui import review_dialog
from crm_campaign_review import identity
from tests.test_crm_simple_editor import document
from tests.test_crm_send_progress import ID
from tests.test_crm_send_flow import CFG
if 'campaign_editor' not in st.session_state:
 editor={'id':ID,'version':1,'name':'Collector edition','document':document(),'archived_at':None}
 st.session_state['campaign_editor']=editor
 st.session_state['campaign_saved']=deepcopy(editor)
 st.query_params['campaign']=ID
 f=Future();f.set_result({'counts':{'eligible':4,'excluded':{}},'blockers':[], 'snapshot_id':'frozen','tracking_ok':True})
 st.session_state['job']=SimpleNamespace(future=f,closed=False,applied=False,identity=identity(editor),editor=deepcopy(editor))
 st.session_state['queue_calls']=0
store=Mock();store.q.return_value=[{'id':ID,'name':'Collector edition','status':'SENDING','counts':{'PENDING':4}}]
def queue(*args,**kwargs):
 st.session_state['queue_calls']+=1
 st.session_state['operation']=args[4]
 if st.session_state.get('queue_fail'):raise ValueError('Review again')
 return {'id':ID,'status':'SENDING','recipients':4,'already_started':False}
with patch('crm_campaign_review.start_review',return_value=st.session_state['job']), patch('crm_campaign_send_ui.queue_campaign',side_effect=queue), patch('crm_preview_cache.preview',return_value={'html':'<p>Offline preview</p>'}), patch('crm_campaign_send_ui.get_resend_marketing_config_status',return_value={'marketing_enabled':True,'sender':'fixture','reply_to':'fixture'}),patch('requests.sessions.Session.request',side_effect=AssertionError('No HTTP')):
 review_dialog(None,store,{},st.session_state['campaign_editor'],'fixture_',CFG)
'''


class ProgressTests(unittest.TestCase):
    def test_every_status_and_exact_denominator(self):
        p=summarize(row(PENDING=1,CLAIMED=1,SUBMITTING=1,ACCEPTED=2,BLOCKED=1,FAILED=1,UNCERTAIN=1))
        self.assertEqual((p['total'],p['pending'],p['processed'],p['submitted'],p['skipped'],p['failed'],p['held']), (8,3,5,2,1,1,1))
        self.assertEqual(p['percent'],5/8);self.assertFalse(p['complete']);self.assertTrue(p['attention'])

    def test_percent_never_declares_sent(self):
        for status in ('SENDING','BUILDING','SCHEDULED','PAUSED','CANCELLED'):
            p=summarize(row(status,ACCEPTED=4));self.assertEqual(p['percent'],1);self.assertFalse(p['complete'])
        p=summarize(row('SENT',ACCEPTED=3,BLOCKED=1))
        self.assertEqual((p['processed'],p['total'],p['submitted'],p['skipped']),(4,4,3,1))
        self.assertTrue(p['complete']);self.assertEqual(p['title'],'Campaign sent')

    def test_failed_held_unknown_and_zero_are_safe(self):
        for counts in ({'UNCERTAIN':4},{'NEW_STATUS':4},{'FAILED':4}):
            p=summarize(row(**counts));self.assertTrue(p['attention']);self.assertFalse(p['complete'])
        self.assertEqual(summarize(row())['percent'],0)
        self.assertIn('needs attention',summarize(row('SENT',FAILED=1))['title'])

    def test_active_idle_and_near_due_scheduling_cadence(self):
        from crm_campaign_progress import polling_seconds
        from crm_logic import now
        from datetime import timedelta
        self.assertEqual(polling_seconds(row()),2.5)
        self.assertEqual(polling_seconds(row('SENT')),30)
        self.assertEqual(polling_seconds({**row('SCHEDULED'),'scheduled_at':now()+timedelta(seconds=30)}),2.5)
        self.assertEqual(polling_seconds({**row('SCHEDULED'),'scheduled_at':now()+timedelta(days=1)}),30)

    def test_one_batch_db_read_no_recipient_fields_or_network(self):
        store=Mock();store.q.return_value=[row(PENDING=4)]
        with patch('requests.sessions.Session.request',side_effect=AssertionError('No HTTP')):
            self.assertEqual(read_progress(store,[ID,uuid.UUID(ID)])[ID]['pending'],4)
        store.q.assert_called_once();sql,args=store.q.call_args.args
        self.assertEqual(args,([ID],));self.assertIn('s.campaign_id=c.id',sql)
        for field in ('shopify_customer_id','recipient_hash','provider_email_id','document','crm_delivery_events'):
            self.assertNotIn(field,sql)
        with self.assertRaises(ValueError):read_progress(store,['not-a-uuid'])

    def test_local_aggregate_cache_expires_and_multiple_ids_remain_independent(self):
        store=Mock();store.q.return_value=[row(PENDING=4)];state={};at=[0]
        for instant in (0,1,1.9):
            at[0]=instant;load_progress(store,state,[ID],clock=lambda:at[0])
        self.assertEqual(store.q.call_count,1)
        at[0]=2.5;load_progress(store,state,[ID],clock=lambda:at[0]);self.assertEqual(store.q.call_count,2)
        b=str(uuid.uuid4());track(state,{'id':ID},'A');track(state,{'id':b},'B')
        self.assertEqual(set(state['campaign_send_progress']),{ID,b})
        self.assertEqual(state['campaign_send_dialog_id'],b)

    def test_completion_expires_only_clean_tray_and_never_open_dialog(self):
        state={};track(state,{'id':ID},'A');rows={ID:summarize(row('SENT',ACCEPTED=4))}
        expire(state,rows,clock=lambda:0);expire(state,rows,clock=lambda:50)
        self.assertIn(ID,state['campaign_send_progress'])
        state.pop('campaign_send_dialog_id');expire(state,rows,clock=lambda:51)
        self.assertFalse(state['campaign_send_progress'])
        track(state,{'id':ID},'A');state.pop('campaign_send_dialog_id')
        expire(state,{ID:summarize(row(UNCERTAIN=4))},clock=lambda:100)
        self.assertIn(ID,state['campaign_send_progress'])

    def test_status_ui_live_transition_and_exact_copy(self):
        app=AppTest.from_string(STATUS_SCRIPT)
        editor={'name':'Campaign B','document':{'subject':'Unsaved B'}}
        app.session_state['campaign_editor']=deepcopy(editor)
        for status,counts,expected in (
          ('SENDING',{'PENDING':4},'0 / 4 processed'),
          ('SENDING',{'PENDING':2,'ACCEPTED':2},'2 / 4 processed'),
          ('SENT',{'ACCEPTED':3,'BLOCKED':1},'4 / 4 processed')):
            app.session_state['row']=row(status,**counts);app.run();self.assertFalse(app.exception)
            self.assertIn(expected,[c.value for c in app.caption]);self.assertEqual(app.session_state['query_count'],1)
            self.assertEqual(app.session_state['campaign_editor'],editor)
        self.assertIn('Done',[b.label for b in app.button]);self.assertIn('View analytics',[b.label for b in app.button])
        self.assertTrue(any('3 submitted · 1 skipped · 0 failed · 0 held'==c.value for c in app.caption))

    def test_held_does_not_show_success_or_analytics(self):
        app=AppTest.from_string(STATUS_SCRIPT);app.session_state['row']=row(UNCERTAIN=4);app.run()
        self.assertFalse(app.exception);self.assertNotIn('Done',[b.label for b in app.button])
        self.assertNotIn('View analytics',[b.label for b in app.button]);self.assertTrue(any('Do not resend' in c.value for c in app.caption))

    def test_success_queue_swaps_session_only_after_receipt_clears_url(self):
        app=AppTest.from_string(QUEUE_SCRIPT).run();self.assertFalse(app.exception)
        next(b for b in app.button if b.label=='Send to 4 recipients').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['queue_calls'],1)
        self.assertEqual(app.session_state['campaign_editor']['name'],'Untitled campaign')
        self.assertIsNone(app.session_state['campaign_editor']['id']);self.assertNotIn('campaign',app.query_params)
        self.assertIn(ID,app.session_state['campaign_send_progress'])
        self.assertTrue(app.session_state['job'].closed)

    def test_post_queue_ui_failure_preserves_receipt_and_reruns_never_queue_again(self):
        app=AppTest.from_string(QUEUE_SCRIPT).run()
        # Simulate the worker finishing before the UI status render fails.
        durable=row('SENT',ACCEPTED=4)
        with patch('crm_campaign_progress_ui.status_content',side_effect=RuntimeError('UI fixture failure')):
            next(b for b in app.button if b.label=='Send to 4 recipients').click().run()
        self.assertTrue(app.exception)
        self.assertEqual(app.session_state['fixture_queued_receipt']['id'],ID)
        self.assertEqual(app.session_state['queue_calls'],1)
        for _ in range(3):
            with patch('crm_campaign_progress_ui.load_progress',return_value={ID:summarize(durable)}):
                app.run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['queue_calls'],1)
            self.assertTrue(any('Campaign sent' in m.value for m in app.markdown))
            self.assertIn('Close',[b.label for b in app.button])
            self.assertNotIn('Cancel',[b.label for b in app.button])
            self.assertFalse(any('Send to' in b.label or 'Preparing' in b.label for b in app.button))

    def test_review_fragment_owns_every_mutated_placeholder(self):
        import ast
        source=Path('crm_campaign_send_ui.py').read_text(encoding='utf-8')
        functions={n.name:n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)}
        dialog=ast.get_source_segment(source,functions['review_dialog'])
        fragment=ast.get_source_segment(source,functions['review_finalization'])
        self.assertNotIn('st.empty()',dialog)
        self.assertNotIn('summary_slot',dialog)
        self.assertNotIn('summary_slot',[a.arg for a in functions['review_finalization'].args.args])
        self.assertIn('summary_slot=st.empty()',fragment)
        self.assertIn('body=st.empty()',fragment)
        self.assertLess(fragment.index('_review_summary('),fragment.index('start_review('))
        page=Path('crm_campaign_page.py').read_text(encoding='utf-8').split('def _selected_campaign')[1]
        self.assertLess(page.index('if delivery:'),page.index('send_control('))
        locked=page.split('if delivery:')[1].split('from crm_campaign_markets')[0]
        self.assertIn('operational_view(',locked)
        self.assertIn('return',locked)


    def test_queue_failure_preserves_editor_url_and_operation(self):
        app=AppTest.from_string(QUEUE_SCRIPT);app.session_state['queue_fail']=True;app.run()
        next(b for b in app.button if b.label=='Send to 4 recipients').click().run()
        self.assertFalse(app.exception);self.assertEqual(app.session_state['campaign_editor']['id'],ID)
        self.assertEqual(app.query_params['campaign'],[ID]);self.assertNotIn('campaign_send_progress',app.session_state)
        self.assertEqual(app.session_state['fixture_production_operation'],app.session_state['operation'])

    def test_polling_modules_cannot_queue_or_own_delivery(self):
        source=Path('crm_campaign_progress_ui.py').read_text(encoding='utf-8')
        for name in ('queue_campaign(', 'Shopify(', 'send_test(', 'render_production(', 'validate_tracking(', 'customer_batch(', 'focus('):
            self.assertNotIn(name,source)
        tray=source.split('def status_tray')[1].split('def operational_view')[0]
        self.assertNotIn('campaign_editor',tray);self.assertIn("st.rerun(scope='fragment')",tray)
        history=Path('crm_campaign_page.py').read_text(encoding='utf-8')
        self.assertNotIn('recent_campaigns(drafts,st.session_state',history)
        home=Path('crm_campaign_home.py').read_text(encoding='utf-8')
        self.assertIn('crm-home-poll',home)
        self.assertIn('arm_home_poll()',home)
        self.assertNotIn('locked_campaign(',history)

    def test_minimise_and_close_only_affect_status_visibility(self):
        for label in ('Minimise','Close'):
            app=AppTest.from_string(STATUS_SCRIPT)
            app.session_state['row']=row(PENDING=4)
            app.session_state['campaign_send_progress']={ID:{'name':'A'}}
            app.session_state['campaign_send_dialog_id']=ID
            app.session_state['campaign_editor']={'name':'B','unsaved':'retained'}
            app.run();next(b for b in app.button if b.label==label).click().run()
            self.assertFalse(app.exception);self.assertNotIn('campaign_send_dialog_id',app.session_state)
            self.assertEqual(app.session_state['campaign_editor'],{'name':'B','unsaved':'retained'})
            self.assertEqual(bool(app.session_state['campaign_send_progress']),label=='Minimise')

    def test_unavailable_db_is_compact_without_exception_secrets(self):
        from crm_store import StoreUnavailable
        with patch('crm_campaign_progress_ui.load_progress',side_effect=StoreUnavailable('secret token and private payload')):
            app=AppTest.from_string(STATUS_SCRIPT);app.session_state['row']=row();app.run()
        self.assertFalse(app.exception);self.assertFalse(app.error)
        captions=' '.join(c.value for c in app.caption)
        self.assertIn('background delivery continues',captions);self.assertNotIn('secret',captions)

    def test_multiple_statuses_escape_names_and_remain_read_only(self):
        script='''
import streamlit as st
from unittest.mock import Mock,patch
from crm_campaign_progress_ui import status_tray
from tests.test_crm_send_progress import ID,row
from crm_campaign_progress import summarize
with patch('crm_campaign_progress_ui.load_progress',return_value={ID:summarize(row(PENDING=4)),'second':summarize(row(ACCEPTED=1,PENDING=3))}):
 status_tray(Mock())
'''
        app=AppTest.from_string(script)
        app.session_state['campaign_send_progress']={ID:{'name':'<script>unsafe</script>'},'second':{'name':'B'}}
        app.session_state['campaign_editor']={'name':'C','dirty':True};app.run()
        self.assertFalse(app.exception);self.assertEqual(sum(b.label=='Open' for b in app.button),2)
        html=' '.join(h.proto.body for h in app.get('html'))
        self.assertIn('&lt;script&gt;unsafe',html);self.assertNotIn('<script>unsafe',html)
        self.assertIn('position:fixed',html);self.assertIn('max-height:180px',html)
        self.assertEqual(app.session_state['campaign_editor'],{'name':'C','dirty':True})


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class SQLProgressTests(unittest.TestCase):
    def test_actual_queue_progress_workerlike_completion_history_and_no_reset(self):
        from tests.test_crm_send_flow import SendFlowTests, LIVE
        from tests.test_crm_campaign_v2 import authority,profile
        from tests.test_crm import ADMIN
        from crm_campaign_send import review,queue_campaign
        flow=SendFlowTests('test_real_queue_once_and_existing_worker_delivers_snapshot_with_mock_provider')
        flow.setUp();self.addCleanup(flow.doCleanups)
        flow.shop=authority([profile(i) for i in range(99001,99005)])
        doc=flow.editor()['document'];doc.update(market_audience=True,market='AU')
        from crm_campaign_markets import audience
        doc['audience']=audience('AU')
        from tests.test_crm_resend_marketing import ENV
        editor=flow.store.save(ADMIN,'Progress fixture '+uuid.uuid4().hex,doc,env=ENV)
        with patch.dict(os.environ,LIVE):
            result=review(flow.shop,flow.store,editor,LIVE)
            receipt=queue_campaign(flow.shop,flow.store,ADMIN,editor,str(uuid.uuid4()),env=LIVE,snapshot_id=result['snapshot_id'])
        identity=str(receipt['id']);draft_before=flow.store.draft(identity)
        p=read_progress(flow.store,[identity])[identity]
        self.assertEqual((p['total'],p['processed'],p['submitted'],p['status']),(4,0,0,'SENDING'))
        flow.store.q("UPDATE crm_marketing_sends SET status='ACCEPTED',first_submitted_at=now() WHERE id IN (SELECT id FROM crm_marketing_sends WHERE campaign_id=%s LIMIT 2)",(identity,))
        self.assertEqual(read_progress(flow.store,[identity])[identity]['processed'],2)
        flow.store.q("UPDATE crm_marketing_sends SET status='BLOCKED' WHERE campaign_id=%s AND status='PENDING'",(identity,))
        self.assertFalse(read_progress(flow.store,[identity])[identity]['complete'])
        flow.store.q("UPDATE crm_campaigns SET status='SENT',sent_at=now(),updated_at=now() WHERE id=%s",(identity,))
        p=read_progress(flow.store,[identity])[identity];self.assertTrue(p['complete'])
        self.assertEqual((p['processed'],p['submitted'],p['skipped']),(4,2,2))
        self.assertNotIn(identity,[str(r['id']) for r in flow.store.list_drafts(working=True)])
        self.assertGreaterEqual(flow.store.history_counts()['sent'],1)
        self.assertEqual(flow.store.draft(identity),draft_before)
        # A later UI exception cannot roll back the already committed send.
        with patch.dict(os.environ,LIVE):
            again=queue_campaign(flow.shop,flow.store,ADMIN,editor,str(uuid.uuid4()),env=LIVE,snapshot_id=result['snapshot_id'])
        self.assertEqual(again['status'],'SENT')
        self.assertTrue(again['already_started'])

        self.assertEqual(flow.store.q('SELECT count(*) n FROM crm_marketing_sends WHERE campaign_id=%s',(identity,),True)['n'],4)
        indexes=flow.store.q("SELECT indexdef FROM pg_indexes WHERE tablename='crm_marketing_sends'")
        self.assertTrue(any('UNIQUE INDEX' in r['indexdef'] and '(campaign_id,' in r['indexdef'] for r in indexes))
        start=time.perf_counter()
        for _ in range(10):read_progress(flow.store,[identity])
        print('Synthetic local SQL progress: 4 rows, 10 aggregate reads, mean_ms='+format((time.perf_counter()-start)*100,'.2f'))
        flow.provider.post.assert_not_called()


if __name__=='__main__':unittest.main()
