"""Short-lived signed permission snapshots for the Sports Cave OS top bar."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

import sc_auth


TOP_BAR_TOKEN_VERSION = 1
TOP_BAR_TOKEN_SECONDS = 60 * 60


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    padded = str(value or "") + ("=" * (-len(str(value or "")) % 4))
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _signing_key(extra_secret: str = "") -> bytes:
    secret = str(
        extra_secret
        or os.getenv("SPORTS_CAVE_AUTH_SECRET")
        or ""
    ).strip()
    material = (
        f"sports-cave-top-bar-v{TOP_BAR_TOKEN_VERSION}|"
        f"{sc_auth.DEFAULT_APP_PASSWORD}|{secret}"
    )
    return hashlib.sha256(material.encode("utf-8")).digest()


def create_top_bar_token(
    user,
    *,
    allowed_routes=(),
    can_view_activity=False,
    can_view_all_activity=False,
    now=None,
    seconds=TOP_BAR_TOKEN_SECONDS,
    extra_secret="",
) -> str:
    """Sign only the safe identity and permission data needed by utility APIs."""
    user = dict(user or {})
    issued_at = int(time.time() if now is None else now)
    payload = {
        "v": TOP_BAR_TOKEN_VERSION,
        "sub": str(user.get("id") or "").strip(),
        "display_name": str(user.get("display_name") or "").strip()[:160],
        "username": str(user.get("username") or "").strip()[:160],
        "role": str(user.get("role") or "").strip().casefold()[:40],
        "allowed_routes": sorted(
            {
                str(route or "").strip()
                for route in allowed_routes
                if str(route or "").strip()
            }
        ),
        "can_view_activity": bool(can_view_activity),
        "can_view_all_activity": bool(can_view_all_activity),
        "iat": issued_at,
        "exp": issued_at + max(int(seconds), 60),
        "nonce": secrets.token_urlsafe(12),
    }
    payload_part = _encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature = hmac.new(
        _signing_key(extra_secret),
        payload_part.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{payload_part}.{_encode(signature)}"


def validate_top_bar_token(token, *, now=None, extra_secret=""):
    """Validate a signed top-bar token and return its claims."""
    if not token or "." not in str(token):
        return False, "missing", {}
    payload_part, signature_part = str(token).split(".", 1)
    expected = hmac.new(
        _signing_key(extra_secret),
        payload_part.encode("ascii"),
        hashlib.sha256,
    ).digest()
    try:
        supplied = _decode(signature_part)
    except Exception:
        return False, "bad-signature", {}
    if not hmac.compare_digest(supplied, expected):
        return False, "bad-signature", {}
    try:
        payload = json.loads(_decode(payload_part).decode("utf-8"))
    except Exception:
        return False, "bad-payload", {}
    if payload.get("v") != TOP_BAR_TOKEN_VERSION:
        return False, "bad-version", {}
    if int(payload.get("exp") or 0) <= int(time.time() if now is None else now):
        return False, "expired", {}
    if not str(payload.get("sub") or "").strip():
        return False, "bad-user", {}
    return True, "ok", payload
