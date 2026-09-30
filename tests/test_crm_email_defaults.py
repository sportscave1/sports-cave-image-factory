"""Singleton defaults: real disposable SQL, synthetic content, no external writes."""
from tests.crm_fixtures import TEST_UNSUBSCRIBE_URL
from copy import deepcopy
import json
import os
import unittest
import uuid
from unittest.mock import Mock,patch
from crm_campaign_store import CampaignStore
from crm_campaign_content import settings,render_campaign
from crm_brand_templates import DEFAULT_KEYS,DEFAULT_KEY,FORMAT,_CACHE
from crm_campaign_footer import DEFAULT_FOOTER
from tests.crm_db_fixture import connect
from tests.test_crm import ADMIN,WORKER,config
from tests.test_crm_campaign_sections import sectioned
from tests.test_crm_resend_marketing import ENV

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable SQL required')
class EmailDefaultsTests(unittest.TestCase):
    def setUp(self):
        from tests.crm_fixtures import TestRecipientShop
        customer_patch=patch('crm_test_recipient.Shopify',return_value=TestRecipientShop())
        customer_patch.start();self.addCleanup(customer_patch.stop)
        self.store=CampaignStore(connect)
        self.reset()
        self.cfg=settings(ENV)
    def reset(self):
        keys=[*DEFAULT_KEYS.values(),DEFAULT_KEY]
        self.store.q('DELETE FROM crm_settings_history WHERE key=ANY(%s)',(keys,))
        self.store.q('DELETE FROM crm_workspace_settings WHERE key=ANY(%s)',(keys,))
        _CACHE.clear()
    def tearDown(self):self.reset()
    def change(self,kind,html):
        row=self.store.email_defaults(self.cfg)[kind]
        return self.store.save_email_default(ADMIN,kind,html,row['version'])

    def test_adopts_exact_active_sources_retains_old_variants(self):
        registry={}
        for kind,source in [('header',' \r\n<h1>Active header</h1>\n'),('footer',DEFAULT_FOOTER+'\n  ')]:
            row=self.store.q("INSERT INTO crm_templates(template_key,name,kind,content) VALUES(%s,%s,'Campaign',%s::jsonb) RETURNING *",('fixture-'+uuid.uuid4().hex,'Active '+kind,json.dumps({'format':FORMAT,'section':kind,'html':source})),True)
            registry[kind]=str(row['id'])
        self.store.q("INSERT INTO crm_workspace_settings(key,value,updated_by) VALUES(%s,%s::jsonb,'fixture')",(DEFAULT_KEY,json.dumps(registry)))
        rows=self.store.email_defaults(self.cfg)
        for kind in registry:
            old=self.store.get('templates',registry[kind])
            self.assertEqual(rows[kind]['value']['html'],old['content']['html'])
            self.assertIsNone(old['archived_at'])
        self.assertEqual(self.store.q('SELECT count(*) n FROM crm_workspace_settings WHERE key=ANY(%s)',(list(DEFAULT_KEYS.values()),),True)['n'],2)

    def test_edits_update_draft_render_not_draft_or_historical_snapshot(self):
        doc=sectioned();row=self.store.save(ADMIN,'Global defaults draft',doc,env=ENV)
        cfg=self.store.render_settings(ENV)
        snapshot=deepcopy(cfg)
        old_render=render_campaign(doc,snapshot)
        history=self.store.q('SELECT * FROM crm_campaign_history WHERE campaign_id=%s',(row['id'],))
        self.change('header','<p>Latest header</p>')
        self.change('footer',DEFAULT_FOOTER.replace('Website','Latest website'))
        current=render_campaign(doc,self.store.render_settings(ENV))
        self.assertIn('Latest header',current['html']);self.assertIn('Latest website',current['html'])
        self.assertEqual(render_campaign(doc,snapshot),old_render)
        self.assertEqual(self.store.draft(row['id'])['document'],doc)
        self.assertEqual(self.store.q('SELECT * FROM crm_campaign_history WHERE campaign_id=%s',(row['id'],)),history)

    def test_persisted_delivery_snapshot_is_not_rewritten(self):
        doc=sectioned();cfg=self.store.render_settings(ENV)
        snapshot={'format':'campaign_delivery_v1','document':doc,'render_settings':cfg}
        row=self.store.q("INSERT INTO crm_templates(template_key,name,kind,content) VALUES(%s,'Sent snapshot','Campaign',%s::jsonb) RETURNING *",('snapshot-'+uuid.uuid4().hex,json.dumps(snapshot)),True)
        url=config(False).unsubscribe_url(str(uuid.uuid4()))
        before=render_campaign(doc,cfg,unsubscribe_url=url,production=True)
        self.change('header','<p>Future emails only</p>')
        loaded=self.store.get('templates',row['id'])
        self.assertEqual(loaded,row)
        self.assertEqual(render_campaign(loaded['content']['document'],loaded['content']['render_settings'],unsubscribe_url=url,production=True),before)

    def test_reload_singletons_concurrency_permissions_and_history(self):
        rows=self.store.email_defaults(self.cfg)
        self.change('header','<h1>Persistent</h1>')
        self.assertEqual(CampaignStore(connect).default_sections(self.cfg)['header'],'<h1>Persistent</h1>')
        with self.assertRaises(ValueError):self.store.save_email_default(ADMIN,'header','<p>Stale</p>',rows['header']['version'])
        with self.assertRaises(PermissionError):self.store.save_email_default(WORKER,'header','<p>Denied</p>',2)
        self.assertEqual(self.store.q('SELECT count(*) n FROM crm_workspace_settings WHERE key=ANY(%s)',(list(DEFAULT_KEYS.values()),),True)['n'],2)
        self.assertEqual(len(self.store.q('SELECT * FROM crm_settings_history WHERE key=%s',(DEFAULT_KEYS['header'],))),2)
        for method in ('save_section_template','set_section_default','delete_section_template'):
            with self.assertRaises(ValueError):getattr(self.store,method)()

    def test_footer_save_blocks_missing_hidden_and_unsafe_markup(self):
        self.store.email_defaults(self.cfg)
        for bad in ['<p>Missing</p>','<a href="{{UNSUBSCRIBE_URL}}" style="display:none">Unsubscribe</a>',DEFAULT_FOOTER+'<script>bad()</script>']:
            with self.assertRaises(ValueError):self.change('footer',bad)
        with self.assertRaises(ValueError):self.change('header','<iframe src="https://bad.test"></iframe>')
        self.assertEqual(self.store.default_sections(self.cfg)['footer'],DEFAULT_FOOTER)

    def test_placeholder_sources_safe_test_and_production(self):
        self.change('footer','<p>{{BUSINESS_NAME}}</p><a href="{{UNSUBSCRIBE_URL}}">Unsubscribe</a>')
        env={**ENV,'CRM_PUBLIC_BASE_URL':'https://hooks.example.test'}
        cfg=self.store.render_settings(env);doc=sectioned()
        preview=render_campaign(doc,cfg)
        self.assertIn('/crm/unsubscribe/test',preview['html']);self.assertNotIn('?token=',preview['html'])
        url=config(False).unsubscribe_url(str(uuid.uuid4()))
        live=render_campaign(doc,cfg,unsubscribe_url=url,production=True)
        self.assertIn(url,live['html']);self.assertNotIn('{{UNSUBSCRIBE_URL}}',live['html'])
        self.assertIn('{{UNSUBSCRIBE_URL}}',self.store.default_sections(cfg)['footer'])
        self.assertFalse(config(False).enabled)
        with self.assertRaises(ValueError):render_campaign(doc,cfg,production=True)

    def test_cache_revision_and_no_external_calls(self):
        with patch('requests.sessions.Session.request',side_effect=AssertionError('External API forbidden')):
            self.store.default_sections(self.cfg)
            with patch.object(self.store,'q',wraps=self.store.q) as reads:
                self.store.default_sections(self.cfg)
                self.assertEqual(reads.call_count,1)
                self.assertIn('SELECT key,version',reads.call_args.args[0])
            self.change('header','<p>Invalidates immediately</p>')
            self.assertEqual(self.store.default_sections(self.cfg)['header'],'<p>Invalidates immediately</p>')

    def test_mocked_test_payload_uses_latest_defaults_and_native_link(self):
        row=self.store.save(ADMIN,'Default test snapshot',sectioned(),env=ENV)
        self.change('header','<p>Latest test header</p>')
        wire=Mock();wire.post.return_value=Mock(status_code=200,json=lambda:{'id':str(uuid.uuid4())})
        env={**ENV,'CRM_PUBLIC_BASE_URL':'https://hooks.example.test'}
        with patch('crm_resend_marketing._audit',return_value=True),patch('requests.sessions.Session.request',side_effect=AssertionError('No external network')):
            self.store.test_campaign(ADMIN,row['id'],row['version'],recipient='manual@example.test',confirmed=True,operation_id=str(uuid.uuid4()),env=env,session=wire)
        payload=wire.post.call_args.kwargs['json']
        self.assertIn('Latest test header',payload['html']);self.assertIn(TEST_UNSUBSCRIBE_URL,payload['html'])
        self.assertEqual(payload['html'],render_campaign(row['document'],self.store.render_settings(env),production=True,test_tracking=True,unsubscribe_url=TEST_UNSUBSCRIBE_URL)['html'])

    def test_ui_has_only_global_edit_actions_and_preserves_body(self):
        from streamlit.testing.v1 import AppTest
        from tests.test_crm_ui import SCRIPT
        at=AppTest.from_string(SCRIPT.replace("'role':'worker'","'role':'admin'"))
        at.session_state['route']='CRM Campaigns';at.run(timeout=20)
        self.assertFalse(at.exception)
        self.assertFalse(any(s.label in ('Header template','Footer template') for s in at.selectbox))
        self.assertFalse(any(t.label in ('Header HTML','Footer HTML') for t in at.text_area))
        before=deepcopy(at.session_state['campaign_editor']['document'])
        at.session_state[at.session_state['campaign_edit_key']+'panel']='Templates';at.run()
        self.assertFalse(at.exception)
        edits=[b for b in at.button if (b.key or '').startswith('edit_email_default_')]
        self.assertEqual(len(edits),2)
        # AppTest does not retain native tab selection on subsequent button events.
        # Exercise the same editor directly, then verify the composer preview anew.
        editor_script="""
import streamlit as st
from crm_brand_template_ui import brand_templates_settings
from crm_campaign_store import CampaignStore
from tests.crm_db_fixture import connect
from tests.test_crm import ADMIN
store=CampaignStore(connect)
brand_templates_settings(store,ADMIN)
"""
        edit=AppTest.from_string(editor_script).run()
        next(b for b in edit.button if b.key=='edit_email_default_header').click().run()
        self.assertTrue(any(t.label=='Header HTML' for t in edit.text_area))
        edit=AppTest.from_string(editor_script.replace('brand_templates_settings(store,ADMIN)',
            "from crm_brand_template_ui import edit_default\nedit_default(store,ADMIN,'header',store.email_defaults(store.render_settings())['header'])")).run()
        next(t for t in edit.text_area if t.label=='Header HTML').set_value('<p>UI default</p>')
        next(b for b in edit.button if b.label=='Save default').click().run()
        self.assertFalse(edit.exception)
        self.assertEqual(self.store.default_sections(self.cfg)['header'],'<p>UI default</p>')
        at.run()
        self.assertEqual(at.session_state['campaign_editor']['document']['custom_html'],before['custom_html'])
        self.assertTrue(any('UI default' in f.proto.srcdoc for f in at.get('iframe')))
