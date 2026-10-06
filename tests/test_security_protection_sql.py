import os
import time
import unittest
from unittest.mock import patch
import sc_auth
import os_accounts
import security_protection as p
from tests.crm_db_fixture import connect


@unittest.skipUnless(os.getenv('SECURITY_TEST_POSTGRES')=='1','Explicit local SQL fixture required')
class SecuritySQLTests(unittest.TestCase):
    def setUp(self):
        self.store=p.ProtectionStore(connect)
        for table in ('os_security_sessions','os_security_audit','os_security_login_limits','os_protection_settings'):
            self.store.q('DELETE FROM '+table)
        self.user={'id':'00000000-0000-0000-0000-000000000001','role':'admin','is_active':True,'password_hash':sc_auth.hash_password('fixture-password')}
        self.store.q("INSERT INTO os_users (id) VALUES (%s) ON CONFLICT(id) DO UPDATE SET is_active=true,session_version=1",(self.user['id'],))
        self.get_user=patch.object(os_accounts.DEFAULT_STORE,'get_user',return_value=self.user);self.get_user.start();self.addCleanup(self.get_user.stop)
        self.policy=patch('security_protection.cached_policy',return_value=p.DEFAULTS);self.policy.start();self.addCleanup(self.policy.stop)
        self.token=sc_auth.create_user_auth_token(self.user['id']);ok,_,self.claims=sc_auth.validate_user_auth_token(self.token);assert ok
        self.sid=self.store.register(self.token,self.claims,self.user,'Fixture browser')
    def test_idempotent_session_creation_and_audit(self):
        self.store.register(self.token,self.claims,self.user)
        self.assertEqual(1,self.store.q('SELECT count(*) n FROM os_security_sessions',one=True)['n'])
        self.assertEqual(1,self.store.q("SELECT count(*) n FROM os_security_audit WHERE event='SESSION_CREATED'",one=True)['n'])
    def test_cookie_handoff_is_single_use_and_reconstructs_same_session(self):
        grant=self.store.issue_cookie_handoff(self.token,self.claims,self.user)
        claims=self.store.consume_cookie_handoff(grant)
        self.assertEqual(self.token,sc_auth.sign_user_auth_claims(claims))
        with self.assertRaises(PermissionError):self.store.consume_cookie_handoff(grant)
        self.assertNotIn(grant,str(self.store.q('SELECT * FROM os_security_sessions')))
    def test_cookie_handoff_expiry(self):
        grant=self.store.issue_cookie_handoff(self.token,self.claims,self.user)
        self.store.q("UPDATE os_security_sessions SET cookie_grant_expires_at=now()-interval '1 second' WHERE id=%s",(self.sid,))
        with self.assertRaises(PermissionError):self.store.consume_cookie_handoff(grant)
    def test_session_revocation_is_durable(self):
        self.store.reauthenticate(self.user['id'],self.sid,'fixture-password')
        self.store.revoke(self.user['id'],self.sid,self.sid)
        restored=p.ProtectionStore(connect)
        with self.assertRaises(PermissionError):restored.validate_session(self.sid,self.user['id'])
        self.store.register(self.token,self.claims,self.user)
        with self.assertRaises(PermissionError):restored.validate_session(self.sid,self.user['id'])
    def test_expired_session_rejected(self):
        self.store.q("UPDATE os_security_sessions SET expires_at=now()-interval '1 minute' WHERE id=%s",(self.sid,))
        with self.assertRaises(PermissionError):self.store.validate_session(self.sid,self.user['id'])
    def test_idle_locks_and_password_restores(self):
        self.store.q("UPDATE os_security_sessions SET last_activity_at=now()-interval '16 minutes' WHERE id=%s",(self.sid,))
        with self.assertRaises(PermissionError):self.store.validate_session(self.sid,self.user['id'])
        self.assertIsNotNone(self.store.q('SELECT locked_at FROM os_security_sessions WHERE id=%s',(self.sid,),one=True)['locked_at'])
        self.store.reauthenticate(self.user['id'],self.sid,'fixture-password')
        self.assertTrue(self.store.validate_session(self.sid,self.user['id']))
    def test_wrong_password_rate_limited_durably(self):
        for _ in range(5):
            with self.assertRaises(PermissionError):self.store.reauthenticate(self.user['id'],self.sid,'wrong')
        with self.assertRaisesRegex(PermissionError,'Too many'):p.ProtectionStore(connect).reauthenticate(self.user['id'],self.sid,'fixture-password')
    def test_settings_require_reauth(self):
        with self.assertRaises(PermissionError):self.store.save_policy(self.user['id'],{},self.sid)
    def test_settings_persist_and_audit_excludes_password(self):
        self.store.reauthenticate(self.user['id'],self.sid,'fixture-password')
        self.store.save_policy(self.user['id'],{'enabled':False},self.sid)
        self.assertFalse(p.ProtectionStore(connect).policy()['enabled'])
        rows=self.store.q('SELECT * FROM os_security_audit')
        self.assertNotIn('fixture-password',str(rows));self.assertNotIn(self.token,str(rows))
    def test_login_rate_limit_persists(self):
        for _ in range(5):self.store.login_attempt('person@example.test')
        with self.assertRaises(PermissionError):p.ProtectionStore(connect).login_attempt('PERSON@example.test')
        self.store.login_success(p.session_key('person@example.test'),self.user)
        self.store.login_attempt('person@example.test')
    def test_rls_and_public_grants(self):
        rows=self.store.q("SELECT relname,relrowsecurity FROM pg_class WHERE relname IN ('os_protection_settings','os_security_sessions','os_security_audit','os_security_login_limits')")
        self.assertEqual(4,len(rows));self.assertTrue(all(r['relrowsecurity'] for r in rows))
        rows=self.store.q("SELECT has_table_privilege('anon','os_security_sessions','select') allowed")
        self.assertFalse(rows[0]['allowed'])
    def test_different_user_cannot_use_session(self):
        with self.assertRaises(PermissionError):self.store.validate_session(self.sid,'00000000-0000-0000-0000-000000000002')
    def test_reauth_expiry(self):
        self.store.reauthenticate(self.user['id'],self.sid,'fixture-password')
        self.store.q("UPDATE os_security_sessions SET reauthenticated_at=now()-interval '6 minutes' WHERE id=%s",(self.sid,))
        with self.assertRaises(PermissionError):self.store.require_reauth(self.user['id'],self.sid)
    def test_disabled_account_immediately_denied(self):
        self.store.q('UPDATE os_users SET is_active=false WHERE id=%s',(self.user['id'],))
        with self.assertRaises(PermissionError):self.store.validate_session(self.sid,self.user['id'])
    def test_account_session_rotation_denies_old_token(self):
        self.store.q('UPDATE os_users SET session_version=2 WHERE id=%s',(self.user['id'],))
        with self.assertRaises(PermissionError):self.store.validate_session(self.sid,self.user['id'])


if __name__=='__main__':unittest.main()
