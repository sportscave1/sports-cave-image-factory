"""Shopify-only image flags. No work is performed at module import or OS startup."""
import threading
import time
import logging

SETTING_KEY = 'storefront_image_protection'
DEFAULTS = dict(enabled=True, disableRightClick=True, preventImageDragging=True,
                preventSelection=True, aggressiveCopyDeterrence=True,
                mobileTouchProtection=True, protectPrinting=True,
                blockSaveShortcuts=True, showCopyrightMessage=True,
                visibleWatermark=False, protectProductImages=True,
                protectCollections=True, protectHomepage=True, protectWallPreview=True,
                screenshotDeterrence=True, wallPreviewWatermark=False,
                watermarkText='Sports Cave', watermarkOpacity=0.25,
                watermarkPosition='bottom-right')
PUBLIC_ORIGIN = 'https://sports-cave-image-factory.onrender.com'
SCRIPT_VERSION = '2026-10-06.3'
_cache = None
_expires = 0.0
_lock = threading.Lock()


def clean_policy(value):
    if not isinstance(value, dict) or set(value)-set(DEFAULTS):
        raise ValueError('Unsupported image protection setting.')
    if any(type(value[k]) is not bool for k in value if type(DEFAULTS[k]) is bool):
        raise ValueError('Image protection switches must be true or false.')
    text = value.get('watermarkText', DEFAULTS['watermarkText'])
    opacity = value.get('watermarkOpacity', DEFAULTS['watermarkOpacity'])
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 60 or any(ord(c)<32 for c in text):
        raise ValueError('Watermark text must contain 1–60 printable characters.')
    if type(opacity) not in (float, int) or not 0.05 <= opacity <= 0.6:
        raise ValueError('Watermark opacity must be between 0.05 and 0.6.')
    if value.get('watermarkPosition', DEFAULTS['watermarkPosition']) not in ('bottom-right','center'):
        raise ValueError('Unsupported watermark position.')
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
    try:
        supabase_backend.record_activity_log(action_type='storefront_image_protection_updated',
            page='Image Protection',message='Updated public storefront image protection settings',
            entity_type='app_setting',entity_id=SETTING_KEY,metadata={'settings':values},
            actor=str(user.get('id') or 'admin'))
    except Exception:
        logging.getLogger(__name__).warning('image_protection_settings_audit_unavailable')
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
                _cache = {**DEFAULTS, 'enabled': False}
            _expires = time.monotonic()+60
        return dict(_cache)


def last_updated():
    """Settings page only; no schema changes or providers."""
    import supabase_backend
    with supabase_backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT updated_at FROM app_settings WHERE key=%s',(SETTING_KEY,))
            row=cur.fetchone()
    return str(row['updated_at']) if row else 'Default settings — not saved yet'
