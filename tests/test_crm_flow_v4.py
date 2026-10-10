"""Flow V4 uses only synthetic documents and mocked read-only dependencies."""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock,patch
import inspect
from PIL import Image
from crm_thumbnail_render import preview_document
from crm_thumbnail_store import valid
from crm_thumbnail_cache import selection,source_loader
from tests.test_crm_simple_editor import document
from tests.test_crm_send_flow import CFG

def webp(colour='black'):
    output=BytesIO();Image.new('RGB',(240,316),colour).save(output,format='WEBP')
    return output.getvalue()

def discount_document():
    from crm_discount_section import section
    doc=document()
    offer={'id':'gid://shopify/DiscountCodeNode/11','code':'FIXTURE5','value':'A$5 off eligible products','type':'DiscountCodeBasic'}
    doc['recovery_discount']=offer
    from crm_middle_sections import middle_sections
    doc['middle_sections']=middle_sections(doc)+[section(offer)]
    doc['content'].update(subject='Your edition is waiting',preheader='Your courtesy code FIXTURE5 awaits')
    return doc

class FlowV4Tests(TestCase):
    def test_discount_only_preview_lowers_actual_saved_offer(self):
        from crm_campaign_content import render_campaign
        original=discount_document();before=deepcopy(original)
        lowered=preview_document(original)
        html=render_campaign(lowered,CFG,production=False)['html']
        self.assertIn('FIXTURE5',html);self.assertIn('A$5 off eligible products',html)
        self.assertNotIn('{{discount_code}}',html)
        self.assertEqual(original,before)

    def test_discount_and_personalisation_and_checkout_are_read_only(self):
        from crm_abandoned_checkout import apply_template
        from crm_campaign_content import render_campaign
        doc=discount_document();offer=deepcopy(doc['recovery_discount']);apply_template(doc)
        from crm_discount_section import section
        doc['recovery_discount']=offer
        doc['middle_sections'].append(section(offer))
        doc['content']['subject']='{{first_name}}, your edition'
        before=deepcopy(doc)
        with patch('requests.sessions.Session.request',side_effect=AssertionError('No provider')):
            prepared=preview_document(doc)
            self.assertIn('Alex',prepared['content']['subject'])
            self.assertIn('FIXTURE5',render_campaign(prepared,CFG)['html'])
        self.assertEqual(doc,before)

    def test_no_fabricated_offer_or_edition(self):
        from crm_recovery_discount import DiscountHold
        doc=document();doc['content']['subject']='Next available edition: {{edition_number}}'
        self.assertNotIn('#001',preview_document(doc)['content']['subject'])
        doc['content']['subject']='{{discount_code}}';doc.pop('recovery_discount',None)
        self.assertIn('unavailable in sample preview',preview_document(doc)['content']['subject'])
        from crm_recovery_discount import substitute
        with self.assertRaises(DiscountHold):substitute(doc)

    def test_corrupt_header_is_not_a_ready_image(self):
        self.assertFalse(valid(b'RIFF0000WEBPtest'));self.assertTrue(valid(webp()))
        self.assertFalse(valid(webp()[:20]))

    def test_oversized_decoded_image_is_a_recoverable_cache_miss(self):
        with patch('PIL.Image.open',side_effect=Image.DecompressionBombError('fixture')):
            self.assertFalse(valid(webp()))

    def test_stable_identity_for_one_three_six_twelve_and_future_triggers(self):
        for trigger in ('abandoned','welcome','post_purchase','win_back'):
            for count in (1,3,6,12):
                steps=[dict(step_id=str(i),document=document(),enabled=i%2==0) for i in range(count)]
                row={'id':trigger,'config':{'revision':1},'steps':[dict(step_id=s['step_id'],template_id='t'+s['step_id'],template_version=10) for s in steps]}
                keys=[selection(row,s)[0] for s in steps]
                self.assertEqual(len(set(keys)),count)
                self.assertEqual([selection(row,s)[0] for s in reversed(steps)],list(reversed(keys)))
                for s in steps:
                    store=Mock();store.template.return_value=dict(automation_id=trigger,step_id=s['step_id'],automation_version=10,document=s['document'],render_settings=CFG)
                    _,label,live=selection(row,s)
                    self.assertEqual(label,'LIVE v10');source_loader(store,row,s,live)()
                    store.render_settings.assert_not_called()

    def test_main_page_restores_operational_controls_and_admin_route_is_gated(self):
        import crm_flow_page as page
        source=inspect.getsource(page.flow_page)
        main=source[source.index("with st.container(key='flow-workspace'):"):]
        self.assertIn('recipient_details(',main);self.assertIn('checkouts(',main)
        self.assertLess(main.index('sequence('),main.index('recipient_details('))
        self.assertIn('os_accounts.is_admin(user)',source)
        import crm_automation_toolbar as toolbar
        code=Path(toolbar.__file__).read_text(encoding="utf8")
        self.assertIn('Open operational diagnostics',code)
        self.assertIn('if not flow_view and os_accounts.is_admin(user):',code)

    def test_no_timer_based_dom_scanning(self):
        from crm_flow_thumbnail import SCRIPT
        self.assertNotIn('setInterval',SCRIPT)
        self.assertIn('setTimeout',SCRIPT);self.assertIn('IntersectionObserver',SCRIPT)

    def test_draft_identity_is_stage_scoped_and_survives_timing_revision(self):
        row={'id':'a','config':{'revision':1},'steps':[]}
        step={'step_id':'one','document':document()}
        key=selection(row,step)[0];row['config']['revision']=2
        self.assertEqual(selection(row,step)[0],key)
        self.assertNotEqual(selection(row,dict(step,step_id='two'))[0],key)

    def test_definition_cache_reuses_documents_but_checks_freshness(self):
        from crm_automation_toolbar import definition
        store=Mock();store.q.return_value={'updated_at':1};store.flow.return_value={'id':'a'}
        state={};definition(store,state,'a');definition(store,state,'a')
        self.assertEqual(store.q.call_count,2);self.assertEqual(store.flow.call_count,1)
        store.q.return_value={'updated_at':2};definition(store,state,'a')
        self.assertEqual(store.flow.call_count,2)
