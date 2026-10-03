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
        self.assertIn('run_every=1 if pending else None',ui);self.assertNotIn("st.dialog('Live preview'",ui)
        self.assertNotIn('live_control',Path('crm_automation_ui.py').read_text(encoding='utf-8'))
        self.assertIn("auto_refresh=False",ui)
        section=Path('crm_section_ui.py').read_text(encoding='utf-8')
        self.assertIn("preview_debounce=350 if getattr(store,'email_mode',None)=='automation' else 750",section)
        self.assertIn("not any(s['type']==BLOCK",section)


    def test_final_html_hash_ignores_nonvisual_input_changes(self):
        state={};store=Mock();store.preview_warning=''
        store.preview_document.return_value=({'subject':'first'},'preview')
        with patch('crm_email_size.render_production',return_value={'html':'<p>Same</p>','text':'Same'}):
            first,_,_=output(state,store,{}, {'email_defaults':{}},'fixture')
            store.preview_document.return_value=({'subject':'second'},'preview')
            second,_,_=output(state,store,{}, {'email_defaults':{}},'fixture')
        self.assertNotEqual(first['token'],second['token'])
        self.assertEqual(first['html_hash'],second['html_hash'])

    def test_editor_pin_is_isolated_from_other_preview_and_ttl(self):
        def submit(load):
            future=Future();future.set_result(load());return future
        state={};shop=Mock(namespace='fixture');initial=context(checkout())
        newer=deepcopy(initial);newer['label']='New collector'
        with patch('crm_abandoned_checkout.latest',side_effect=[initial,newer,RuntimeError('Unavailable')]) as lookup,patch('crm_campaign_home_cache.POOL.submit',side_effect=submit),patch('crm_campaign_home_cache.CAPACITY') as capacity:
            capacity.acquire.return_value=True
            pinned,_=preview_context(state,shop,auto_refresh=False,slot='_automation_checkout_pin')
            for second in range(0,901,3):
                with patch('time.monotonic',return_value=second):
                    current,_=preview_context(state,shop,auto_refresh=False,slot='_automation_checkout_pin')
                    self.assertEqual(current,pinned)
            self.assertEqual(lookup.call_count,1)
            other,_=preview_context(state,shop,refresh=True,auto_refresh=False)
            self.assertEqual(other['label'],'New collector')
            self.assertEqual(state['_automation_checkout_pin']['last_good'],initial)
            current,_=preview_context(state,shop,refresh=True,auto_refresh=False,slot='_automation_checkout_pin')
            self.assertEqual(current,initial)
            self.assertEqual(lookup.call_count,3)
            preview_context(state,shop,auto_refresh=False,slot='_automation_checkout_pin')
            self.assertEqual(lookup.call_count,3)

    def test_native_preview_and_native_size_have_no_asset_dependency(self):
        ui=Path('crm_abandoned_checkout_ui.py').read_text()
        canvas=ui.split('def template_control')[0]
        self.assertNotIn('declare_component',canvas)
        self.assertIn("components.html(cache['message']['html']",canvas)
        self.assertIn('iframe[data-testid="stIFrame"]',canvas)
        size=Path('crm_email_size_ui.py').read_text().split('@st.fragment')[0]
        self.assertNotIn('declare_component',size)
        self.assertIn("st.html(meter_html(cache['size']))",size)

    def test_send_test_does_not_replace_pinned_editor_checkout(self):
        import streamlit as st
        from crm_automation_store import AutomationStore
        from tests.test_crm_abandoned_checkout import native_document
        pinned=context(checkout());state={'_automation_checkout_pin':{'last_good':pinned,'started':0}}
        original=deepcopy(state)
        store=AutomationStore(Mock());store.draft_identity='fixture';store.preview_shop=Mock()
        store.flow=Mock(return_value={'config':{'draft':{'trigger':'abandoned'}}})
        fresh=deepcopy(pinned);fresh['label']='Another collector'
        with patch.object(st,'session_state',state),patch('crm_abandoned_checkout.latest',return_value=fresh) as lookup:
            rendered=store.test_document(native_document(),'test-operation')
        lookup.assert_called_once();self.assertEqual(state,original)
        self.assertIn('Recovery action disabled',str(rendered))


    def test_leaving_editor_invalidates_pin_scope_only_after_navigation_allowed(self):
        from crm_navigation import navigation_allowed
        editor={'document':{'copy':'same'},'name':'Reminder'}
        state={'automation_editor':deepcopy(editor),'automation_saved':deepcopy(editor),'_automation_preview_open':'scope'}
        state['automation_editor']['document']['copy']='unsaved'
        self.assertFalse(navigation_allowed(state,'CRM Automations','Orders'))
        self.assertEqual(state['_automation_preview_open'],'scope')
        state['automation_saved']=deepcopy(state['automation_editor'])
        self.assertTrue(navigation_allowed(state,'CRM Automations','Orders'))
        self.assertNotIn('_automation_preview_open',state)


    def test_size_and_canvas_representations_do_not_evict_each_other(self):
        state={};store=Mock();store.preview_warning=''
        with patch('crm_email_size.render_production',return_value={'html':'<p>Same</p>','text':'Same'}) as render:
            for _ in range(30):
                for variant in ('stored','editor'):
                    store.preview_document.return_value=({'representation':variant},'preview')
                    output(state,store,{}, {'email_defaults':{}},'fixture')
            self.assertEqual(render.call_count,2)
            for index in range(10):
                store.preview_document.return_value=({'representation':index},'preview')
                output(state,store,{}, {'email_defaults':{}},'fixture')
            self.assertEqual(len(state['_automation_visual_outputs']),4)


    def test_pipeline_lengths_and_preview_only_compiler_failure(self):
        from crm_abandoned_checkout import hydrate,block_html
        from crm_checkout_styles import default_html,MARKER
        from tests.test_crm_abandoned_checkout import native_document
        from crm_campaign_html import import_html
        from crm_email_size import render_production
        from tests.test_crm_send_flow import CFG
        data=context(checkout());doc=native_document()
        self.assertIn(MARKER,default_html())
        self.assertGreater(len(block_html(data)),0)
        compiled=hydrate(doc,data,preview=True)
        message=render_production(compiled,CFG)
        self.assertGreater(len(message['html']),0)
        self.assertNotIn(MARKER,message['html'])
        self.assertIn('sc-cart-variant',message['html'])
        with patch('crm_checkout_styles.compile_document',side_effect=RuntimeError('Synthetic compiler failure')):
            with self.assertLogs('crm_abandoned_checkout',level='ERROR'):
                warnings=[]
                fallback=hydrate(doc,data,preview=True,preview_warnings=warnings)
            self.assertTrue(warnings)
            safe=render_production(fallback,CFG)
            self.assertIn('Complete Your Order',safe['html'])
            self.assertIn('Black frame / Large',safe['html'])
            with self.assertRaises(RuntimeError):hydrate(doc,data,preview=False)

    def test_failed_render_retains_last_good_native_preview(self):
        import streamlit as st
        from crm_abandoned_checkout_ui import _automation_canvas
        from crm_email_size import analyze_rendered_email
        from unittest.mock import MagicMock
        cache={'html_hash':'known','message':{'html':'<p>Last good design</p>','text':'Last good design'},'size':analyze_rendered_email('<p>Last good design</p>','Last good design')}
        state={'fixture_last_good_visual':(cache,'Previewing: Fixture','')}
        with patch.object(st,'session_state',state),patch.object(st,'container',return_value=MagicMock()),patch.object(st,'markdown'),patch.object(st,'button',return_value=False),patch.object(st,'caption'),patch.object(st,'html'),patch('crm_automation_preview_cache.output',side_effect=RuntimeError('Synthetic render failure')),patch('crm_abandoned_checkout_ui.components.html') as preview, self.assertLogs('crm_abandoned_checkout_ui',level='ERROR'):
            _automation_canvas({}, {}, 'fixture_',Mock(),current_document=False)
        preview.assert_called_once_with('<p>Last good design</p>',width=600,height=520,scrolling=True)


    def test_first_render_failure_stops_completed_lookup_timer(self):
        import streamlit as st
        from crm_abandoned_checkout_ui import _automation_canvas
        from unittest.mock import MagicMock
        future=Future();future.set_result(context(checkout()))
        state={'_automation_checkout_pin':{'future':future}}
        with patch.object(st,'session_state',state),patch.object(st,'container',return_value=MagicMock()),patch.object(st,'markdown'),patch.object(st,'button',return_value=False),patch.object(st,'caption'),patch.object(st,'html'),patch.object(st,'rerun') as rerun,patch('crm_automation_preview_cache.output',side_effect=RuntimeError('Synthetic failure')), self.assertLogs('crm_abandoned_checkout_ui',level='ERROR'):
            _automation_canvas({}, {}, 'fixture_',Mock(),current_document=False,loading=True)
        rerun.assert_called_once_with(scope='app')
