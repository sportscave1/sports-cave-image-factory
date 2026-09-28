"""Storage recovery regressions. SQL tests use the explicitly isolated loopback fixture."""
import os
import unittest
from unittest.mock import patch, MagicMock
from streamlit.testing.v1 import AppTest
import crm_schema
import os_accounts
import run_migrations
from crm_store import Store, StoreUnavailable
from tests.test_crm import ADMIN


class RecoveryTests(unittest.TestCase):
    def test_settings_is_navigable_without_new_worker_permission(self):
        self.assertIn('CRM Settings', os_accounts.allowed_navigation_routes(ADMIN))
        worker={'id':'test','role':'worker','is_active':True,'page_permissions':['crm_campaigns_manage']}
        self.assertIn('CRM Settings', os_accounts.allowed_navigation_routes(worker))
        self.assertNotIn('crm_settings_view',[p['key'] for p in os_accounts.worker_assignable_pages()])
        self.assertNotIn('CRM Settings',os_accounts.allowed_navigation_routes(dict(worker,page_permissions=[])))

    def test_manifest_is_reviewed_and_check_never_connects(self):
        self.assertEqual(run_migrations.DEPLOYMENT_MIGRATIONS[-3:],run_migrations.CRM_MIGRATIONS)
        with patch('run_migrations.psycopg.connect',side_effect=AssertionError('No DB in check mode')):
            run_migrations.run_crm_migrations(check=True)
        for name in run_migrations.CRM_MIGRATIONS:
            p=run_migrations.MIGRATIONS_DIR/name
            self.assertTrue(run_migrations.reviewed_migration_sql(p,p.read_text()))
            self.assertFalse(run_migrations.reviewed_migration_sql(p,p.read_text()+'-- changed'))

    def test_storage_errors_are_safe_and_specific(self):
        for code,expected in [('42P01','missing'),('42501','permissions'),('08006','connectivity')]:
            error=type('DatabaseError',(Exception,),{'sqlstate':code})('credential-secret')
            with self.subTest(code=code),self.assertRaises(StoreUnavailable) as caught:
                Store(lambda:(_ for _ in ()).throw(error)).state('cache_version')
            self.assertIn(expected,str(caught.exception));self.assertNotIn('credential-secret',str(caught.exception))

    def test_migration_failure_does_not_commit_ddl_or_ledger(self):
        conn=MagicMock();conn.__enter__.return_value=conn
        cur=conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value=None
        def execute(sql,*args):
            if 'CREATE TABLE IF NOT EXISTS crm_campaign_drafts' in sql:
                raise RuntimeError('fixture DDL failure')
        cur.execute.side_effect=execute
        with patch.object(run_migrations,'get_database_url',return_value=('fixture','DATABASE_URL')),patch.object(run_migrations.psycopg,'connect',return_value=conn):
            with self.assertRaisesRegex(RuntimeError,'fixture DDL failure'):
                run_migrations.run_crm_migrations()
        conn.commit.assert_not_called()
        self.assertIs(conn.__exit__.call_args.args[0],RuntimeError)
        statements=[c.args[0] for c in cur.execute.call_args_list]
        self.assertTrue(any('pg_advisory_xact_lock' in s for s in statements))
        for sql in statements:
            if 'CREATE TABLE IF NOT EXISTS crm_' in sql:
                self.assertNotIn('\nCOMMIT;',sql)

    def test_recorded_migrations_are_not_replayed(self):
        conn=MagicMock();conn.__enter__.return_value=conn
        cur=conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value={'filename':'already recorded'}
        cur.fetchall.return_value=[{'filename':n} for n in run_migrations.CRM_MIGRATIONS]
        with patch.object(run_migrations,'get_database_url',return_value=('fixture','DATABASE_URL')),patch.object(run_migrations.psycopg,'connect',return_value=conn) as connect,patch.object(crm_schema,'schema_issues',return_value=[]):
            run_migrations.run_crm_migrations()
        self.assertEqual(connect.call_count,2)
        self.assertFalse(any('CREATE TABLE IF NOT EXISTS crm_' in c.args[0] for c in cur.execute.call_args_list))

    def test_outage_keeps_navigation_and_blocks_creating(self):
        script='''
from unittest.mock import patch
import streamlit as st
from crm_page import render_page
from crm_store import Store
from crm_resend import Config
from tests.test_crm import ADMIN
def unavailable(): raise ConnectionError('secret DSN')
with patch('requests.sessions.Session.request',side_effect=AssertionError('No external I/O')):
 render_page(st.session_state.get('route','CRM Campaigns'),ADMIN,store=Store(unavailable),config=Config({}))
'''
        for route in ('CRM Campaigns','CRM Automations','CRM Settings'):
            at=AppTest.from_string(script);at.session_state['route']=route
            at.session_state['crm_settings_section']='Branding';at.run()
            self.assertFalse(at.exception)
            self.assertTrue(at.error)
            self.assertTrue({'Campaigns','Flows','Settings'}.issubset({b.label for b in at.button}))
            if route=='CRM Campaigns':
                self.assertTrue(next(b for b in at.button if b.label=='+ New Campaign').disabled)
                self.assertTrue(any('LIVE MARKETING DELIVERY: DISABLED' in w.value for w in at.caption))
            at.run();self.assertFalse(at.exception)


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Requires isolated loopback PostgreSQL fixture')
class SchemaRecoveryTests(unittest.TestCase):
    def test_full_schema_contract(self):
        from tests.crm_db_fixture import connect
        class Cursor:
            def execute(self,*args): self.result=connect().execute(*args)
            def fetchall(self): return self.result.fetchall()
        self.assertEqual(crm_schema.schema_issues(Cursor()),[])

    def test_empty_list_and_healthy_settings_render(self):
        from tests.test_crm_ui import SCRIPT
        for route in ('CRM Campaigns','CRM Settings','CRM Automations'):
            at=AppTest.from_string(SCRIPT);at.session_state['route']=route
            if route=='CRM Settings':at.session_state['crm_settings_section']='Templates'
            at.run(timeout=20);self.assertFalse(at.exception);self.assertFalse(at.error)
            if route=='CRM Campaigns':
                next(t for t in at.text_input if t.label=='Search campaigns').set_value('no-such-campaign-739421');at.run()
                self.assertTrue(any('No matching campaigns' in i.value for i in at.info))
                self.assertFalse(next(b for b in at.button if b.label=='+ New Campaign').disabled)

    def test_save_reload_edit_duplicate_archive_history(self):
        from tests.crm_db_fixture import connect
        from crm_campaign_store import CampaignStore
        from crm_campaign_content import new_document
        row=CampaignStore(connect).save(ADMIN,'Storage regression draft',new_document())
        reopened=CampaignStore(connect).draft(row['id']);self.assertEqual(reopened['name'],row['name'])
        edited=CampaignStore(connect).save(ADMIN,'Storage regression edited',reopened['document'],row['id'],row['version'])
        self.assertEqual(CampaignStore(connect).draft(row['id'])['name'],'Storage regression edited')
        duplicate=CampaignStore(connect).duplicate(ADMIN,row['id'])
        self.assertNotEqual(duplicate['id'],row['id'])
        CampaignStore(connect).archive(ADMIN,duplicate['id'],duplicate['version'])
        self.assertEqual(CampaignStore(connect).draft(duplicate['id'])['status'],'ARCHIVED')
        self.assertEqual(edited['version'],2)
        self.assertTrue(CampaignStore(connect).history(row['id']))
