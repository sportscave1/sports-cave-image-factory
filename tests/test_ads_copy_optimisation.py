"""Offline final copy prompt, button placement and existing CSV round trips."""
import ast
import copy
import csv
import io
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock,patch
import ads_page as ads
import ads_copy_optimisation as optimisation
from tests.test_ads_posting_handoff import completed_ad as original_completed_ad,save_locally

def completed_ad(campaign):
    if campaign == "Single Image / Video":
        from tests.test_ads_refresh_workflow import completed_single
        result,workflow=completed_single()
        result["workflow_mode"]=ads.ADS_WORKFLOW_MODE_NEW
        return result,workflow
    return original_completed_ad(campaign)


def payload(prompt):
    text=prompt.split('CURRENT PACKAGE CONTEXT (data, not new generation instructions)\n',1)[1]
    context,end=json.JSONDecoder().raw_decode(text)
    data=prompt.split('```csv\n',1)[1].rsplit('\n```',1)[0]
    return context,data.encode('utf-8-sig')

class CopyOptimisationTests(unittest.TestCase):
    def test_exact_current_csv_context_and_no_mutation_all_formats(self):
        for campaign in ('Instant Experience','Carousel','Single Image / Video'):
            result,workflow=completed_ad(campaign)
            result['selected_audience']='Existing selected supporters'
            result['product_metadata']={'verified_facts':[{'text':'Approved edition fact','verified':True}], 'edition_limit':100,'edition_limit_source':'Owner confirmed'}
            before=copy.deepcopy((result,workflow))
            with patch.object(ads.st,'session_state',{}):
                prompt=ads.build_final_ad_review_copy_prompt(result,workflow)
                context,data=payload(prompt)
                expected=ads.build_instant_experience_copy_csv(result,copy.deepcopy(workflow)) if campaign=='Instant Experience' else ads.build_carousel_copy_csv(result,copy.deepcopy(workflow)) if campaign=='Carousel' else ads.ads_standard_workflow.csv_bytes(ads,result,workflow)
            self.assertEqual(data,expected)
            self.assertEqual((result,workflow),before)
            self.assertEqual(context['selected_audience'],'Existing selected supporters')
            self.assertEqual(context['csv_contract']['row_count'],len(list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))))
            self.assertEqual(context['carousel_character_limit'],ads.CAROUSEL_CARD_MAX_CHARACTERS if campaign=='Carousel' else None)
            for forbidden in ('WEIGHTED SCORE','PRODUCT LANDING PAGE','final campaign approver','VISUAL AUDIT','ad-to-landing-page journey'):
                self.assertNotIn(forbidden,prompt)
            self.assertTrue(prompt.startswith(optimisation.INSTRUCTIONS))
            self.assertIn('Create an actual downloadable file.',prompt)

    def test_current_imported_copy_is_in_prompt_and_roundtrips(self):
        for campaign in ('Instant Experience','Carousel','Single Image / Video'):
            result,workflow=completed_ad(campaign)
            with patch.object(ads.st,'session_state',{}):
                context,data=payload(ads.build_final_ad_review_copy_prompt(result,workflow))
                if campaign=='Instant Experience':ads.apply_instant_experience_copy_csv(result,workflow,data)
                elif campaign=='Carousel':ads.apply_carousel_copy_csv(result,workflow,data)
                else:ads.ads_standard_workflow.apply_csv(ads,result,workflow,data)
                after,newdata=payload(ads.build_final_ad_review_copy_prompt(result,workflow))
            self.assertEqual(context['current_csv_rows'],after['current_csv_rows'])
            self.assertEqual(data,newdata)
            save_locally(result,workflow)
            self.assertIn(ads.posting_handoff.SAVED_PACKAGE_KEY,workflow)

    def test_four_card_source_is_not_hardcoded_to_three(self):
        from tests.fixtures.refresh_ui import ready_carousel
        result,workflow=ready_carousel(4)
        with patch.object(ads.st,'session_state',{}):context,data=payload(ads.build_final_ad_review_copy_prompt(result,workflow))
        self.assertEqual(context['csv_contract']['image_count'],4)
        self.assertEqual(len([r for r in context['current_csv_rows'] if r['row_type']=='card']),4)

    def test_copy_button_immediately_precedes_each_existing_save_button(self):
        for campaign in ('Instant Experience','Carousel','Single Image / Video'):
            result,workflow=completed_ad(campaign);events=[]
            st=MagicMock();st.session_state={};st.button.side_effect=lambda label,**kw:events.append(('button',label)) or False
            st.caption.side_effect=lambda *a,**k:events.append(('caption',a[0]))
            with patch.object(ads,'st',st),patch.object(ads,'render_prompt_copy_button',side_effect=lambda text,key,**kw:events.append(('copy',kw))),patch.object(ads,'_render_saved_ad_post_now'):
                ads._render_ads_image_save(result,workflow)
            copies=[i for i,e in enumerate(events) if e[0]=='copy']
            self.assertEqual(len(copies),1)
            i=copies[0];self.assertEqual(events[i][1]['label'],'Copy Final Review Prompt')
            self.assertEqual(events[i][1]['success_label'],'Final review prompt copied')
            self.assertEqual(events[i+1][0],'button')
            self.assertTrue(events[i+1][1].startswith('Save'))

    def test_button_only_and_original_clipboard_styling(self):
        result,workflow=completed_ad('Carousel')
        with patch.object(ads.st,'session_state',{}),patch.object(ads.components,'html') as rendered:
            ads._render_final_ad_review(result,workflow)
        html=rendered.call_args.args[0]
        for token in ('Copy Final Review Prompt','Final review prompt copied','navigator.clipboard.writeText(promptText)'):
            self.assertIn(token,html)
        source=Path(ads.__file__).read_text(encoding='utf-8');tree=ast.parse(source)
        render=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_render_final_ad_review')
        self.assertNotIn('expander',ast.unparse(render));self.assertNotIn('st.caption',ast.unparse(render));self.assertNotIn('st.markdown',ast.unparse(render))
        page=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='render_page')
        self.assertNotIn('_render_final_ad_review(',ast.unparse(page))

    def test_invalid_draft_export_does_not_break_copy_button_or_invent_rows(self):
        result,workflow=completed_ad('Carousel')
        with patch.object(ads,'build_carousel_copy_csv',side_effect=ValueError('Draft CSV validation issue')):
            prompt=ads.build_final_ad_review_copy_prompt(result,workflow)
        self.assertIn('Draft CSV validation issue',prompt)
        self.assertIn('request the existing package CSV/schema',prompt)
        self.assertIn('"columns": [',prompt)
        self.assertNotIn('```csv',prompt)

    def test_obsolete_override_cannot_restore_old_audits(self):
        result,workflow=completed_ad('Instant Experience')
        prompt=ads.build_final_ad_review_copy_prompt(result,workflow,resolved_prompt='WEIGHTED SCORE old landing-page audit')
        self.assertTrue(prompt.startswith(optimisation.INSTRUCTIONS));self.assertNotIn('WEIGHTED SCORE',prompt)

if __name__=='__main__':unittest.main()
