"""Bounded advisory HEAD metadata cache. No response bodies, redirects or logs."""
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import time
from urllib.parse import urlsplit

_POOL=ThreadPoolExecutor(max_workers=2,thread_name_prefix='email-asset-size')
_LOCK=Lock()
_CACHE={}


def head_size(url):
    # Only public Shopify CDN assets are probed automatically. Other hosts are
    # Unknown; never turn arbitrary campaign URLs into server-side requests.
    try:
        parts=urlsplit(url)
        if parts.scheme!='https' or parts.hostname!='cdn.shopify.com' or parts.port not in (None,443) or parts.username:return None
        import requests
        with requests.head(url,timeout=(1,1),allow_redirects=False) as response:
            value=response.headers.get('Content-Length','')
            return int(value) if response.status_code==200 and value.isdigit() else None
    except Exception:return None


def metadata(urls,start=False):
    result={};at=time.monotonic()
    with _LOCK:
        # Bound retained URLs and outstanding tasks across sessions.
        for url,(created,future) in list(_CACHE.items()):
            if future.done() and (at-created>3600 or len(_CACHE)>512):del _CACHE[url]
        pending=sum(not future.done() for _,future in _CACHE.values())
        for url in dict.fromkeys(urls):
            entry=_CACHE.get(url)
            if entry is None and start and pending<32 and len(_CACHE)<512:
                future=_POOL.submit(head_size,url);entry=(at,future);_CACHE[url]=entry;pending+=1
            if entry and entry[1].done():
                try:result[url]=entry[1].result()
                except Exception:result[url]=None
            else:result[url]=None
    return result
