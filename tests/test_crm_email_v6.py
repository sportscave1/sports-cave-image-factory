"""V6 source/preview/delivery boundaries, no external services."""
from copy import deepcopy
import json
from unittest import TestCase
from unittest.mock import Mock,patch
from crm_campaign_content import validate_document,preflight
from crm_campaign_html import import_html
from crm_discount_section import section,disconnect,validate_presentation
from crm_middle_sections import apply_event,commit_middle,middle_sections
from crm_recovery_discount import substitute
from crm_local_preview import model
from tests.test_crm_campaign_sections import sectioned
from tests.test_crm_discount_editor_v2 import add,event
from tests.test_crm_send_flow import CFG,LIVE

class CustomisationTests(TestCase):
    def test_all_discount_presentations_save_and_preview_without_association(self):
        for source in ('','<table><tr><td>unfinished','<p>Custom invitation</p>','<p>{{discount_code}}</p>','<p>{{discount_value}}</p>'):
            for mode in ('campaign','automation'):
                doc=sectioned();s=section();s['html']=source;commit_middle(doc,[s]);original=deepcopy(doc)
                validate_document(json.loads(json.dumps(doc)))
                with patch('streamlit.session_state',{}):seed=model(doc,CFG,Mock(email_mode=mode))
                self.assertEqual(seed['errors'],{});self.assertEqual(doc,original)
                self.assertFalse(doc.get('recovery_discount'))

    def test_hidden_deleted_restored_and_custom_html_preserve_offer_until_disconnect(self):
        doc=sectioned();s=add(doc);offer=deepcopy(doc['recovery_discount']);source='<h2 style="color:#123456">A personal invitation</h2>'
        apply_event(doc,event(doc,'html',id=s['id'],html=source));validate_presentation(doc)
        apply_event(doc,event(doc,'visible',id=s['id'],visible=False));self.assertEqual(doc['recovery_discount'],offer)
        apply_event(doc,event(doc,'remove',id=s['id'],confirmed=True));self.assertEqual(doc['recovery_discount'],offer)
        from crm_discount_section import migrate_editor
        self.assertFalse(any(s['type']=='discount' for s in migrate_editor(doc)['middle_sections']))
        disconnect(doc);self.assertNotIn('recovery_discount',doc)
        apply_event(doc,event(doc,'restore_section',section={**s,'html':source},position=0))
        self.assertNotIn('recovery_discount',doc,'Undo may restore creative, never silently reconnect a disconnected offer')

    def test_draft_claims_are_visible_but_delivery_remains_guarded(self):
        for source in ('<p>Save 50%</p>','<p>Use code FAKECODE</p>','<p>Free shipping</p>'):
            doc=sectioned();s=add(doc);s['html']=source;commit_middle(doc,[s]);validate_document(doc)
            with patch('streamlit.session_state',{}):seed=model(doc,CFG)
            self.assertEqual(seed['errors'],{})
            with self.assertRaises(ValueError):substitute(doc)
            self.assertFalse(preflight(doc,LIVE,CFG)['test_ready'])

    def test_unbound_placeholder_never_reaches_delivery(self):
        doc=sectioned();commit_middle(doc,[section()])
        with self.assertRaises(ValueError):substitute(doc)
        self.assertFalse(preflight(doc,LIVE,CFG)['test_ready'])
        self.assertIn('[Discount code]',substitute(doc,preview=True)['middle_sections'][0]['html'])

    def test_code_free_bound_presentation_passes_delivery_copy_validation(self):
        doc=sectioned();s=add(doc);s['html']='<p>Explore your selected edition.</p>';commit_middle(doc,[s])
        validate_presentation(doc);rendered=substitute(doc)
        self.assertEqual(rendered['recovery_discount'],doc['recovery_discount'])

    def test_template_reopening_preserves_authored_source(self):
        from crm_campaign_library import _template_html
        source='<style>.headline{color:#123456}</style><!-- keep author note --><h2 class="headline">{{discount_code}}</h2>'
        doc=sectioned();sections=middle_sections(doc);sections[0]['html']=source;commit_middle(doc,sections)
        store=Mock();store.template_document.return_value=doc
        self.assertEqual(_template_html(store,{'id':'v6-source','version':1,'content':{'document':doc}}),source)

    def test_safe_class_styles_render_without_touching_source_or_footer(self):
        source='<style>.headline{color:#123456;padding:22px} h2{background-color:#ffffff}</style><h2 class="headline" style="color:#654321">Custom</h2>'
        self.assertNotIn('padding:22px',import_html(source)[0], 'Legacy published markup keeps its original renderer')
        rendered,_,checks=import_html(source,inline_styles=True)
        self.assertIn('padding:22px',rendered);self.assertIn('color:#654321',rendered)
        self.assertNotIn('<style',rendered);self.assertIn('<style',source)
        unsafe,_,checks=import_html('<style>.x{background:url(https://example.com/pixel.png);position:fixed}</style><p class="x" onclick="alert(1)">X</p><script>alert(1)</script>',inline_styles=True)
        self.assertNotIn('url(',unsafe);self.assertNotIn('position:',unsafe);self.assertNotIn('onclick',unsafe)
        self.assertFalse(checks['HTML contains only safe email markup'])

    def test_unused_optional_assets_do_not_block_plain_preview(self):
        with patch('streamlit.session_state',{}),patch('crm_lifestyle_images.gallery') as gallery,patch('crm_frame_banner_assets.prepare') as banner:
            model(sectioned(),CFG)
            gallery.assert_not_called();banner.assert_not_called()

    def test_legacy_render_changes_only_after_an_explicit_source_edit(self):
        from crm_middle_sections import render_middle
        doc=sectioned();parts=middle_sections(doc)
        parts[0]['html']='<style>.title{padding:23px}</style><p class="title">Legacy</p>'
        commit_middle(doc,parts);published=deepcopy(doc);old=render_middle(published)[0]
        apply_event(doc,event(doc,'visible',id=parts[0]['id'],visible=False))
        apply_event(doc,event(doc,'visible',id=parts[0]['id'],visible=True))
        self.assertEqual(render_middle(doc)[0],old)
        apply_event(doc,event(doc,'html',id=parts[0]['id'],html=parts[0]['html']))
        self.assertIn('padding:23px',render_middle(doc)[0])
        self.assertEqual(render_middle(published)[0],old)

    def test_template_insertion_preserves_hidden_source_and_ids_are_new(self):
        doc=sectioned();original=deepcopy(doc)
        parts=[dict(id='a',type='html',html_number=1,visible=False,html='<!-- retained --><p>Hidden</p>'),section()]
        parts[1]['html']='<p>Personal creative</p>'
        action=event(doc,'add',kind='template',new_ids=['new-a','new-b'])
        apply_event(doc,action,resolve_insert=lambda _:dict(html='',sections=parts))
        self.assertEqual(doc['middle_sections'][-2]['id'],'new-a')
        self.assertFalse(doc['middle_sections'][-2]['visible'])
        self.assertEqual(doc['middle_sections'][-2]['html'],parts[0]['html'])
        self.assertEqual(doc['middle_sections'][0],middle_sections(original)[0])
        self.assertNotIn('recovery_discount',doc)
        self.assertIsNone(doc['middle_sections'][-1]['offer'])

    def test_single_catalogue_template_keeps_its_native_type(self):
        from crm_campaign_content import new_document
        from tests.test_crm_modular_catalogue import catalogue_doc
        doc=new_document();doc.update(content_mode='HTML',custom_html='')
        source=[catalogue_doc()['middle_sections'][-1]]
        apply_event(doc,event(doc,'add',kind='template',new_ids=['new-catalogue']),resolve_insert=lambda _:dict(html='',sections=source))
        validate_document(doc)
        self.assertEqual(len(doc['middle_sections']),1)
        self.assertEqual(doc['middle_sections'][0]['type'],'catalogue')
        self.assertNotIn('css_version',doc['middle_sections'][0])

    def test_large_draft_source_is_saveable_but_oversize_delivery_is_blocked(self):
        from crm_email_size import validate_rendered_email
        from crm_campaign_content import render_campaign
        doc=sectioned();sections=middle_sections(doc);sections[0]['html']='<p>Creative source</p>'*7000
        commit_middle(doc,sections);validate_document(doc)
        with self.assertRaises(ValueError):validate_rendered_email(render_campaign(doc,CFG))
