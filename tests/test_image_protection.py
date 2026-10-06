"""Local-only settings, baseline login, utility authorization and lazy loading."""
import asyncio
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from starlette.requests import Request
import image_protection as policy
import image_protection_ui as ui
import sc_auth
import top_bar_api
import top_bar_security
import os_accounts
import daily_planner
import storefront_protection_api as public

ADMIN={'id':'fixture-admin','role':'admin','is_active':True,'account_status':'active','session_version':1}


def request(token='',cookie=''):
    return Request({'type':'http','method':'GET','path':'/','headers':[
        (b'authorization',('Bearer '+token).encode()),(b'cookie',cookie.encode())]})


class ImageProtectionTests(unittest.TestCase):
    def setUp(self):
        policy._cache=None;policy._expires=0

    def test_public_config_allowlist_cached_no_provider_or_schema_work(self):
        import supabase_backend as db
        with patch.object(db,'get_app_setting',return_value={'enabled':False}) as read:
            for _ in range(3):self.assertFalse(policy.public_policy()['enabled'])
        read.assert_called_once_with(policy.SETTING_KEY,{},ensure_schema_first=False)
        self.assertEqual(set(policy.public_policy()),set(policy.DEFAULTS))
        self.assertFalse(policy.public_policy()['visibleWatermark'])

    def test_outage_cached_and_does_not_fail_storefront(self):
        with patch.object(policy,'load_policy',side_effect=RuntimeError('offline')) as read:
            for _ in range(3):self.assertEqual(policy.public_policy(),{**policy.DEFAULTS,'enabled':False})
        read.assert_called_once()
        with patch.object(public,'public_policy',side_effect=RuntimeError('offline')):
            response=asyncio.run(public.config(request()))
        self.assertEqual(response.status_code,200)

    def test_save_existing_admin_only_no_new_tables(self):
        import supabase_backend as db
        with patch.object(db,'set_app_setting') as save, patch.object(db,'record_activity_log') as audit:
            with self.assertRaises(PermissionError):policy.save_policy({'role':'worker','is_active':True},{})
            with self.assertRaises(ValueError):policy.save_policy(ADMIN,{'enabled':'true'})
            with self.assertRaises(ValueError):policy.save_policy(ADMIN,{'private_key':'not-allowed'})
            policy.save_policy(ADMIN,{'visibleWatermark':True})
        save.assert_called_once_with(policy.SETTING_KEY,{**policy.DEFAULTS,'visibleWatermark':True},ensure_schema_first=False)
        audit.assert_called_once()

    def test_settings_route_admin_only_and_lazy(self):
        self.assertTrue(os_accounts.can_access_page(ADMIN,'Image Protection'))
        self.assertFalse(os_accounts.can_access_page({'role':'worker','is_active':True},'Image Protection'))
        with patch.object(policy,'load_policy') as load:
            ui.render(Mock(),{'role':'worker','is_active':True})
        load.assert_not_called()
        import inspect,app
        self.assertNotIn('image_protection',inspect.getsource(app.main))
        self.assertNotIn('image_protection',inspect.getsource(app.is_app_authenticated))

    def test_legacy_settings_preserved_with_new_scopes(self):
        values=policy.clean_policy({'enabled':False,'visibleWatermark':True})
        self.assertFalse(values['enabled'])
        self.assertTrue(values['visibleWatermark'])
        self.assertTrue(values['protectWallPreview'])
        self.assertFalse(values['wallPreviewWatermark'])

    def test_watermark_validation(self):
        for values in ({'watermarkOpacity':True},{'watermarkOpacity':2},{'watermarkText':''},{'watermarkPosition':'script'}):
            with self.assertRaises(ValueError):policy.clean_policy(values)

    def test_etag_and_only_allowlisted_public_values(self):
        import json
        with patch.object(public,'public_policy',return_value=dict(policy.DEFAULTS)):
            first=asyncio.run(public.config(request()))
            req=Request({'type':'http','method':'GET','path':'/', 'headers':[(b'if-none-match',first.headers['etag'].encode())]})
            self.assertEqual(asyncio.run(public.config(req)).status_code,304)
            self.assertEqual(set(json.loads(first.body)),set(policy.DEFAULTS))

    def test_baseline_login_cookie_30_days_without_optional_secret_in_render(self):
        with patch.dict(os.environ,{'RENDER':'true','SPORTS_CAVE_AUTH_SECRET':''}):
            token=sc_auth.create_user_auth_token(ADMIN['id'],now=100,session_version=1)
            valid,_,claims=sc_auth.validate_user_auth_token(token,now=101)
            self.assertTrue(valid);self.assertEqual(claims['exp']-claims['iat'],30*86400)
            self.assertEqual(sc_auth.auth_cookie_max_age(),30*86400)

    def test_retired_httponly_cookie_cleanup_has_no_auth_or_database_dependency(self):
        from auth_cookie_cleanup import clear_cookie
        for origin,expected in [('https://fixture.test',204),('https://other.test',403),('',403)]:
            req=Request({'type':'http','method':'POST','path':'/api/os/auth/clear-cookie',
                'headers':[(b'origin',origin.encode()),(b'host',b'fixture.test')]})
            response=asyncio.run(clear_cookie(req))
            self.assertEqual(response.status_code,expected)
            if expected==204:
                self.assertIn('Max-Age=0',response.headers['set-cookie'])
                self.assertIn(sc_auth.AUTH_COOKIE_NAME,response.headers['set-cookie'])

    def test_signed_top_bar_endpoints_without_extra_session_or_database_auth_lookup(self):
        import support_email_notifications as email
        import support_email_events
        with patch.dict(os.environ,{'RENDER':'true','SPORTS_CAVE_AUTH_SECRET':''}),patch.object(os_accounts.DEFAULT_STORE,'get_user',side_effect=AssertionError('Unexpected per-poll account lookup')):
            token=top_bar_security.create_top_bar_token(ADMIN,allowed_routes=['Orders','Email'],can_manage_daily_planner=True)
            req=request(token)
            with patch.object(top_bar_api,'load_order_status',return_value={}),patch.object(top_bar_api,'load_daily_planner_status',return_value={}),patch.object(email,'status',return_value={}):
                for handler in (top_bar_api.top_bar_order_status,top_bar_api.top_bar_email_status,top_bar_api.top_bar_daily_planner_status,support_email_events.email_events):
                    with self.subTest(handler=handler.__name__):
                        self.assertEqual(asyncio.run(handler(req)).status_code,200)
                        self.assertEqual(asyncio.run(handler(request('invalid'))).status_code,403)
            self.assertTrue(daily_planner._claims(req)['can_manage_daily_planner'])

    def test_analytics_retains_account_permissions_without_durable_sessions(self):
        import wall_preview_analytics_api as api
        with patch.dict(os.environ,{'SPORTS_CAVE_AUTH_SECRET':''}),patch.object(os_accounts.DEFAULT_STORE,'get_user',return_value=ADMIN):
            token=sc_auth.create_user_auth_token(ADMIN['id'])
            self.assertEqual(api.authorize(request(cookie=sc_auth.AUTH_COOKIE_NAME+'='+token)),ADMIN)
            with self.assertRaises(PermissionError):api.authorize(request())

    def test_migration_history_preserved_but_not_required_on_startup(self):
        import run_migrations
        name='20261005092224_os_security_protection.sql'
        self.assertTrue(Path('migrations',name).exists())
        self.assertIn(name,run_migrations.REVIEWED_MIGRATION_SHA256)
        self.assertNotIn(name,run_migrations.DEPLOYMENT_MIGRATIONS)

    def test_normal_navigation_does_not_call_image_policy(self):
        from tests.test_app_startup_scope_regression import AppStartupScopeRegressionTests
        with patch.object(policy,'load_policy',side_effect=AssertionError('Policy read during navigation')),patch.object(policy,'public_policy',side_effect=AssertionError('Policy read during navigation')):
            for route in ('Dashboard','Orders','Email','Files'):
                AppStartupScopeRegressionTests().run_main_route(route)

    def test_settings_screen_has_only_website_controls_and_saves_explicitly(self):
        # Streamlit's process-global DeltaGenerator context is shared by bare-mode
        # tests. Exercise the real screen in a fresh runtime, as the app uses it.
        import subprocess, sys
        code = """
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import image_protection as policy
screen = "import streamlit as st\\nfrom image_protection_ui import render\\nrender(st,{'id':'fixture-admin','role':'admin','is_active':True,'account_status':'active'})"
with patch.object(policy,'last_updated',return_value='2026-10-06'),patch.object(policy,'load_policy',return_value=dict(policy.DEFAULTS)),patch.object(policy,'save_policy') as save:
    page=AppTest.from_string(screen).run()
    assert not page.exception
    assert page.title[0].value=='Image Protection'
    assert len(page.checkbox)==15 and not page.checkbox[-1].value
    save.assert_not_called()
    page.button[0].click().run()
    assert not page.exception
    save.assert_called_once()
"""
        result=subprocess.run([sys.executable,'-X','utf8','-c',code],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
