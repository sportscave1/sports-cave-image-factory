"""Production-matching placeholder attributes, with no remote reads or delivery."""
import unittest
from copy import deepcopy
from unittest.mock import patch
from crm_campaign_content import preflight, settings
from crm_campaign_issues import issue_groups, CampaignValidationError
from crm_campaign_html import import_html
from tests.test_crm_modular_catalogue import catalogue_doc, event, service, node
from tests.test_crm_resend_marketing import ENV

HTML_ID='661173abb85e42228b05c2997dce431b'
CAT_ID='e23b65cb9f17476eaa91600bd4b678f5'
PLACEHOLDERS=('ICON_URL_CERTIFICATE','ICON_URL_FRAME','ICON_URL_FINISH','ICON_URL_DELIVERY')

def affected_document():
    doc=catalogue_doc()
    doc['middle_sections'][0].update(id=HTML_ID,html_number=2,html='<p>Collector assurance</p>'+''.join('<img src="'+src+'" alt="">' for src in PLACEHOLDERS))
    doc['middle_sections'][1].update(id=CAT_ID,visible=True,products=[])
    doc['custom_html']=''
    doc['copy_reviewed']=True
    return doc


class GroupTests(unittest.TestCase):
    def checks(self,doc):return preflight(doc,ENV,settings(ENV))

    def test_four_images_eight_faults_two_groups_without_mutating_source(self):
        doc=affected_document();before=deepcopy(doc);checks=self.checks(doc)
        self.assertFalse(checks['test_ready']);self.assertEqual(doc,before)
        groups=issue_groups(checks)
        self.assertEqual([g['display_label'] for g in groups],['HTML Section 2','Catalogue'])
        self.assertEqual(groups[0]['image_count'],4)
        self.assertEqual(groups[0]['messages'],['4 missing or unsupported image URLs','4 missing ALT texts'])
        self.assertIn('Add products or hide',groups[1]['messages'][0])
        self.assertEqual(len(checks['section_issues']),3)

    def test_fix_urls_alt_and_hide_or_populate_catalogue(self):
        doc=affected_document();section=doc['middle_sections'][0]
        for placeholder in PLACEHOLDERS:section['html']=section['html'].replace(placeholder,'https://cdn.shopify.com/'+placeholder.lower()+'.webp?v=123')
        checks=self.checks(doc);self.assertTrue(checks['test']['Images use durable public JPEG/PNG URLs'])
        self.assertFalse(checks['test']['Image alt text complete'])
        section['html']=section['html'].replace('alt=""','alt="Collector assurance"')
        event(doc,'visible',id=CAT_ID,visible=False);doc['copy_reviewed']=True
        self.assertTrue(self.checks(doc)['test_ready'])
        event(doc,'visible',id=CAT_ID,visible=True);doc['copy_reviewed']=True
        doc['middle_sections'][1]['products']=service().resolve([node()['id']])
        self.assertTrue(self.checks(doc)['test_ready'])
        rendered=import_html(section['html'])[0]
        self.assertIn('.webp?v=123&amp;format=png',rendered)

    def test_expected_error_carries_data_not_a_repeated_wall_of_text(self):
        checks=self.checks(affected_document());error=CampaignValidationError(checks)
        self.assertLess(len(str(error)),100);self.assertIs(error.checks,checks)

    def test_modal_expected_failure_renders_structured_readiness(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file('tests/fixtures/crm_test_preflight_preview.py').run()
        app.session_state['preflight_fixture_test_popover']=True;app.run()
        app.text_input[0].set_value('fixture@example.com')
        app.session_state['preflight_fixture_test_popover']=True
        next(button for button in app.button if button.label=='→').click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertIn('image_source',app.code[0].value)

    def test_primary_ui_hides_raw_ids_and_technical_details_are_separate(self):
        import crm_campaign_test_ui as ui
        with patch.object(ui.st,'html') as html,patch.object(ui.st,'expander'),patch.object(ui.st,'code') as code:
            ui.readiness(self.checks(affected_document()))
        from html.parser import HTMLParser
        class Text(HTMLParser):
            def __init__(self):super().__init__();self.text=''
            def handle_data(self,data):self.text+=data
        parser=Text();parser.feed(html.call_args.args[0])
        self.assertNotIn(HTML_ID,parser.text);self.assertNotIn(CAT_ID,parser.text)
        self.assertIn('2 sections need attention',parser.text)
        self.assertIn('4 images need attention',parser.text)
        self.assertEqual(html.call_args.args[0].count('Go to section'),2)
        self.assertIn(HTML_ID,code.call_args.args[0])

if __name__=='__main__':unittest.main()
