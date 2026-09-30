"""Middle-section actions remain atomic and use the existing draft schema."""
from copy import deepcopy
import unittest
import os
from unittest.mock import patch
from crm_middle_sections import apply_event,middle_sections
from crm_campaign_content import validate_document,render_campaign
from tests.test_crm_image_sections import image_doc,event
from tests.test_crm import ADMIN


class SectionUXTests(unittest.TestCase):
    def test_delete_first_last_and_restore_exact_hidden_section(self):
        doc=image_doc();system=deepcopy(doc['html_sections'])
        event(doc,'visible',id='html-1',visible=False)
        original=deepcopy(doc['middle_sections']);first=original[0]
        event(doc,'remove',id='html-1',confirmed=True)
        validate_document(doc);self.assertEqual(doc['custom_html'],'')
        self.assertNotIn('A collector moment',render_campaign(doc)['html'])
        event(doc,'restore_section',section=first,position=0)
        self.assertEqual(doc['middle_sections'],original)
        for s in original:event(doc,'remove',id=s['id'],confirmed=True)
        validate_document(doc);self.assertEqual(middle_sections(doc),[])
        self.assertEqual(doc['html_sections'],system)
        event(doc,'restore_section',section=original[-1],position=1)
        self.assertEqual(doc['middle_sections'],[original[-1]])

    def test_structural_operation_atomically_preserves_latest_unsaved_html(self):
        doc=image_doc();ids=[s['id'] for s in doc['middle_sections']]
        event(doc,'order',ids=ids[::-1],edits={'html-1':'<p>Unsaved newest text</p>'})
        self.assertEqual(doc['middle_sections'][-1]['id'],'html-1')
        self.assertEqual(doc['middle_sections'][-1]['html'],'<p>Unsaved newest text</p>')
        self.assertIn('Unsaved newest text',render_campaign(doc)['html'])
        validate_document(doc)

    def test_add_during_delete_undo_window_does_not_reuse_html_number(self):
        doc=image_doc();original=deepcopy(doc['middle_sections'][0])
        event(doc,'remove',id='html-1',confirmed=True)
        event(doc,'add',kind='html',reserved_html_number=1)
        self.assertEqual(doc['middle_sections'][-1]['html_number'],2)
        event(doc,'restore_section',section=original,position=0)
        validate_document(doc)
        self.assertEqual(doc['middle_sections'][0],original)

    def test_bad_restore_and_stale_events_cannot_change_content(self):
        doc=image_doc();before=deepcopy(doc)
        for bad in ({'type':'restore_section','section':{'id':'header','type':'header'},'position':0},
                    {'type':'restore_section','section':doc['middle_sections'][0],'position':0},
                    {'type':'remove','id':'html-1'},
                    {'type':'order','ids':['header','footer']},
                    {'type':'visible','id':'html-1','visible':False,'edits':{'not-a-section':'oops'}}):
            with self.assertRaises(ValueError):apply_event(doc,{'base':[s['id'] for s in middle_sections(doc)],**bad})
            self.assertEqual(doc,before)


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable SQL required')
class SectionUXPersistenceTests(unittest.TestCase):
    def test_reorder_delete_restore_and_html_undo_use_normal_checkpoints(self):
        from crm_campaign_store import CampaignStore
        from crm_campaign_recovery import save_checkpoint
        from tests.crm_db_fixture import connect
        store=CampaignStore(connect);doc=image_doc()
        editor={'name':'Section UX fixture','document':doc}
        with patch('requests.sessions.Session.request',side_effect=AssertionError('No external I/O')):
            row=save_checkpoint(store,ADMIN,editor);editor.update(id=row['id'],version=row['version'])
            ids=[s['id'] for s in doc['middle_sections']]
            original=deepcopy(doc['middle_sections'][0])
            event(doc,'order',ids=ids[::-1],edits={'html-1':'<p>Newest text</p>'})
            event(doc,'visible',id='html-1',visible=False)
            row=save_checkpoint(store,ADMIN,editor);editor['version']=row['version']
            self.assertEqual(store.draft(row['id'])['document'],doc)
            snapshot=deepcopy(doc['middle_sections'][-1])
            event(doc,'remove',id='html-1',confirmed=True)
            row=save_checkpoint(store,ADMIN,editor);editor['version']=row['version']
            self.assertNotIn('html-1',[s['id'] for s in store.draft(row['id'])['document']['middle_sections']])
            event(doc,'restore_section',section=snapshot,position=1)
            event(doc,'html',id='html-1',html=original['html'])
            row=save_checkpoint(store,ADMIN,editor)
            loaded=store.draft(row['id'])['document'];self.assertEqual(loaded,doc)
            self.assertFalse(loaded['middle_sections'][-1]['visible'])
            self.assertEqual(store.duplicate(ADMIN,row['id'])['document']['middle_sections'],doc['middle_sections'])
            self.assertGreaterEqual(len(store.history(row['id'])),4)
