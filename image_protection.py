"""Shopify-only image flags. No work is performed at module import or OS startup."""
import threading
import time

SETTING_KEY = 'storefront_image_protection'
DEFAULTS = dict(enabled=True, disableRightClick=True, preventImageDragging=True,
                preventSelection=True, aggressiveCopyDeterrence=True,
                mobileTouchProtection=True, protectPrinting=True,
                blockSaveShortcuts=True, showCopyrightMessage=True,
                visibleWatermark=False)
_cache = None
_expires = 0.0
_lock = threading.Lock()


def clean_policy(value):
    if not isinstance(value, dict) or set(value)-set(DEFAULTS):
        raise ValueError('Unsupported image protection setting.')
    if any(type(v) is not bool for v in value.values()):
        raise ValueError('Image protection switches must be true or false.')
    return {**DEFAULTS, **value}


def load_policy():
    import supabase_backend
    return clean_policy(supabase_backend.get_app_setting(SETTING_KEY, {}, ensure_schema_first=False))


def save_policy(user, values):
    import os_accounts
    if not os_accounts.is_admin(user) or not os_accounts.account_is_active(user):
        raise PermissionError('Administrator access required.')
    values = clean_policy(values)
    import supabase_backend
    supabase_backend.set_app_setting(SETTING_KEY, values, ensure_schema_first=False)
    global _cache, _expires
    with _lock:
        _cache, _expires = values, time.monotonic()+60


def public_policy():
    global _cache, _expires
    with _lock:
        if time.monotonic() >= _expires:
            try:
                _cache = load_policy()
            except Exception:
                # Also cache failures, avoiding repeated database work during an outage.
                _cache = _cache or dict(DEFAULTS)
            _expires = time.monotonic()+60
        return dict(_cache)
