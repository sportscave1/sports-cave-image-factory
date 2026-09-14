import unittest
from unittest.mock import patch
import app
import product_upload_modes as modes
from product_collector_copy import RULES
from tests.test_product_upload_prompts import ProductUploadFakeStreamlit, source_context


class ModeTests(unittest.TestCase):
    def prompt(self,mode):
        return app.get_product_upload_prompt(source_context(),publication_mode=mode)

    def test_same_core_and_all_standards_differ_only_in_finalisation(self):
        draft,live=self.prompt('DRAFT'),self.prompt('LIVE')
        self.assertEqual(modes.common_build(draft),modes.common_build(live))
        for text in (draft,live):
            self.assertIn(RULES,text)
            self.assertIn(app.PRODUCT_UPLOAD_META_PROMPT,text)
            self.assertIn(app.PRODUCT_UPLOAD_ALT_TEXT_PROMPT,text)
            self.assertIn(app.product_upload_price_ladder_prompt_text(),text)
            self.assertIn(app.PRODUCT_UPLOAD_MEDIA_RELIABILITY_SHARED,text)
            for required in ('16-variant','SKU','gallery','compare-at','Size guide','Prints in Posters, Prints, & Visual Artwork'):
                self.assertIn(required,text)

    def test_draft_has_no_live_finalisation_and_never_releases(self):
        text=self.prompt('DRAFT')
        self.assertIn(modes.DRAFT_FINAL,text)
        self.assertNotIn(modes.LIVE_FINAL,text)
        for requirement in ('Final Status: DRAFT. Published: false','Never set ACTIVE','never change Markets',
                            'do not set quantity to 20','Do not mutate collection publications','INCOMPLETE DRAFT'):
            self.assertIn(requirement,text)

    def test_live_stages_then_qa_then_activation_and_independent_publications(self):
        text=self.prompt('LIVE')
        self.assertNotIn(modes.DRAFT_FINAL,text)
        for contradiction in ('BRUTAL DRAFT RULE','Never publish a new product automatically.',
                              'Never set the product status to Active.','Only the user may approve publication after checking the full draft.'):
            self.assertNotIn(contradiction,text)
        self.assertLess(text.index(modes.CORE_END),text.index('4. ACTIVATE AND PUBLISH'))
        for requirement in ('all\n8 required image roles','fresh read verifies','all 16 exact variants','exactly 20',
                            'inventory\npolicy CONTINUE','SPORT COLLECTION','COLLECTOR SERIES','PRODUCT',
                            'active Markets/catalogs','No duplicate collections','paginate variants/media/publications'):
            self.assertIn(requirement,text)
        for channel in ('Online Store','Facebook & Instagram','Google & YouTube','Shop','Pinterest','Linktree'):
            self.assertIn(channel,text)

    def test_failure_and_retry_contracts_are_explicit(self):
        text=self.prompt('LIVE')
        for requirement in ('classification, media, variants, prices','either collection publication','Markets',
                            'ONLY this newly created product to DRAFT','DRAFT FALLBACK UNVERIFIED',
                            'never roll back\nshared collection publications','never increment by 20',
                            'never create a\nduplicate','perform only missing work'):
            self.assertIn(requirement,text)
        self.assertIn('media, variants, memberships or publication records',text)
        self.assertIn('ambiguous, leave Draft',text)

    def test_saved_shared_core_cannot_retain_other_mode_finalisation(self):
        for old in ('DRAFT','LIVE'):
            for new in ('DRAFT','LIVE'):
                text=app.apply_product_upload_prompt_updates(self.prompt(old),source_context(),publication_mode=new)
                self.assertEqual(text,self.prompt(new))
                self.assertEqual(text.splitlines().count(modes.START),1)
        draft=app.product_upload_operation_config(app.PRODUCT_UPLOAD_NEW_TYPE)
        live=app.product_upload_operation_config(app.PRODUCT_UPLOAD_LIVE_TYPE)
        self.assertEqual(draft['prompt_id'],live['prompt_id'])
        self.assertNotEqual(draft['key'],live['key'])
        self.assertEqual(draft['title'],'UPLOAD TO DRAFT')
        self.assertEqual(live['title'],'UPLOAD & PUBLISH LIVE')

    def test_invalid_or_existing_live_mode_rejected(self):
        with self.assertRaises(ValueError): self.prompt('MAYBE')
        with self.assertRaises(ValueError): app.get_product_upload_prompt(source_context(),update_existing=True,publication_mode='LIVE')

    def test_live_confirmation_gate_exports_no_prompt_until_confirmed(self):
        for confirmed in (False,True):
            fake=ProductUploadFakeStreamlit(upload_type=app.PRODUCT_UPLOAD_LIVE_TYPE,product_name='Approved Product')
            fake.checkbox=lambda *a,**k:confirmed
            with patch.object(app,'st',fake),patch.object(app,'current_product_upload_source_metadata',return_value=source_context()),patch.object(app,'log_app_memory'),patch.object(app,'render_copyable_prompt') as render:
                app.render_product_uploads_page()
            if not confirmed:
                render.assert_not_called()
                self.assertTrue(any('confirm live publication' in w for w in fake.warnings))
            else:
                self.assertEqual(render.call_args.args[0],'UPLOAD & PUBLISH LIVE')
                self.assertIn(modes.LIVE_FINAL,render.call_args.args[1])


if __name__=='__main__': unittest.main()
