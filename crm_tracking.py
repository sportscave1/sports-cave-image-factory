"""Deterministic, PII-free campaign links. Never modifies recovery/signed links."""
import ipaddress
import re
import os
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode


def public_https(value):
    if not isinstance(value,str) or len(value)>2000 or any(c.isspace() or ord(c)<32 for c in value): return False
    try:
        p=urlsplit(value)
        if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443): return False
        host=p.hostname.lower()
        if host=='localhost' or host.endswith(('.localhost','.local','.internal')) or '.' not in host: return False
        try: return ipaddress.ip_address(host).is_global
        except ValueError: return True
    except ValueError: return False


def asset_url(value):
    """No server fetching: SSRF impossible. Only durable public JPEG/PNG references."""
    if not public_https(value): return False
    p=urlsplit(value); keys={k.lower() for k,v in parse_qsl(p.query)}
    cdn_jpeg=p.hostname=='cdn.shopify.com' and dict(parse_qsl(p.query)).get('format')=='jpg'
    return bool((re.search(r'\.(jpe?g|png)$',p.path,re.I) or cdn_jpeg) and not keys.intersection(
        {'token','signature','expires','x-amz-signature','x-goog-signature','se','sig'}))


def campaign_link(url,campaign_key,block_key,*,test=True,kind='content',legacy=False):
    if kind!='content' or not public_https(url): return url
    p=urlsplit(url); pairs=parse_qsl(p.query,keep_blank_values=True)
    if not legacy and not store_host(p.hostname):return url
    protected={'signature','token','key','checkout','hmac','x-amz-signature','x-goog-signature','expires'}
    paths=r'/(checkouts?|recover|unsubscribe|privacy)(/|$)' if legacy else r'/(account|checkouts?|recover|unsubscribe|privacy|policies)(/|$)'
    if re.search(paths,p.path,re.I) or any(k.lower() in protected for k,v in pairs): return url
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',campaign_key) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',block_key): raise ValueError('Invalid tracking reference.')
    keys={'utm_source','utm_medium','utm_campaign','utm_content','sc_test'}
    if not legacy:keys.add('sc_campaign_id')
    pairs=[(k,v) for k,v in pairs if k.lower() not in keys]
    pairs += [('utm_source','sports_cave' if legacy else 'sports_cave_os'),('utm_medium','email'),('utm_campaign',campaign_key),('utm_content',block_key)]
    if not legacy:pairs.append(('sc_campaign_id',campaign_key))
    if test: pairs.append(('sc_test','1'))
    return urlunsplit((p.scheme,p.netloc,p.path,urlencode(pairs),p.fragment))

def store_host(host):
    hosts={'sportscaveshop.com','www.sportscaveshop.com','sportscave-nb.myshopify.com'}
    for setting in ('CRM_BUSINESS_WEBSITE','SHOPIFY_STORE_DOMAIN'):
        value=os.getenv(setting,'')
        if value:hosts.add((urlsplit(value if '://' in value else 'https://'+value).hostname or '').lower())
    return (host or '').lower() in hosts

def event_link(url):
    """Keep attribution evidence only. Drop tokens, PII query parameters and fragments."""
    if not public_https(url):return None
    p=urlsplit(url)
    if not store_host(p.hostname):return None
    if re.search(r'/(account|checkouts?|recover|unsubscribe)(/|$)',p.path,re.I):return None
    pairs=[(k,v) for k,v in parse_qsl(p.query) if k in ('utm_source','utm_medium','utm_campaign','utm_content','sc_campaign_id','sc_test')]
    return urlunsplit((p.scheme,p.netloc,p.path,urlencode(pairs),''))
