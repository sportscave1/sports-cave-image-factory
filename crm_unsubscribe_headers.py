"""RFC 8058 headers use the existing signed, suppression-first POST endpoint."""
from crm_tracking import public_https
from urllib.parse import urlsplit


def configured(config):
    secret=getattr(config,'secret','')
    base=getattr(config,'public_base','')
    return bool(isinstance(secret,str) and len(secret)>=32 and isinstance(base,str) and public_https(base)
                and not any(c in base for c in '<>') and not urlsplit(base).query and not urlsplit(base).fragment)


def headers(config,send_id,native_url,*,test=False):
    """Keep the native body link; advertise POST only for our own signed route.

    Missing legacy signing configuration retains the native navigation header.
    It must not interrupt an otherwise valid Shopify-native delivery.
    """
    if not isinstance(native_url,str) or not public_https(native_url) or any(ord(c)<33 for c in native_url) or any(c in native_url for c in '<>'):
        raise ValueError('Invalid unsubscribe header URL.')
    result={'List-Unsubscribe':'<'+native_url+'>'}
    if not test and configured(config):
        result={'List-Unsubscribe':'<'+config.unsubscribe_url(send_id)+'>',
                'List-Unsubscribe-Post':'List-Unsubscribe=One-Click'}
    return result
