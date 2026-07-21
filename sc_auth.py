import base64
import hashlib
import hmac
import json
import secrets
import time


AUTH_COOKIE_NAME = "sports_cave_auth"
DEFAULT_APP_PASSWORD = "Sportscaveshop26!"
DEFAULT_AUTH_DAYS = 30
TOKEN_VERSION = 1
USER_TOKEN_VERSION = 2
PASSWORD_HASH_SCHEME = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 310_000


def password_matches(candidate, expected=DEFAULT_APP_PASSWORD):
    return hmac.compare_digest(str(candidate or ""), str(expected or ""))


def hash_password(password, *, iterations=PASSWORD_HASH_ITERATIONS, salt=None):
    password = str(password or "")
    if not password:
        raise ValueError("Password is required.")
    rounds = max(int(iterations), 100_000)
    raw_salt = salt if isinstance(salt, bytes) else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), raw_salt, rounds)
    return f"{PASSWORD_HASH_SCHEME}${rounds}${_b64_encode(raw_salt)}${_b64_encode(digest)}"


def verify_password(password, stored_hash):
    try:
        scheme, rounds_text, salt_text, digest_text = str(stored_hash or "").split("$", 3)
        if scheme != PASSWORD_HASH_SCHEME:
            return False
        rounds = int(rounds_text)
        if rounds < 100_000:
            return False
        salt = _b64_decode(salt_text)
        expected = _b64_decode(digest_text)
        supplied = hashlib.pbkdf2_hmac(
            "sha256",
            str(password or "").encode("utf-8"),
            salt,
            rounds,
        )
    except (TypeError, ValueError, UnicodeError):
        return False
    return hmac.compare_digest(supplied, expected)


def _signing_key(password=DEFAULT_APP_PASSWORD, extra_secret=""):
    material = f"sports-cave-auth-v{TOKEN_VERSION}|{password}|{extra_secret or ''}"
    return hashlib.sha256(material.encode("utf-8")).digest()


def _b64_encode(raw):
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64_decode(value):
    padded = value + ("=" * (-len(value) % 4))
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def create_auth_token(
    *,
    password=DEFAULT_APP_PASSWORD,
    extra_secret="",
    now=None,
    days=DEFAULT_AUTH_DAYS,
):
    issued_at = int(time.time() if now is None else now)
    expires_at = issued_at + int(days * 24 * 60 * 60)
    payload = {
        "v": TOKEN_VERSION,
        "iat": issued_at,
        "exp": expires_at,
        "nonce": secrets.token_urlsafe(16),
    }
    payload_part = _b64_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature = hmac.new(
        _signing_key(password=password, extra_secret=extra_secret),
        payload_part.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{payload_part}.{_b64_encode(signature)}"


def create_user_auth_token(
    user_id,
    *,
    password=DEFAULT_APP_PASSWORD,
    extra_secret="",
    now=None,
    days=DEFAULT_AUTH_DAYS,
):
    clean_user_id = str(user_id or "").strip()
    if not clean_user_id:
        raise ValueError("User id is required.")
    issued_at = int(time.time() if now is None else now)
    expires_at = issued_at + int(days * 24 * 60 * 60)
    payload = {
        "v": USER_TOKEN_VERSION,
        "sub": clean_user_id,
        "iat": issued_at,
        "exp": expires_at,
        "nonce": secrets.token_urlsafe(16),
    }
    payload_part = _b64_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature = hmac.new(
        _signing_key(password=password, extra_secret=extra_secret),
        payload_part.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{payload_part}.{_b64_encode(signature)}"


def validate_auth_token(
    token,
    *,
    password=DEFAULT_APP_PASSWORD,
    extra_secret="",
    now=None,
):
    if not token or "." not in str(token):
        return False, "missing"

    payload_part, signature_part = str(token).split(".", 1)
    expected_signature = hmac.new(
        _signing_key(password=password, extra_secret=extra_secret),
        payload_part.encode("ascii"),
        hashlib.sha256,
    ).digest()

    try:
        supplied_signature = _b64_decode(signature_part)
    except Exception:
        return False, "bad-signature"

    if not hmac.compare_digest(supplied_signature, expected_signature):
        return False, "bad-signature"

    try:
        payload = json.loads(_b64_decode(payload_part).decode("utf-8"))
    except Exception:
        return False, "bad-payload"

    if payload.get("v") != TOKEN_VERSION:
        return False, "bad-version"

    current_time = int(time.time() if now is None else now)
    try:
        expires_at = int(payload["exp"])
    except (KeyError, TypeError, ValueError):
        return False, "bad-expiry"

    if expires_at <= current_time:
        return False, "expired"

    return True, "ok"


def validate_user_auth_token(
    token,
    *,
    password=DEFAULT_APP_PASSWORD,
    extra_secret="",
    now=None,
):
    if not token or "." not in str(token):
        return False, "missing", {}
    payload_part, signature_part = str(token).split(".", 1)
    expected_signature = hmac.new(
        _signing_key(password=password, extra_secret=extra_secret),
        payload_part.encode("ascii"),
        hashlib.sha256,
    ).digest()
    try:
        supplied_signature = _b64_decode(signature_part)
    except Exception:
        return False, "bad-signature", {}
    if not hmac.compare_digest(supplied_signature, expected_signature):
        return False, "bad-signature", {}
    try:
        payload = json.loads(_b64_decode(payload_part).decode("utf-8"))
    except Exception:
        return False, "bad-payload", {}
    if payload.get("v") != USER_TOKEN_VERSION:
        return False, "bad-version", {}
    user_id = str(payload.get("sub") or "").strip()
    if not user_id:
        return False, "bad-user", {}
    current_time = int(time.time() if now is None else now)
    try:
        expires_at = int(payload["exp"])
    except (KeyError, TypeError, ValueError):
        return False, "bad-expiry", {}
    if expires_at <= current_time:
        return False, "expired", {}
    return True, "ok", payload


def auth_cookie_max_age(days=DEFAULT_AUTH_DAYS):
    return int(days * 24 * 60 * 60)
