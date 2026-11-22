"""Managed customer identity and opaque, server-side sessions. Never grants OS access."""
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import time

import requests

from marketplace import BASE_PATH, PUBLIC_ORIGIN, clean_text, email, identifier, now
from marketplace_store import PREFIX, read, put, lock

COOKIE = '__Secure-sc-marketplace'
FLOW_COOKIE = '__Secure-sc-marketplace-recovery'
NEXT_COOKIE = '__Secure-sc-marketplace-next'
MAX_AGE = 60 * 60 * 24 * 14


class SignInRequired(PermissionError):
    pass


class AuthUnavailable(RuntimeError):
    pass


def digest(value):
    return hashlib.sha256(str(value).encode()).hexdigest()


def prune_expired(conn, kind):
    if kind not in ('session:', 'recovery:'):
        raise ValueError('Invalid temporary record type.')
    conn.execute('''DELETE FROM crm_runtime_state WHERE key IN (
        SELECT key FROM crm_runtime_state WHERE key > %s AND key < %s
        AND COALESCE((value->>'expires')::double precision,0) < %s ORDER BY key LIMIT 25)''',
        (PREFIX + kind, PREFIX + kind + '~', time.time()))


def password(value):
    value = str(value or '')
    if not 12 <= len(value) <= 128:
        raise ValueError('Use a password between 12 and 128 characters.')
    return value


def safe_next(value):
    from urllib.parse import urlsplit
    value = str(value or '')
    try:
        part = urlsplit(value)
    except ValueError:
        return BASE_PATH + '/inbox'
    if (part.scheme or part.netloc or '\\' in value or any(ord(c) < 32 for c in value)
            or not part.path.startswith(BASE_PATH + '/') or part.path.startswith(BASE_PATH + '/auth/')):
        return BASE_PATH + '/inbox'
    return value[:500]


class Provider:
    """Supabase Auth REST API. Only its publishable key is needed, never service_role."""
    def __init__(self, config=None, transport=None):
        if config is None:
            config = json.loads(Path(__file__).with_name('marketplace_auth_public.json').read_text())
            url, key = os.getenv('MARKETPLACE_SUPABASE_URL'), os.getenv('MARKETPLACE_SUPABASE_PUBLISHABLE_KEY')
            if url or key:
                config = {'url': url, 'key': key}
        self.url, self.key = config.get('url', ''), config.get('key', '')
        from urllib.parse import urlsplit
        parsed = urlsplit(self.url or '')
        if (parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.supabase.co')
                or parsed.path not in ('', '/') or parsed.query or parsed.fragment or parsed.username
                or parsed.port or not str(self.key).startswith('sb_publishable_')):
            raise AuthUnavailable('Account setup is temporarily unavailable.')
        self.transport = transport or requests

    def call(self, method, path, data=None, *, token=None, params=None):
        headers = {'apikey': self.key, 'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        try:
            response = self.transport.request(method, self.url.rstrip('/') + '/auth/v1/' + path,
                json=data, params=params, headers=headers, timeout=(5, 12), allow_redirects=False)
            if response.status_code >= 500 or response.status_code in (301, 302, 307, 308):
                raise AuthUnavailable('Accounts are temporarily unavailable. Please try again shortly.')
            if response.status_code == 429:
                raise ValueError('Please wait before trying again. Check your email for an existing link.')
            if response.status_code >= 400:
                code = response.json().get('code') or response.json().get('error_code')
                if code in ('email_address_not_authorized', 'email_provider_disabled', 'unexpected_failure', 'over_email_send_rate_limit'):
                    raise AuthUnavailable('Account emails are temporarily unavailable. Please try again later.')
                raise SignInRequired('Check your email and password, or confirm your email before signing in.')
            return response.json() if response.content else {}
        except requests.RequestException:
            raise AuthUnavailable('Accounts are temporarily unavailable. Please try again shortly.') from None
        except (ValueError, TypeError) as exc:
            if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError):
                raise
            raise AuthUnavailable('Accounts are temporarily unavailable. Please try again shortly.') from None

    def signup(self, address, secret, name):
        self.call('POST', 'signup', {'email': address, 'password': password(secret),
            'data': {'display_name': clean_text(name, 'your display name', 70)}},
            params={'redirect_to': PUBLIC_ORIGIN + BASE_PATH + '/account/confirmed'})

    def signin(self, address, secret):
        if not secret or len(str(secret)) > 128:
            raise SignInRequired('Check your email and password.')
        return self.call('POST', 'token', {'email': address, 'password': secret}, params={'grant_type': 'password'})

    def user(self, token):
        user = self.call('GET', 'user', token=token)
        if not user.get('email_confirmed_at') or user.get('is_anonymous'):
            raise SignInRequired('Confirm your email before signing in.')
        return user

    def refresh(self, token):
        return self.call('POST', 'token', {'refresh_token': token}, params={'grant_type': 'refresh_token'})

    def logout(self, token):
        self.call('POST', 'logout', token=token, params={'scope': 'local'})


def token_session(token, user_id):
    # Decode only AFTER the provider verified this token via /user. These claims
    # are never accepted directly from a request or treated as a signature check.
    try:
        claims = json.loads(base64.urlsafe_b64decode(token.split('.')[1] + '==='))
        if identifier(claims['sub']) != identifier(user_id):
            raise ValueError
        return identifier(claims['session_id'])
    except (ValueError, KeyError, IndexError, TypeError):
        raise SignInRequired('Please sign in again.') from None


class Accounts:
    def __init__(self, store, provider=None):
        self.store, self.provider = store, provider or Provider()

    def _profile(self, conn, user):
        uid, address = identifier(user['id']), email(user['email'])
        row = read(conn, 'account:' + uid)
        owner = read(conn, 'account-email:' + digest(address))
        if owner and owner['id'] != uid:
            raise PermissionError('Contact Sports Cave to restore access to this marketplace account.')
        if row and (row['status'] != 'active' or row['email'] != address):
            raise PermissionError('Contact Sports Cave about access to your marketplace account.')
        if not row:
            name = clean_text(user.get('user_metadata', {}).get('display_name') or 'Collector', 'display name', 70)
            row = {'id': uid, 'email': address, 'name': name, 'status': 'active', 'created_at': now()}
            put(conn, 'account:' + uid, row)
            put(conn, 'account-email:' + digest(address), {'id': uid})
            invitation = read(conn, 'invitation:' + digest(address))
            if invitation:
                invitation.update(status='joined', user_id=uid, joined_at=now())
                put(conn, 'invitation:' + digest(address), invitation)
        return row

    def signin(self, address, secret):
        tokens = self.provider.signin(email(address), secret)
        user = self.provider.user(tokens['access_token'])
        sid = token_session(tokens['access_token'], user['id'])
        bearer = secrets.token_urlsafe(32)
        with self.store.db() as conn:
            lock(conn, 'account-email:' + digest(user['email'].lower()))
            profile = self._profile(conn, user)
            self._check_provider_session(conn, sid, profile['id'])
            prune_expired(conn, 'session:')
            put(conn, 'session:' + digest(bearer), {'user_id': profile['id'], 'provider_session': sid,
                'access_token': tokens['access_token'], 'refresh_token': tokens['refresh_token'],
                'token_expires': time.time() + int(tokens.get('expires_in', 3600)),
                'expires': time.time() + MAX_AGE, 'verified_at': time.time()})
        return bearer, profile

    @staticmethod
    def _check_provider_session(conn, sid, uid):
        result = conn.execute('''SELECT id FROM auth.sessions WHERE id=%s AND user_id=%s
            AND (not_after IS NULL OR not_after > now())''', (sid, uid)).fetchone()
        if not result:
            raise SignInRequired('Your session ended. Please sign in again.')

    def authenticate(self, bearer):
        if not bearer or len(bearer) > 100:
            raise SignInRequired('Create an account or sign in to continue.')
        key = 'session:' + digest(bearer)
        with self.store.db() as conn:
            lock(conn, key)
            session = read(conn, key)
            if not session or session.get('revoked') or session['expires'] <= time.time():
                raise SignInRequired('Your session ended. Please sign in again.')
            self._check_provider_session(conn, session['provider_session'], session['user_id'])
            profile = read(conn, 'account:' + session['user_id'])
            if not profile or profile['status'] != 'active':
                raise PermissionError('Contact Sports Cave about access to your marketplace account.')
            if session['token_expires'] < time.time() + 90:
                tokens = self.provider.refresh(session['refresh_token'])
                user = self.provider.user(tokens['access_token'])
                if identifier(user['id']) != profile['id'] or email(user['email']) != profile['email']:
                    raise SignInRequired('Please sign in again.')
                session.update(access_token=tokens['access_token'], refresh_token=tokens['refresh_token'],
                    token_expires=time.time() + int(tokens.get('expires_in', 3600)), verified_at=time.time(),
                    provider_session=token_session(tokens['access_token'], profile['id']))
                self._check_provider_session(conn, session['provider_session'], profile['id'])
                put(conn, key, session)
            elif session['verified_at'] < time.time() - 300:
                user = self.provider.user(session['access_token'])
                if identifier(user['id']) != profile['id'] or email(user['email']) != profile['email']:
                    raise SignInRequired('Please sign in again.')
                session['verified_at'] = time.time()
                put(conn, key, session)
        return profile

    def logout(self, bearer):
        key = 'session:' + digest(bearer or '')
        with self.store.db() as conn:
            lock(conn, key)
            session = read(conn, key)
            if session:
                # Local revocation succeeds even during a provider outage.
                put(conn, key, {'revoked': True, 'expires': 0})
        if session and not session.get('revoked'):
            try:
                self.provider.logout(session['access_token'])
            except (AuthUnavailable, SignInRequired, ValueError):
                pass

    def recover(self, address):
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        bearer = secrets.token_urlsafe(32)
        self.provider.call('POST', 'recover', {'email': email(address), 'code_challenge': challenge,
            'code_challenge_method': 's256'}, params={'redirect_to': PUBLIC_ORIGIN + BASE_PATH + '/auth/recovery'})
        with self.store.db() as conn:
            prune_expired(conn, 'recovery:')
            put(conn, 'recovery:' + digest(bearer), {'verifier': verifier, 'email': email(address),
                'expires': time.time() + 900})
        return bearer

    def recovery_exchange(self, bearer, code):
        if not bearer or not code or len(code) > 500:
            raise ValueError('Open the reset email in the browser where you requested it, or request a new link.')
        with self.store.db() as conn:
            key = 'recovery:' + digest(bearer)
            lock(conn, key)
            flow = read(conn, key, {})
            if flow.get('expires', 0) <= time.time() or not flow.get('verifier'):
                raise ValueError('This reset link expired. Please request another.')
            tokens = self.provider.call('POST', 'token', {'auth_code': code, 'code_verifier': flow['verifier']},
                                        params={'grant_type': 'pkce'})
            user = self.provider.user(tokens['access_token'])
            if email(user['email']) != flow['email']:
                raise PermissionError('Please request a new password reset link.')
            put(conn, key, {'email': flow['email'], 'expires': time.time() + 600,
                           'access_token': tokens['access_token']})

    def reset_password(self, bearer, secret):
        secret = password(secret)
        with self.store.db() as conn:
            key = 'recovery:' + digest(bearer or '')
            lock(conn, key)
            flow = read(conn, key, {})
            if flow.get('expires', 0) <= time.time() or not flow.get('access_token'):
                raise SignInRequired('Request a new password reset link.')
            if not flow.get('password_updated'):
                self.provider.call('PUT', 'user', {'password': secret}, token=flow['access_token'])
                flow['password_updated'] = True
                put(conn, key, flow)
        # Save completion before logout: a provider outage must not roll back
        # the fact that the password changed or cause us to change it twice.
        with self.store.db() as conn:
            lock(conn, key)
            flow = read(conn, key, {})
            if not flow.get('password_updated') or flow.get('expires', 0) <= time.time():
                raise SignInRequired('Sign in with your new password, or request a new reset link.')
            # Provider global logout also invalidates older app sessions because
            # every protected request checks auth.sessions, not just JWT expiry.
            self.provider.call('POST', 'logout', token=flow['access_token'], params={'scope': 'global'})
            put(conn, key, {'expires': 0})
