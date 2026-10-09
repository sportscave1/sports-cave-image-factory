"""Shared local editor contract; no live services or provider calls."""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch
from crm_middle_sections import apply_event,commit_middle,middle_sections
from crm_recovery_discount import substitute,DiscountHold
from crm_campaign_content import render_campaign,validate_document
from tests.test_crm_campaign_sections import sectioned
from tests.test_crm_send_flow import CFG


class LocalEditorTests(TestCase):
    def test_hidden_first_html_discount_mirror_does_not_block_preview_or_publication_render(self):
        doc=sectioned();s=middle_sections(doc)[0]
        s.update(html='<p>{{discount_code}}</p>',visible=False);commit_middle(doc,[s]);original=deepcopy(doc)
        rendered=substitute(doc);validate_document(rendered)
        self.assertNotIn('{{discount_code}}',render_campaign(rendered,CFG)['html'])
        self.assertEqual(doc,original)
        s['visible']=True;commit_middle(doc,[s])
        with self.assertRaises(DiscountHold):substitute(doc)

    def test_mirror_tracks_transformed_first_section(self):
        from tests.test_crm_discount_editor_v2 import add
        doc=sectioned();add(doc);sections=middle_sections(doc)
        sections[0]['html']='<p>{{discount_value}}</p>';commit_middle(doc,sections)
        rendered=substitute(doc);validate_document(rendered)
        self.assertEqual(rendered['custom_html'],'<p>A$5 off</p>')

    def test_rapid_batch_keeps_stable_ids_and_order(self):
        doc=sectioned();initial=deepcopy(doc);base=[s['id'] for s in middle_sections(doc)]
        actions=[dict(type='duplicate',id=base[0],new_id='client-copy',base=base),
                 dict(type='visible',id=base[0],visible=False,base=[base[0],'client-copy']),
                 dict(type='order',ids=['client-copy',base[0]],base=[base[0],'client-copy']),
                 dict(type='html',id='client-copy',html='<p>Newest draft</p>',base=['client-copy',base[0]])]
        apply_event(doc,dict(type='batch',base=base,events=actions));validate_document(doc)
        self.assertEqual([s['id'] for s in doc['middle_sections']],['client-copy',base[0]])
        self.assertFalse(doc['middle_sections'][1]['visible'])
        self.assertEqual(doc['html_sections'],initial['html_sections'])
        self.assertEqual(middle_sections(initial)[0]['visible'],True)
        self.assertIn('Newest draft',render_campaign(doc,CFG)['html'])

    def test_batch_failure_is_atomic_and_rejects_duplicate_identity(self):
        doc=sectioned();prior=deepcopy(doc);base=[s['id'] for s in middle_sections(doc)]
        with self.assertRaises(ValueError):
            apply_event(doc,dict(type='batch',base=base,events=[dict(type='visible',id=base[0],visible=False,base=base),dict(type='duplicate',id=base[0],new_id=base[0],base=base)]))
        self.assertEqual(doc,prior)

    def test_preview_is_section_isolated_and_never_changes_draft(self):
        from crm_local_preview import model
        doc=sectioned();sections=middle_sections(doc);sections[0]['html']='<p>{{discount_code}}</p>'
        sections.append(dict(id='valid',type='html',html_number=2,visible=True,html='<p>Valid neighbour</p>'))
        commit_middle(doc,sections);prior=deepcopy(doc)
        with patch('streamlit.session_state',{}):result=model(doc,CFG)
        self.assertIn('html-1',result['errors']);self.assertIn('Valid neighbour',result['resolved']['valid']['html'])
        self.assertIn('sc-local-sections',result['shell']);self.assertEqual(doc,prior)
