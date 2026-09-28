"""Deterministic, PII-free campaign links. Never modifies recovery/signed links."""
import ipaddress
import re
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


def campaign_link(url,campaign_key,block_key,*,test=True,kind='content'):
    if kind!='content' or not public_https(url): return url
    p=urlsplit(url); pairs=parse_qsl(p.query,keep_blank_values=True)
    protected={'signature','token','key','checkout','hmac','x-amz-signature','x-goog-signature','expires'}
    if re.search(r'/(checkouts?|recover|unsubscribe|privacy)(/|$)',p.path,re.I) or any(k.lower() in protected for k,v in pairs): return url
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',campaign_key) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',block_key): raise ValueError('Invalid tracking reference.')
    keys={'utm_source','utm_medium','utm_campaign','utm_content','sc_test'}
    pairs=[(k,v) for k,v in pairs if k.lower() not in keys]
    pairs += [('utm_source','sports_cave'),('utm_medium','email'),('utm_campaign',campaign_key),('utm_content',block_key)]
    if test: pairs.append(('sc_test','1'))
    return urlunsplit((p.scheme,p.netloc,p.path,urlencode(pairs),p.fragment))
