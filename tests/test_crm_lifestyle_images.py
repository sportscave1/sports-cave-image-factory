"""Image-only inserts use confirmed product gallery positions; no external sends."""
from copy import deepcopy
from unittest.mock import Mock, patch
import unittest
import os
from crm_lifestyle_images import TOKENS, source, resolve, gallery, present
from crm_campaign_library import insert_saved_template, library_rows
from crm_checkout_preview import document as preview_document, sample
from crm_abandoned_checkout import hydrate, publication_document
from crm_campaign_content import render_campaign
from tests.test_crm_wall_preview_template import checkout_data
from tests.test_crm_simple_editor import document
from tests.test_crm_send_flow import CFG
from crm_checkout_styles import MARKER


class LifestyleTests(unittest.TestCase):
    def setUp(self):
        self.store=Mock(connect=object(),email_mode='automation')
        self.store.html_library.return_value=[]
        self.shop=Mock()
        self.images=[{'url':f'https://cdn.shopify.com/s/files/gallery-{n}.jpg'} for n in range(1,5)]
        self.shop.campaign_images.return_value={'nodes':self.images,'pageInfo':{'hasNextPage':False}}

    def combined(self):
        doc=document()
        doc['middle_sections']=[dict(id='original',type='html',html_number=1,name='Original',visible=True,html='<p>Original design</p>'+MARKER)]
        for n in (1,2,3):insert_saved_template(self.store,doc,f'builtin-lifestyle-image-{n}',1)
        return doc

    def test_three_independent_image_only_inserts(self):
        rows=library_rows(self.store)
        self.assertTrue(all(any(r['name']==f'Lifestyle Image {n}' for r in rows) for n in (1,2,3)))
        doc=self.combined()
        self.assertEqual(len(doc['middle_sections']),4)
        self.assertEqual(len({s['id'] for s in doc['middle_sections']}),4)
        for position,section in zip((2,3,4),doc['middle_sections'][1:]):
            self.assertEqual(section['html'],source(position))
            self.assertEqual(section['html'].count('<img'),1)
            self.assertNotIn('<a ',section['html'])
            self.assertIn('max-width:520px',section['html'])
        self.assertEqual(doc['middle_sections'][0]['html'].count(MARKER),1)

    def test_preview_test_and_hydration_match_without_mutating_draft(self):
        doc=self.combined();before=deepcopy(doc);data=checkout_data()
        for hydrated in (hydrate(doc,data,shop=self.shop),preview_document(doc,data,shop=self.shop)[0],
                         preview_document(doc,data,test=True,shop=self.shop)[0]):
            html=render_campaign(hydrated,CFG)['html']
            for n in (2,3,4):self.assertIn(f'gallery-{n}.jpg',html)
            self.assertNotIn('gallery-1.jpg',html)
            self.assertNotIn('SC_LIFESTYLE_IMAGE_',html)
        self.shop.campaign_images.assert_called_with('gid://shopify/Product/456',after=None)
        self.assertEqual(doc,before)

    def test_missing_and_unsafe_images_do_not_shift_positions(self):
        self.shop.campaign_images.return_value['nodes']=[self.images[0],{'url':'http://unsafe.test/a.jpg'},self.images[2]]
        result=resolve(self.combined(),checkout_data(),shop=self.shop)
        self.assertNotIn('<img',result['middle_sections'][1]['html'])
        self.assertIn('gallery-3.jpg',result['middle_sections'][2]['html'])
        self.assertNotIn('<img',result['middle_sections'][3]['html'])

    def test_no_context_or_invalid_leading_product_never_uses_another_product(self):
        doc=self.combined()
        for data in (None,sample(doc),{'items':[{'product_id':'invalid'},{'product_id':'gid://shopify/Product/456'}]}):
            result=resolve(doc,data,shop=self.shop)
            self.assertFalse(present(result))
            for section in result['middle_sections'][1:]:self.assertNotIn('<img',section['html'])
        self.shop.campaign_images.assert_not_called()

    def test_pagination_and_failed_optional_lookup(self):
        self.shop.campaign_images.side_effect=[{'nodes':self.images[:1],'pageInfo':{'hasNextPage':True,'endCursor':'page2'}},
                                               {'nodes':self.images[1:],'pageInfo':{'hasNextPage':False}}]
        self.assertEqual(gallery(checkout_data(),self.shop),self.images)
        self.shop.campaign_images.assert_called_with('gid://shopify/Product/456',after='page2')
        self.shop.campaign_images.side_effect=RuntimeError('unavailable')
        result=resolve(self.combined(),checkout_data(),shop=self.shop)
        self.assertFalse(present(result))

    def test_shopify_adapter_excludes_videos_preserving_gallery_order(self):
        from crm_shopify import Shopify
        shop=object.__new__(Shopify)
        shop.query=Mock(return_value={'product':{'media':{'nodes':[{'image':self.images[0]}, {}, {'image':self.images[1]}], 'pageInfo':{'hasNextPage':False}}}})
        self.assertEqual([i['url'] for i in shop.campaign_images('gid://shopify/Product/456')['nodes']],
                         [i['url'] for i in self.images[:2]])

    def test_manual_html_tokens_resolve_and_missing_tokens_are_removed(self):
        doc=document();doc['custom_html']='<p>Keep design</p>'+source(2)
        result=resolve(doc,checkout_data(),shop=self.shop)
        self.assertIn('gallery-2.jpg',render_campaign(result,CFG)['html'])
        self.assertIn(TOKENS[2],doc['custom_html'])
        self.assertNotIn(TOKENS[2],render_campaign(doc,CFG)['html'])
        doc['custom_html']+='<a href="SC_CHECKOUT_RECOVERY_URL">Return to checkout</a>'
        self.assertNotIn(TOKENS[2],publication_document(doc,'abandoned')['custom_html'])

    def test_reordering_editing_and_removing_preserve_original(self):
        from crm_middle_sections import apply_event
        doc=self.combined();original=deepcopy(doc['middle_sections'][0]);sid=doc['middle_sections'][-1]['id']
        def event(kind,**kwargs):apply_event(doc,dict(type=kind,base=[s['id'] for s in doc['middle_sections']],id=sid,**kwargs))
        event('order',ids=[sid]+[s['id'] for s in doc['middle_sections'][:-1]])
        event('html',html=source(4).replace('520','500'))
        event('rename',name='Custom lifestyle');event('visible',visible=False);event('visible',visible=True)
        self.assertEqual(doc['middle_sections'][1],original)
        event('remove',confirmed=True)
        self.assertEqual(doc['middle_sections'][0],original)

    def test_dispatch_uses_bound_recipient_context(self):
        from crm_automation_runtime import render
        from tests.test_crm_abandoned_checkout import checkout
        import uuid
        raw=checkout(customer=99)
        raw['lineItems']['nodes'][0]['variant']={'id':'gid://shopify/ProductVariant/123','product':{'id':'gid://shopify/Product/456'}}
        content={'document':self.combined(),'render_settings':CFG,'trigger':'abandoned'}
        row={'id':str(uuid.uuid4()),'shopify_customer_id':'gid://shopify/Customer/99'}
        with patch('crm_campaign_send.production_checks',return_value={'safe':True}), patch('crm_shopify.Shopify',return_value=self.shop), patch('supabase_backend.list_edition_products_read_only',return_value=[]):
            result=render(content,row,'https://example.test/unsubscribe',{'_checkout':raw,'_checkout_id':raw['id']})
            self.assertIn('gallery-2.jpg',result['html'])
            self.assertNotIn('SC_LIFESTYLE_IMAGE_',result['html'])
            with self.assertRaisesRegex(ValueError,'context mismatch'):
                render(content,row,'https://example.test/unsubscribe',{'_checkout':checkout(customer=1),'_checkout_id':raw['id']})


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable SQL required')
class PersistenceTests(unittest.TestCase):
    def test_inserted_images_survive_save_reopen_and_duplicate_without_publishing(self):
        from crm_automation_store import AutomationStore
        from tests.crm_db_fixture import connect
        from tests.test_crm import ADMIN
        from crm_flow_builder import edit_sequence
        store=AutomationStore(connect);row=store.create(ADMIN,'abandoned','Lifestyle image fixture')
        flow=deepcopy(row['config']['draft']);doc=flow['emails'][0]['document']
        doc.update(content_mode='HTML',custom_html='<p>Original design</p>')
        for n in (1,2,3):insert_saved_template(store,doc,f'builtin-lifestyle-image-{n}',1)
        store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision'])
        reopened=store.flow(row['id'])
        self.assertEqual(reopened['config']['draft']['emails'][0]['document'],doc)
        self.assertEqual(reopened['config']['published_version'],0)
        duplicate=edit_sequence(reopened['config']['draft'],flow['emails'][0]['step_id'],'duplicate')
        self.assertEqual(duplicate['emails'][1]['document'],doc)
        self.assertEqual(store.q('SELECT count(*) AS n FROM crm_automation_enrollments WHERE automation_id=%s',(row['id'],),True)['n'],0)


if __name__=='__main__':unittest.main()
