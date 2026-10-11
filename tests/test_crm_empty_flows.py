"""Empty draft and preservation contracts using the existing disposable SQL fixture."""
from copy import deepcopy
import json
import os
import unittest
import uuid
from unittest.mock import patch

from crm_automation_definition import TRIGGERS, new_flow, validate, email_step
from crm_automation_store import AutomationStore
from tests.crm_db_fixture import connect
from tests.test_crm import ADMIN
from tests.test_crm_send_flow import CFG
from tests import test_crm_lifecycle_expansion as lifecycle_tests


class DefinitionTests(unittest.TestCase):
    def test_empty_drafts_are_saveable_but_not_publishable(self):
        for kind in TRIGGERS:
            flow=new_flow(kind);flow['emails']=[]
            self.assertEqual(validate(flow,draft=True),flow)
            with self.assertRaisesRegex(ValueError,'Add an email'):validate(flow)


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable SQL required')
class EmptyFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):lifecycle_tests.DatabaseTests.setUpClass()

    def setUp(self):
        self.store=AutomationStore(connect)
        self.render=patch.object(self.store,'render_settings',return_value=deepcopy(CFG)).start()
        self.addCleanup(patch.stopall)

    def test_all_new_flows_stay_empty_on_reopen_then_save_individual_email(self):
        for kind in TRIGGERS:
            row=self.store.create(ADMIN,kind,empty=True,lifecycle=kind in ('welcome','post_purchase','win_back'))
            self.assertEqual(row['status'],'DRAFT')
            self.assertEqual(row['steps'],[])
            for _ in range(2):self.assertEqual(self.store.flow(row['id'])['config'],row['config'])
            flow=deepcopy(row['config']['draft'])
            self.assertEqual(flow['emails'],[])
            self.assertEqual(self.store.save_flow(ADMIN,row['id'],row['name'],flow,1)['config']['revision'],1)
            step=email_step(delay_seconds=86400)
            if flow.get('lifecycle_version'):step['anchor']={'welcome':'subscription','post_purchase':'payment','win_back':'last_purchase'}[kind]
            step['document']['content']['subject']='Individually saved email'
            flow['emails'].append(step)
            saved=self.store.save_flow(ADMIN,row['id'],row['name'],flow,1)
            self.assertEqual(self.store.flow(row['id'])['config']['draft'],flow)
            self.assertEqual(saved['steps'],[])
            self.assertEqual(saved['status'],'DRAFT')
            self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_automation_enrollments WHERE automation_id=%s',(row['id'],),True)['n'],0)
        self.render.assert_not_called()  # No template/settings reads on creation.

    def test_unused_empty_legacy_initialisation_is_idempotent(self):
        identity=str(uuid.uuid4())
        row=self.store.q("INSERT INTO crm_automations(id,automation_key,name,trigger_type,config,steps) VALUES(%s,%s,'Empty legacy','welcome','{}','[]') RETURNING *",(identity,identity),True)
        first=self.store.adopt(ADMIN,identity)
        self.assertEqual(first['config']['draft']['emails'],[])
        self.assertEqual(first['steps'],row['steps'])
        self.assertEqual(first,self.store.adopt(ADMIN,identity))

    def test_existing_native_definitions_are_not_prepared_or_reset(self):
        for kind in TRIGGERS:
            row=self.store.create(ADMIN,kind,lifecycle=kind in ('welcome','post_purchase','win_back'))
            self.assertTrue(row['config']['draft']['emails'])
            self.assertEqual(self.store.adopt(ADMIN,row['id']),row)

    def test_legacy_record_with_saved_draft_retains_email_ids_content_and_settings(self):
        flow=new_flow('welcome')
        flow['emails'][0]['document']['content']['subject']='Saved before conversion'
        flow['emails'][0]['delay_seconds']=12360
        flow['reentry_days']=30
        identity=str(uuid.uuid4())
        self.store.q("INSERT INTO crm_automations(id,automation_key,name,trigger_type,config,steps) VALUES(%s,%s,'Saved draft','welcome',%s::jsonb,'[]')",(identity,identity,json.dumps({'draft':flow})))
        self.assertEqual(self.store.adopt(ADMIN,identity)['config']['draft'],flow)

    def test_legacy_saved_templates_delays_config_and_source_steps_are_retained(self):
        self.store.seed()
        identity=str(uuid.uuid4())
        steps=[{'type':'delay','hours':24},{'type':'revalidate'},{'type':'send','template':'welcome_1'},{'type':'stop'}]
        cfg={'retained_setting':'original'}
        self.store.q("INSERT INTO crm_automations(id,automation_key,name,trigger_type,config,steps) VALUES(%s,%s,'Saved legacy','welcome',%s::jsonb,%s::jsonb)",(identity,identity,json.dumps(cfg),json.dumps(steps)))
        template=self.store.q("SELECT * FROM crm_templates WHERE template_key='welcome_1'",one=True)
        saved=self.store.adopt(ADMIN,identity)
        self.assertEqual(saved['steps'],steps)
        self.assertEqual(saved['config']['legacy_config'],cfg)
        self.assertEqual(saved['config']['retained_setting'],'original')
        emails=saved['config']['draft']['emails']
        self.assertEqual(len(emails),1)
        self.assertEqual(emails[0]['delay_seconds'],86400)
        self.assertEqual(self.store.q('SELECT * FROM crm_templates WHERE id=%s',(template['id'],),True),template)
        self.assertEqual(self.store.adopt(ADMIN,identity),saved)
