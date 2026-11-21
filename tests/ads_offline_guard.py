"""Opt-in regression guard: forbid real provider I/O; fixtures may replace adapters."""
from urllib.parse import urlsplit


def pytest_configure(config):
    import requests
    import supabase_backend
    original=requests.sessions.Session.request
    def request(session,method,url,*args,**kwargs):
        if urlsplit(str(url)).hostname not in ('127.0.0.1','localhost','::1'):
            raise AssertionError('Ads regression attempted unmocked provider HTTP')
        return original(session,method,url,*args,**kwargs)
    requests.sessions.Session.request=request
    def database(*args,**kwargs):
        raise AssertionError('Ads regression attempted an unmocked production database connection')
    supabase_backend.connect=database
