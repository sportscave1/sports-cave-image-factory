"""One-canvas UX and narrowly authorized draft deletion, isolated SQL only."""
from copy import deepcopy
import os
import unittest
import uuid
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from crm_campaign_content import new_document,render_campaign
from crm_html_workspace import html_document
from crm_email_blocks import block
from tests.test_crm import ADMIN,WORKER
from tests.test_crm_simple_editor import document,HTML


class CanvasTests(unittest.TestCase):
    def test_original_html_and_blocks_are_preserved(self):
        doc=document();doc['blocks']=[block('text',text='Retained dormant blocks')]
        self.assertEqual(html_document(doc),doc)
        old=new_document();old['blocks']=[block('text',text='Existing design')]
        converted=html_document(old)
        self.assertEqual(old['blocks'],converted['blocks'])
        self.assertIn('Existing design',converted['custom_html'])
        self.assertNotIn('custom_html',old)
        self.assertIn('Unsubscribe',render_campaign(converted)['html'])


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Requires disposable SQL fixture')
class SqlWorkspaceTests(unittest.TestCase):
    def setUp(self):
        from tests.crm_db_fixture import connect
        from crm_campaign_store import CampaignStore
        self.store=CampaignStore(connect)

    def draft(self):return self.store.save(ADMIN,'Delete fixture '+uuid.uuid4().hex[:8],document())

    def test_delete_requires_confirmation_name_version_permission(self):
        row=self.draft()
        for args in ({},{'confirmed':True,'confirmed_name':'wrong name'},{'confirmed':False,'confirmed_name':row['name']}):
            with self.assertRaises(ValueError):self.store.delete_draft(ADMIN,row['id'],row['version'],**args)
        with self.assertRaises(PermissionError):self.store.delete_draft(WORKER,row['id'],row['version'],confirmed=True,confirmed_name=row['name'])
        self.assertEqual(self.store.draft(row['id'])['name'],row['name'])

    def test_delete_only_target_and_its_authoring_history_and_audits(self):
        row=self.draft();other=self.draft()
        with patch('activity_log.record_activity_log',return_value={'id':1}) as audit:
            result=self.store.delete_draft(ADMIN,row['id'],row['version'],confirmed=True,confirmed_name=row['name'])
        self.assertTrue(result['deleted']);audit.assert_called_once()
        self.assertEqual(audit.call_args.kwargs['entity_id'],str(row['id']))
        self.assertGreaterEqual(len(self.store.history(row['id'])),2)
        self.assertTrue(self.store.draft(row['id'])['archived_at'])
        self.assertEqual(self.store.draft(other['id'])['name'],other['name'])
        self.assertTrue(self.store.history(other['id']))

    def test_test_history_blocks_deletion_even_if_status_is_draft(self):
        row=self.draft()
        self.store.q("INSERT INTO crm_internal_tests(id,campaign_id,campaign_version,render_hash,recipient,sender,actor,status) VALUES(%s,%s,1,'hash','test@example.com','sender@example.com','fixture','FAILED')",(str(uuid.uuid4()),row['id']))
        with self.assertRaisesRegex(ValueError,'history'):self.store.delete_draft(ADMIN,row['id'],row['version'],confirmed=True,confirmed_name=row['name'])
        self.assertTrue(self.store.draft(row['id']))

    def test_archived_and_tested_and_stale_drafts_cannot_be_deleted(self):
        for status in ('ARCHIVED','TESTED','TEST_READY'):
            row=self.draft();self.store.q('UPDATE crm_campaign_drafts SET status=%s WHERE id=%s',(status,row['id']))
            with self.assertRaises(ValueError):self.store.delete_draft(ADMIN,row['id'],row['version'],confirmed=True,confirmed_name=row['name'])
        row=self.draft();updated=self.store.save(ADMIN,row['name'],row['document'],row['id'],row['version'])
        with self.assertRaises(ValueError):self.store.delete_draft(ADMIN,row['id'],row['version'],confirmed=True,confirmed_name=row['name'])
        self.assertEqual(self.store.draft(row['id'])['version'],updated['version'])

    def test_flow_save_forks_only_selected_email_and_keeps_inactive(self):
        from crm_flow_editor import save_flow_email
        self.store.seed();flow=next(f for f in self.store.list('automations') if f['status']=='DRAFT')
        index=next(i for i,s in enumerate(flow['steps']) if s['type']=='send')
        old=self.store.q('SELECT * FROM crm_templates WHERE template_key=%s',(flow['steps'][index]['template'],),True)
        with patch('crm_service.audit'):
            updated,saved=save_flow_email(self.store,ADMIN,flow,index,document(),old['version'])
        self.assertEqual(updated['status'],'DRAFT')
        self.assertEqual(self.store.template_document(saved)['custom_html'],HTML)
        self.assertEqual(self.store.q('SELECT content FROM crm_templates WHERE id=%s',(old['id'],),True)['content'],old['content'])
        expected=deepcopy(flow['steps']);expected[index]['template']=saved['template_key']
        self.assertEqual(updated['steps'],expected)
        with self.assertRaises(ValueError):save_flow_email(self.store,ADMIN,flow,index,document(),old['version'])

    def app(self):
        from tests.test_crm_ui import SCRIPT
        at=AppTest.from_string(SCRIPT);at.session_state['route']='CRM Campaigns';return at.run(timeout=20)

    def test_blank_new_canvas_no_blocks_and_preview_roundtrip(self):
        at=self.app()
        self.assertFalse(at.exception)
        doc=at.session_state['campaign_editor']['document']
        self.assertEqual(doc['custom_html'],'');self.assertEqual(doc['content']['subject'],'');self.assertEqual(doc['content']['preheader'],'')
        self.assertFalse(any(r.label=='Content mode' for r in at.radio))
        self.assertFalse(any('Blocks' in r.options for r in at.radio))
        from crm_middle_sections import apply_event
        apply_event(doc, {'type':'html','base':['html-1'],'id':'html-1','html':HTML})
        at.run(timeout=20)
        self.assertFalse(at.exception)
        self.assertEqual([t.label for t in at.tabs],['Settings','Editor','Templates'])
        iframe=next(e for e in at.get('iframe') if 'A collector moment' in e.proto.srcdoc)
        self.assertIn('Unsubscribe',iframe.proto.srcdoc)
        next(b for b in at.button if str(b.key).endswith('device_Mobile')).click().run()
        self.assertEqual(at.session_state['campaign_editor']['document']['custom_html'],HTML)
        self.assertFalse(at.exception)

    def test_delete_confirmation_is_explicit_and_cancel_retains_draft(self):
        at=self.app()
        next(b for b in at.button if b.label=='Save draft').click().run(timeout=20)
        identity=at.session_state['campaign_editor']['id']
        at.run(timeout=20)
        next(b for b in at.button if b.key=='recent_delete_'+str(identity)).click().run(timeout=20)
        self.assertTrue(any('audit history are retained' in w.value for w in at.warning))
        self.assertTrue(any('Untitled campaign' in m.value for m in at.markdown))
        self.assertTrue(self.store.draft(identity))
        next(b for b in at.button if b.label=='Cancel').click().run(timeout=20)
        self.assertTrue(self.store.draft(identity));self.assertFalse(at.exception)


    def test_empty_compose_creates_no_draft_and_initial_reads_are_bounded(self):
        from crm_campaign_store import CampaignStore
        before=self.store.q('SELECT count(*) AS n FROM crm_campaign_drafts',one=True)['n']
        with patch.object(CampaignStore,'history',side_effect=AssertionError('History must be lazy')),patch.object(CampaignStore,'templates',side_effect=AssertionError('Templates must be lazy')),patch('crm_campaign_page.selection_page',side_effect=AssertionError('Eligibility must be explicit')):
            at=self.app();at.run()
        self.assertFalse(at.exception)
        self.assertIsNone(at.session_state['campaign_editor']['id'])
        self.assertEqual(before,self.store.q('SELECT count(*) AS n FROM crm_campaign_drafts',one=True)['n'])
        labels={b.label for b in at.button}
        self.assertTrue(labels.isdisjoint({'Campaigns','Flows','Refresh','+ New Campaign','Preview'}))
        self.assertFalse(any(t.label=='Search campaigns' for t in at.text_input))
        self.assertTrue(any('Recent campaigns' in m.value for m in at.markdown))
        from crm_middle_sections import apply_event
        apply_event(at.session_state['campaign_editor']['document'], {'type':'html','base':['html-1'],'id':'html-1','html':HTML})
        next(t for t in at.text_input if t.label=='Subject').set_value('Saved subject')
        next(t for t in at.text_input if t.label=='Preview text').set_value('Saved preview')
        next(b for b in at.button if b.label=='Save draft').click().run(timeout=20)
        self.assertFalse(at.exception)
        row=self.store.draft(at.session_state['campaign_editor']['id'])
        self.assertEqual(row['document']['custom_html'],HTML)
        self.assertEqual(row['document']['content']['subject'],'Saved subject')
        self.assertEqual(row['document']['content']['preheader'],'Saved preview')
        self.assertTrue(any('A collector moment' in e.proto.srcdoc for e in at.get('iframe')))
        next(b for b in at.button if b.label=='+ New campaign').click().run(timeout=20)
        self.assertIsNone(at.session_state['campaign_editor']['id'])
        self.assertEqual(at.session_state['campaign_editor']['document']['custom_html'],'')
        self.assertEqual(before+1,self.store.q('SELECT count(*) AS n FROM crm_campaign_drafts',one=True)['n'])

    def test_recent_open_uses_same_editor_and_protects_unsaved_compose(self):
        saved=self.draft();at=self.app()
        next(t for t in at.text_input if t.label=='Subject').set_value('Keep this local edit').run()
        next(b for b in at.button if b.key=='recent_open_'+str(saved['id'])).click().run()
        self.assertTrue(self.store.q("SELECT id FROM crm_campaign_drafts WHERE document->'content'->>'subject'=%s",('Keep this local edit',)))
        self.assertFalse(at.exception)
        self.assertEqual(str(at.session_state['campaign_editor']['id']),str(saved['id']))
        self.assertEqual(at.session_state['campaign_editor']['document']['custom_html'],HTML)
        at.run()
        self.assertEqual(at.session_state['campaign_editor']['document']['custom_html'],HTML)
