"""Offline offers, callback lifecycle and immutable delivery contracts."""
from concurrent.futures import Future
from copy import deepcopy
import json
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch,Mock
from crm_discount_api import search,code_page,metadata,selectable,SEARCH,CODES
from crm_discount_section import insert,offer_sections,migrate_editor,validate_presentation
from crm_middle_sections import middle_sections,apply_event,commit_middle
from crm_recovery_discount import substitute,prepare,DiscountHold
from crm_campaign_content import validate_document,render_campaign
from tests.test_crm_discounts import DiscountShop,node
from tests.test_crm_campaign_sections import sectioned
from tests.test_crm_send_flow import CFG


def event(doc,action,**kwargs):return {'type':action,'base':[s['id'] for s in middle_sections(doc)],**kwargs}
def add(doc,shop=None,code='FIXTURE5'):
    shop=shop or DiscountShop();insert(doc,metadata(shop.node,code),event(doc,'discount_select'),trigger='abandoned')
    return offer_sections(doc)[-1]


class EditorDiscountTests(unittest.TestCase):
    def setUp(self):self.doc=sectioned();self.shop=DiscountShop()
    def test_selection_inserts_bound_editable_html_and_correct_value(self):
        s=add(self.doc,self.shop);validate_document(self.doc)
        self.assertEqual(self.doc['recovery_discount']['value'],'A$5 off')
        self.assertIn('{{discount_code}}',s['html']);self.assertIn('{{discount_value}}',s['html'])
        rendered=render_campaign(substitute(self.doc),CFG)
        self.assertIn('FIXTURE5',rendered['html']);self.assertIn('A$5 off',rendered['html']);self.assertNotIn('{{discount_',rendered['html'])
    def test_all_compatible_types_use_shopify_metadata(self):
        for kind in ('DiscountCodeBasic','DiscountCodeFreeShipping','DiscountCodeBxgy','DiscountCodeApp'):
            self.shop.node=node(kind);doc=sectioned();add(doc,self.shop);validate_presentation(doc)
            self.assertEqual(doc['middle_sections'][-1]['offer']['type'],kind)
            self.assertEqual(substitute(doc)['middle_sections'][-1]['type'],'image')
    def test_no_other_email_or_published_copy_changed(self):
        emails=[sectioned() for _ in range(3)];frozen=deepcopy(emails)
        add(emails[2]);self.assertEqual(emails[:2],frozen[:2]);self.assertNotIn('recovery_discount',frozen[2])
    def test_html_style_edits_move_duplicate_hide_remove_restore(self):
        s=add(self.doc);identity=s['id'];html=s['html'].replace('18px 22px','10px 12px').replace('#171717','#202020').replace('AN EXCLUSIVE COLLECTOR OFFER','A personal collector offer')
        apply_event(self.doc,event(self.doc,'html',id=identity,html=html))
        apply_event(self.doc,event(self.doc,'order',ids=[identity,'html-1']))
        apply_event(self.doc,event(self.doc,'duplicate',id=identity))
        self.assertEqual(len(offer_sections(self.doc)),2)
        self.assertEqual(offer_sections(self.doc)[0]['html'],html)
        for s in offer_sections(self.doc):apply_event(self.doc,event(self.doc,'visible',id=s['id'],visible=False))
        self.assertNotIn('recovery_discount',self.doc);substitute(self.doc)
        apply_event(self.doc,event(self.doc,'visible',id=identity,visible=True))
        self.assertEqual(self.doc['recovery_discount']['code'],'FIXTURE5')
        snapshot=deepcopy(offer_sections(self.doc)[0])
        for s in offer_sections(self.doc):apply_event(self.doc,event(self.doc,'remove',id=s['id'],confirmed=True))
        self.assertNotIn('recovery_discount',self.doc)
        apply_event(self.doc,event(self.doc,'restore_section',section=snapshot,position=0))
        self.assertEqual(self.doc['recovery_discount']['code'],'FIXTURE5')
    def test_conflicting_duplicate_cannot_become_active(self):
        add(self.doc);s=deepcopy(offer_sections(self.doc)[0]);s['id']='other';s['offer']['code']='OTHER'
        before=deepcopy(self.doc)
        with self.assertRaisesRegex(ValueError,'one Shopify offer'):commit_middle(self.doc,middle_sections(self.doc)+[s])
        self.assertEqual(self.doc,before)
    def test_change_offer_updates_all_presentations_without_erasing_html(self):
        s=add(self.doc);apply_event(self.doc,event(self.doc,'duplicate',id=s['id']))
        html=[s['html'] for s in offer_sections(self.doc)]
        add(self.doc,self.shop,code='SECOND')
        self.assertEqual({s['offer']['code'] for s in offer_sections(self.doc)},{'SECOND'})
        self.assertEqual([s['html'] for s in offer_sections(self.doc)],html)
    def test_manual_amount_or_missing_authoritative_token_holds(self):
        s=add(self.doc)
        for replacement in ('50% OFF','A$50 off','fifty percent off','Free shipping'):
            copy=deepcopy(self.doc);copy['middle_sections'][-1]['html']=s['html'].replace('{{discount_value}}',replacement)
            with self.assertRaises(ValueError):substitute(copy)
        self.doc['middle_sections'][-1]['html']+='<p>Save 50%</p>'
        with self.assertRaises(ValueError):substitute(self.doc)

    def test_code_only_and_code_plus_value_survive_edit_move_and_json_reopen(self):
        for markup in ('<p style="color:#bd9650;font-size:24px">Collector code {{discount_code}}</p>',
                       '<p>{{discount_code}} — {{discount_value}}</p>'):
            doc=sectioned();s=add(doc);offer=deepcopy(doc['recovery_discount']);frozen=deepcopy(doc)
            apply_event(doc,event(doc,'html',id=s['id'],html=markup))
            for ids in ([s['id'],'html-1'],['html-1',s['id']]):
                apply_event(doc,event(doc,'order',ids=ids))
                doc=json.loads(json.dumps(doc));validate_presentation(doc)
                self.assertEqual(doc['recovery_discount'],offer)
                self.assertEqual(offer_sections(doc)[0]['offer'],offer)
            rendered=render_campaign(substitute(doc),CFG)
            self.assertIn('FIXTURE5',rendered['html']);self.assertNotIn('{{discount_',rendered['html'])
            self.assertEqual('A$5 off' in rendered['html'],'discount_value' in markup)
            self.assertNotEqual(offer_sections(frozen)[0]['html'],markup)

    def test_code_required_even_when_amount_omitted(self):
        s=add(self.doc)
        for markup in ('<p>Collector offer</p>','<style>{{discount_code}}</style><p>Offer</p>','<p>{{discount_value}}</p>'):
            self.doc['middle_sections'][-1]['html']=markup
            with self.assertRaisesRegex(ValueError,'Keep {{discount_code}}'):validate_presentation(self.doc)

    def test_preview_cache_updates_immediately_for_code_only_edit(self):
        from crm_automation_preview_cache import output
        s=add(self.doc);store=Mock();store.preview_warning=''
        store.preview_document.side_effect=lambda doc:(substitute(doc),'Sample')
        state={};cfg={**CFG,'email_defaults':{}}
        old=output(state,store,self.doc,cfg)[0]
        apply_event(self.doc,event(self.doc,'html',id=s['id'],html='<p>Private collector code {{discount_code}}</p>'))
        new=output(state,store,self.doc,cfg)[0]
        self.assertNotEqual(new['html_hash'],old['html_hash'])
        self.assertIn('Private collector code FIXTURE5',new['message']['html'])
        self.assertNotIn('A$5 off',new['message']['html'])
        self.assertEqual(output(state,store,self.doc,cfg)[0],new)
    def test_removed_offer_tokens_save_as_draft_but_cannot_publish_or_render(self):
        from crm_automation_definition import new_flow,email_step,validate
        add(self.doc);self.doc['content']['subject']='Offer {{discount_value}}'
        apply_event(self.doc,event(self.doc,'remove',id=offer_sections(self.doc)[0]['id'],confirmed=True))
        flow=new_flow('abandoned');flow['emails']=[email_step(self.doc,0)]
        validate(flow,draft=True)
        with self.assertRaises(ValueError):validate(flow)
        with self.assertRaisesRegex(ValueError,'discount_not_selected'):substitute(self.doc)
    def test_legacy_editor_migration_is_lossless_without_mutating_source(self):
        row=metadata(self.shop.node,'FIXTURE5');self.doc['recovery_discount']={k:row[k] for k in ('id','code','value','type')}
        before=deepcopy(self.doc);migrated=migrate_editor(self.doc)
        self.assertEqual(self.doc,before);self.assertEqual(migrated['recovery_discount'],before['recovery_discount'])
        self.assertEqual(len(offer_sections(migrated)),1);self.assertEqual(migrate_editor(migrated),migrated)
    def test_bound_offer_html_uses_existing_recovery_actions_and_preserves_wall_preview(self):
        from crm_recovery_links import TOKEN,inspect,verify,destination
        from crm_abandoned_checkout import context,hydrate
        from crm_checkout_elements import element
        from tests.test_crm_abandoned_checkout import native_document,checkout
        doc=native_document();s=add(doc)
        s['html']+=f'<a href="{TOKEN}">Claim Your Edition</a><a href="https://example.test/wall-preview">Wall Preview</a>'
        doc['middle_sections'][-1]=s
        doc['middle_sections'].extend([element('product_image'),element('lifestyle',position=2),element(text='Complete Your Order')])
        cart=checkout();self.shop.checkout.update(id=cart['id'],customer=cart['customer'],abandonedCheckoutUrl=cart['abandonedCheckoutUrl'])
        verified=prepare(self.shop,doc,cart,cart['customer']['id'])
        data=context(cart,edition_reader=Mock(return_value=[]));data['recovery_url']=destination(data,verified)
        gallery=Mock();gallery.campaign_images.return_value={'nodes':[{'url':'https://cdn.shopify.com/first.png'},{'url':'https://cdn.shopify.com/lifestyle.png'}]}
        before=deepcopy(doc);html=render_campaign(hydrate(substitute(doc,verified),data,shop=gallery),CFG)
        urls=[u for u in inspect(html['html']).urls if '/checkouts/' in u]
        self.assertGreaterEqual(len(urls),5);self.assertEqual(set(urls),{verified['url']})
        verify(html,verified['url'],len(urls));self.assertIn('https://example.test/wall-preview',html['html'])
        self.assertNotIn(TOKEN,html['html']);self.assertEqual(doc,before)
    def test_unverified_offer_text_holds_before_any_shopify_reads(self):
        s=add(self.doc);self.doc['middle_sections'][-1]['html']=s['html']+'<p>Save 90%</p>'
        with self.assertRaisesRegex(DiscountHold,'discount_copy_unverified'):
            prepare(self.shop,self.doc,self.shop.checkout,self.shop.checkout['customer']['id'])
        self.assertEqual(self.shop.calls,[])
    def test_inactive_expired_unsupported_and_noncheckout_selection_rejected(self):
        row=metadata(self.shop.node,'FIXTURE5')
        for status in ('SCHEDULED','EXPIRED','INACTIVE'):
            with self.assertRaises(ValueError):insert(self.doc,{**row,'status':status},event(self.doc,'discount_select'),trigger='abandoned')
        with self.assertRaises(ValueError):insert(self.doc,{**row,'supported':False},event(self.doc,'discount_select'),trigger='abandoned')
        with self.assertRaises(ValueError):insert(self.doc,row,event(self.doc,'discount_select'),trigger='welcome')
        self.assertNotIn('recovery_discount',self.doc)


class SearchTests(unittest.TestCase):
    def setUp(self):self.shop=DiscountShop()
    def test_browse_partial_exact_and_title_search_are_bounded(self):
        for term in ('','FIXTURE5','FIX','Fixture discount'):
            search(self.shop,term)
        requests=[v for q,v,_ in self.shop.calls if q==SEARCH]
        self.assertEqual(requests[0]['query'],'method:code')
        self.assertIn('title:FIX*',requests[2]['query']);self.assertIn('code:FIX*',requests[2]['query'])
        self.assertIn('title:Fixture*',requests[3]['query']);self.assertIn('title:discount*',requests[3]['query'])
        self.assertIn('first:15',SEARCH);self.assertIn('codes(first:20',SEARCH)
    def test_cached_metadata_refresh_and_explicit_pagination(self):
        search(self.shop,'FIX');n=len(self.shop.calls);search(self.shop,'FIX');self.assertEqual(len(self.shop.calls),n)
        search(self.shop,'FIX',refresh=True);self.assertGreater(len(self.shop.calls),n)
        search(self.shop,'FIX','page2');self.assertEqual(next(v for q,v,_ in reversed(self.shop.calls) if q==SEARCH)['after'],'page2')
    def test_bulk_code_query_keeps_cursor_and_term(self):
        code_page(self.shop,self.shop.node['id'],'cursor',term='FIX')
        query,variables,_=self.shop.calls[-1];self.assertEqual(query,CODES)
        self.assertEqual(variables['codesQuery'],'FIX*');self.assertEqual(variables['codesAfter'],'cursor')
    def test_transport_failure_and_malformed_response_are_not_empty_results(self):
        original=self.shop.query
        for failure in (TimeoutError('offline'),{}):
            def query(q,*args,**kwargs):
                if q!=SEARCH:return original(q,*args,**kwargs)
                if isinstance(failure,Exception):raise failure
                return failure
            self.shop.query=query
            with self.assertRaises((ValueError,TimeoutError)):search(self.shop,refresh=True)
    def test_empty_results_are_explicit_success(self):
        original=self.shop.query
        self.shop.query=lambda q,*a,**k: {'discountNodes':{'nodes':[],'pageInfo':{'hasNextPage':False}}} if q==SEARCH else original(q,*a,**k)
        self.assertEqual(search(self.shop)['rows'],[])


class CallbackTests(unittest.TestCase):
    def setUp(self):
        import crm_discount_ui as ui
        self.ui=ui;self.state={};self.mock=patch.object(ui.st,'session_state',self.state);self.mock.start();self.addCleanup(self.mock.stop)
        self.shop=DiscountShop();self.doc=sectioned();self.key='discount-v2-'
    def request(self,action,**extra):return self.ui.handle(self.shop,self.doc,self.key,event(self.doc,action,**extra),trigger='abandoned')
    def done(self):
        job=self.ui.state(self.key).get('job')
        if job:job['future'].result(timeout=2)
        self.ui.collect(self.ui.state(self.key))
    def test_open_search_poll_close_reopen_never_reruns_or_edits(self):
        before=deepcopy(self.doc)
        with patch.object(self.ui.st,'rerun',side_effect=AssertionError('Forbidden imperative rerun')):
            self.request('add',kind='discount');self.done();self.request('discount_poll')
            self.assertEqual(len(self.ui.view(self.key,trigger='abandoned')['rows']),1)
            self.request('discount_search',term='FIX');self.done();self.request('discount_close')
            n=len(self.shop.calls);self.request('discount_open');self.assertEqual(len(self.shop.calls),n)
        self.assertEqual(self.doc,before)
    def test_timeout_retains_form_results_and_late_completion_cannot_overwrite(self):
        state=self.ui.state(self.key);state['rows']=[metadata(self.shop.node,'OLD')]
        late=Future();state['job']={'future':late,'started':time.monotonic()-31,'generation':0}
        before=deepcopy(self.doc);self.ui.collect(state)
        self.assertIn('timed out',state['error']);self.assertEqual(state['rows'][0]['code'],'OLD');self.assertEqual(self.doc,before)
        self.assertNotIn('job',state)
    def test_search_errors_preserve_existing_results(self):
        state=self.ui.state(self.key);state['rows']=[metadata(self.shop.node,'OLD')]
        future=Future();future.set_exception(TimeoutError('offline'))
        state['job']={'future':future,'started':time.monotonic(),'generation':0}
        self.ui.collect(state);self.assertIn('failed',state['error']);self.assertEqual(state['rows'][0]['code'],'OLD')
    def test_obsolete_search_never_replaces_new_results(self):
        state=self.ui.state(self.key);old=Future();old.set_running_or_notify_cancel();new=Future()
        with patch.object(self.ui.POOL,'submit',side_effect=[old,new]):
            self.ui.launch(state,lambda:None);self.ui.launch(state,lambda:None)
            page={'rows':[metadata(self.shop.node,'NEW')],'pageInfo':{'hasNextPage':False}}
            new.set_result(page);self.ui.collect(state)
            old.set_result({**page,'rows':[metadata(self.shop.node,'OLD')]});self.ui.collect(state)
        self.assertEqual(state['rows'][0]['code'],'NEW')
        # These fake futures did not execute the worker's finally block.
        self.ui.CAPACITY.release();self.ui.CAPACITY.release()
    def test_group_search_restarts_cursor_and_paginates_with_same_query(self):
        self.shop.node['codeDiscount']['codes']['pageInfo']={'hasNextPage':True,'endCursor':'bulk-cursor'}
        self.request('discount_open');self.done()
        self.request('discount_codes',id=self.shop.node['id']);self.done()
        self.assertIsNone(self.shop.calls[-1][1]['codesAfter'])
        self.request('discount_search',term='FIX');self.done()
        self.assertEqual(self.shop.calls[-1][1]['codesQuery'],'FIX*');self.assertIsNone(self.shop.calls[-1][1]['codesAfter'])
        self.request('discount_next');self.done()
        self.assertEqual(self.shop.calls[-1][1]['codesAfter'],'bulk-cursor');self.assertEqual(self.shop.calls[-1][1]['codesQuery'],'FIX*')
        self.assertEqual(len(self.ui.state(self.key)['rows']),1)
        self.request('discount_browse');self.done();self.assertIsNone(self.ui.state(self.key)['group'])
    def test_expired_display_cache_is_refreshed_when_reopened(self):
        self.request('discount_open');self.done();state=self.ui.state(self.key)
        self.request('discount_close');state['loaded_at']-=61
        with patch.object(self.ui,'search',return_value={'rows':[],'pageInfo':{'hasNextPage':False}}) as search:
            self.request('discount_open');self.done();search.assert_called_once()
        self.assertEqual(state['rows'],[])
    def test_callback_only_persists_a_real_selection_and_acks_once(self):
        editor={'name':'Email 3','document':self.doc};self.state.update(email_editor_mode='automation',automation_editor=editor,automation_saved=deepcopy(editor))
        self.ui.state(self.key)['rows']=[metadata(self.shop.node,'FIXTURE5')]
        self.state[self.key+'middle']=event(self.doc,'discount_select',id=self.shop.node['id'],code='FIXTURE5',event='one')
        with patch('crm_campaign_recovery.flush_current') as save,patch.object(self.ui.st,'rerun',side_effect=AssertionError):
            self.ui.callback(self.shop,self.doc,self.key,trigger='abandoned');self.ui.callback(self.shop,self.doc,self.key,trigger='abandoned')
            save.assert_called_once()
        self.assertEqual(self.doc['recovery_discount']['code'],'FIXTURE5')
    def test_discovery_callback_never_writes_draft_or_requests_rerun(self):
        self.state[self.key+'middle']=event(self.doc,'add',kind='discount',event='open')
        with patch('crm_campaign_recovery.flush_current') as save,patch.object(self.ui.st,'rerun',side_effect=AssertionError):
            self.ui.callback(self.shop,self.doc,self.key,trigger='abandoned');self.done();save.assert_not_called()
    def test_no_settings_controls_or_imperative_discount_rerun_remain(self):
        source=Path('crm_campaign_page.py').read_text(encoding='utf-8');discount=Path('crm_discount_ui.py').read_text(encoding='utf-8')
        self.assertNotIn('discount_control',source);self.assertNotIn('st.rerun(',discount)
        self.assertNotIn('Apply Shopify discount automatically',discount)


if __name__=='__main__':unittest.main()
