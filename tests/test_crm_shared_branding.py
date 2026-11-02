"""Offline regressions: saved shared sources must supersede copied sections."""
from copy import deepcopy
import unittest
from crm_campaign_content import render_campaign
from crm_campaign_sections import with_email_defaults
from tests.test_crm_campaign_sections import sectioned
from tests.test_crm_resend_marketing import ENV
from crm_campaign_content import settings
from crm_campaign_footer import DEFAULT_FOOTER
import os


class SharedBrandingTests(unittest.TestCase):
    def test_legacy_queued_payload_without_section_metadata(self):
        from crm_shared_branding import rebrand
        from crm_email_size import render_production,REPRESENTATIVE_ID
        from crm_tracking import send_identity
        doc=sectioned();doc.pop('html_sections')
        old=settings(ENV);new={**old,'email_defaults':{'header':'<p>Shared legacy header</p>','footer':DEFAULT_FOOTER},'shared_branding_policy':1}
        frozen=render_production(doc,old)
        self.assertEqual(rebrand(frozen,doc,old,new,REPRESENTATIVE_ID,send_identity(REPRESENTATIVE_ID)),render_production(doc,new))

    def test_frozen_payload_rebranding_preserves_body_subject_and_tracking(self):
        from crm_shared_branding import rebrand
        from crm_email_size import render_production,REPRESENTATIVE_ID
        from crm_tracking import send_identity
        doc=sectioned();old=settings(ENV)
        old['email_defaults']=deepcopy(doc['html_sections'])
        new=deepcopy(old);new['email_defaults']['header']='<p>Newest header</p>'
        frozen=render_production(doc,old)
        result=rebrand(frozen,doc,old,new,REPRESENTATIVE_ID,send_identity(REPRESENTATIVE_ID))
        self.assertEqual(result,render_production(doc,new))
        self.assertEqual(frozen['subject'],result['subject'])
        self.assertIn('Discover the collection.',result['html'])
        bad={**frozen,'html':frozen['html'].replace('Discover the collection.','Discover the collection.')+'unexpected'}
        with self.assertRaises(ValueError):rebrand(bad,doc,old,new,REPRESENTATIVE_ID,send_identity(REPRESENTATIVE_ID))

    def test_existing_document_uses_saved_sources_without_rewriting_body(self):
        doc=sectioned(); original=deepcopy(doc)
        cfg=settings(ENV)
        cfg['email_defaults']={'header':'<p>Saved shared header</p>',
                              'footer':DEFAULT_FOOTER.replace('Website','Saved shared footer')}
        message=render_campaign(doc,cfg)
        self.assertEqual(message['html'].count('Saved shared header'),1)
        self.assertEqual(message['html'].count('Saved shared footer'),1)
        self.assertEqual(doc,original)
        self.assertEqual(with_email_defaults(doc,cfg)['custom_html'],doc['custom_html'])

    def test_preview_cache_changes_with_saved_revision(self):
        from crm_preview_cache import preview
        state={};doc=sectioned();cfg=settings(ENV)
        cfg['email_defaults']={'header':'<p>First shared header</p>','footer':DEFAULT_FOOTER}
        first=preview(state,doc,cfg)
        cfg['email_defaults']['header']='<p>Second shared header</p>'
        second=preview(state,doc,cfg)
        self.assertIn('First shared header',first['html'])
        self.assertIn('Second shared header',second['html'])
        self.assertNotIn('First shared header',second['html'])


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable SQL required')
class BrandingMigrationTests(unittest.TestCase):
    def test_release_sql_runs_twice_and_retains_footer(self):
        from crm_campaign_store import CampaignStore
        from scripts.shared_email_branding_release import sql
        from tests.crm_db_fixture import connect
        store=CampaignStore(connect);cfg=store.render_settings(ENV)
        footer=store.email_defaults(cfg)['footer']
        store.q("DELETE FROM crm_runtime_state WHERE key='migration:shared-email-branding:20261030'")
        with store.db() as conn:conn.execute(sql())
        saved=store.email_defaults(cfg)['header']
        with store.db() as conn:conn.execute(sql())
        self.assertEqual(store.email_defaults(cfg)['header'],saved)
        self.assertEqual(store.email_defaults(cfg)['footer'],footer)
        self.assertIn('flows',store.state('migration:shared-email-branding:20261030'))
        from tests.test_crm import ADMIN
        store.save_email_default(ADMIN,'header','<p>Later approved edit</p>',saved['version'])
        with store.db() as conn:conn.execute(sql())
        self.assertEqual(store.default_sections(cfg)['header'],'<p>Later approved edit</p>')
