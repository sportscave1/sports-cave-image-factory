from copy import deepcopy
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
