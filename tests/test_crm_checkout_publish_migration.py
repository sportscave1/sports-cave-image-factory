"""Current production draft fixture; no production writes or email transports."""
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from crm_checkout_styles import rules, count, MARKER, compile_html
from crm_checkout_migration import migrate, migrate_flow
from crm_checkout_preview import document as preview, legacy
from crm_abandoned_checkout import hydrate, context, publication_document
from crm_campaign_content import render_campaign
from crm_campaign_send import production_checks, validate_tracking
from crm_automation_definition import production_document
from crm_campaign_sections import with_email_defaults
from crm_email_size import validate_rendered_email
from tests.test_crm_abandoned_checkout import checkout
from tests.test_crm_send_flow import CFG, LIVE


def current():
    return json.loads((Path(__file__).parent/'fixtures'/'abandoned_checkout_reminder_1.json').read_text(encoding='utf-8'))


class PublishMigrationTests(unittest.TestCase):
    def setUp(self):
        guard=patch('requests.sessions.Session.request',side_effect=AssertionError('External I/O forbidden'))
        guard.start();self.addCleanup(guard.stop)

    def test_general_css_is_not_checkout_css(self):
        source='<style>html, body {background:#0c0c0c; -webkit-text-size-adjust:100%} @media(max-width:600px){.sc-pad{padding:4px}}</style>'
        self.assertEqual(rules(source),{})
        self.assertEqual(compile_html(source,{}),source)
        from crm_campaign_html import import_html
        markup,_,checks=import_html(compile_html(source+'<p style="color:#ffffff">Copy</p>',{}))
        self.assertTrue(all(checks.values()));self.assertNotIn('<style>',markup)
        self.assertIn('color:#ffffff',markup)
        self.assertEqual(rules(source+'<style>.sc-cart-title{color:#ffffff}</style>')['sc-cart-title']['color'][0],'#ffffff')

    def test_unsupported_checkout_selectors_and_values_still_fail(self):
        for rule in ('.sc-cart-unknown{color:red}', '.sc-cart-title:hover{color:red}',
                     'body, .sc-cart-title{color:red}', '@media(max-width:600px){.sc-cart-title{color:red}}',
                     '.sc-cart-title{color:expression(alert(1))}', '.sc-cart-title{background:url(https://example.test)}',
                     '.sc-cart-title{position:fixed}', '.sc-cart-title{color:red'):
            with self.subTest(rule=rule),self.assertRaises(ValueError):rules('<style>'+rule+'</style>')

    def test_current_draft_lossless_native_migration_is_idempotent(self):
        original=current();saved=deepcopy(original);native=migrate(original)
        self.assertEqual(original,saved);self.assertEqual(migrate(native),native)
        self.assertEqual(count(native),1);self.assertFalse(legacy(native))
        sections=native['middle_sections']
        self.assertEqual(sections[0]['html']+MARKER+sections[2]['html'],original['middle_sections'][0]['html'])
        self.assertEqual(sections[3],original['middle_sections'][1])
        for key in original.keys()-{'middle_sections','custom_html'}:self.assertEqual(native[key],original[key])

    def test_current_preview_and_live_render_preserve_exact_layout_and_theme(self):
        original=current();native=migrate(original);data=context(checkout())
        before=render_campaign(hydrate(original,data),CFG)
        after=render_campaign(hydrate(native,data),CFG)
        self.assertEqual(before,after)
        rendered,warning=preview(native,data)
        self.assertFalse(warning);self.assertEqual(render_campaign(rendered,CFG),after)
        for token in ('{{','{%','SC_ABANDONED_CHECKOUT'):self.assertNotIn(token,after['html'])
        self.assertIn('sc-cart-title',after['html']);self.assertIn('Still',after['html'])

    def test_current_publication_passes_shared_checks_after_explicit_copy_review(self):
        doc=migrate(current())
        # The real draft has not checked its copy review; migration must not set it.
        self.assertFalse(doc['copy_reviewed'])
        def checks(doc):
            compiled=publication_document(with_email_defaults(production_document(doc),CFG),'abandoned')
            return compiled,production_checks(compiled,CFG,LIVE,reviewed_audience=True)
        _,result=checks(doc)
        self.assertFalse(result['Subject present and truthful-copy review complete'])
        doc['copy_reviewed']=True;compiled,result=checks(doc)
        self.assertTrue(all(result.values()),result)
        size=validate_rendered_email(validate_tracking(compiled,CFG,'00000000-0000-0000-0000-000000000001'))
        self.assertEqual(size['status'],'SAFE')
        self.assertNotIn(MARKER,str(compiled))

    def test_ambiguous_liquid_is_not_silently_migrated(self):
        doc=current();doc['middle_sections'][0]['html']+='{{ abandoned_checkout.url }}'
        self.assertEqual(migrate(doc),doc)
        with self.assertRaisesRegex(ValueError,'Unresolved'):publication_document(doc,'abandoned')

    def test_marker_inside_css_or_attribute_is_not_migrated(self):
        for source in ('<style>p{content:"'+MARKER+'"}</style>', '<div title="'+MARKER+'">Copy</div>'):
            doc=current();doc['middle_sections'][0]['html']=source
            self.assertEqual(migrate(doc),doc)

    def test_other_flows_and_historical_input_are_untouched(self):
        flow={'trigger':'welcome','emails':[{'document':current()}]};original=deepcopy(flow)
        self.assertEqual(migrate_flow(flow),original);self.assertEqual(flow,original)


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class StoreMigrationTests(unittest.TestCase):
    def test_draft_load_save_and_rollback_publication_leave_versions_immutable(self):
        from tests.crm_db_fixture import connect, Connection
        from tests.test_crm import ADMIN
        from crm_automation_store import AutomationStore
        from crm_automation_definition import email_step
        from crm_logic import now
        store=AutomationStore(connect)
        with patch('requests.sessions.Session.request',side_effect=AssertionError('No external I/O')),patch.object(store,'render_settings',return_value=deepcopy(CFG)):
            row=store.create(ADMIN,'abandoned','Current draft local validation fixture')
            flow=deepcopy(row['config']['draft']);flow['emails']=[email_step(current(),60)]
            # Seed the historical shape directly in the disposable fixture only.
            cfg=deepcopy(row['config']);cfg['draft']=flow
            store.q('UPDATE crm_automations SET config=%s::jsonb WHERE id=%s',(json.dumps(cfg),row['id']))
            store.step_id=flow['emails'][0]['step_id']
            draft=store.draft(row['id']);self.assertFalse(legacy(draft['document']))
            self.assertEqual(store.flow(row['id'])['config']['draft'],flow)
            native=deepcopy(flow);native['emails'][0]['document']=draft['document']
            saved=store.save_flow(ADMIN,row['id'],row['name'],native,1)
            again=store.save_flow(ADMIN,row['id'],row['name'],native,2)
            self.assertEqual(saved['config'],again['config'])
            native['emails'][0]['document']['copy_reviewed']=True
            saved=store.save_flow(ADMIN,row['id'],row['name'],native,2)
            store.set_state('shopify_automation_capabilities',{'checked_at':now().isoformat(),'triggers':{'abandoned':'AVAILABLE'}})
            before=store.q('SELECT count(*) n FROM crm_template_versions',one=True)['n']
            class Rollback(Connection):
                def __exit__(self,*args):return super().__exit__(RuntimeError,None,None)
            validator=AutomationStore(Rollback)
            with patch.object(validator,'render_settings',return_value=deepcopy(CFG)), patch('crm_automation_capabilities.require') as readiness:
                result=validator.publish(ADMIN,row['id'],saved['config']['revision'],env=LIVE)
            readiness.assert_called_once_with(validator,'abandoned')
            self.assertEqual(result['config']['published_version'],1)
            self.assertEqual(store.flow(row['id'])['status'],'DRAFT')
            self.assertEqual(store.q('SELECT count(*) n FROM crm_template_versions',one=True)['n'],before)
