"""Template display cache and copy semantics; no Shopify or mail transport."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import os
import unittest
import uuid
from unittest.mock import Mock,patch

from crm_campaign_content import new_document
from crm_campaign_library import library_rows,template_html,insert_saved_template,save_template
from crm_campaign_store import CampaignStore
from crm_middle_sections import middle_sections
from crm_template_cache import CACHE,invalidate,TTL
from tests.crm_db_fixture import connect
from tests.test_crm import ADMIN


class TemplateCacheTests(unittest.TestCase):
    def setUp(self):invalidate()
    def tearDown(self):invalidate()
    def row(self):
        return {'id':'fixture','name':'Trust Icons','version':1,'kind':'Campaign',
                'content':{'format':'campaign_blocks_v1'}}
    def test_metadata_shared_sorted_and_copied_without_bodies(self):
        s=Mock(connect=object());s.html_library.return_value=[self.row(),{**self.row(),'id':'a','name':'Alpha'}]
        self.assertEqual([r['name'] for r in library_rows(s)],['Alpha','Trust Icons'])
        library_rows(s)[0]['name']='mutated'
        self.assertEqual(library_rows(s)[0]['name'],'Alpha')
        s.html_library.assert_called_once_with(metadata=True);s.get.assert_not_called()
    def test_ttl_and_connections_isolated(self):
        s=Mock(connect=object());s.html_library.return_value=[]
        with patch.object(CACHE,'clock',return_value=1):library_rows(s);library_rows(s)
        with patch.object(CACHE,'clock',return_value=TTL+2):library_rows(s)
        self.assertEqual(s.html_library.call_count,2)
        other=Mock(connect=object());other.html_library.return_value=[];library_rows(other)
        other.html_library.assert_called_once()
    def test_concurrent_misses_query_once(self):
        s=Mock(connect=object());s.html_library.return_value=[self.row()]
        with ThreadPoolExecutor(8) as pool:list(pool.map(lambda _:library_rows(s),range(20)))
        s.html_library.assert_called_once()
    def test_selected_body_cache_and_failure_preserves_document(self):
        s=Mock(connect=object());meta=self.row();doc=new_document();doc.update(content_mode='HTML',custom_html='<p>source</p>')
        s.html_library.return_value=[meta];s.get.return_value={**meta,'content':{'format':'campaign_blocks_v1','document':doc}}
        s.template_document.side_effect=lambda r:deepcopy(r['content']['document'])
        self.assertEqual(template_html(s,meta),'<p>source</p>');template_html(s,meta)
        s.get.assert_called_once_with('templates','fixture')
        target=deepcopy(doc);insert_saved_template(s,target,'fixture',1)
        self.assertEqual(s.get.call_count,1)
        before=deepcopy(target)
        with self.assertRaises(ValueError):insert_saved_template(s,target,'missing',1)
        self.assertEqual(target,before)
    def test_failure_not_cached(self):
        from crm_store import StoreUnavailable
        s=Mock(connect=object());s.html_library.side_effect=[StoreUnavailable('Unavailable'),[]]
        with self.assertRaises(StoreUnavailable):library_rows(s)
        self.assertEqual(library_rows(s),[]);self.assertEqual(s.html_library.call_count,2)
    def test_success_and_cancel_clear_dialog_fields_but_failure_retains_work(self):
        from crm_campaign_library import finish_action
        state={'name':'unfinished','html':'<p>draft</p>'};dialog=Mock()
        with patch('crm_campaign_library.st') as ui:
            ui.session_state=state
            finish_action('composer',None,dialog,('name','html'))
            self.assertNotIn('name',state);self.assertNotIn('html',state)
            ui.rerun.assert_called_once_with(scope='composer')
            ui.rerun.reset_mock();state.update(name='keep',html='<p>keep</p>')
            finish_action('composer',Mock(side_effect=ValueError('Conflict')),dialog,('name','html'))
            self.assertEqual(state['name'],'keep');self.assertEqual(state['html'],'<p>keep</p>')
            ui.rerun.assert_not_called()
    def test_defaults_list_does_not_load_default_bodies(self):
        from crm_brand_template_ui import brand_templates_settings
        s=Mock();s.email_default.side_effect=AssertionError('No edit requested')
        with patch('crm_brand_template_ui.st') as ui:
            action=Mock();action.button.return_value=False;ui.columns.return_value=(Mock(),action)
            ui.session_state={};brand_templates_settings(s,ADMIN,{})
        s.email_defaults.assert_not_called();s.render_settings.assert_not_called();s.email_default.assert_not_called()


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable SQL required')
class TemplateLifecycleTests(unittest.TestCase):
    def setUp(self):self.store=CampaignStore(connect);invalidate();self.ids=[]
    def tearDown(self):
        for identity in self.ids:
            row=self.store.get('templates',identity)
            if not row['archived_at']:self.store.archive_design(ADMIN,identity,row['version'])
        invalidate()
    def test_create_rename_edit_archive_invalidates_caches_and_preserves_copies(self):
        library_rows(self.store)
        row=save_template(self.store,ADMIN,'Picker '+uuid.uuid4().hex,'<p>Original</p>');self.ids.append(row['id'])
        meta=next(r for r in library_rows(self.store) if r['id']==row['id'])
        doc=new_document();doc.update(content_mode='HTML',custom_html='')
        insert_saved_template(self.store,doc,row['id'],row['version'])
        self.assertEqual(middle_sections(doc)[0]['html'],'<p>Original</p>')
        new=save_template(self.store,ADMIN,'Renamed '+row['name'],'<p>Changed</p>',meta)
        latest=next(r for r in library_rows(self.store) if r['id']==row['id'])
        self.assertEqual(latest['name'],new['name']);self.assertEqual(template_html(self.store,latest),'<p>Changed</p>')
        self.assertEqual(middle_sections(doc)[0]['html'],'<p>Original</p>')
        doc['middle_sections'][0]['html']='<p>Campaign only</p>'
        self.assertEqual(template_html(self.store,latest),'<p>Changed</p>')
        self.store.archive_design(ADMIN,row['id'],new['version'])
        self.assertFalse(any(r['id']==row['id'] for r in library_rows(self.store)))
        self.assertEqual(middle_sections(doc)[0]['html'],'<p>Campaign only</p>')
        with self.assertRaises(ValueError):insert_saved_template(self.store,doc,row['id'],new['version'])
    def test_version_conflict_cannot_load_a_stale_body(self):
        row=save_template(self.store,ADMIN,'Version '+uuid.uuid4().hex,'<p>old</p>');self.ids.append(row['id'])
        meta=next(r for r in library_rows(self.store) if r['id']==row['id'])
        template_html(self.store,meta)
        save_template(self.store,ADMIN,row['name'],'<p>new</p>',meta)
        with self.assertRaises(ValueError):template_html(self.store,meta)

    def test_save_and_use_target_composer_not_workspace(self):
        from crm_campaign_library import COMPOSER_TARGET
        if COMPOSER_TARGET is None:self.skipTest('Named fragment targeting requires newer Streamlit; native fallback is tested by Email navigation.')
        from streamlit.testing.v1 import AppTest
        from tests.test_crm_ui import SCRIPT
        row=save_template(self.store,ADMIN,'Scoped '+uuid.uuid4().hex,'<p>Scoped</p>');self.ids.append(row['id'])
        at=AppTest.from_string(SCRIPT.replace("'role':'worker'","'role':'admin'"))
        at.session_state['route']='CRM Campaigns';at.run(timeout=20)
        panel=at.session_state['campaign_edit_key']+'panel'
        at.session_state[panel]='Templates';at.run(timeout=20)
        # AppTest's default click executes an app run; explicitly keep the tab open
        # for that setup. Named callback reruns then exercise the real fragment.
        at.session_state[panel]='Templates'
        at.button(key='edit_'+str(row['id'])).click().run(timeout=20)
        self.assertFalse(at.exception)
        with (patch.object(CampaignStore,'list_drafts',side_effect=AssertionError('History reloaded')),
              patch.object(CampaignStore,'render_settings',side_effect=AssertionError('Workspace reloaded')),
              patch('crm_segment_counts.COUNTS.display',side_effect=AssertionError('Counts reloaded'))):
            at.session_state[panel]='Templates'
            next(b for b in at.button if b.label=='Save template').click().run(timeout=20)
            self.assertFalse(at.exception)
            at.session_state[panel]='Templates'
            at.button(key='use_'+str(row['id'])).click().run(timeout=20)
            self.assertFalse(at.exception)
        self.assertIn('Scoped',middle_sections(at.session_state['campaign_editor']['document'])[0]['html'])
