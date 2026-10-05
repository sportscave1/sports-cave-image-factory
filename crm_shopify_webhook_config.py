"""Non-secret webhook configuration and receiver-owned readiness.

The UI and leased CRM worker do not own the receiver's HMAC environment.
Never copy a webhook signing secret into those services for diagnostics.
"""
import os
from urllib.parse import urlsplit

CANONICAL_BASE = 'https://sports-cave-os-webhooks.onrender.com'
READINESS_PATH = '/webhooks/shopify/readiness'
SECRET_ENV_NAMES = ('SHOPIFY_WEBHOOK_SECRET', 'SHOPIFY_API_SECRET_KEY',
                    'SHOPIFY_API_SECRET', 'SHOPIFY_SHARED_SECRET', 'SHOPIFY_CLIENT_SECRET')
# shpss_ is a Shopify shared/app secret, NOT an Admin access token.
ADMIN_TOKEN_PREFIXES = ('shpat_', 'shpca_', 'shppa_')
HMAC_STATUSES = ('CONFIGURED', 'VERIFIED', 'MISSING',
                 'MALFORMED — Admin API token is not a webhook secret')


class ReceiverReadinessError(ValueError):
    """Safe diagnostic reason only; never includes response bodies or credentials."""


def base_url(env=None):
    env = os.environ if env is None else env
    value = (env.get('SPORTS_CAVE_WEBHOOK_BASE_URL') or env.get('CRM_PUBLIC_BASE_URL') or
             (CANONICAL_BASE if env.get('RENDER') or env.get('RENDER_SERVICE_NAME') else '')).strip().rstrip('/')
    from crm_tracking import public_https
    if not public_https(value):
        return ''
    parsed = urlsplit(value)
    if parsed.path or parsed.query or parsed.fragment:
        return ''
    return value


def callbacks(env=None):
    base = base_url(env)
    return {'crm': base + '/webhooks/shopify/crm', 'paid': base + '/webhooks/shopify/orders-paid'}


def hmac_configuration(env=None):
    env = os.environ if env is None else env
    values = [env.get(name, '').strip() for name in SECRET_ENV_NAMES if env.get(name, '').strip()]
    usable = any(not value.startswith(ADMIN_TOKEN_PREFIXES) for value in values)
    return 'CONFIGURED' if usable else 'MALFORMED — Admin API token is not a webhook secret' if values else 'MISSING'


def receiver_readiness(env=None):
    """Bounded HTTPS read. Reject redirects/malformed reports; never infer readiness."""
    import requests
    base = base_url(env)
    if not base:
        raise ReceiverReadinessError('Invalid HTTPS receiver base URL')
    try:
        response = requests.get(base + READINESS_PATH, timeout=(3, 5), allow_redirects=False)
    except requests.Timeout:
        raise ReceiverReadinessError('Receiver timed out') from None
    except requests.RequestException:
        raise ReceiverReadinessError('Receiver unreachable') from None
    if response.status_code != 200:
        raise ReceiverReadinessError('Receiver HTTP ' + str(response.status_code))
    if len(response.content) > 4096:
        raise ReceiverReadinessError('Receiver response exceeds 4096 bytes')
    try:
        report = response.json()
    except ValueError:
        raise ReceiverReadinessError('Receiver returned invalid JSON') from None
    if (not isinstance(report, dict) or report.get('service') != 'sports-cave-os-webhooks' or
        not isinstance(report.get('base_url'), str) or
        not isinstance(report.get('api_version'), str) or
        type(report.get('routes_ready')) is not bool or
        not isinstance(report.get('callbacks'), dict) or
        set(report['callbacks']) != {'crm', 'paid'} or
        any(not isinstance(v, str) for v in report['callbacks'].values()) or
        report.get('hmac_status') not in HMAC_STATUSES or
        ('receiver_reachable' in report and report['receiver_reachable'] is not True)):
        raise ReceiverReadinessError('Receiver returned a malformed readiness report')
    return report


def receiver_callback_status(report, env=None):
    """Distinguish a reachable but misconfigured receiver from transport failure."""
    if not report['base_url']:
        return 'MISSING / INVALID HTTPS BASE URL — receiver configuration'
    if report['base_url'] != base_url(env):
        return 'UNVERIFIED — receiver base URL mismatch'
    if report['callbacks'] != callbacks(env):
        return 'UNVERIFIED — receiver callback routes mismatch'
    if not report['routes_ready']:
        return 'UNVERIFIED — receiver callback routes missing'
    if report['api_version'] != '2026-04':
        return 'UNVERIFIED — receiver API version mismatch (requires 2026-04)'
    return 'VERIFIED'
