"""Offline Creative Refresh reference UX and format provenance contracts."""
import base64
import copy
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
import ads_page as ads
import ads_refresh_reference as reference
import meta_review_handoff as handoff
from tests.test_ads_refresh_workflow import winner, completed_single
from tests.test_ads_posting_handoff import completed_ad, save_locally
from tests.test_meta_review import ad, CREATIVE
import meta_review_analysis as analysis
import ads_posting_handoff as posting_handoff
import ads_posting_page as posting

ROOT=Path(__file__).resolve().parents[1]

class ReferenceCleanupTests(unittest.TestCase):
    def test_saved_format_aliases_and_manual_edit_survive(self):
        for raw, expected in [('SINGLE_IMAGE','Single Image / Video'),('VIDEO','Single Image / Video'),('carousel','Carousel'),('instant_experience','Instant Experience')]:
            source=winner();source['format']=raw
            state={handoff.PENDING:source}
            handoff.hydrate(state)
            self.assertEqual(state['ads_campaign_type'],expected)
            self.assertTrue(state[handoff.ACTIVE]['campaign_type_resolution']['confirmed'])
            value=ads.build_ads_result_record(source['product_mapping']['product_title'],'Football','Australia',state['ads_campaign_type'],
                product_url=source['product_mapping']['product_url'],creative_refresh_context={
                    'winning_primary_text':source['components']['primary_text']['value'],
                    'winning_headline':source['components']['headline']['value'], 'source_winner':state[handoff.ACTIVE]})
            self.assertEqual(value['campaign_type'],expected)
            if expected == 'Instant Experience':
                self.assertIn('INSTANT EXPERIENCE WINNER REFINEMENT',value['master_prompt'])
                self.assertIn('canonical Sports Cave product image',value['master_prompt'])
            else:
                self.assertIn('Campaign format: '+expected,value['master_prompt'])
            state['ads_campaign_type']='Carousel'
            self.assertFalse(handoff.hydrate(state))
            self.assertEqual(state['ads_campaign_type'],'Carousel')
            self.assertEqual(state[handoff.ACTIVE]['components'],source['components'])

    def test_actual_meta_creative_formats_in_advanced_handoff(self):
        from tests.test_meta_review_creative import inline
        for creative,expected in [(CREATIVE,'Single Image / Video'),
          (inline(5),'Carousel'),
          ({'object_story_spec':{'link_data':{'link':'https://www.facebook.com/canvas/123'}}},'Instant Experience')]:
            selected=ad();selected['raw']={'creative':copy.deepcopy(creative)}
            choices={k:analysis.component_candidates([selected],k)[0] for k in ('image','primary_text','headline')}
            package=handoff.build_package(selected,choices,{},'complete_ad')
            state={handoff.PENDING:package};handoff.hydrate(state)
            self.assertEqual(state['ads_campaign_type'],expected)
            self.assertTrue(state[handoff.ACTIVE]['campaign_type_resolution']['confirmed'])

    def test_benchmark_and_mapping_evidence_without_changing_scoring(self):
        selected=ad();selected['benchmark']={'format':'INSTANT EXPERIENCE'};selected['assets']['carousel']=True
        choices={k:analysis.component_candidates([selected],k)[0] for k in ('image','primary_text','headline')}
        package=handoff.build_package(selected,choices,{},'complete_ad')
        state={handoff.PENDING:package};handoff.hydrate(state)
        self.assertEqual(state['ads_campaign_type'],'Single Image / Video')
        self.assertFalse(state[handoff.ACTIVE]['campaign_type_resolution']['confirmed'])
        self.assertEqual(selected['benchmark']['format'], 'INSTANT EXPERIENCE')
        self.assertEqual(handoff.resolve_campaign_type({'ad_mapping':{'ad_type':'Carousel'}})['campaign_type'],'Carousel')
        self.assertEqual(handoff.resolve_campaign_type({'format':'Instant Experience','carousel':True})['campaign_type'],'Instant Experience')

    def test_unknown_is_explicit_fallback_not_image_guess(self):
        source=winner();source.pop('format');source.pop('carousel')
        state={handoff.PENDING:source};handoff.hydrate(state)
        self.assertEqual(state['ads_campaign_type'],'Single Image / Video')
        self.assertEqual(state[handoff.ACTIVE]['campaign_type_resolution'],{'campaign_type':'Single Image / Video','confirmed':False,'source':'legacy_default'})
        self.assertFalse(handoff.resolve_campaign_type({'format':None,'raw':None})['confirmed'])
        ambiguous={'creative_metadata':{'asset_feed_spec':{'ad_formats':['SINGLE_IMAGE','CAROUSEL']}}}
        self.assertFalse(handoff.resolve_campaign_type(ambiguous)['confirmed'])
        self.assertEqual(handoff.resolve_campaign_type(ambiguous)['source'],'ambiguous_creative_formats')

    def test_reference_preview_bytes_and_source_preserved_without_old_controls(self):
        source=winner();st=MagicMock();st.session_state={handoff.ACTIVE:copy.deepcopy(source)};st.query_params={}
        st.columns.return_value=(MagicMock(),MagicMock())
        with patch.object(handoff.store,'load_media',return_value=(b'original-bytes','image/jpeg')),patch.object(reference,'render_winning_image_copy') as copy_image:
            self.assertTrue(handoff.render_source(st))
        st.image.assert_called_once_with(b'original-bytes',width=200)
        copy_image.assert_called_once_with(b'original-bytes','image/jpeg')
        st.download_button.assert_not_called();st.expander.assert_not_called();st.button.assert_not_called()
        self.assertEqual(st.session_state[handoff.ACTIVE],source)
        html=reference.winning_image_copy_html(b'original-bytes','image/jpeg')
        self.assertIn(base64.b64encode(b'original-bytes').decode(),html)
        for text in ('Copy winning image','Open full-resolution image','ClipboardItem','Copied','image.naturalWidth','image.naturalHeight'):
            self.assertIn(text,html)
        self.assertNotIn('download=',html)
        self.assertNotIn('fetch(',html)

    def test_files_link_is_lazy_separate_window_and_exact_existing_root(self):
        st=MagicMock()
        before=winner()
        st.session_state=copy.deepcopy(before)
        reference.render_product_image_link(st)
        st.link_button.assert_called_once_with('Find product image','/files-window?relative_path=04_OUTPUT/product-images',icon=':material/folder_open:')
        self.assertEqual(st.session_state,before)
        source=(ROOT/'ads_page.py').read_text(encoding='utf-8')
        self.assertIn("if is_creative_refresh and campaign_type != 'Carousel':\n        from ads_refresh_reference import render_product_image_link",source)
        self.assertIn('elif not is_creative_refresh and not is_google:\n        render_product_artwork_reference(product_selection, product_url)',source)
        self.assertNotIn('shopify',Path(reference.__file__).read_text(encoding='utf-8').lower())

    def test_format_and_provenance_survive_existing_save_and_posting(self):
        for campaign_type in ('Single Image / Video','Carousel','Instant Experience'):
            if campaign_type=='Single Image / Video':value,workflow=completed_single()
            else:value,workflow=completed_ad(campaign_type,ads.ADS_WORKFLOW_MODE_CREATIVE_REFRESH)
            source=winner();source['format']=campaign_type
            state={handoff.PENDING:source};handoff.hydrate(state)
            value['campaign_type']=state['ads_campaign_type']
            value['creative_refresh_context']={'source_winner':state[handoff.ACTIVE]}
            save_locally(value,workflow)
            package=workflow[posting_handoff.SAVED_PACKAGE_KEY]
            self.assertEqual(package['ad_type'],campaign_type)
            self.assertTrue(package['source_provenance']['source_winner']['campaign_type_resolution']['confirmed'])
            queued={};posting_handoff.queue_saved_package(package,state=queued)
            self.assertEqual(queued[posting_handoff.PENDING_KEY]['package']['ad_type'],campaign_type)
            from tests.test_posting_import_csv import product_records
            from tests.test_ads_refresh_workflow import ROW
            records=ads.build_ads_product_selector_records([ROW]) if campaign_type=='Single Image / Video' else product_records()
            self.assertTrue(posting.consume_saved_posting_package(records,state=queued))
            self.assertEqual(queued[posting.AD_TYPE_KEY],campaign_type)

if __name__=='__main__':unittest.main()
