import io
import json
import unittest
from copy import deepcopy
from unittest.mock import Mock, patch
from PIL import Image
import crm_frame_banner_assets as assets
import crm_frame_banner_template as banner
from crm_campaign_library import insert_saved_template, library_rows
from crm_campaign_content import render_campaign
from crm_middle_sections import apply_event
from crm_abandoned_checkout import hydrate, publication_document
from crm_checkout_styles import MARKER
from tests.test_crm_simple_editor import document
from tests.test_crm_send_flow import CFG

URL='https://cdn.shopify.com/s/files/1/0722/2332/6515/files/art.webp?v=123&format=png'
SOURCE='https://www.sportscaveshop.com/cdn/shop/files/art.webp?v=123&width=2000&height=2000&crop=center'


def item(frame='Black',size='XL'):
    return dict(title='Collector Wall Art',variant=frame+' / '+size,image=URL,
        product_id='gid://shopify/Product/456',variant_id='gid://shopify/ProductVariant/123',
        product_url='https://www.sportscaveshop.com/products/art?token=private#private')


def picture(w=1000,h=1000):
    output=io.BytesIO();Image.new('RGB',(w,h),(20,50,100)).save(output,format='PNG');return output.getvalue()


class BannerTests(unittest.TestCase):
    def setUp(self):
        assets.CACHE.invalidate()
        self.store=Mock(connect=object(),email_mode='automation');self.store.html_library.return_value=[]

    def doc(self):
        doc=document();insert_saved_template(self.store,doc,banner.IDENTITY,1);return doc

    def test_insert_both_modes_independent_reorder_save_reload(self):
        for mode in ('campaign','automation'):
            self.store.email_mode=mode
            self.assertIn(banner.IDENTITY,[r['id'] for r in library_rows(self.store)])
        doc=document();doc['middle_sections']=[dict(id='checkout',type='html',html_number=1,visible=True,html=MARKER)];doc['custom_html']=MARKER
        original=deepcopy(doc['middle_sections'][0]);insert_saved_template(self.store,doc,banner.IDENTITY,1)
        sid=doc['middle_sections'][-1]['id']
        apply_event(doc,dict(type='order',base=[s['id'] for s in doc['middle_sections']],ids=[sid,original['id']]))
        self.assertEqual(doc['middle_sections'][1],original)
        self.assertEqual(sum(s.get('html','').count(MARKER) for s in doc['middle_sections']),1)
        reopened=json.loads(json.dumps(doc));self.assertEqual(reopened,doc)
        insert_saved_template(self.store,reopened,banner.IDENTITY,1)
        self.assertNotEqual(reopened['middle_sections'][0]['id'],reopened['middle_sections'][-1]['id'])
        reopened['middle_sections'][-1]['html']='Edited independent copy'
        self.assertEqual(reopened['middle_sections'][0]['html'],banner.source())

    def test_all_frames_sizes_resolve_without_mutating_draft(self):
        doc=self.doc();original=deepcopy(doc)
        for frame in ('Black','Oak','White','Unframed'):
            for size in ('S','M','L','XL'):
                data={'items':[item(frame,size)]}
                with patch.object(assets,'prepare',return_value=URL):
                    resolved=hydrate(doc,data)
                html=render_campaign(resolved,CFG)['html']
                self.assertIn(frame+' / '+size,html);self.assertIn('variant=123',html)
                self.assertIn('sc_wall_preview=1',html);self.assertNotIn('private',html)
                self.assertNotIn(banner.PREFIX,html)
        self.assertEqual(doc,original)

    def test_first_eligible_and_no_image_fallback(self):
        doc=self.doc();gift={**item(),'title':'Gift card','variant':'$50'}
        with patch.object(assets,'prepare',return_value='') as prepare:
            html=render_campaign(banner.resolve(doc,{'items':[gift,item()]}),CFG)['html']
        prepare.assert_called_once_with(item());self.assertIn('PREVIEW IN MY CAVE',html)
        self.assertNotIn('Gift card',html);self.assertNotIn(URL,html)

    def test_campaign_generic_and_offline_publication(self):
        doc=self.doc();original=deepcopy(doc)
        with patch.object(assets,'fetch',side_effect=AssertionError('No network without checkout')):
            for resolved in (doc,publication_document(doc,'welcome')):
                html=render_campaign(resolved,CFG)['html']
                self.assertNotIn(banner.PREFIX,html);self.assertNotIn('PREVIEW IN MY CAVE',html)
                self.assertIn('SEE IT IN YOUR CAVE',html)
        self.assertEqual(doc,original)
        with self.assertRaisesRegex(ValueError,'at least one'):publication_document(doc,'abandoned')

    def test_verified_crop_and_cache_key_contains_no_customer_data(self):
        with patch.object(assets,'fetch',return_value=picture()) as fetch,patch.object(assets,'wall_source',return_value=SOURCE),patch.object(assets,'public_asset',return_value='https://assets.example.com/banner.jpg') as upload:
            self.assertEqual(assets.prepare(item()),'https://assets.example.com/banner.jpg')
            calls=fetch.call_count;assets.prepare(item());self.assertEqual(fetch.call_count,calls)
            self.assertRegex(upload.call_args.args[1],r'^email/frame-banner/[a-f0-9]{64}\.jpg$')
            for frame in ('Black','Oak','White','Unframed'):
                assets.prepare(item(frame))
            self.assertEqual(upload.call_count,4)

    def test_missing_storage_mismatch_unknown_frame_preserve_original(self):
        with patch.object(assets,'fetch',return_value=picture()),patch.object(assets,'wall_source',return_value=SOURCE),patch.object(assets,'public_asset',return_value=''):
            self.assertEqual(assets.prepare(item()),URL)
        assets.CACHE.invalidate()
        with patch.object(assets,'fetch',return_value=picture()),patch.object(assets,'wall_source',return_value=SOURCE.replace('art.webp','other.webp')),patch.object(assets,'crop_image') as crop:
            self.assertEqual(assets.prepare(item()),URL);crop.assert_not_called()
        with patch.object(assets,'fetch',return_value=picture(600,900)),patch.object(assets,'wall_source') as mapping:
            self.assertEqual(assets.prepare(item('Unknown')),URL);mapping.assert_not_called()

    def test_bad_images_and_private_hosts_never_reach_email(self):
        with patch.object(assets,'fetch',return_value=b'not-image'):
            self.assertEqual(assets.prepare(item()),'')
        for url in ('http://localhost/a.png','https://127.0.0.1/a.png',URL+'&token=private',URL.replace('0722','9999')):
            with patch.object(assets,'fetch') as fetch:
                self.assertEqual(assets.prepare({**item(),'image':url}),'');fetch.assert_not_called()

    def test_public_storage_requires_upload_and_readback_confirmation(self):
        from services import r2_storage
        with patch.dict(os.environ,{'CRM_EMAIL_ASSET_PUBLIC_BASE_URL':'https://assets.example.com'}),patch.object(r2_storage,'get_bucket_name',return_value='assets'),patch.object(r2_storage,'safe_r2_enabled',return_value=True),patch.object(r2_storage,'object_exists',return_value=False),patch.object(r2_storage,'upload_bytes',return_value={'ok':True}) as upload,patch.object(assets.requests,'get') as get:
            response=get.return_value.__enter__.return_value
            response.status_code=200;response.headers={'Content-Type':'image/jpeg'}
            self.assertEqual(assets.public_asset(b'image','email/a.jpg'),'https://assets.example.com/email/a.jpg')
            upload.assert_called_once_with('assets','email/a.jpg',b'image','image/jpeg')
            response.status_code=404;self.assertEqual(assets.public_asset(b'image','email/a.jpg'),'')
            upload.return_value={'ok':False};get.reset_mock()
            self.assertEqual(assets.public_asset(b'image','email/a.jpg'),'');get.assert_not_called()

    def test_crop_aspect_ratio_and_non_square_rejection(self):
        for frame,(_,_,w,h) in assets.CROPS.items():
            with Image.open(io.BytesIO(assets.crop_image(picture(),frame))) as image:
                self.assertEqual(image.size,(1200,round(1200*h/w)))
        with self.assertRaises(ValueError):assets.crop_image(picture(1200,800),'black')

    def test_snapshot_crops_match_implementation(self):
        from pathlib import Path
        js=Path('tests/fixtures/wall_banner/sports-cave-wall-artwork.js').read_text(encoding='utf-8')
        import re
        for frame,(x,y,w,h) in assets.CROPS.items():
            self.assertRegex(js,frame+r':\s*\{x:\s*'+str(x)+r',\s*y:\s*'+str(y)+r',\s*w:\s*'+str(w)+r',\s*h:\s*'+str(h))

    def test_dispatch_requires_actual_recipient_checkout(self):
        from crm_automation_runtime import render
        from tests.test_crm_abandoned_checkout import checkout
        import uuid
        raw=checkout(customer=99)
        raw['lineItems']['nodes'][0]['variant']={'id':'gid://shopify/ProductVariant/123','product':{
            'id':'gid://shopify/Product/456','status':'ACTIVE','onlineStoreUrl':item()['product_url']}}
        doc=self.doc();row={'id':str(uuid.uuid4()),'shopify_customer_id':'gid://shopify/Customer/99'}
        content={'document':doc,'render_settings':CFG,'trigger':'abandoned'}
        with patch('crm_campaign_send.production_checks',return_value={'safe':True}),patch.object(assets,'prepare',return_value=''):
            message=render(content,row,'https://example.test/unsubscribe',{'_checkout':raw,'_checkout_id':raw['id']})
            self.assertNotIn(banner.PREFIX,message['html'])
            with self.assertRaisesRegex(ValueError,'context mismatch'):render(content,row,'https://example.test/unsubscribe',{})

    def test_hidden_banner_never_fetches_and_renders_no_tokens(self):
        doc=self.doc();doc['middle_sections'][-1]['visible']=False
        with patch.object(assets,'prepare') as prepare:
            html=render_campaign(hydrate(doc,{'items':[item()]}),CFG)['html']
        self.assertNotIn(banner.PREFIX,html);prepare.assert_not_called()


import os
@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable SQL required')
class BannerPersistenceTests(unittest.TestCase):
    def test_campaign_draft_and_duplicate_keep_inserted_section(self):
        from crm_campaign_store import CampaignStore
        from tests.crm_db_fixture import connect
        from tests.test_crm import ADMIN
        store=CampaignStore(connect);doc=document()
        insert_saved_template(store,doc,banner.IDENTITY,1)
        row=store.save(ADMIN,'Frame banner campaign fixture',doc)
        self.assertEqual(store.draft(row['id'])['document']['middle_sections'],doc['middle_sections'])
        copied=store.duplicate(ADMIN,row['id'])
        self.assertEqual(copied['document']['middle_sections'],doc['middle_sections'])
        self.assertEqual(copied['status'],'DRAFT')

    def test_saved_flow_reopened_and_duplicate_do_not_publish(self):
        from crm_automation_store import AutomationStore
        from tests.crm_db_fixture import connect
        from tests.test_crm import ADMIN
        from crm_flow_builder import edit_sequence
        store=AutomationStore(connect);row=store.create(ADMIN,'abandoned','Frame banner fixture')
        flow=deepcopy(row['config']['draft']);doc=flow['emails'][0]['document']
        doc.update(content_mode='HTML',custom_html='')
        insert_saved_template(store,doc,banner.IDENTITY,1)
        store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision'])
        saved=store.flow(row['id'])
        self.assertEqual(saved['config']['draft']['emails'][0]['document'],doc)
        self.assertEqual(saved['config']['published_version'],0)
        duplicate=edit_sequence(saved['config']['draft'],flow['emails'][0]['step_id'],'duplicate')
        self.assertEqual(duplicate['emails'][1]['document'],doc)
        self.assertEqual(store.q('SELECT count(*) AS n FROM crm_automation_enrollments WHERE automation_id=%s',(row['id'],),True)['n'],0)


if __name__=='__main__':unittest.main()
