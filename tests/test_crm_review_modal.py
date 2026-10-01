"""Offline review concurrency and overlay boundaries; no provider sends."""
from copy import deepcopy
from pathlib import Path
import threading
import unittest
import json
import hashlib
from uuid import UUID
from unittest.mock import Mock, patch
from crm_campaign_review import start_review, identity, ReviewJob
from tests.test_crm_simple_editor import document


class ReviewModalTests(unittest.TestCase):
    def setUp(self):
        self.editor={'id':'fixture','version':1,'name':'Fixture','document':document(),'archived_at':None}
        self.saved=deepcopy(self.editor)

    def test_uuid_identity_matches_existing_string_hash_and_preserves_none(self):
        from crm_campaign_recovery import checkpoint
        value=UUID('47bb53bc-9a37-4f99-a840-e775073dbce5')
        self.editor['id']=str(value)
        expected=hashlib.sha256(json.dumps([str(value),1,checkpoint(self.editor)],sort_keys=True).encode()).hexdigest()
        self.assertEqual(identity(self.editor),expected)
        self.editor['id']=value
        self.assertEqual(identity(self.editor),expected)
        self.assertIs(self.editor['id'],value)
        self.editor['id']=None
        expected=hashlib.sha256(json.dumps([None,1,checkpoint(self.editor)],sort_keys=True).encode()).hexdigest()
        self.assertEqual(identity(self.editor),expected)
        self.assertNotIn('id',checkpoint(self.editor))

    def test_identity_does_not_hide_unsupported_checkpoint_or_id_types(self):
        self.editor['document']['unexpected']=UUID(int=1)
        with self.assertRaises(TypeError):identity(self.editor)
        del self.editor['document']['unexpected']
        self.editor['id']=object()
        with self.assertRaises(TypeError):identity(self.editor)

    def test_uuid_job_and_string_reopen_reuse_one_review_without_save(self):
        value=UUID('47bb53bc-9a37-4f99-a840-e775073dbce5')
        self.editor['id']=value;self.saved['id']=value
        gate=threading.Event()
        def finalize(*args):
            gate.wait(3)
            return {'snapshot_id':'one'}
        with patch('crm_campaign_review.review',side_effect=finalize) as review,patch('crm_campaign_review.save_checkpoint') as save:
            job=ReviewJob(Mock(),Mock(),{},self.editor,self.saved)
            try:
                string_editor={**self.editor,'id':str(value)}
                self.assertIs(start_review(job,Mock(),Mock(),{},string_editor,self.saved),job)
            finally:gate.set()
            job.future.result(3)
            self.assertIs(start_review(job,Mock(),Mock(),{},string_editor,self.saved),job)
            review.assert_called_once();save.assert_not_called()

    def test_unsaved_review_accepts_saved_draft_uuid_without_mutating_original(self):
        from crm_campaign_recovery import checkpoint
        self.editor['id']=None;self.editor['version']=None
        saved={**deepcopy(self.editor),'id':UUID(int=42),'version':1}
        with patch('crm_campaign_review.save_checkpoint',return_value=saved) as save,patch('crm_campaign_review.review',return_value={'snapshot_id':'one'}):
            job=start_review(None,Mock(),Mock(),{},self.editor,None)
            job.future.result(3)
            save.assert_called_once()
            self.assertIsInstance(job.editor['id'],UUID)
            self.assertEqual(identity(job.editor),identity({**saved,'id':str(saved['id'])}))
            json.dumps(checkpoint(job.editor))
            self.assertIsNone(self.editor['id'])

    def test_production_shaped_uuid_opens_actual_streamlit_review_dialog(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_string('''
import streamlit as st
from uuid import UUID
from copy import deepcopy
from crm_campaign_send_ui import review_dialog
from tests.test_crm_simple_editor import document
if 'campaign_editor' not in st.session_state:
 st.session_state.campaign_editor={'id':UUID('47bb53bc-9a37-4f99-a840-e775073dbce5'),'version':1,'name':'UUID fixture','document':document(),'archived_at':None}
 st.session_state.campaign_saved=deepcopy(st.session_state.campaign_editor)
if st.button('Open review'):
 review_dialog(None,None,{},st.session_state.campaign_editor,'uuid_fixture_')
''')
        result={'counts':{'eligible':3,'excluded':{}},'blockers':[],'snapshot_id':'one','tracking_ok':True}
        with patch('crm_campaign_review.review',return_value=result) as review,patch('crm_campaign_review.save_checkpoint') as save,patch('crm_campaign_send_ui.queue_campaign',side_effect=AssertionError('Never send')) as send:
            app.run();app.button[0].click().run()
            self.assertFalse(app.exception)
            job=app.session_state['uuid_fixture_review_job'];job.future.result(3)
            app.run();next(b for b in app.button if b.label=='Open review').click().run()
            self.assertFalse(app.exception)
            self.assertIs(app.session_state['uuid_fixture_review_job'],job)
            review.assert_called_once();save.assert_not_called();send.assert_not_called()

    def test_shell_returns_before_finalization_and_reopening_coalesces(self):
        gate=threading.Event()
        with patch('crm_campaign_review.review',side_effect=lambda *a:gate.wait(3) or {'snapshot_id':'one'}) as review:
            job=start_review(None,Mock(),Mock(),{},self.editor,self.saved)
            self.assertFalse(job.future.done())
            job.closed=True
            again=start_review(job,Mock(),Mock(),{},self.editor,self.saved)
            self.assertIs(job,again);self.assertFalse(job.closed)
            self.assertEqual(self.editor,self.saved)
            gate.set();job.future.result(3)
            review.assert_called_once()

    def test_error_retry_only_repeats_review_and_saved_draft_not_rewritten(self):
        with patch('crm_campaign_review.review',side_effect=[ValueError('Unavailable'),{'snapshot_id':'one'}]) as review,patch('crm_campaign_review.save_checkpoint') as save:
            first=start_review(None,Mock(),Mock(),{},self.editor,self.saved)
            with self.assertRaises(ValueError):first.future.result(3)
            second=start_review(first,Mock(),Mock(),{},self.editor,self.saved)
            self.assertEqual(second.future.result(3)['snapshot_id'],'one')
            self.assertEqual(review.call_count,2);save.assert_not_called()

    def test_pending_draft_saved_once_before_existing_review(self):
        dirty=deepcopy(self.editor);dirty['document']['content']['subject']='Changed'
        updated={**dirty,'version':2}
        order=[]
        with patch('crm_campaign_review.save_checkpoint',side_effect=lambda *a:order.append('save') or updated),patch('crm_campaign_review.review',side_effect=lambda *a:order.append('review') or {'snapshot_id':'one'}):
            job=start_review(None,Mock(),Mock(),{},dirty,self.saved);job.future.result(3)
            self.assertEqual(order,['save','review']);self.assertEqual(job.editor['version'],2)
            self.assertEqual(dirty['version'],1)

    def test_changed_segment_or_schedule_requires_new_review(self):
        original=identity(self.editor)
        for change in ({'market':'US'},{'send_timing':{'mode':'schedule','date':'2026-12-01','time':'09:00'}}):
            edited=deepcopy(self.editor);edited['document'].update(change)
            self.assertNotEqual(identity(edited),original)

    def test_ui_scope_and_fail_closed_confirmation(self):
        source=Path('crm_campaign_send_ui.py').read_text(encoding='utf-8')
        control=source.split('@st.fragment\ndef send_control')[1].split('@st.dialog')[0]
        self.assertNotIn('st.rerun',control);self.assertNotIn('history',control)
        shell=source.split('def review_dialog')[1].split('@st.fragment')[0]
        self.assertLess(shell.index('summary.write'),shell.index('start_review('))
        self.assertNotIn('render_settings(',shell)
        self.assertIn('disabled=not ready',source)
        self.assertIn("result.get('snapshot_id')",source)
        self.assertIn('event.stopImmediatePropagation()',source)
        self.assertIn('button[aria-label="Close"]',source)
        self.assertIn("st.rerun(scope='fragment')",source)
        self.assertNotIn('run_every=',source)
        self.assertNotIn('review_dialog(',Path('crm_campaign_page.py').read_text(encoding='utf-8'))

    def test_failed_finalization_stays_visible_and_retry_is_local(self):
        from streamlit.testing.v1 import AppTest
        from concurrent.futures import Future
        from types import SimpleNamespace
        app=AppTest.from_string('''
import streamlit as st
from concurrent.futures import Future
from types import SimpleNamespace
from copy import deepcopy
from crm_campaign_send_ui import review_finalization
from crm_campaign_review import identity
from tests.test_crm_simple_editor import document
if 'editor' not in st.session_state:
 st.session_state.editor={'id':'fixture','version':1,'name':'Fixture','document':document(),'archived_at':None}
 f=Future();f.set_exception(ValueError('Shopify temporarily unavailable'))
 st.session_state.job=SimpleNamespace(future=f,closed=False,applied=False)
review_finalization(None,None,{},st.session_state.editor,'test_',st.session_state.job,{'marketing_enabled':True})
''')
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(any('Audience verification failed' in c.value for c in app.caption))
        self.assertTrue(next(b for b in app.button if b.label=='Send now').disabled)
        original=deepcopy(app.session_state['editor'])
        done=Future();done.set_result({'counts':{'eligible':3,'excluded':{}},'blockers':[],'snapshot_id':'frozen','tracking_ok':True})
        replacement=SimpleNamespace(future=done,closed=False,applied=False,identity=identity(original),editor=original)
        with patch('crm_campaign_review.start_review',return_value=replacement) as retry,patch('streamlit.rerun') as rerun:
            next(b for b in app.button if b.label=='Retry').click().run()
            retry.assert_called_once()
            rerun.assert_called_once_with(scope='fragment')
        app.run()  # AppTest does not simulate fragment-scoped timer reruns.
        self.assertFalse(app.exception)
        self.assertFalse(next(b for b in app.button if b.label=='Send to 3 recipients').disabled)
        self.assertTrue(any('Ready to send' in c.value for c in app.caption))
        self.assertFalse(any('administrator verification' in w.value.lower() for w in app.warning))
        self.assertEqual(app.session_state['editor'],original)


if __name__=='__main__':unittest.main()
