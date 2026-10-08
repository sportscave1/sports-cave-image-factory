from copy import deepcopy
import os
import unittest
from crm_middle_sections import apply_event,commit_middle
from crm_campaign_content import render_campaign,validate_document
from tests.test_crm_simple_editor import document
from tests.test_crm_send_flow import CFG,LIVE


def rename(doc,identity,name,**extra):
    apply_event(doc,dict(type='rename',base=[s['id'] for s in doc['middle_sections']],id=identity,name=name,**extra))


class SectionNameTests(unittest.TestCase):
    def test_names_only_change_metadata_for_all_editable_types(self):
        doc=document()
        commit_middle(doc,[dict(id='a',type='html',html_number=1,html='<p>Original</p>',visible=True),
            dict(id='b',type='image',html='<p>Image copy</p>',visible=True)])
        before=render_campaign(doc,CFG)
        for section in doc['middle_sections']:rename(doc,section['id'],'Hero / Heading <internal>')
        self.assertEqual(render_campaign(doc,CFG),before)
        apply_event(doc,dict(type='add',kind='catalogue',base=['a','b']))
        identity=doc['middle_sections'][-1]['id'];rename(doc,identity,'Customer Artwork')
        self.assertEqual(doc['middle_sections'][-1]['name'],'Customer Artwork')
        rename(doc,identity,'',reset=True);self.assertEqual(doc['middle_sections'][-1]['name'],'')
        validate_document(doc)

    def test_rename_preserves_pending_html_and_survives_other_events(self):
        doc=document();commit_middle(doc,[dict(id='one',type='html',html_number=1,html='<p>Before</p>',visible=True)])
        rename(doc,'one','  Complete Order CTA  ',edits={'one':'<p>Typing</p>'})
        for kind,extra in [('visible',{'visible':False}),('duplicate',{}),('html',{'html':'<p>After</p>'})]:
            apply_event(doc,dict(type=kind,id='one',base=[s['id'] for s in doc['middle_sections']],**extra))
        apply_event(doc,dict(type='order',base=[s['id'] for s in doc['middle_sections']],ids=[s['id'] for s in reversed(doc['middle_sections'])]))
        self.assertEqual([s['name'] for s in doc['middle_sections']],['Complete Order CTA']*2)
        self.assertEqual(doc['middle_sections'][0]['html'],'<p>Typing</p>')
        for bad in ('',None,4,'x'*81):
            before=deepcopy(doc)
            with self.assertRaises(ValueError):rename(doc,'one',bad)
            self.assertEqual(doc,before)

    def test_reset_checkout_label_does_not_split_or_rewrite_source(self):
        from crm_checkout_section import editable
        from crm_abandoned_checkout import apply_template
        from crm_checkout_migration import migrate
        doc=document();apply_template(doc);doc=editable(doc);before=deepcopy(doc)
        rename(doc,doc['middle_sections'][0]['id'],'',reset=True)
        self.assertEqual(doc['custom_html'],before['custom_html'])
        self.assertEqual(migrate(doc),doc)


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class SectionNamePersistenceTests(unittest.TestCase):
    def test_campaign_reopen_duplicate_and_render(self):
        from crm_campaign_store import CampaignStore
        from tests.crm_db_fixture import connect
        from tests.test_crm import ADMIN
        doc=document();commit_middle(doc,[dict(id='one',type='html',html_number=1,html='<p>Original</p>',visible=True)])
        before=render_campaign(doc,CFG);rename(doc,'one','Hero / Heading')
        store=CampaignStore(connect);row=store.save(ADMIN,'Rename fixture',doc)
        reopened=CampaignStore(connect).draft(row['id'])
        self.assertEqual(reopened['document']['middle_sections'][0]['name'],'Hero / Heading')
        copied=store.duplicate(ADMIN,row['id'])
        self.assertEqual(copied['document']['middle_sections'][0]['name'],'Hero / Heading')
        self.assertEqual(render_campaign(reopened['document'],CFG),before)

    def test_flow_and_step_duplication_published_snapshot_keep_names(self):
        from crm_automation_store import AutomationStore
        from crm_automation_definition import email_step
        from tests.crm_db_fixture import connect
        from tests.test_crm import ADMIN
        store=AutomationStore(connect);row=store.create(ADMIN,'welcome','Rename flow fixture')
        doc=document();commit_middle(doc,[dict(id='one',type='html',html_number=1,html='<p>Original</p>',visible=True)])
        rename(doc,'one','Customer Artwork');flow=row['config']['draft'];flow['emails']=[email_step(doc,0),email_step(doc,3600)]
        row=store.save_flow(ADMIN,row['id'],row['name'],flow,1)
        copied=store.duplicate(ADMIN,row['id'])
        self.assertEqual([s['document']['middle_sections'][0]['name'] for s in copied['config']['draft']['emails']],['Customer Artwork']*2)
        store.render_settings=lambda env=None:deepcopy(CFG)
        from crm_logic import now
        store.set_state('shopify_automation_capabilities',{'checked_at':now().isoformat(),'triggers':{'welcome':'AVAILABLE'}})
        row=store.publish(ADMIN,row['id'],row['config']['revision'],env=LIVE)
        for step in row['steps']:
            template=store.q('SELECT content FROM crm_templates WHERE id=%s',(step['template_id'],),True)
            self.assertIn('Customer Artwork',str(template))
        reopened=AutomationStore(connect).flow(row['id'])
        self.assertEqual(reopened['config']['draft']['emails'][0]['document']['middle_sections'][0]['name'],'Customer Artwork')
        self.assertEqual(store.q('SELECT count(*) n FROM crm_automation_enrollments WHERE automation_id=%s',(row['id'],),True)['n'],0)
