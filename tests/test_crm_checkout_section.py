from copy import deepcopy
import os
import unittest
from unittest.mock import Mock
from crm_checkout_section import insert,editable
from crm_checkout_styles import default_html,MARKER
from crm_middle_sections import apply_event,commit_middle,render_middle
from crm_abandoned_checkout import apply_template,hydrate,context,publication_document
from crm_campaign_content import validate_document,render_campaign
from crm_campaign_sections import with_email_defaults
from tests.test_crm_simple_editor import document
from tests.test_crm_abandoned_checkout import checkout
from tests.test_crm_send_flow import CFG


class CheckoutSectionTests(unittest.TestCase):
    def setUp(self):
        self.store=Mock();self.store.state.return_value={'revision':2,'html':default_html()}
        self.doc=document();self.doc.update(content_mode='HTML');commit_middle(self.doc,[])

    def event(self,kind,**extra):
        apply_event(self.doc,dict(type=kind,base=[s['id'] for s in self.doc['middle_sections']],**extra))

    def test_latest_master_independent_copies_and_drafts(self):
        insert(self.store,self.doc);first=deepcopy(self.doc)
        self.store.state.return_value['html']=default_html().replace('Still thinking it over?','New master copy')
        other=deepcopy(first);insert(self.store,other)
        self.assertEqual(first,self.doc);self.assertIn('New master copy',other['middle_sections'][-1]['html'])
        section=self.doc['middle_sections'][0]
        self.event('html',id=section['id'],html=section['html'].replace('Still thinking it over?','My own draft'))
        self.assertNotIn('My own draft',self.store.state.return_value['html'])
        self.assertEqual(section['name'],'Abandoned Checkout');validate_document(self.doc)
        self.store.db.assert_not_called()

    def test_personalized_preview_and_safe_publication(self):
        insert(self.store,self.doc);original=deepcopy(self.doc)
        data=context(checkout(items=2),edition_reader=lambda **kw:[])
        rendered=render_campaign(hydrate(self.doc,data),CFG)['html']
        self.assertNotIn(MARKER,rendered);self.assertIn(data['recovery_url'],rendered)
        self.assertEqual(rendered.count('YOUR COLLECTION AWAITS'),1)
        self.assertEqual(self.doc,original)
        publication_document(self.doc,'abandoned')
        with self.assertRaises(ValueError):publication_document(self.doc,'welcome')
        with self.assertRaisesRegex(ValueError,'checkout recovery automation'):render_middle(self.doc)
        from crm_checkout_preview import document as preview,sample
        self.assertFalse(preview(self.doc,sample(self.doc),test=True)[1])
        self.assertNotIn(MARKER,render_campaign(preview(self.doc,sample(self.doc),test=True)[0],CFG)['html'])

    def test_rename_duplicate_reorder_visibility_delete_roundtrip(self):
        insert(self.store,self.doc);identity=self.doc['middle_sections'][0]['id']
        self.event('rename',id=identity,name='My reminder');self.event('duplicate',id=identity)
        sections=self.doc['middle_sections'];self.assertNotEqual(sections[0]['id'],sections[1]['id'])
        with self.assertRaises(ValueError):publication_document(self.doc,'abandoned')
        self.event('visible',id=sections[1]['id'],visible=False)
        publication_document(self.doc,'abandoned')
        self.event('order',ids=[s['id'] for s in reversed(sections)])
        self.event('remove',id=identity,confirmed=True);validate_document(self.doc)
        self.assertEqual(self.doc['middle_sections'][0]['name'],'My reminder')

    def test_existing_split_copy_is_lossless_and_original_untouched(self):
        apply_template(self.doc);original=deepcopy(self.doc);upgraded=editable(self.doc)
        self.assertEqual(len(upgraded['middle_sections']),1)
        self.assertEqual(self.doc,original)
        data=context(checkout(),edition_reader=lambda **kw:[])
        self.assertEqual(render_campaign(hydrate(original,data),CFG)['html'],render_campaign(hydrate(upgraded,data),CFG)['html'])
        from crm_checkout_migration import migrate
        self.assertEqual(migrate(upgraded),upgraded)

    def test_defaults_are_copies_not_live_references(self):
        cfg={'email_defaults':{'header':'<p>First header</p>','footer':'<p>First footer</p>'}}
        doc=with_email_defaults(self.doc,cfg);before=deepcopy(doc)
        cfg['email_defaults']['header']='<p>New master</p>'
        self.assertEqual(with_email_defaults(doc,cfg),before)

    def test_pending_edits_survive_insertion_and_failure_is_atomic(self):
        commit_middle(self.doc,[dict(id='one',type='html',html_number=1,visible=True,html='<p>Old</p>')])
        insert(self.store,self.doc,{'base':['one'],'edits':{'one':'<p>Unsaved</p>'}})
        self.assertEqual(self.doc['middle_sections'][0]['html'],'<p>Unsaved</p>')
        before=deepcopy(self.doc);self.store.state.return_value['html']='Broken'
        with self.assertRaises(ValueError):insert(self.store,self.doc)
        self.assertEqual(before,self.doc)


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class CheckoutCopyPersistenceTests(unittest.TestCase):
    def test_campaign_and_individual_steps_reopen_independently(self):
        from crm_automation_store import AutomationStore
        from crm_campaign_store import CampaignStore
        from crm_checkout_template import load,save,KEY
        from tests.crm_db_fixture import connect
        from tests.test_crm import ADMIN
        store=AutomationStore(connect);previous=store.state(KEY)
        try:
            master=load(store);source=master['html'].replace('Still thinking it over?','Master at creation')
            saved=save(store,ADMIN,source,master['revision'])
            row=store.create(ADMIN,'abandoned','Independent checkout templates')
            self.assertEqual(len(row['config']['draft']['emails']),3)
            flow=deepcopy(row['config']['draft']);first=flow['emails'][0]['document']
            first['middle_sections'][0]['html']=source.replace('Master at creation','Email one only')
            commit_middle(first,first['middle_sections'])
            updated=store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision'])
            save(store,ADMIN,source.replace('Master at creation','Future master'),saved['revision'])
            reopened=AutomationStore(connect).flow(row['id'])
            docs=[s['document'] for s in reopened['config']['draft']['emails']]
            self.assertIn('Email one only',docs[0]['custom_html'])
            self.assertIn('Master at creation',docs[1]['custom_html'])
            self.assertEqual(reopened['config']['published_version'],0)
            self.assertEqual(reopened['steps'],[])
            campaign=CampaignStore(connect);doc=document();commit_middle(doc,[]);insert(campaign,doc)
            row=campaign.save(ADMIN,'Checkout draft only',doc)
            self.assertEqual(CampaignStore(connect).draft(row['id'])['document'],doc)
            self.assertIn('Future master',doc['custom_html'])
        finally:
            if previous:store.set_state(KEY,previous)
            else:store.q('DELETE FROM crm_runtime_state WHERE key=%s',(KEY,))
