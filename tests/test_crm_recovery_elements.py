"""Universal recovery actions and composable checkout designs; no live I/O."""
from copy import deepcopy
import json
import os
import unittest
import uuid
from unittest.mock import Mock, patch
from crm_checkout_elements import element, starter, validate, render as element_html
from crm_recovery_links import TOKEN, inspect, verify, destination
from crm_abandoned_checkout import context, hydrate, publication_document, edition_label
from crm_middle_sections import commit_middle, apply_event
from crm_campaign_content import render_campaign, validate_document
from tests.test_crm_simple_editor import document
from tests.test_crm_abandoned_checkout import checkout, native_document
from tests.test_crm_send_flow import CFG


def design(*sections):
    doc=document();doc['content_mode']='HTML';commit_middle(doc,list(sections));return doc


def html_section(source):
    return dict(id='custom',type='html',html_number=1,visible=True,html=source)


class RecoveryElementsTests(unittest.TestCase):
    def setUp(self):
        self.network=patch('requests.sessions.Session.request',side_effect=AssertionError('No external requests'))
        self.network.start();self.addCleanup(self.network.stop)
        self.raw=checkout(items=2)
        self.raw['abandonedCheckoutUrl']+='&opaque=a%2Fb+%20&blank=#resume%2Fhere'
        self.data=context(self.raw,edition_reader=Mock(return_value=[]))
        for i,item in enumerate(self.data['items']):
            item.update(title='Product '+str(i+1),product_id='gid://shopify/Product/'+str(i+1),
                        product_url='https://sportscaveshop.com/products/item-'+str(i+1),
                        edition={'limit':100 if i==0 else 150,'next':78 if i==0 else 4,'remaining':22 if i==0 else 146})

    def message(self, doc, **kw): return render_campaign(hydrate(doc,self.data,**kw),CFG)

    def test_many_buttons_and_images_reuse_exact_destination_after_tracking(self):
        source=''.join(f'<a href="{TOKEN}">Claim {n}</a><a href="{TOKEN}"><img src="https://cdn.shopify.com/a.png" alt="Artwork"></a>' for n in range(120))
        doc=design(html_section(source));before=deepcopy(doc);msg=self.message(doc)
        self.assertEqual([u for u in inspect(msg['html']).urls if '/checkouts/' in u],[self.data['recovery_url']]*240)
        verify(msg,self.data['recovery_url'],240);self.assertEqual(doc,before)

    def test_native_and_custom_share_exact_discounted_destination(self):
        from crm_recovery_discount import recovery_url
        doc=native_document();doc['middle_sections'][-1]['html']+=f'<a href="{TOKEN}">Own The Moment</a>'
        data=deepcopy(self.data);original=data['recovery_url']
        data['recovery_url']=destination(data,{'original_url':original,'url':recovery_url(original,'MYCAVE5')})
        msg=render_campaign(hydrate(doc,data),CFG);verify(msg,data['recovery_url'],4)
        self.assertIn('&opaque=a%2Fb+%20&blank=&discount=MYCAVE5#resume%2Fhere',data['recovery_url'])
        with self.assertRaises(ValueError):destination(self.data,{'original_url':'wrong','url':data['recovery_url']})

    def test_bad_missing_or_nested_destinations_fail_closed(self):
        for url in ('','http://example.test/checkouts/1','https://localhost/checkouts/1','https://example.test/cart','javascript:alert(1)'):
            with self.subTest(url=url),self.assertRaises(ValueError):hydrate(design(element()),{**self.data,'recovery_url':url})
        for source in (f'<a href="{TOKEN}"><a href="{TOKEN}">Nested</a></a>',f'<a href="https://example.test/?to={TOKEN}">Wrong</a>',f'<p>{TOKEN}</p>'):
            with self.subTest(source=source),self.assertRaises(ValueError):self.message(design(html_section(source)))

    def test_rendered_destination_corruption_is_detected(self):
        msg=self.message(design(element()))
        for wrong in (msg['html'].replace('opaque=a%2Fb+%20','opaque=changed'),msg['html'].replace('/checkouts/1/','/checkouts/2/')):
            with self.assertRaises(ValueError):verify({**msg,'html':wrong},self.data['recovery_url'],1)
        with self.assertRaises(ValueError):verify(msg,self.data['recovery_url'],2)

    def test_disabled_test_and_sample_keep_copy_and_images(self):
        doc=design(element(),element('product_image'),html_section(f'<a href="{TOKEN}">Claim Your Edition</a>'))
        for data,test in ((self.data,True),({**self.data,'preview_only':True},False)):
            msg=render_campaign(hydrate(doc,data,test=test),CFG)
            self.assertNotIn('/checkouts/',msg['html']);self.assertNotIn('/checkouts/',msg['text'])
            self.assertIn('Claim Your Edition',msg['html']);self.assertIn('<img',msg['html']);self.assertNotIn(TOKEN,msg['html'])

    def test_pasted_customer_links_cannot_bypass_recovery_action(self):
        with self.assertRaisesRegex(ValueError,'Choose Recover Checkout'):
            validate(element(action='custom',url=self.data['recovery_url'])['settings'])
        doc=design(html_section('<a href="'+self.data['recovery_url']+'">Pasted checkout</a>'))
        with self.assertRaisesRegex(ValueError,'pasted customer'):publication_document(doc,'abandoned')
        self.assertNotIn('/checkouts/',self.message(doc,test=True)['html'])

    def test_publication_minimal_no_native_or_edition_and_no_empty_action(self):
        doc=design(element('headline',text='One last reminder'),element(text='Own The Moment'))
        original=deepcopy(doc);publication_document(doc,'abandoned');self.assertEqual(doc,original)
        for sections in ([element('headline',text='No recovery')],[element(text='')],[{**element(),'visible':False}],[html_section(f'<a href="{TOKEN}"></a>')],[html_section(f'<div style="display:none"><a href="{TOKEN}">Hidden action</a></div>')]):
            with self.assertRaisesRegex(ValueError,'at least one'):publication_document(design(*sections),'abandoned')
        with self.assertRaises(ValueError):publication_document(doc,'welcome')

    def test_static_visual_elements_work_without_checkout_on_other_automations(self):
        doc=design(element('headline',text='Welcome'),element('text',text='Your collector story'),element(action='custom',url='https://example.test/collections'))
        publication_document(doc,'welcome')
        message=render_campaign(doc,CFG)
        self.assertIn('Your collector story',message['html']);self.assertIn('https://example.test/collections',message['html'])

    def test_recovery_only_render_skips_product_and_edition_reads(self):
        from crm_abandoned_checkout import render_context,needs_items
        doc=design(element());raw=deepcopy(self.raw);raw.pop('lineItems')
        with patch('supabase_backend.list_edition_products_read_only') as reader:
            self.assertFalse(needs_items(doc));data=render_context(raw,doc);reader.assert_not_called()
        self.assertEqual(data['recovery_url'],raw['abandonedCheckoutUrl'])

    def test_hide_remove_restore_and_position_edition_without_empty_space(self):
        edition=element('edition',product=1);image=element('product_image',product=1);headline=element('headline',text='Collector story')
        doc=design(headline,edition,image,element())
        def event(kind,**extra):apply_event(doc,dict(type=kind,base=[s['id'] for s in doc['middle_sections']],**extra))
        self.assertLess(self.message(doc)['html'].index('NEXT AVAILABLE'),self.message(doc)['html'].index('fixture.png'))
        event('visible',id=edition['id'],visible=False)
        hidden=self.message(doc)['html'];self.assertNotIn('NEXT AVAILABLE',hidden);self.assertNotIn('#078',hidden)
        event('visible',id=edition['id'],visible=True)
        event('order',ids=[image['id'],headline['id'],edition['id'],doc['middle_sections'][-1]['id']])
        msg=self.message(doc)['html'];self.assertLess(msg.index('fixture.png'),msg.index('Collector story'));self.assertLess(msg.index('Collector story'),msg.index('NEXT AVAILABLE'))
        event('remove',id=edition['id'],confirmed=True);self.assertNotIn('#078',self.message(doc)['html'])
        event('restore_section',section=edition,position=0);self.assertIn('#078',self.message(doc)['html'])

    def test_styling_size_resize_hidden_product_fields_and_multi_product_association(self):
        doc=design(element('edition',edition_style='collector',align='left',color='#123456',background='#eeeeee',size=24,border=2,padding=3,spacing=4),
                   element('product_image',width=240),element('details'),element())
        msg=self.message(doc)['html']
        for text in ('Product 1 — NEXT AVAILABLE EDITION · #078/100','Product 2 — NEXT AVAILABLE EDITION · #004/150','color:#123456','font-size:24px','border:2px','max-width:240px','height:auto','A$199.50'):self.assertIn(text,msg)
        doc['middle_sections'][1]['visible']=False;doc['middle_sections'][2]['visible']=False
        msg=self.message(doc)['html'];self.assertNotIn('fixture.png',msg);self.assertNotIn('A$199.50',msg)

    def test_lifestyle_gallery_reused_once_per_product_and_hidden_no_io(self):
        shop=Mock();shop.campaign_images.side_effect=lambda identity,**kw:{'nodes':[{'url':f'https://cdn.shopify.com/{identity.rsplit("/",1)[-1]}-{n}.png'} for n in range(1,5)]}
        doc=design(element('lifestyle',position=3),element('lifestyle',position=4),element())
        msg=self.message(doc,shop=shop);self.assertEqual(shop.campaign_images.call_count,2)
        for image in ('1-3.png','2-3.png','1-4.png','2-4.png'):self.assertIn(image,msg['html'])
        verify(msg,self.data['recovery_url'],5)
        shop.reset_mock();doc['middle_sections'][0]['visible']=False;doc['middle_sections'][1]['visible']=False
        self.message(doc,shop=shop);shop.campaign_images.assert_not_called()

    def test_link_actions_and_product_bound_wall_preview(self):
        for action,part in (('wall','sc_wall_preview=1'),('product','/products/item-2'),('custom','https://example.test/info')):
            cfg=element(action=action,product=2,url='https://example.test/info')['settings']
            html=element_html(cfg,self.data);self.assertIn(part,html);self.assertNotIn('item-1',html)
            if action=='product':self.assertNotIn('sc_wall_preview',html)
        self.assertNotIn('<a',element_html(element(action='none')['settings'],self.data))

    def test_duplicate_reorder_json_roundtrip_and_no_open_mutation(self):
        doc=design(*starter());before=json.dumps(doc,sort_keys=True);validate_document(doc);publication_document(doc,'abandoned');self.message(doc)
        self.assertEqual(json.dumps(doc,sort_keys=True),before)
        button=next(s for s in doc['middle_sections'] if s['settings']['kind']=='button')
        apply_event(doc,dict(type='duplicate',id=button['id'],base=[s['id'] for s in doc['middle_sections']]))
        frozen=json.loads(json.dumps(doc));self.assertEqual(self.message(doc),self.message(frozen))
        ids=[s['id'] for s in doc['middle_sections']];apply_event(doc,dict(type='order',base=ids,ids=list(reversed(ids))))
        self.assertEqual(doc['middle_sections'][0]['id'],ids[-1])

    def test_edition_missing_sold_out_different_limits_and_never_reserved(self):
        self.assertEqual(edition_label(None),'');self.assertEqual(edition_label({'next':1}),'')
        self.assertEqual(edition_label({'limit':150,'next':151,'remaining':0}),'LIMITED TO 150 WORLDWIDE')
        self.assertNotIn('WILL BE',edition_label({'limit':25,'next':4,'remaining':21}))
        data=deepcopy(self.data);data['items'][0]['edition']=None
        self.assertEqual(element_html(element('edition',product=1)['settings'],data),'')

    def test_edition_reader_exact_products_no_write_path(self):
        raw=checkout(items=2)
        for i,line in enumerate(raw['lineItems']['nodes']):line['product']={'id':'gid://shopify/Product/'+str(100+i)}
        reader=Mock(return_value=[]);data=context(raw,edition_reader=reader)
        reader.assert_called_once_with(product_ids=['gid://shopify/Product/100','gid://shopify/Product/101'],handles=[],limit=100)
        before=deepcopy(data);hydrate(design(*starter()),data);self.assertEqual(data,before)

    def test_custom_master_no_required_styles_and_explicit_native_separation(self):
        from crm_checkout_template import validate as master_validate
        master_validate(f'<h1>Own The Moment</h1><a href="{TOKEN}">Return To Checkout</a>')
        from crm_checkout_section import editable
        doc=editable(native_document());frozen=deepcopy(doc)
        apply_event(doc,dict(type='separate_checkout',id=doc['middle_sections'][0]['id'],base=[s['id'] for s in doc['middle_sections']]))
        self.assertNotIn('SC_ABANDONED_CHECKOUT',str(doc));self.assertIn('SC_ABANDONED_CHECKOUT',str(frozen))
        self.assertEqual(sum(s.get('settings',{}).get('kind')=='edition' for s in doc['middle_sections']),1)
        self.assertIn('YOUR COLLECTION AWAITS',self.message(doc)['html'])
        publication_document(doc,'abandoned')

    def test_visual_values_cannot_override_shopify_price_or_inject_html(self):
        doc=design(element('price',text='Fake $1'),element('headline',text='<script>bad</script>'),element())
        msg=self.message(doc)['html'];self.assertIn('A$199.50',msg);self.assertNotIn('Fake',msg);self.assertNotIn('<script>',msg)
        for patch_values in ({'size':True},{'color':'url(secret)'},{'image_url':'http://unsafe.test/a.png'},{'url':'javascript:bad'}):
            with self.assertRaises(ValueError):validate(element(**patch_values)['settings'])

    def test_live_runtime_verifies_recipient_and_resolves_discount_once(self):
        from crm_automation_runtime import render
        raw=deepcopy(self.raw);row={'id':str(uuid.uuid4()),'shopify_customer_id':raw['customer']['id']}
        doc=design(element(),element('product_image'),html_section(f'<a href="{TOKEN}">Final CTA</a>'))
        content={'document':doc,'render_settings':CFG,'trigger':'abandoned'}
        ctx={'_checkout':raw,'_checkout_id':raw['id']}
        with patch('crm_campaign_send.production_checks',return_value={'safe':True}):
            msg=render(content,row,'https://example.test/unsubscribe',ctx);verify(msg,raw['abandonedCheckoutUrl'],4)
            with self.assertRaises(ValueError):render(content,row,'https://example.test/unsubscribe',{})
            with patch('crm_campaign_content.render_campaign',return_value={**msg,'html':msg['html'].replace('/checkouts/1/','/checkouts/9/')}):
                with self.assertRaisesRegex(ValueError,'verification failed'):render(content,row,'https://example.test/unsubscribe',ctx)


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class RecoveryPersistenceTests(unittest.TestCase):
    def setUp(self):
        from tests.test_crm_native_automations import NativeAutomationTests
        fixture=NativeAutomationTests();fixture.setUp();self.addCleanup(fixture.doCleanups);self.f=fixture
        self.cart=checkout(88001);self.cart['customer']=deepcopy(fixture.customer)
        fixture.shop.checkout.return_value=self.cart

    def published(self):
        from crm_automation_definition import email_step
        from tests.test_crm import ADMIN
        from tests.test_crm_send_flow import LIVE
        f=self.f;a=f.store.create(ADMIN,'abandoned','Composable fixture');f.created.append(str(a['id']))
        doc=design(element('headline',text='Your collection awaits'),element('product_image'),element(text='Own The Moment'))
        doc['copy_reviewed']=True
        flow=deepcopy(a['config']['draft']);flow['emails']=[email_step(doc,0),email_step(doc,3600)]
        saved=f.store.save_flow(ADMIN,a['id'],a['name'],flow,1)
        return f.store.publish(ADMIN,a['id'],saved['config']['revision'],env=LIVE)

    def test_frozen_versions_reopen_new_publication_and_provider_once(self):
        from crm_automation_runtime import enter,advance
        from crm_logic import now
        from datetime import timedelta
        from tests.test_crm import ADMIN
        from tests.test_crm_send_flow import LIVE
        f=self.f;a=self.published()
        journey=enter(f.engine,a,f.customer['id'],self.cart['id'],str(uuid.uuid4()),now()+timedelta(seconds=2))
        self.assertIsNotNone(journey);frozen=deepcopy(journey['steps'])
        before=deepcopy(f.store.flow(a['id'])['config'])
        from crm_checkout_section import editable
        doc=before['draft']['emails'][0]['document'];editable(doc);publication_document(doc,'abandoned')
        self.assertEqual(f.store.flow(a['id'])['config'],before)
        future=deepcopy(before['draft']);future['emails'][0]['document']['middle_sections'][1]['visible']=False
        saved=f.store.save_flow(ADMIN,a['id'],a['name'],future,before['revision'])
        f.store.publish(ADMIN,a['id'],saved['config']['revision'],env=LIVE)
        self.assertEqual(f.store.q('SELECT steps FROM crm_automation_enrollments WHERE id=%s',(journey['id'],),True)['steps'],frozen)
        advance(f.engine,f.due(journey));f.engine.send_one();f.engine.send_one();f.provider.send.assert_called_once()
        message=f.provider.send.call_args.args[1]
        verify(message,self.cart['abandonedCheckoutUrl'],2)
        self.assertIn('fixture.png',message['html']);self.assertIn('Own The Moment',message['html'])
        self.assertNotIn(TOKEN,message['html']);self.assertIn('Unsubscribe',message['html'])

    def test_removing_last_action_blocks_publication_without_changing_live_version(self):
        from tests.test_crm import ADMIN
        from tests.test_crm_send_flow import LIVE
        f=self.f;a=self.published();published=deepcopy(a['config']['published'])
        flow=deepcopy(a['config']['draft']);flow['emails'][0]['document']['middle_sections']=[element('headline',text='Only copy')]
        saved=f.store.save_flow(ADMIN,a['id'],a['name'],flow,a['config']['revision'])
        with self.assertRaisesRegex(ValueError,'at least one'):f.store.publish(ADMIN,a['id'],saved['config']['revision'],env=LIVE)
        self.assertEqual(f.store.flow(a['id'])['config']['published'],published);f.provider.send.assert_not_called()


if __name__=='__main__':unittest.main()
