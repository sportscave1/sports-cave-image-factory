"""Image authoring through existing JSON, renderer and offline persistence."""
from copy import deepcopy
import os
import unittest
from unittest.mock import patch
from crm_middle_sections import apply_event, middle_sections, render_middle
from crm_campaign_content import validate_document, render_campaign
from crm_image_prompt import base_prompt, image_prompt
from tests.test_crm_campaign_sections import sectioned
from tests.test_crm import ADMIN
from tests.test_crm_resend_marketing import ENV

HTML = '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"><tr><td><img src="https://cdn.shopify.com/s/files/1/artwork.jpg" alt="Sports artwork" width="600" border="0" style="display:block;width:100%;max-width:600px;height:auto;border:0"></td></tr></table>'


def event(doc, action, **extra):
    apply_event(doc, {'type':action, 'base':[s['id'] for s in middle_sections(doc)], **extra})


def image_doc():
    doc=sectioned();event(doc,'add',kind='image')
    event(doc,'html',id=doc['middle_sections'][-1]['id'],html=HTML)
    return doc


class ImageTests(unittest.TestCase):
    def test_empty_add_edit_reorder_hide_remove_and_legacy_unchanged(self):
        doc=sectioned();before=deepcopy(doc)
        event(doc,'add',kind='image');image=doc['middle_sections'][-1]
        self.assertEqual(image['type'],'image');self.assertEqual(image['html'],'')
        self.assertEqual(doc['custom_html'],before['custom_html'])
        event(doc,'html',id=image['id'],html=HTML);validate_document(doc)
        event(doc,'order',ids=[image['id'],'html-1'])
        self.assertEqual(doc['middle_sections'][0]['html'],HTML)
        self.assertIn('artwork.jpg',render_campaign(doc)['html'])
        event(doc,'visible',id=image['id'],visible=False)
        self.assertNotIn('artwork.jpg',render_campaign(doc)['html'])
        event(doc,'remove',id=image['id'],confirmed=True)
        self.assertEqual(doc['html_sections'],before['html_sections'])
        self.assertEqual(doc['custom_html'],before['custom_html'])

    def test_image_only_counts_as_content_and_sanitizer_stays_authoritative(self):
        doc=image_doc();event(doc,'visible',id='html-1',visible=False)
        self.assertTrue(render_middle(doc)[2]['HTML content present'])
        for bad in ('data:image/png;base64,AAAA','http://example.test/image.jpg','javascript:alert(1)'):
            event(doc,'html',id=doc['middle_sections'][-1]['id'],html=HTML.replace('https://cdn.shopify.com/s/files/1/artwork.jpg',bad))
            rendered,_,checks=render_middle(doc)
            self.assertNotIn(bad,rendered)
            self.assertFalse(checks['Images use durable public JPEG/PNG URLs'])
        event(doc,'html',id=doc['middle_sections'][-1]['id'],html=HTML.replace(' alt="Sports artwork"',''))
        self.assertFalse(render_middle(doc)[2]['Image alt text complete'])

    def test_prompt_projection_has_no_customer_or_credentials_or_calls(self):
        doc=sectioned();doc.update(product={'title':'Collector artwork','token':'secret'},notes='private customer data')
        with patch('requests.sessions.Session.request',side_effect=AssertionError('No network')):
            prompt=image_prompt(doc)
        self.assertTrue(prompt.startswith(base_prompt()))
        self.assertIn('Collector artwork',prompt)
        self.assertNotIn('secret',prompt);self.assertNotIn('private customer',prompt)
        for text in ('STEP 6','Do not invent a Shopify URL.','320px','600px','Do not use placeholders.'):
            self.assertIn(text,prompt)


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable SQL required')
class ImagePersistenceTests(unittest.TestCase):
    def test_autosave_reload_manual_save_duplicate_history_and_version_restore(self):
        from crm_campaign_store import CampaignStore
        from crm_campaign_recovery import save_checkpoint
        from tests.crm_db_fixture import connect
        store=CampaignStore(connect);doc=image_doc()
        with patch('requests.sessions.Session.request',side_effect=AssertionError('No external I/O')):
            row=save_checkpoint(store,ADMIN,{'name':'Image fixture','document':doc})
            self.assertEqual(store.draft(row['id'])['document'],doc)
            saved=store.save(ADMIN,row['name'],doc,row['id'],row['version'],env=ENV)
            duplicate=store.duplicate(ADMIN,saved['id'])
            self.assertEqual(duplicate['document']['middle_sections'],doc['middle_sections'])
            changed=deepcopy(doc);event(changed,'visible',id=changed['middle_sections'][-1]['id'],visible=False)
            updated=store.save(ADMIN,row['name'],changed,saved['id'],saved['version'],env=ENV)
            history=store.history(row['id'])
            self.assertIn('content_changed',[h['action'] for h in history])
            # Restore the actual persisted prior snapshot through normal Save.
            prior=store.q("SELECT before_value FROM crm_campaign_history WHERE campaign_id=%s AND action='content_changed' ORDER BY version DESC LIMIT 1",(row['id'],),True)['before_value']['document']
            self.assertEqual(prior,doc)
            restored=store.save(ADMIN,row['name'],prior,updated['id'],updated['version'],env=ENV)
            self.assertEqual(store.draft(restored['id'])['document'],doc)
