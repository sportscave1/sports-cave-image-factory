from concurrent.futures import Future
from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock,patch
from crm_automation_preview_cache import digest,output
from crm_abandoned_checkout import preview_context
from tests.test_crm_abandoned_checkout import checkout
from crm_abandoned_checkout import context


class PreviewStabilityTests(TestCase):
    def test_digest_is_stable_and_sensitive_to_content(self):
        self.assertEqual(digest({'a':1,'b':2}),digest({'b':2,'a':1}))
        self.assertNotEqual(digest('old'),digest('new'))

    def test_idle_and_typing_do_not_refresh_expired_context(self):
        future=Future();future.set_result(context(checkout()))
        state={'abandoned_preview':{'future':future,'started':0,'namespace':'fixture','last_good':None}}
        shop=Mock(namespace='fixture')
        with patch('crm_abandoned_checkout.latest') as latest:
            for _ in range(50):preview_context(state,shop,auto_refresh=False)
            latest.assert_not_called()

    def test_synthetic_old_ttl_polling_vs_new_idle_path(self):
        from crm_abandoned_checkout import latest
        calls=[]
        def submit(load):
            future=Future();future.set_result(load());return future
        for automatic in (True,False):
            state={};shop=Mock(namespace='fixture')
            with patch('crm_abandoned_checkout.latest',return_value=context(checkout())) as lookup,patch('crm_campaign_home_cache.POOL.submit',side_effect=submit),patch('crm_campaign_home_cache.CAPACITY') as capacity:
                capacity.acquire.return_value=True
                for second in range(0,61,3):
                    with patch('time.monotonic',return_value=second):preview_context(state,shop,auto_refresh=automatic)
                calls.append(lookup.call_count)
        self.assertEqual(calls,[2,1]) # Original TTL polling vs no idle refresh.

    def test_html_size_and_viewport_share_one_render(self):
        state={};store=Mock();store.default_sections.return_value={}
        store.preview_document.return_value=({'content':'unchanged'},'preview')
        store.preview_warning='';message={'html':'<p>Same email</p>','text':'Same email'}
        with patch('crm_email_size.render_production',return_value=message) as render:
            for _ in range(30):cache,_,_=output(state,store,{},{} ,'fixture')
            render.assert_called_once()
            self.assertEqual(cache['size']['html_bytes'],len(message['html'].encode()))
            store.preview_document.return_value=({'content':'changed'},'preview')
            output(state,store,{},{} ,'fixture');self.assertEqual(render.call_count,2)

    def test_hydration_and_warning_cached_until_authored_content_changes(self):
        import streamlit as st
        from crm_automation_store import AutomationStore
        from tests.test_crm_checkout_preview_fallback import PreviewFallbackTests
        doc=PreviewFallbackTests().legacy_document();store=AutomationStore(Mock());store.preview_shop=Mock()
        with patch.object(st,'session_state',{}),patch('crm_abandoned_checkout.preview_context',return_value=(context(checkout()),'')),patch('crm_checkout_preview.document',wraps=__import__('crm_checkout_preview').document) as hydrate:
            for _ in range(20):store.preview_document(doc)
            hydrate.assert_called_once();self.assertIn('Legacy',store.preview_warning)
            doc=deepcopy(doc);doc['middle_sections'][0]['html']='<p>Native replacement</p>';doc['custom_html']=doc['middle_sections'][0]['html']
            store.preview_document(doc);self.assertEqual(store.preview_warning,'')

    def test_automation_only_polling_and_debounce(self):
        ui=Path('crm_abandoned_checkout_ui.py').read_text()
        self.assertNotIn('run_every',ui);self.assertNotIn('st.dialog',ui)
        self.assertNotIn('live_control',Path('crm_automation_ui.py').read_text(encoding='utf-8'))
        self.assertIn("auto_refresh=False",ui)
        section=Path('crm_section_ui.py').read_text(encoding='utf-8')
        self.assertIn("preview_debounce=350 if getattr(store,'email_mode',None)=='automation' else 750",section)
        self.assertIn("not any(s['type']==BLOCK",section)
