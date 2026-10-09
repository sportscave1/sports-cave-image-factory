"""Insertable copies and safe dynamic links; never contact Shopify or send email."""
from copy import deepcopy
import os
import unittest
from unittest.mock import Mock,patch
from crm_wall_preview_template import IDENTITY,NAME,TOKEN,source,product_link,present
from crm_campaign_library import insert_saved_template,library_rows
from crm_middle_sections import apply_event,render_middle
from crm_abandoned_checkout import context,hydrate,publication_document
from crm_checkout_styles import MARKER
from crm_checkout_preview import document as preview_document,needs_checkout,sample
from crm_campaign_content import render_campaign
from tests.test_crm_abandoned_checkout import checkout
from tests.test_crm_simple_editor import document
from tests.test_crm_send_flow import CFG


def checkout_data():
    raw=checkout()
    raw['lineItems']['nodes'][0]['variant']={'id':'gid://shopify/ProductVariant/123',
        'product':{'id':'gid://shopify/Product/456','status':'ACTIVE',
                   'onlineStoreUrl':'https://www.sportscaveshop.com/products/collector?key=private#private'}}
    return context(raw,edition_reader=lambda **kwargs:[])


class WallSectionTests(unittest.TestCase):
    def setUp(self):
        self.store=Mock(connect=object(),email_mode='automation')
        self.store.html_library.return_value=[]

    def combined(self):
        doc=document();doc['middle_sections']=[dict(id='checkout',type='html',html_number=1,name='Checkout',visible=True,html='<p>Keep original</p>'+MARKER)]
        doc['custom_html']=doc['middle_sections'][0]['html']
        before=deepcopy(doc)
        insert_saved_template(self.store,doc,IDENTITY,1)
        self.assertEqual(doc['middle_sections'][:-1],before['middle_sections'])
        for key in ('content','product','html_sections'):
            self.assertEqual(doc.get(key),before.get(key))
        return doc

    def test_library_inserts_independent_copy_and_preserves_checkout(self):
        self.assertEqual(library_rows(self.store)[-1]['name'],NAME)
        doc=self.combined();first=doc['middle_sections'][-1]
        self.assertEqual(first['name'],NAME);self.assertEqual(first['html'],source())
        insert_saved_template(self.store,doc,IDENTITY,1)
        self.assertNotEqual(first['id'],doc['middle_sections'][-1]['id'])
        doc['middle_sections'][-1]['html']='Custom copy'
        self.assertEqual(first['html'],source());self.store.get.assert_not_called()
        self.assertEqual(sum(s.get('html','').count(MARKER) for s in doc['middle_sections']),1)

    def test_manual_reorder_rename_edit_hide_and_remove_preserve_identity(self):
        doc=self.combined();saved=deepcopy(doc['middle_sections'][0]);sid=doc['middle_sections'][1]['id']
        def event(kind,**kwargs):apply_event(doc,dict(type=kind,base=[s['id'] for s in doc['middle_sections']],id=sid,**kwargs))
        event('order',ids=[sid,'checkout']);event('rename',name='Wall Preview CTA')
        event('html',html=source().replace('find the right place','choose a spot'))
        event('visible',visible=False);event('visible',visible=True)
        self.assertEqual(doc['middle_sections'][1],saved)
        self.assertEqual(doc['middle_sections'][0]['id'],sid)
        event('remove',confirmed=True);self.assertEqual(doc['middle_sections'],[saved])

    def test_context_and_preview_production_render_resolve_same_public_variant(self):
        doc=self.combined();before=deepcopy(doc);data=checkout_data()
        self.assertTrue(needs_checkout(doc));self.assertTrue(present(doc))
        url=product_link(data)
        self.assertEqual(url,'https://www.sportscaveshop.com/products/collector?variant=123&sc_wall_preview=1')
        for rendered_doc in (hydrate(doc,data),preview_document(doc,data)[0]):
            rendered=render_campaign(rendered_doc,CFG)
            self.assertIn('variant=123&amp;sc_wall_preview=1',rendered['html'])
            self.assertIn('SEE IT ON YOUR WALL',rendered['text'])
            self.assertNotIn(TOKEN,rendered['html']);self.assertNotIn('key=private',rendered['html'])
        self.assertEqual(doc,before)

    def test_missing_url_unsafe_host_and_non_product_paths_remove_cta(self):
        doc=self.combined()
        for url in ('','http://www.sportscaveshop.com/products/test','https://evil.test/products/test',
                    'https://www.sportscaveshop.com/checkouts/secret','https://www.sportscaveshop.com/products/a%2fsecret'):
            data=checkout_data();data['items'][0]['product_url']=url
            rendered=render_campaign(hydrate(doc,data),CFG)['html']
            self.assertNotIn(TOKEN,rendered);self.assertNotIn('>SEE IT ON YOUR WALL<',rendered)
            self.assertIn('See It On Your Wall',rendered)
        no_variant=checkout_data();no_variant['items'][0]['variant_id']=None
        self.assertEqual(product_link(no_variant),'https://www.sportscaveshop.com/products/collector?sc_wall_preview=1')
        no_variant['items'].append(checkout_data()['items'][0]);no_variant['items'][0]['product_url']=''
        self.assertEqual(product_link(no_variant),'')

    def test_standalone_section_preview_and_publication_are_safe(self):
        doc=document();insert_saved_template(self.store,doc,IDENTITY,1)
        original=deepcopy(doc)
        preview=preview_document(doc,sample(doc))[0]
        self.assertNotIn(TOKEN,render_campaign(preview,CFG)['html'])
        with self.assertRaisesRegex(ValueError,'Resolve the wall preview'):render_middle(doc)
        with self.assertRaisesRegex(ValueError,'Checkout abandoned'):publication_document(doc,'welcome')
        with self.assertRaisesRegex(ValueError,'at least one'):publication_document(doc,'abandoned')
        self.assertEqual(original,doc)

    def test_dispatch_uses_only_bound_checkout_not_editor_preview(self):
        from crm_automation_runtime import render
        doc=self.combined();raw=checkout(customer=99)
        raw['lineItems']['nodes'][0]['variant']={'id':'gid://shopify/ProductVariant/987',
            'product':{'status':'ACTIVE','onlineStoreUrl':'https://www.sportscaveshop.com/products/recipient-artwork'}}
        import uuid
        row={'id':str(uuid.uuid4()),'shopify_customer_id':'gid://shopify/Customer/99'}
        content={'document':doc,'render_settings':CFG,'trigger':'abandoned'}
        with patch('crm_campaign_send.production_checks',return_value={'safe':True}):
            rendered=render(content,row,'https://example.test/unsubscribe',{'_checkout':raw,'_checkout_id':raw['id']})
            self.assertIn('/products/recipient-artwork?variant=987',rendered['html'])
            self.assertNotIn(TOKEN,rendered['html'])
            with self.assertRaisesRegex(ValueError,'context mismatch'):
                render(content,row,'https://example.test/unsubscribe',{'_checkout':checkout(customer=1),'_checkout_id':raw['id']})


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable SQL required')
class PersistenceTests(unittest.TestCase):
    def test_draft_reopen_and_duplicate_preserve_section_without_publication(self):
        from crm_automation_store import AutomationStore
        from tests.crm_db_fixture import connect
        from tests.test_crm import ADMIN
        store=AutomationStore(connect);row=store.create(ADMIN,'abandoned','Wall section fixture')
        flow=deepcopy(row['config']['draft']);doc=flow['emails'][0]['document']
        doc.update(content_mode='HTML',custom_html='')
        insert_saved_template(store,doc,IDENTITY,1)
        store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision'])
        reopened=store.flow(row['id'])
        self.assertEqual(reopened['config']['draft']['emails'][0]['document'],doc)
        self.assertEqual(reopened['config']['published_version'],0)
        from crm_flow_builder import edit_sequence
        duplicate=edit_sequence(reopened['config']['draft'],flow['emails'][0]['step_id'],'duplicate')
        self.assertEqual(duplicate['emails'][1]['document'],doc)
        self.assertEqual(store.q('SELECT count(*) AS n FROM crm_automation_enrollments WHERE automation_id=%s',(row['id'],),True)['n'],0)


if __name__=='__main__':unittest.main()
