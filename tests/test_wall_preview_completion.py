"""Local-only completion regression tests; no customer/provider writes."""
import io
import os
import unittest
from PIL import Image
from tests import test_wall_preview_crm_v2 as fixture
import wall_preview_crm_api as api
import wall_preview_crm_store as store

class CompositeTests(unittest.TestCase):
    def test_finished_download_bytes_and_resolution_preserved(self):
        out=io.BytesIO();Image.new('RGB',(3200,2400),'blue').save(out,'JPEG',quality=92)
        raw=out.getvalue();clean,w,h=api.clean_image(raw,'image/jpeg',True)
        self.assertEqual(clean,raw);self.assertEqual((w,h),(3200,2400))
    def test_finished_source_metadata_still_removed(self):
        raw=fixture.jpeg(exif=True);clean,w,h=api.clean_image(raw,'image/jpeg',True)
        with Image.open(io.BytesIO(clean)) as image:self.assertFalse(image.getexif())

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class CompletionDatabaseTests(unittest.TestCase):
    setUpClass=classmethod(fixture.DatabaseTests.setUpClass.__func__)
    setUp=fixture.DatabaseTests.setUp
    tearDown=fixture.DatabaseTests.tearDown
    def test_place_download_consent_and_replace_same_record(self):
        first,_=store.confirm(self.data,self.upload)
        self.assertFalse(first['marketing_permission'])
        self.data['image_reuse_allowed']=True
        self.data['identity']['customer_email']='fixture@example.test'
        second,duplicate=store.confirm(self.data,self.upload)
        self.assertTrue(duplicate);self.assertEqual(first['id'],second['id'])
        self.assertTrue(second['marketing_permission']);self.assertEqual(second['customer_email'],'fixture@example.test')
        self.assertEqual(second['version'],1);self.upload.assert_called_once()
        self.data.pop('image_reuse_allowed')
        same,_=store.confirm(self.data,self.upload)
        self.assertTrue(same['marketing_permission'])
        self.data['image_sha256']='f'*64
        changed,_=store.confirm(self.data,self.upload)
        self.assertEqual(changed['id'],first['id']);self.assertEqual(changed['version'],2)
        self.assertFalse(changed['marketing_permission'])
        with self.Adapter() as cur:
            cur.execute('SELECT count(*) AS n FROM public.wall_preview_email_jobs');self.assertEqual(cur.fetchone()['n'],0)
            cur.execute('SELECT count(*) AS n FROM public.wall_previews');self.assertEqual(cur.fetchone()['n'],1)
    def test_download_unchecked_explicitly_records_not_approved(self):
        self.data['image_reuse_allowed']=False
        row,_=store.confirm(self.data,self.upload)
        self.assertFalse(row['marketing_permission'])
        self.assertEqual(row['image_reuse_consent_source'],'wall_preview_download_checkbox')
        self.assertIsNotNone(row['image_reuse_consent_at'])
    def test_wrong_session_cannot_change_permission(self):
        store.confirm(self.data,self.upload)
        self.data.update(session_id=fixture.payload()['session_id'],image_reuse_allowed=True)
        with self.assertRaises(PermissionError):store.confirm(self.data,self.upload)

class UnchangedBehaviorTests(unittest.TestCase):
    def test_existing_core_functions_unchanged_from_published_theme(self):
        import re, hashlib
        from pathlib import Path
        source=Path('shopify_theme/snippets/sc-wall-visualizer-v1.liquid').read_text(encoding='utf-8')
        expected={'buildCompositeCanvas': '9b2cad9c46806481c625f883679c196be92a65d605d47688841a8fddfa007d09', 'addSelectedVariantToCart': 'bec145ae7e7a90b094f76cdbed36eb43254529128d4b0b26fcf364e90f39964f', 'shareConfirmedPreview': '1c81d0c402b558e5af3af08794ec1620488628a606d7f344c76306948d32e78a', 'closeDialog': '7ee4eb97e40167ffa2d2c32f95aed0c66d44fd326363bae6c3371e2c74e6e816', 'currentVariant': '72e97bcb423e7f9c332d3fd0836fe25283d30071b35f38a40a5697ce72eba7f5', 'startRearCamera': '1b8df3f22675a8eeaa84b93ea473a4104ea16b5ceb77b12a155412d25174b854'}
        for name,digest in expected.items():
            with self.subTest(function=name):
                match=re.search(r'^(?:async )?function '+name+r'\([^\n]*[\s\S]*?(?=^(?:async )?function |\Z)',source,re.M)
                self.assertEqual(hashlib.sha256(match.group().encode()).hexdigest(),digest)

class CompletionApiTests(unittest.TestCase):
    def test_anonymous_place_does_not_infer_permission(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        params={'client_preview_id':fixture.payload()['client_preview_id'],'session_id':fixture.payload()['session_id'],
                'product_url':'https://sportscaveshop.com/products/test-art','finished_composite':'1'}
        with patch.object(store,'confirm',return_value=({'id':params['client_preview_id'],'version':1},False)) as confirm:
            response=api.save(SimpleNamespace(query_params=params),fixture.jpeg(),'image/jpeg',{})
        self.assertEqual(response.status_code,200)
        saved=confirm.call_args.args[0]
        self.assertNotIn('image_reuse_allowed',saved)
        self.assertEqual(saved['archive_image'],fixture.jpeg())
        self.assertEqual(saved['identity']['identity_source'],'anonymous')
    def test_checkbox_contract_true_false_and_invalid(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        base={'client_preview_id':fixture.payload()['client_preview_id'],'session_id':fixture.payload()['session_id'],
              'product_url':'https://sportscaveshop.com/products/test-art','reuse_consent_source':'wall_preview_download_checkbox'}
        for value,expected in [('1',True),('0',False),('yes',None)]:
            with self.subTest(value=value),patch.object(store,'confirm',return_value=({'id':base['client_preview_id'],'version':1},True)) as confirm:
                response=api.save(SimpleNamespace(query_params={**base,'image_reuse_allowed':value}),fixture.jpeg(),'image/jpeg',{})
                self.assertEqual(response.status_code,400 if expected is None else 200)
                if expected is None:confirm.assert_not_called()
                else:self.assertIs(confirm.call_args.args[0]['image_reuse_allowed'],expected)
