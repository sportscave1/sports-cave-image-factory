"""Server-owned protection policy. Public responses use an explicit allowlist."""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from datetime import datetime, timezone
from functools import lru_cache

import os_accounts
from crm_store import Store

DEFAULTS = {
    'enabled': True, 'disableRightClick': True, 'preventImageDragging': True,
    'preventSelection': True, 'protectPrinting': True, 'blockSaveShortcuts': True,
    'mobileTouchProtection': True, 'aggressiveCopyDeterrence': True,
    'showCopyrightMessage': True, 'visibleWatermark': False,
    'protectedWebImagesOnly': True, 'neverServePrintMasters': True,
    'appRightClick': True, 'appImageDragging': True, 'appSelection': True,
    'appPrinting': True, 'appCopyDeterrence': True, 'blurOnFocusLoss': True, 'appWatermark': False,
    'autoLockMinutes': 15, 'sensitiveReauth': True, 'maxImageEdge': 1800,
    'watermarkOpacity': 'Low', 'watermarkPosition': 'corner',
}
PUBLIC_KEYS = tuple(k for k in DEFAULTS if not k.startswith('app') and k not in {
    'blurOnFocusLoss', 'autoLockMinutes', 'sensitiveReauth', 'watermarkOpacity',
    'watermarkPosition', 'maxImageEdge',
})


def clean_policy(values):
    if not isinstance(values, dict) or set(values) - set(DEFAULTS):
        raise ValueError('Unsupported protection setting.')
    result = dict(DEFAULTS)
    for key, value in values.items():
        if isinstance(DEFAULTS[key], bool) and type(value) is not bool:
            raise ValueError('Protection switches must be true or false.')
        if key == 'autoLockMinutes' and (type(value) is not int or value not in (0, 5, 10, 15, 30, 60)):
            raise ValueError('Unsupported lock interval.')
        if key == 'maxImageEdge' and (type(value) is not int or value not in (1200, 1600, 1800, 2000, 2400)):
            raise ValueError('Unsupported image dimensions.')
        if key == 'watermarkOpacity' and value not in ('Low', 'Medium', 'High'):
            raise ValueError('Unsupported watermark opacity.')
        if key == 'watermarkPosition' and value not in ('corner', 'centre', 'repeated'):
            raise ValueError('Unsupported watermark position.')
        result[key] = value
    result['neverServePrintMasters'] = True
    result['protectedWebImagesOnly'] = True
    return result


def session_key(token):
    return hashlib.sha256(str(token).encode()).hexdigest()


def timestamp(value):
    return value.timestamp() if hasattr(value,'timestamp') else datetime.fromisoformat(str(value).replace('Z','+00:00')).timestamp()


class ProtectionStore(Store):
    def issue_cookie_handoff(self,token,payload,user):
        sid=self.register(token,payload,user)
        grant=secrets.token_urlsafe(32)
        self.q("UPDATE os_security_sessions SET cookie_grant_hash=%s,cookie_grant_expires_at=now()+interval '90 seconds',cookie_claims=%s::jsonb WHERE id=%s AND revoked_at IS NULL",(session_key(grant),json.dumps(payload),sid))
        return grant

    def consume_cookie_handoff(self,grant):
        with self.db() as conn:
            row=conn.execute('SELECT id,cookie_claims FROM os_security_sessions WHERE cookie_grant_hash=%s AND cookie_grant_expires_at>now() AND revoked_at IS NULL FOR UPDATE',(session_key(grant),)).fetchone()
            if not row or not row['cookie_claims']:raise PermissionError('Sign-in handoff expired. Sign in again.')
            conn.execute('UPDATE os_security_sessions SET cookie_grant_hash=NULL,cookie_grant_expires_at=NULL,cookie_claims=NULL WHERE id=%s',(row['id'],))
            return row['cookie_claims']
    def login_attempt(self,login):
        key=hashlib.sha256(str(login or '').strip().casefold().encode()).hexdigest()
        row=self.q("INSERT INTO os_security_login_limits (key) VALUES (%s) ON CONFLICT (key) DO UPDATE SET attempts=CASE WHEN os_security_login_limits.window_started_at<now()-interval '15 minutes' THEN 1 ELSE os_security_login_limits.attempts+1 END,window_started_at=CASE WHEN os_security_login_limits.window_started_at<now()-interval '15 minutes' THEN now() ELSE os_security_login_limits.window_started_at END RETURNING attempts",(key,),one=True)
        if row['attempts']>5:
            raise PermissionError('Too many sign-in attempts. Try again in 15 minutes.')
        return key

    def login_success(self,key,user):
        with self.db() as conn:
            conn.execute('DELETE FROM os_security_login_limits WHERE key=%s',(key,))
            conn.execute('INSERT INTO os_security_audit (event,user_id) VALUES (%s,%s)',('LOGIN_SUCCESS',user['id']))

    def policy(self):
        row = self.q('SELECT policy FROM os_protection_settings WHERE singleton = true', one=True)
        return clean_policy((row or {}).get('policy') or {})

    def admin(self, user_id):
        user = os_accounts.DEFAULT_STORE.get_user(user_id)
        if not os_accounts.account_is_active(user) or not os_accounts.is_admin(user):
            raise PermissionError('Administrator access required.')
        return user

    def audit(self, event, user_id=None, resource='', result='success', session_id=''):
        # Deliberately no caller-supplied payload: secrets cannot enter metadata.
        self.q('INSERT INTO os_security_audit (event, user_id, resource, result, session_id) VALUES (%s,%s,%s,%s,%s)',
               (event[:80], user_id, resource[:160], result[:40], session_id[:64]))

    def save_policy(self, user_id, values, session_id):
        self.admin(user_id)
        self.require_reauth(user_id, session_id)
        policy = clean_policy(values)
        with self.db() as conn:
            conn.execute('INSERT INTO os_protection_settings (singleton,policy) VALUES (true,%s::jsonb) ON CONFLICT (singleton) DO UPDATE SET policy=excluded.policy, updated_at=now()', (json.dumps(policy),))
            for event in ('SECURITY_SETTING_CHANGED','STOREFRONT_SECURITY_SETTING_CHANGED','IMAGE_PROTECTION_CHANGED'):
                conn.execute('INSERT INTO os_security_audit (event,user_id,resource,session_id) VALUES (%s,%s,%s,%s)', (event,user_id,'protection_policy',session_id))
        cached_policy.cache_clear()
        return policy

    def register(self, token, payload, user, device=''):
        sid = session_key(token)
        with self.db() as conn:
            created=conn.execute('INSERT INTO os_security_sessions (id,user_id,session_version,expires_at,device) VALUES (%s,%s,%s,to_timestamp(%s),%s) ON CONFLICT (id) DO NOTHING RETURNING id',
                   (sid,user['id'],payload.get('sv',1),payload['exp'],str(device)[:200])).fetchone()
            if created:
                conn.execute('INSERT INTO os_security_audit (event,user_id,session_id) VALUES (%s,%s,%s)',('SESSION_CREATED',user['id'],sid))
        return sid

    def validate_session(self, sid, user_id, *, touch=False):
        row = self.q("SELECT s.* FROM os_security_sessions s JOIN os_users u ON u.id=s.user_id WHERE s.id=%s AND s.user_id=%s AND s.revoked_at IS NULL AND s.expires_at>now() AND u.is_active AND u.account_status='active' AND u.session_version=s.session_version", (sid,user_id),one=True)
        if not row:
            expired=self.q('UPDATE os_security_sessions SET revoked_at=now() WHERE id=%s AND user_id=%s AND revoked_at IS NULL AND expires_at<=now() RETURNING id',(sid,user_id),one=True)
            if expired:self.audit('SESSION_EXPIRED',user_id,session_id=sid)
            raise PermissionError('Session expired or revoked. Sign in again.')
        if row.get('locked_at'):
            raise PermissionError('Session locked. Verify your password.')
        minutes = cached_policy()['autoLockMinutes']
        last = timestamp(row['last_activity_at'])
        if minutes and time.time() - last >= minutes * 60:
            self.q('UPDATE os_security_sessions SET locked_at=now() WHERE id=%s', (sid,))
            self.audit('AUTO_LOCK',user_id,session_id=sid)
            raise PermissionError('Session locked. Verify your password.')
        if touch and time.time()-last >= 30:
            self.q('UPDATE os_security_sessions SET last_activity_at=now() WHERE id=%s', (sid,))
        return row

    def require_reauth(self, user_id, sid):
        row = self.validate_session(sid,user_id)
        when = row.get('reauthenticated_at')
        if cached_policy()['sensitiveReauth'] and (not when or time.time()-timestamp(when)>300):
            raise PermissionError('Verify your password before this sensitive action.')

    def reauthenticate(self, user_id, sid, password):
        # Rate state is durable and checked under a row lock before password work.
        with self.db() as conn:
            row = conn.execute('SELECT * FROM os_security_sessions WHERE id=%s AND user_id=%s AND revoked_at IS NULL AND expires_at>now() FOR UPDATE', (sid,user_id)).fetchone()
            if not row:
                raise PermissionError('Session expired or revoked.')
            if row['failed_attempts'] >= 5 and row.get('failed_at') and time.time()-timestamp(row['failed_at'])<900:
                raise PermissionError('Too many attempts. Try again in 15 minutes.')
            user = os_accounts.DEFAULT_STORE.get_user(user_id)
            ok = os_accounts.account_is_active(user) and int(user.get('session_version') or 1)==row['session_version'] and os_accounts.verify_password(password,user.get('password_hash'))
            if ok:
                conn.execute('UPDATE os_security_sessions SET reauthenticated_at=now(),last_activity_at=now(),locked_at=NULL,failed_attempts=0 WHERE id=%s',(sid,))
            else:
                conn.execute('UPDATE os_security_sessions SET failed_attempts=CASE WHEN failed_at<now()-interval \'15 minutes\' THEN 1 ELSE failed_attempts+1 END,failed_at=now() WHERE id=%s',(sid,))
            conn.execute('INSERT INTO os_security_audit (event,user_id,session_id,result) VALUES (%s,%s,%s,%s)',('REAUTH_SUCCESS' if ok else 'REAUTH_FAILED',user_id,sid,'success' if ok else 'denied'))
        if not ok:
            raise PermissionError('Password could not be verified.')

    def revoke(self, user_id, current_sid, target_sid):
        self.admin(user_id)
        self.require_reauth(user_id,current_sid)
        with self.db() as conn:
            conn.execute('UPDATE os_security_sessions SET revoked_at=now() WHERE id=%s AND revoked_at IS NULL',(target_sid,))
            conn.execute('INSERT INTO os_security_audit (event,user_id,resource,session_id) VALUES (%s,%s,%s,%s)',('SESSION_REVOKED',user_id,target_sid,current_sid))


STORE = ProtectionStore()


def sensitive_admin(actor):
    actor=dict(actor or {})
    user=STORE.admin(actor.get('id'))
    STORE.require_reauth(user['id'],actor.get('_security_sid') or '')
    return user


@lru_cache(maxsize=1)
def _policy_bucket(bucket):
    return STORE.policy()


def cached_policy():
    return dict(_policy_bucket(int(time.time()//30)))


cached_policy.cache_clear = _policy_bucket.cache_clear


def public_policy():
    policy = cached_policy()
    return {key: policy[key] for key in PUBLIC_KEYS}
