"""HTML-first editor regressions; all persistence uses disposable loopback SQL."""
from copy import deepcopy
import os
import unittest
from unittest.mock import patch
from crm_campaign_content import new_document,render_campaign,preflight,validate_document,settings
from crm_campaign_html import import_html
from crm_block_editor import apply_event
from crm_email_blocks import block
from tests.test_crm_resend_marketing import ENV

HTML='<!doctype html><html><head><style>body{display:none}</style></head><body><table><tr><td><h1>A collector moment</h1><p>Discover the collection.</p><a href="https://www.sportscaveshop.com">Explore</a></td></tr></table></body></html>'


def document():
    doc=new_document();doc.update(content_mode='HTML',custom_html=HTML,copy_reviewed=True)
    doc['content'].update(subject='Collector edit',preheader='A sporting moment')
    return doc


class ContentTests(unittest.TestCase):
    def test_full_document_preview_and_plain_text_locked_footer(self):
        doc=document();rendered=render_campaign(doc,settings(ENV))
        self.assertIn('<h1>A collector moment</h1>',rendered['html'])
        self.assertIn('A collector moment',rendered['text'])
        self.assertIn('Unsubscribe',rendered['html']);self.assertNotIn('display:none}</style>',rendered['html'])
        self.assertEqual(doc['custom_html'],HTML)
        self.assertTrue(preflight(doc,ENV)['test_ready'])
        self.assertFalse(preflight(doc,ENV)['live_ready'])
        self.assertIn('sc_test=1',rendered['html'])

    def test_unsafe_import_cannot_escape_footer_or_run_scripts(self):
        doc=document();doc['custom_html']='</td></tr></table><script>alert(1)</script><p onclick="evil()" style="position:fixed;z-index:999;margin:-999px">Safe</p><img src="javascript:x"><a href="http://example.com">x</a>'
        rendered=render_campaign(doc,settings(ENV));fragment,_,checks=import_html(doc['custom_html'])
        for value in ('<script','onclick','position:','z-index','javascript:','href="http:'):
            self.assertNotIn(value,rendered['html'])
        self.assertTrue(fragment.startswith('<p'))
        self.assertFalse(all(checks.values()));self.assertFalse(preflight(doc,ENV)['test_ready'])
        self.assertIn('Unsubscribe',rendered['text'])

    def test_modes_retain_both_sources_and_legacy_still_renders(self):
        doc=document();doc['blocks']=[block('text',text='Independent block copy')]
        original=deepcopy(doc)
        doc['content_mode']='Blocks';self.assertIn('Independent block copy',render_campaign(doc)['html'])
        self.assertNotIn('A collector moment',render_campaign(doc)['html'])
        doc['content_mode']='HTML';self.assertEqual(doc,original)
        del doc['content_mode'];del doc['custom_html'];validate_document(doc)
        self.assertIn('Independent block copy',render_campaign(doc)['html'])

    def test_alt_https_and_empty_content_checks(self):
        for source in ('', '<img src="https://example.com/a.png">', '<a href="javascript:x">bad</a>'):
            doc=document();doc['custom_html']=source
            self.assertFalse(preflight(doc,ENV)['test_ready'])

    def test_drag_order_add_copy_delete_and_stale_events(self):
        blocks=[block('text',text='First'),block('text',text='Second')]
        ids=[b['id'] for b in blocks]
        reordered,_=apply_event(blocks,{'base':ids,'type':'order','ids':ids[::-1]})
        self.assertEqual([b['text'] for b in reordered],['Second','First'])
        with self.assertRaises(ValueError):apply_event(reordered,{'base':ids,'type':'order','ids':ids})
        with self.assertRaises(ValueError):apply_event(blocks,{'base':ids,'type':'order','ids':[ids[0],ids[0]]})
        added,selected=apply_event(blocks,{'base':ids,'type':'add','kind':'divider','index':1})
        self.assertEqual(added[1]['id'],selected)
        copied,selected=apply_event(added,{'base':[b['id'] for b in added],'type':'copy','id':ids[0]})
        self.assertNotEqual(selected,ids[0]);self.assertEqual(copied[1]['text'],'First')
        deleted,_=apply_event(copied,{'base':[b['id'] for b in copied],'type':'delete','id':selected})
        self.assertEqual(deleted,added)


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Requires isolated SQL fixture')
class PersistenceTests(unittest.TestCase):
    def test_modes_order_and_history_survive_reload_duplicate_archive(self):
        from crm_campaign_store import CampaignStore
        from tests.crm_db_fixture import connect
        from tests.test_crm import ADMIN
        store=CampaignStore(connect);doc=document()
        doc['blocks']=[block('text',text='one'),block('text',text='two')]
        row=store.save(ADMIN,'HTML persistence test',doc)
        doc['blocks'],_=apply_event(doc['blocks'],{'base':[b['id'] for b in doc['blocks']],'type':'order','ids':[b['id'] for b in doc['blocks']][::-1]})
        row=store.save(ADMIN,row['name'],doc,row['id'],row['version'])
        reloaded=store.draft(row['id']);self.assertEqual(reloaded['document'],doc)
        copy=store.duplicate(ADMIN,row['id']);self.assertEqual(copy['document']['custom_html'],HTML)
        store.archive(ADMIN,copy['id'],copy['version']);self.assertTrue(store.draft(copy['id'])['archived_at'])
        store.restore(ADMIN,copy['id'],store.draft(copy['id'])['version'])
        self.assertFalse(store.draft(copy['id'])['archived_at']);self.assertGreaterEqual(len(store.history(row['id'])),2)
        template=store.save_design(ADMIN,'HTML template verification',doc)
        snapshot=store.template_document(template)
        self.assertEqual(snapshot['custom_html'],HTML)
        self.assertEqual(snapshot['content_mode'],'HTML')
        self.assertEqual(snapshot['blocks'],doc['blocks'])

    def test_new_direct_editor_no_wizard_or_send_on_render(self):
        from streamlit.testing.v1 import AppTest
        from tests.test_crm_ui import SCRIPT
        with patch('crm_resend_marketing._send_admin_email',side_effect=AssertionError('No email')):
            at=AppTest.from_string(SCRIPT);at.session_state['route']='CRM Campaigns';at.run(timeout=20)
            next(b for b in at.button if b.label=='+ New Campaign').click().run(timeout=20)
            self.assertFalse(at.exception)
            self.assertEqual(at.session_state['campaign_editor']['name'],'Untitled campaign')
            self.assertEqual(at.session_state['campaign_editor']['document']['content_mode'],'HTML')
            self.assertEqual(next(t for t in at.text_input if t.label=='Subject').value,'')
            self.assertFalse(any(b.label in ('Next →','Test only','← Back') for b in at.button))
            self.assertTrue(any(b.label=='Save draft' for b in at.button))
            at.run();self.assertFalse(at.exception)
