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


def valid(data):
    if not (12<len(data)<=80000 and data[:4]==b'RIFF' and data[8:12]==b'WEBP'):return False
    from io import BytesIO
    from PIL import Image
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format!='WEBP' or not (0<image.width<=600 and 0<image.height<=790):return False
            image.load()
        return True
    except (OSError,ValueError,Image.DecompressionBombError):return False


def acquire(store,key):
    name=state_key(key)
    value=store.state(name)
    if value.get('state')=='READY':
        try:data=base64.b64decode(value['webp'],validate=True)
        except (KeyError,ValueError):data=b''
        if valid(data):return 'READY',data,None
        # Fence invalidation to the corrupt value we inspected. A concurrent
        # worker may already have replaced it with a valid, newly ready image.
        store.q("UPDATE crm_runtime_state SET value='{}'::jsonb,updated_at=now()-interval '4 minutes' WHERE key=%s AND value->>'state'='READY' AND value->>'webp' IS NOT DISTINCT FROM %s",(name,value.get('webp')))
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
