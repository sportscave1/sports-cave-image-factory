"""Preview-only reuse, recipient isolation and fresh-send boundaries."""
from copy import deepcopy
from concurrent.futures import Future
from unittest import TestCase
from unittest.mock import Mock,patch
from crm_flow_preview import hydrate,_hydrate,artwork_key,PreviewShop,NoPreviewCustomer
from crm_collector_images import configurations,marker,render
from crm_middle_sections import commit_middle
from tests.test_crm_flow_customer_preview import preview_wire,document
from tests.test_crm_send_flow import CFG


class UltimatePreviewTests(TestCase):
    def test_large_history_is_fingerprinted_once_until_verified_revision_changes(self):
        from crm_flow_preview import fingerprint,preview_key
        data={'key':'order','_customer':{'id':'customer'},'_lifecycle_orders':[{'id':str(i),'lineItems':{'nodes':[{'title':'Artwork '*30,'quantity':1}]*10}} for i in range(1000)]}
        fingerprint(data);first=preview_key(data)
        with patch('crm_flow_preview.digest') as calculate:
            for _ in range(50):self.assertEqual(preview_key(data),first)
        calculate.assert_not_called()
        data['_preview_revision']=2;fingerprint(data);self.assertNotEqual(preview_key(data),first)

    def fixture(self):
        store,shop,_,candidate,_=preview_wire()
        data=dict(key=candidate['key'],label='Fixture customer',_customer=shop.customer.return_value,
                  _order=shop.orders.return_value['nodes'][0],_lifecycle_orders=shop.orders.return_value['nodes'])
        doc=document();parts=deepcopy(doc['middle_sections']);parts.append({**deepcopy(parts[0]),'id':'second-gallery','html_number':2})
        commit_middle(doc,parts)
        blocks={marker(c):[dict(id='owned',title='Correct customer artwork',quantity=2,image='https://cdn.shopify.com/owned.png',url='https://www.sportscaveshop.com/products/owned')] for c in configurations(doc)}
        facts=dict(recipient=data['_customer']['id'],blocks=blocks)
        state={'_automation_flow_facts':{artwork_key(doc,data):facts}}
        pin=dict(selected=data,options=[candidate],error='',renders={})
        return store,shop,doc,data,state,pin,facts

    def test_full_document_hydrates_once_and_sections_share_exact_facts(self):
        from crm_local_preview import model
        store,_,doc,data,state,pin,facts=self.fixture()
        store.preview_document=Mock(return_value=(render(doc,facts['blocks']),data['label']))
        with patch('streamlit.session_state',state),patch('crm_flow_preview.context',return_value=pin):
            result=model(doc,CFG,store)
        store.preview_document.assert_called_once_with(doc)
        self.assertFalse(result['errors']);self.assertEqual(result['collector'],facts['blocks'])
        for section in result['resolved'].values():self.assertIn('Correct customer artwork',section['html'])

    def test_shared_production_document_and_text_edits_compile_only_changed_section(self):
        from crm_local_preview import model
        import crm_middle_sections
        store,_,doc,data,state,pin,facts=self.fixture();store.preview_document=Mock()
        with patch('streamlit.session_state',state),patch('crm_flow_preview.context',return_value=pin):
            model(doc,CFG,store,hydrated_document=render(doc,facts['blocks']))
            doc['middle_sections'][1]['html']+='<p>Edited second section</p>'
            commit_middle(doc,doc['middle_sections'])
            with patch('crm_middle_sections.render_middle',wraps=crm_middle_sections.render_middle) as compile:
                model(doc,CFG,store,hydrated_document=render(doc,facts['blocks']))
        self.assertEqual(compile.call_count,1)
        store.preview_document.assert_not_called()

    def test_in_flight_html_edits_share_one_background_fact_job(self):
        store,_,doc,data,state,pin,facts=self.fixture();state={};future=Future()
        with patch('crm_flow_preview.context',return_value=pin),patch('crm_campaign_home_cache.CAPACITY'),patch('crm_campaign_home_cache.POOL.submit',return_value=future) as submit:
            with self.assertRaises(NoPreviewCustomer):hydrate(state,store,doc)
            doc['middle_sections'][0]['html']+='<p>Typing while artwork loads</p>'
            commit_middle(doc,doc['middle_sections'])
            with self.assertRaises(NoPreviewCustomer):hydrate(state,store,doc)
            self.assertEqual(submit.call_count,1)

    def test_visual_shop_is_session_local_deduplicated_and_does_not_cache_failures(self):
        shop=Mock();shop.query.return_value={'value':'verified'}
        a=PreviewShop(shop);b=PreviewShop(shop)
        first=a.query('query',{'id':'owned'},fresh=True);first['value']='edited'
        self.assertEqual(a.query('query',{'id':'owned'},fresh=True),{'value':'verified'})
        b.query('query',{'id':'owned'},fresh=True);self.assertEqual(shop.query.call_count,2)
        shop.query.side_effect=ValueError('Temporary outage')
        for _ in range(2):
            with self.assertRaises(ValueError):a.query('other',{})
        self.assertEqual(shop.query.call_count,4)

    def test_fresh_test_render_bypasses_visual_shop_and_artwork_cache(self):
        store,shop,doc,data,state,pin,facts=self.fixture()
        state['_automation_flow_visual_shop']=Mock()
        with patch('crm_flow_preview.context',return_value=pin),patch('crm_collector_resolver.resolve',return_value=facts) as resolve:
            _hydrate(state,store,doc,fresh=True,data=data)
        self.assertIs(resolve.call_args.args[0],shop)

    def test_other_recipient_global_artwork_is_never_exposed_to_local_editor(self):
        from crm_local_preview import model
        store,_,doc,data,state,pin,facts=self.fixture()
        state['_automation_selected_artwork']=facts['blocks'];state['_automation_flow_facts']={}
        with patch('streamlit.session_state',state),patch('crm_flow_preview.context',return_value=pin):
            result=model(doc,CFG,store,hydrated_document=render(doc,{}))
        self.assertEqual(result['collector'],{})

    def test_stale_customer_job_does_not_invalidate_active_model(self):
        store,_,doc,data,state,pin,facts=self.fixture()
        future=Future();future.set_result(((render(doc,facts['blocks']),'Previous'),{},'previous-document'))
        pin.update(renders={'old':future},render_customers={'old':'another-customer'},render_dependencies={'old':'old-dependency'},render_revision=4)
        with patch('crm_flow_preview.context',return_value=pin):hydrate(state,store,doc)
        self.assertEqual(pin['render_revision'],4)

    def test_loading_visual_does_not_overwrite_unsaved_editor_sections(self):
        from crm_local_preview import loading_canvas
        store,_,doc,_,state,_,_=self.fixture()
        with patch('streamlit.session_state',state),patch('streamlit.html') as emit,patch('streamlit.components.v1.html'):
            loading_canvas(doc,CFG,'fixture')
        source=emit.call_args.args[0]
        self.assertNotIn('s.sections=p.sections',source)
        self.assertIn('"items": []',source);self.assertIn('"collector": {}',source)

    def test_failed_artwork_refresh_retains_only_matching_recipient_document(self):
        from crm_flow_preview import fingerprint,preview_key,document_key
        from crm_automation_preview_cache import digest
        store,_,doc,data,state,pin,facts=self.fixture();fingerprint(data)
        previous=render(doc,facts['blocks']);state['_automation_flow_facts']={}
        pin.update(render_error=(digest([doc,preview_key(data)]),'Temporary image outage'),last_documents={document_key(doc,data):previous})
        with patch('crm_flow_preview.context',return_value=pin):
            self.assertEqual(hydrate(state,store,doc)[0],previous)
            self.assertEqual(store.preview_warning,'Temporary image outage')
            data['_customer']={**data['_customer'],'id':'different-customer'}
            with self.assertRaises(NoPreviewCustomer):hydrate(state,store,doc)

    def test_fingerprint_never_bypasses_fresh_artwork_comparison(self):
        from crm_flow_preview import fingerprint
        store,_,doc,data,state,pin,facts=self.fixture()
        clean=deepcopy(data);fingerprint(data)
        state['_automation_flow_facts']={artwork_key(doc,data):facts}
        changed=deepcopy(facts)
        for rows in changed['blocks'].values():rows[0]['title']='Changed since preview'
        with patch('crm_flow_preview.context',return_value=pin),patch('crm_flow_preview.verify',return_value=clean),patch('crm_collector_resolver.resolve',return_value=changed):
            with self.assertRaisesRegex(ValueError,'availability changed'):_hydrate(state,store,doc,fresh=True)

    def test_contradictory_cached_order_cannot_be_assigned_to_another_customer(self):
        from crm_flow_preview import cached_candidate
        store,shop,row,candidate,_=preview_wire()
        o=deepcopy(shop.orders.return_value['nodes'][0])
        candidate.update(profile=shop.customer.return_value,verified_at='2026-10-13',paid_at=o['createdAt'],order_record={'shopify_order_id':o['id'],'financial_status':'PAID','created_at':o['createdAt'],'raw_json':o})
        self.assertIsNotNone(cached_candidate(row,candidate))
        o['customer']={'id':'different-customer'}
        self.assertIsNone(cached_candidate(row,candidate))

    def test_failed_refresh_cannot_send_content_that_has_not_reappeared_in_preview(self):
        store,_,doc,data,state,pin,facts=self.fixture()
        state['_automation_flow_pin']=pin;pin['render_error']=('failed','Image service unavailable');state['_automation_flow_facts']={}
        with patch('crm_collector_resolver.resolve',return_value=facts) as resolve:
            with self.assertRaisesRegex(ValueError,'Refresh the preview'):_hydrate(state,store,doc,fresh=True,data=data)
        resolve.assert_not_called()

    def test_full_validation_error_still_displays_isolated_editor_sections(self):
        from crm_abandoned_checkout_ui import _lifecycle_canvas
        store,_,doc,data,state,pin,facts=self.fixture()
        resolved=render(doc,facts['blocks']);store.preview_document=Mock(return_value=(resolved,data['label']))
        with patch('crm_abandoned_checkout_ui.st') as ui,patch('crm_flow_preview.context',return_value=pin),patch('crm_flow_preview.pending',return_value=False),patch('crm_automation_preview_cache.output',side_effect=ValueError('Invalid section HTML')),patch('crm_preview_toolbar.toolbar') as toolbar,patch('crm_local_preview.canvas') as canvas:
            ui.session_state=state
            _lifecycle_canvas.__wrapped__(doc,CFG,'fixture',store,current_document=False)
        self.assertEqual(canvas.call_args.kwargs['hydrated_document'],resolved)
        self.assertIn('Invalid section HTML',toolbar.call_args.kwargs['warning'])
