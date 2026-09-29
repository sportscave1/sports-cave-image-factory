from copy import deepcopy
import os
import unittest
import uuid
from unittest.mock import patch
from crm_campaign_store import CampaignStore
from crm_campaign_recovery import save_checkpoint,restore,activate,browser_checkpoint,preference_key
from tests.crm_db_fixture import connect
from tests.test_crm import ADMIN
from tests.test_crm_modular_catalogue import catalogue_doc


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable SQL required')
class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.store=CampaignStore(connect)
        self.user={**ADMIN,'id':'recovery-'+uuid.uuid4().hex}
    def editor(self):
        doc=catalogue_doc();doc['send_timing']={'mode':'schedule','date':'2030-10-01','time':'07:30'}
        return {'name':'Recovery collector campaign','id':None,'version':None,'document':doc,'recovery_seed':uuid.uuid4().hex}
    def test_entire_draft_survives_complete_session_loss(self):
        editor=self.editor();editor['document']['content'].update(subject='Saved subject',preheader='Saved preview')
        section=editor['document']['middle_sections'][-1]
        section['settings']['cta']='Collector choice';section['settings']['columns']=1;section['settings']['display']['price']=False
        saved=save_checkpoint(self.store,self.user,editor)
        fresh_store=CampaignStore(connect);reopened=restore(fresh_store,self.user)
        self.assertEqual(reopened['id'],saved['id']);self.assertEqual(reopened['name'],editor['name'])
        self.assertEqual(reopened['document'],editor['document'])
    def test_lost_first_save_response_does_not_duplicate_draft(self):
        editor=self.editor();one=save_checkpoint(self.store,self.user,editor);two=save_checkpoint(self.store,self.user,editor)
        self.assertEqual(one['id'],two['id']);self.assertEqual(one['version'],two['version'])
    def test_explicit_id_beats_pointer_and_users_are_isolated(self):
        one=save_checkpoint(self.store,self.user,self.editor());two=save_checkpoint(self.store,self.user,self.editor())
        self.assertEqual(restore(self.store,self.user)['id'],two['id'])
        self.assertEqual(restore(self.store,self.user,one['id'])['id'],one['id'])
        self.assertIsNone(restore(self.store,{**self.user,'id':'another-'+uuid.uuid4().hex}))
        activate(self.store,self.user,None);self.assertIsNone(restore(self.store,self.user))
    def test_conflict_preserves_both_copies(self):
        original=save_checkpoint(self.store,self.user,self.editor());newer=deepcopy(original)
        newer['name']='Other tab';newer=save_checkpoint(self.store,self.user,newer)
        local=deepcopy(original);local['name']='My pending work'
        with self.assertRaisesRegex(ValueError,'newer draft'):save_checkpoint(self.store,self.user,local)
        self.assertEqual(local['name'],'My pending work');self.assertEqual(self.store.draft(original['id'])['name'],'Other tab')
        with self.assertRaisesRegex(ValueError,'newer saved draft'):
            browser_checkpoint(self.store,self.user,newer,{'scope':preference_key(self.user),'editor':local})
    def test_browser_copy_exact_revision_only(self):
        saved=save_checkpoint(self.store,self.user,self.editor());pending=deepcopy(saved);pending['name']='Browser pending'
        result=browser_checkpoint(self.store,self.user,saved,{'scope':preference_key(self.user),'editor':pending})
        self.assertEqual(result['name'],'Browser pending')
        with self.assertRaises(ValueError):browser_checkpoint(self.store,self.user,saved,{'scope':'wrong','editor':pending})
    def test_archived_or_production_campaign_cannot_restore_or_autosave(self):
        row=save_checkpoint(self.store,self.user,self.editor())
        self.store.archive(self.user,row['id'],row['version'])
        self.assertIsNone(restore(self.store,self.user))
        with self.assertRaisesRegex(ValueError,'no longer editable'):save_checkpoint(self.store,self.user,row)
    def test_failed_transaction_never_discards_editor(self):
        from crm_store import StoreUnavailable
        editor=self.editor();before=deepcopy(editor)
        with patch.object(self.store,'db',side_effect=StoreUnavailable('Unavailable')):
            with self.assertRaises(StoreUnavailable):save_checkpoint(self.store,self.user,editor)
        self.assertEqual(editor,before)

    def test_real_ui_autosaves_without_save_button_and_fresh_session_restores(self):
        from streamlit.testing.v1 import AppTest
        from tests.test_crm_ui import SCRIPT
        script=SCRIPT
        at=AppTest.from_string(script);at.session_state['fixture_user_id']=self.user['id'];at.session_state['route']='CRM Campaigns';at.run(timeout=20)
        self.assertIsNone(at.session_state['campaign_editor']['id'])
        next(w for w in at.text_input if w.label=='Campaign name').set_value('Autosaved UI').run(timeout=20)
        next(w for w in at.text_input if w.label=='Subject').set_value('Subject survives').run(timeout=20)
        self.assertFalse(at.exception)
        next(w for w in at.text_input if w.label=='Preview text').set_value('Preview survives').run(timeout=20)
        # Component events mutate this same document before the autosaving fragment exits.
        next(w for w in at.selectbox if w.label=='Segment').set_value('US').run(timeout=20)
        next(w for w in at.radio if w.label=='Send timing').set_value('Schedule').run(timeout=20)
        doc=catalogue_doc();doc['content'].update(subject='Subject survives',preheader='Preview survives')
        doc['market']='US'
        from crm_campaign_markets import audience
        doc['audience']=audience('US');doc['market_audience']=True
        doc['send_timing']={'mode':'schedule','date':'2030-10-01','time':'07:30'}
        from tests.test_crm_modular_catalogue import service,node,event
        doc['middle_sections'][-1]['products']=service().resolve([node(i)['id'] for i in range(1,6)])
        doc['middle_sections'][-1]['settings']['cta']='My saved CTA'
        doc['middle_sections'][-1]['settings']['columns']=1
        doc['middle_sections'][-1]['settings']['display']['price']=False
        event(doc,'add',kind='html')
        last=doc['middle_sections'][-1]['id']
        event(doc,'html',id=last,html='<p>Inserted template content</p>')
        event(doc,'visible',id=last,visible=False)
        event(doc,'order',ids=[v['id'] for v in doc['middle_sections']][::-1])
        at.session_state['campaign_editor']['document']=doc
        at.run(timeout=20)
        self.assertFalse(at.exception)
        expected=deepcopy(at.session_state['campaign_editor']['document'])
        self.assertEqual(expected['market'],'US')
        self.assertEqual(expected['send_timing']['mode'],'schedule')
        self.assertEqual(len(next(s for s in expected['middle_sections'] if s['type']=='catalogue')['products']),5)
        identity=at.session_state['campaign_editor']['id'];self.assertIsNotNone(identity)
        fresh=AppTest.from_string(script);fresh.session_state['fixture_user_id']=self.user['id'];fresh.session_state['route']='CRM Campaigns';fresh.run(timeout=20)
        self.assertFalse(fresh.exception)
        self.assertEqual(fresh.session_state['campaign_editor']['id'],identity)
        self.assertEqual(fresh.session_state['campaign_editor']['document']['content']['subject'],'Subject survives')

        self.assertEqual(fresh.session_state['campaign_editor']['document'],expected)

    def test_blur_and_debounce_merge_only_independent_fields(self):
        base=save_checkpoint(self.store,self.user,self.editor())
        native=deepcopy(base);native['name']='Native blur';native=save_checkpoint(self.store,self.user,native)
        pending=deepcopy(base);pending['document']['content']['subject']='Debounced subject'
        saved=browser_checkpoint(self.store,self.user,native,{'scope':preference_key(self.user),'base':base,'editor':pending})
        self.assertEqual(saved['name'],'Native blur')
        self.assertEqual(saved['document']['content']['subject'],'Debounced subject')
        conflicting=deepcopy(base);conflicting['name']='Different name'
        with self.assertRaisesRegex(ValueError,'conflicts'):
            browser_checkpoint(self.store,self.user,saved,{'scope':preference_key(self.user),'base':base,'editor':conflicting})
        self.assertEqual(self.store.draft(saved['id'])['name'],'Native blur')

    def test_terminal_campaigns_are_not_reopened(self):
        self.store.seed()
        template=self.store.q('SELECT template_id,version FROM crm_template_versions LIMIT 1',one=True)
        for status in ('SENT','CANCELLED','SENDING','SCHEDULED'):
            row=save_checkpoint(self.store,self.user,self.editor())
            self.store.q("INSERT INTO crm_campaigns(id,name,shopify_segment_id,template_id,template_version,status) VALUES(%s,%s,'fixture',%s,%s,%s)",
                         (row['id'],row['name'],template['template_id'],template['version'],status))
            self.assertIsNone(restore(self.store,self.user))
            with self.assertRaisesRegex(ValueError,'no longer editable'):save_checkpoint(self.store,self.user,row)

    def test_ui_save_failure_retains_work_and_blocks_draft_switch(self):
        from streamlit.testing.v1 import AppTest
        from tests.test_crm_ui import SCRIPT
        from crm_store import StoreUnavailable
        at=AppTest.from_string(SCRIPT);at.session_state['route']='CRM Campaigns';at.run(timeout=20)
        with patch('crm_campaign_recovery.save_checkpoint',side_effect=StoreUnavailable('Fixture persistence unavailable')):
            next(w for w in at.text_input if w.label=='Subject').set_value('Do not discard').run(timeout=20)
            next(b for b in at.button if b.label=='+ New campaign').click().run(timeout=20)
            self.assertEqual(at.session_state['campaign_editor']['document']['content']['subject'],'Do not discard')
            self.assertEqual(at.session_state['campaign_save_status'],'Save failed')
            self.assertTrue(any(b.label=='Save draft and leave' for b in at.button))
            self.assertFalse(at.exception)
