"""Private cross-service thumbnail assets and short, fenced generation leases."""
import base64
import json
import uuid


def private_store(store):
    from crm_automation_store import AutomationStore
    from crm_publication_connection import Connection
    from crm_store import Store
    if not isinstance(store,AutomationStore):return None
    factory=store.connect.connect if isinstance(store.connect,Connection) else store.connect
    return Store(factory)


def state_key(key):return 'email-thumbnail:'+key


def valid(data):return len(data)<=80000 and data[:4]==b'RIFF' and data[8:12]==b'WEBP'


def acquire(store,key):
    name=state_key(key)
    value=store.state(name)
    if value.get('state')=='READY':
        try:data=base64.b64decode(value['webp'],validate=True)
        except (KeyError,ValueError):data=b''
        if valid(data):return 'READY',data,None
        store.q("UPDATE crm_runtime_state SET value='{}'::jsonb,updated_at=now()-interval '4 minutes' WHERE key=%s AND value->>'state'='READY'",(name,))
    owner=str(uuid.uuid4())
    claimed=store.q("""INSERT INTO crm_runtime_state(key,value) VALUES(%s,%s::jsonb)
      ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=now()
      WHERE crm_runtime_state.value->>'state' IS DISTINCT FROM 'READY'
        AND crm_runtime_state.updated_at<now()-CASE WHEN crm_runtime_state.value->>'state'='ERROR'
          THEN interval '60 seconds' ELSE interval '3 minutes' END
      RETURNING key""",(name,json.dumps({'state':'RUNNING','owner':owner})),True)
    return ('CLAIMED',None,owner) if claimed else ('BUSY',None,None)


def finish(store,key,owner,data=None):
    value={'state':'READY','webp':base64.b64encode(data).decode()} if data else {'state':'ERROR'}
    store.q("UPDATE crm_runtime_state SET value=%s::jsonb,updated_at=now() WHERE key=%s AND value->>'owner'=%s",
            (json.dumps(value),state_key(key),owner))
