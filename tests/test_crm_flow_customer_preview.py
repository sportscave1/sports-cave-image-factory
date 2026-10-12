"""Synthetic fixtures only. No credentials, real customers or provider I/O."""
from copy import deepcopy
from concurrent.futures import Future
from datetime import timedelta
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock,MagicMock,patch
import json

from crm_post_purchase_templates import source,PREFIX,library_rows
from crm_collector_images import configurations,marker,purchased,render,REPEAT
from crm_collector_resolver import resolve,ORDER,BESTSELLERS,PRODUCTS
from crm_campaign_content import new_document,validate_document,render_campaign
from crm_middle_sections import commit_middle,apply_event
from crm_flow_preview import verify,hydrate,context,NoPreviewCustomer
from tests.test_crm_collector_personalisation import order,product,wire,A,B,P,Q,O,AT,IMAGE
from tests.test_crm_send_flow import CFG


def document(key='purchased'):
    doc=new_document();doc['content_mode']='HTML';doc['content'].update(subject='Thank you {{first_name}}',preheader='Your artwork')
    commit_middle(doc,[dict(id='gallery',type='html',visible=True,html_number=1,html=source(key))])
    return doc


def preview_wire(kind='post_purchase',age=1):
    customer=dict(id=A,firstName='Fixture Ada',email='ada@example.invalid',validEmailAddress=True,
                  emailMarketingConsent={'marketingState':'SUBSCRIBED','consentUpdatedAt':AT.isoformat()},
                  defaultEmailAddress={'marketingState':'SUBSCRIBED','validFormat':True,'emailAddress':'ada@example.invalid'},
                  defaultAddress={'countryCodeV2':'AU'})
    paid=AT-timedelta(days=age)
    o=order();o.update(createdAt=paid.isoformat(),displayFulfillmentStatus='FULFILLED')
    flow=dict(trigger=kind,rules=[],inactive_days=90,emails=[{'step_id':'one','delay_seconds':0,'document':document()}])
    row=dict(id='fixture-flow',trigger_type=kind,config={'draft':flow})
    store=Mock();store.email_mode='automation';store.preview_row=row;store.preview_flow=flow;store.preview_trigger=kind;store.connect=None
    store.state.return_value={'scopes':['read_customers','read_orders','read_all_orders']};store.suppressed.return_value=False
    def query(sql,args=(),*rest):
        if 'SELECT * FROM shopify_orders' in sql:return [dict(shopify_order_id=O,created_at=paid.isoformat())]
        if 'SELECT object_id,topic' in sql:return [dict(object_id=O,topic='orders/paid',occurred_at=paid.isoformat())]
        return []
    store.q.side_effect=query
    shop=Mock(namespace='fixture');shop.customer.return_value=customer
    shop.orders.return_value={'nodes':[] if kind=='welcome' else [o],'pageInfo':{'hasNextPage':False}}
    shop.products.return_value=[product(P)]
    shop.query.side_effect=lambda q,v,*rest: {'order':o} if q==ORDER else {'nodes':[]}
    store.preview_shop=shop
    operational={O:dict(id=O,risk={'recommendation':'ACCEPT'},disputes=[],returnStatus='NO_RETURN',
                  fulfillments=[dict(status='SUCCESS',createdAt=paid.isoformat(),deliveredAt=None)])}
    candidate=dict(key=A if kind=='welcome' else O,customer_id=A,name='Fixture Ada')
    return store,shop,row,candidate,operational


class GalleryTests(TestCase):
    def test_single_multiple_variant_quantities_missing_image_and_links(self):
        o=order();line=o['lineItems']['nodes'][0];line['quantity']=2
        line['variant']=dict(id='gid://shopify/ProductVariant/1',product={'id':P},image={'url':'https://cdn.shopify.com/exact.png'})
        duplicate=deepcopy(line);duplicate['quantity']=3
        other=dict(id='gid://shopify/LineItem/2',title='Other sporting artwork',quantity=1,product={'id':Q})
        o['lineItems']['nodes']=[line,duplicate,other]
        facts=purchased(o,A,[product(P),{**product(Q),'featuredImage':{}}])
        self.assertEqual(len(facts),2);self.assertEqual(facts[0]['quantity'],5)
        doc=document();original=deepcopy(doc);cfg=configurations(doc)[0]
        out=render(doc,{marker(cfg):facts})
        out['content']['subject']='Thank you';html=render_campaign(out,CFG,production=True,unsubscribe_url='https://www.sportscaveshop.com/account/unsubscribe?token=fixture')['html']
        self.assertIn('exact.png',html);self.assertEqual(html.count('exact.png'),1)
        self.assertIn('Quantity: 5',html);self.assertIn('Other sporting artwork',html)
        self.assertIn('/products/fixture-1',html);self.assertNotIn('src=""',html)
        self.assertEqual(doc,original)

    def test_edit_duplicate_remove_reorder_and_json_reopen_bindings(self):
        doc=document();s=doc['middle_sections'][0];s['html']=s['html'].replace('font-size:22px;font-family:Georgia','font-size:18px;font-family:Arial').replace('Explore artwork','See my art')
        commit_middle(doc,[s]);apply_event(doc,dict(type='duplicate',base=['gallery'],id='gallery',new_id='copy'))
        restored=json.loads(json.dumps(doc));validate_document(restored)
        cfg=configurations(restored)[0];facts=purchased(order(),A,[product(P)])
        html=render(restored,{marker(cfg):facts})['middle_sections'][1]['html']
        self.assertIn('See my art',html);self.assertIn('font-size:18px;font-family:Arial',html)
        self.assertNotIn('[[product.',html)
        apply_event(restored,dict(type='remove',base=['gallery','copy'],id='gallery',confirmed=True))
        self.assertEqual(len(configurations(restored)),1)

    def test_damaged_binding_is_validation_error_not_sample(self):
        doc=document();doc['middle_sections'][0]['html']=doc['middle_sections'][0]['html'].replace('<!--SC_COLLECTOR_REPEAT_END-->','')
        with self.assertRaisesRegex(ValueError,'binding'):configurations(doc)

    def test_collections_six_sales_rank_exclusions_duplicates_and_unavailable(self):
        collection={'id':'gid://shopify/Collection/1','title':'Motorsport','handle':'motorsport'}
        pp=product(P,collections={'nodes':[collection],'pageInfo':{'hasNextPage':False}})
        candidates=[product('gid://shopify/Product/'+str(n)) for n in range(2,11)]
        candidates[0]['variants']['nodes'][0]['sellableOnlineQuantity']=0
        candidates[1]=product('gid://shopify/Product/3','Basketball')
        candidates[2]['status']='DRAFT'
        shop,store=wire();shop.products.return_value=[pp]
        ranks=[P,P,*[p['id'] for p in candidates]]
        shop.query.side_effect=lambda q,v,*rest:({'order':order()} if q==ORDER else {'collection':{'id':collection['id'],'products':{'nodes':[{'id':i} for i in ranks]}}} if q==BESTSELLERS else {'nodes':candidates})
        doc=document('collections');cfg=configurations(doc)[0];ctx={'_customer':{'id':A,'defaultAddress':{'countryCodeV2':'AU'}},'_order':order(),'_lifecycle_orders':[order()]}
        rows=resolve(shop,store,doc,ctx,A,AT)['blocks'][marker(cfg)]
        self.assertEqual(len(rows),6);self.assertEqual(len({p['id'] for p in rows}),6)
        self.assertEqual(rows[0]['id'],'gid://shopify/Product/5')
        self.assertNotIn(P,[p['id'] for p in rows]);self.assertEqual(rows[-1]['id'],'gid://shopify/Product/10')
        self.assertNotIn('bestseller',render(doc,{marker(cfg):rows})['custom_html'].lower())

    def test_no_matching_collection_never_discovers_storewide(self):
        shop,store=wire();doc=document('collections');ctx={'_customer':{'id':A,'defaultAddress':{'countryCodeV2':'AU'}},'_order':order(),'_lifecycle_orders':[order()]}
        rows=resolve(shop,store,doc,ctx,A,AT)['blocks'][marker(configurations(doc)[0])]
        self.assertEqual(rows,[]);self.assertEqual(shop.query.call_count,1)

    def test_mixed_collections_and_default_order_fallback(self):
        from crm_shopify import CapabilityUnavailable
        motor={'id':'gid://shopify/Collection/1','title':'Motorsport','handle':'motorsport'}
        basket={'id':'gid://shopify/Collection/2','title':'Basketball','handle':'basketball'}
        o=order();o['lineItems']['nodes'].append(dict(id='gid://shopify/LineItem/2',title='Fixture Basketball',product={'id':Q},quantity=1))
        shop,store=wire(source=o)
        shop.products.return_value=[product(P,collections={'nodes':[motor]}),product(Q,'Basketball',collections={'nodes':[basket]})]
        candidates=[product('gid://shopify/Product/3'),product('gid://shopify/Product/4','Basketball')]
        default=BESTSELLERS.replace('BEST_SELLING','COLLECTION_DEFAULT')
        def query(q,args,*rest):
            if q==ORDER:return {'order':o}
            if q==BESTSELLERS:raise CapabilityUnavailable('fixture ranking unavailable')
            if q==default:return {'collection':{'id':args['id'],'products':{'nodes':[{'id':candidates[0 if args['id']==motor['id'] else 1]['id']}]}}}
            return {'nodes':candidates}
        shop.query.side_effect=query
        doc=document('collections');ctx={'_customer':{'id':A,'defaultAddress':{'countryCodeV2':'AU'}},'_order':o,'_lifecycle_orders':[o]}
        rows=resolve(shop,store,doc,ctx,A,AT)['blocks'][marker(configurations(doc)[0])]
        self.assertEqual([r['id'] for r in rows],[p['id'] for p in candidates])
        self.assertEqual(sum(call.args[0]==default for call in shop.query.call_args_list),2)

    def test_builtin_html_save_and_reopen_preserve_edited_bindings(self):
        from crm_template_library import save_builtin,source as reopen
        from crm_template_cache import invalidate
        from tests.test_crm import ADMIN
        row=library_rows()[0];row['revision']=0
        html=source(row['id']).replace('Your artwork, chosen by you','My own heading').replace('color:#f4efe5','color:#eeddcc')
        persisted={'revision':0};store=Mock(connect=object());store.db=MagicMock()
        def execute(sql,args=()):
            nonlocal persisted
            if sql.startswith('UPDATE crm_runtime_state'):persisted=json.loads(args[0])
            cursor=Mock();cursor.fetchone.return_value={'value':persisted};return cursor
        store.db.return_value.__enter__.return_value.execute.side_effect=execute
        save_builtin(store,ADMIN,row,'My purchased gallery',html,'Post Purchase')
        store.state.return_value=persisted;invalidate()
        reopened=reopen(store,{**row,'revision':1,'version':2})
        self.assertEqual(reopened,html);self.assertIn('[[product.image]]',reopened)
        self.assertIn('My own heading',reopened);self.assertIn('color:#eeddcc',reopened)

    def test_order_lines_are_paginated_with_exact_variant_facts(self):
        shop,store=wire();first=order();first['lineItems']['pageInfo']={'hasNextPage':True,'endCursor':'next'}
        last=order();last['lineItems']['nodes']=[dict(id='gid://shopify/LineItem/2',title='Second artwork',quantity=1,product={'id':Q})]
        shop.query.side_effect=lambda q,v,*rest:{'order':last if v.get('after') else first}
        shop.products.return_value=[product(P),product(Q)]
        doc=document();ctx={'_customer':{'id':A},'_order':order(),'_lifecycle_orders':[order()]}
        facts=resolve(shop,store,doc,ctx,A,AT)['blocks'][marker(configurations(doc)[0])]
        self.assertEqual(len(facts),2);self.assertEqual(shop.query.call_args_list[-1].args[1]['after'],'next')


class PreviewTests(TestCase):
    def test_native_delivery_reuses_history_without_changing_eligibility(self):
        from crm_collector_resolver import with_history
        store,shop,_,_,_=preview_wire('win_back')
        before={'_customer':shop.customer.return_value};original=deepcopy(before)
        previous={**order(),'createdAt':AT.isoformat()}
        with patch('crm_lifecycle_runtime.verified_plan',return_value={'eligible':False,'reason':'not_yet_inactive','orders':[previous]}) as read:
            result=with_history(shop,store,document(),before,'win_back',AT)
        self.assertEqual(result['_order']['id'],O);self.assertEqual(before,original)
        self.assertEqual(result['_lifecycle_orders'],[previous]);read.assert_called_once()
        store.enqueue.assert_not_called()

    def test_manual_transport_uses_selected_artwork_only_to_authorised_address(self):
        from crm_campaign_store import CampaignStore
        from crm_automation_store import AutomationStore
        from tests.test_crm_customer_test import USER,ADDRESS
        from tests.crm_fixtures import TestRecipientShop
        import uuid
        store,shop,row,candidate,operational=preview_wire();doc=document()
        state={};cfg=deepcopy(CFG)
        saved={'id':str(uuid.uuid4()),'version':1,'archived_at':None,'document':doc}
        store.step_id=str(uuid.uuid4());store.draft_identity=saved['id'];store.draft.return_value=saved
        store.flow.return_value=row;store.render_settings.return_value=cfg;store.q.side_effect=None;store.q.return_value=None
        store.db=MagicMock();conn=store.db.return_value.__enter__.return_value
        conn.execute.return_value.fetchone.return_value={'id':'fixture-receipt','n':0}
        store.test_document=lambda d,op,**kw:AutomationStore.test_document(store,d,op,**kw)
        internal=TestRecipientShop().customers(query='email:'+json.dumps(ADDRESS),fresh=True)['nodes'][0]
        with patch('crm_lifecycle_shopify.order_facts',return_value=operational),patch('crm_flow_preview.now',return_value=AT):
            # Use the already verified synthetic context; SQL remains mock-only.
            data={'key':O,'label':'Fixture Ada','_customer':shop.customer.return_value,'_order':shop.orders.return_value['nodes'][0],'_lifecycle_orders':shop.orders.return_value['nodes']}
            pin={'selected':data,'options':[candidate]}
            with patch('streamlit.session_state',state),patch('crm_flow_preview.context',return_value=pin),patch('crm_flow_preview.verify',return_value=data),patch('crm_personalisation_data.allocation',return_value=None),patch('crm_test_recipient.test_recipient_customer',return_value=internal),patch('crm_campaign_store.preflight',return_value={'test_ready':True}),patch('crm_resend_marketing.get_resend_marketing_config_status',return_value={'configured':True,'sender':'internal@example.test'}),patch('crm_resend_marketing._send_admin_email',return_value={'message_id':'fixture-send','accepted_at':AT.isoformat(),'audit_saved':True}) as send:
                CampaignStore.test_campaign(store,USER,saved['id'],1,recipient=ADDRESS,confirmed=True,operation_id=str(uuid.uuid4()),env={},shop=shop)
        args=send.call_args.kwargs
        self.assertEqual(args['recipient'],ADDRESS);self.assertNotEqual(args['recipient'],data['_customer']['email'])
        self.assertIn('Fixture Ada',args['message']['subject']);self.assertIn(IMAGE,args['message']['html'])
        store.enqueue.assert_not_called()

    def test_all_noncheckout_triggers_reuse_real_eligibility(self):
        for kind in ('welcome','post_purchase','fulfilled','win_back'):
            with self.subTest(kind=kind):
                store,shop,row,candidate,operational=preview_wire(kind,age=100 if kind=='win_back' else 1)
                with patch('crm_lifecycle_shopify.order_facts',return_value=operational),patch('crm_flow_preview.now',return_value=AT):
                    result=verify(store,shop,row,candidate)
                self.assertEqual(result['_customer']['firstName'],'Fixture Ada')
                self.assertEqual(result['_order'].get('id'),None if kind=='welcome' else O)
                store.db.assert_not_called();store.enqueue.assert_not_called()

    def test_recent_winback_unsubscribed_suppressed_and_rules_rejected(self):
        store,shop,row,candidate,operational=preview_wire('win_back',age=1)
        with patch('crm_lifecycle_shopify.order_facts',return_value=operational),patch('crm_flow_preview.now',return_value=AT):
            with self.assertRaisesRegex(ValueError,'inactive'):verify(store,shop,row,candidate)
            store.suppressed.return_value=True
            with self.assertRaisesRegex(ValueError,'eligible'):verify(store,shop,row,candidate)

    def test_preview_and_fresh_test_same_personalised_production_render(self):
        store,shop,row,candidate,operational=preview_wire();doc=document();state={}
        with patch('crm_lifecycle_shopify.order_facts',return_value=operational),patch('crm_flow_preview.now',return_value=AT):
            data=verify(store,shop,row,candidate);pin={'selected':data,'options':[candidate]}
            with patch('crm_flow_preview.context',return_value=pin),patch('crm_personalisation_data.allocation',return_value=None):
                preview=hydrate(state,store,doc)[0];tested=hydrate(state,store,doc,fresh=True)[0]
                self.assertEqual(preview,tested)
                url='https://www.sportscaveshop.com/account/unsubscribe?token=fixture'
                self.assertEqual(render_campaign(preview,CFG,production=True,unsubscribe_url=url),render_campaign(tested,CFG,production=True,unsubscribe_url=url))
                doc['middle_sections'][0]['html']=doc['middle_sections'][0]['html'].replace('Your artwork, chosen by you','Edited heading')
                commit_middle(doc,doc['middle_sections'])
                edited=hydrate(state,store,doc)[0]
                self.assertIn('Edited heading',edited['custom_html']);self.assertIn('Fixture Ada',edited['content']['subject'])
                self.assertIn(IMAGE,edited['custom_html'])

    def test_empty_context_refuses_preview_and_test_without_fake_data(self):
        store,_,_,_,_=preview_wire()
        with patch('crm_flow_preview.context',return_value={'selected':None,'error':''}):
            for fresh in (False,True):
                with self.assertRaises(NoPreviewCustomer):hydrate({},store,document(),fresh=fresh)

    def test_pin_does_not_read_again_during_edits_or_devices(self):
        store,_,_,candidate,_=preview_wire();state={};data={'key':O,'label':'Fixture Ada'}
        def submit(fn):
            f=Future();f.set_result(fn());return f
        with patch('crm_flow_preview.examples',return_value={'selected':data,'options':[candidate],'error':''}) as read,patch('crm_campaign_home_cache.POOL.submit',side_effect=submit):
            for _ in range(5):self.assertEqual(context(state,store)['selected'],data)
            self.assertEqual(read.call_count,1)
            context(state,store,refresh=True);self.assertEqual(read.call_count,2)

    def test_library_two_defaults_and_legacy_edits_preserved(self):
        from crm_template_library import rows,group_for
        from crm_template_cache import invalidate
        store=Mock(connect=object(),email_mode='automation',preview_trigger='post_purchase');store.html_library.return_value=[]
        legacy='builtin-collector-v1-collected-artwork'
        store.q.return_value=[dict(key='email_library_builtin_v1:'+legacy,name='My old edited artwork',library_group='Post Purchase',revision=2)]
        invalidate();available=rows(store)
        self.assertEqual([r['name'] for r in available if group_for(r)=='Post Purchase'],list(DESIGN_NAMES))
        saved=next(r for r in available if r['id']==legacy)
        self.assertEqual(saved['name'],'My old edited artwork');self.assertEqual(group_for(saved),'Other Templates')
        store.q.assert_called_once();store.db.assert_not_called()


DESIGN_NAMES=('Products Purchased','Collections of Products Purchased')
