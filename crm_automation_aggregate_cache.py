"""Process-local last-success aggregates only. No recipients, disk or DB writes."""
from collections import OrderedDict
from copy import deepcopy
from threading import RLock
from time import monotonic
from datetime import datetime,timezone

FRESH_SECONDS=180
RETENTION_SECONDS=3600
MAX_SCOPES=32
_entries=OrderedDict()
_lock=RLock()


def scope(connect,user,namespace):
    actor=user.get('id') or user.get('username')
    if not actor or not isinstance(namespace,str) or not namespace.strip():return None
    return (connect,str(actor),namespace,'rolling-30-day-utc-v1')


def bucket(identity):
    if identity is None:return None
    at=monotonic()
    with _lock:
        for key in list(_entries):
            if at-_entries[key]['used']>RETENTION_SECONDS:_entries.pop(key)
        if identity not in _entries:_entries[identity]={'used':at,'values':{},'epochs':{}}
        value=_entries[identity];value['used']=at;_entries.move_to_end(identity)
        while len(_entries)>MAX_SCOPES:_entries.popitem(last=False)
        return value


def get(identity,group):
    with _lock:
        item=bucket(identity)
        if item is None:return None
        value=item['values'].get(group)
        if value and monotonic()-value['at']<=RETENTION_SECONDS:return deepcopy(value)
        item['values'].pop(group,None)
        return None


def token(identity,group):
    with _lock:
        item=bucket(identity)
        return (item,item['epochs'].get(group,0)) if item is not None else None


def put(identity,group,value,started,window=None):
    if started is None:return
    with _lock:
        item=_entries.get(identity)
        if item is not started[0] or item['epochs'].get(group,0)!=started[1]:return
        item['values'][group]={'value':deepcopy(value),'at':monotonic(),
          'updated_at':datetime.now(timezone.utc).isoformat(),'window':window}


def invalidate(identity,groups=('counts',)):
    with _lock:
        item=bucket(identity)
        if item is None:return
        for group in groups:
            item['epochs'][group]=item['epochs'].get(group,0)+1
            # Retain labelled last-good display, but force a fresh calculation.
            if group in item['values']:item['values'][group]['expired']=True
