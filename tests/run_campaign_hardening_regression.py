"""Run campaign regressions using only the dedicated local PostgreSQL cluster."""
import os
os.environ['CRM_TEST_POSTGRES']='1'
import unittest
import sys
from contextlib import contextmanager
from unittest.mock import patch
import psycopg
from tests.campaign_real_postgres import connect as native_connect
import tests.crm_db_fixture as fixture

class Connection:
    def __init__(self):self.conn=native_connect()
    def __enter__(self):self.conn.__enter__();return self
    def __exit__(self,*args):return self.conn.__exit__(*args)
    def execute(self,*args,**kwargs):
        try:return self.conn.execute(*args,**kwargs)
        except psycopg.Error as exc:raise RuntimeError(str(exc)) from exc
def connect():return Connection()

fixture.connect=connect
modules=['test_crm_campaign_v7_1','test_crm_campaign_v8','test_crm_campaign_v2',
 'test_crm_campaigns_v1','test_crm_send_flow','test_crm_batch_dispatch',
 'test_crm_production_v2','test_crm_send_progress','test_crm_home_live_progress',
 'test_crm_campaign_home','test_crm_campaign_home_cache','test_crm_campaign_history',
 'test_crm_campaign_cleanup','test_crm_campaign_sections','test_crm_campaign_preparation',
 'test_crm_campaign_loading','test_crm_campaign_first_paint','test_campaign_recovery',
 'test_campaign_leave_dialog','test_crm_tracking_hardening','test_crm_resend_marketing',
 'test_crm_production_unsubscribe','test_crm_production_style_test','test_campaign_hardening']
with patch('requests.sessions.Session.request',side_effect=AssertionError('External I/O forbidden')):
    suite=unittest.defaultTestLoader.loadTestsFromNames(['tests.'+m for m in (sys.argv[1:] or modules)])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
