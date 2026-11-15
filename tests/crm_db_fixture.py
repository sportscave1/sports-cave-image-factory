"""Explicit localhost-only adapter for real SQL tests and fabricated CRM UI."""
import os
import threading
_TRANSACTION_LOCK=threading.RLock()
import json
import urllib.request
import urllib.error

class Cursor:
    def __init__(self,data):self.rows=data['rows'];self.description=data.get('fields') or None
    def fetchone(self):return self.rows[0] if self.rows else None
    def fetchall(self):return self.rows
class Connection:
    def __enter__(self):
        _TRANSACTION_LOCK.acquire()
        try:self.execute('BEGIN');return self
        except BaseException:_TRANSACTION_LOCK.release();raise
    def __exit__(self,typ,*_):
        try:self.execute('ROLLBACK' if typ else 'COMMIT')
        finally:_TRANSACTION_LOCK.release()
    def execute(self,sql,args=()):
        chunks=sql.split('%s');sql=chunks[0]+''.join('$'+str(i)+part for i,part in enumerate(chunks[1:],1))
        payload=json.dumps({'sql':sql,'args':list(args)},default=str).encode()
        request=urllib.request.Request('http://127.0.0.1:'+str(int(os.environ.get('CRM_FIXTURE_SQL_PORT','8873'))),data=payload,headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=20) as response:return Cursor(json.load(response))
        except urllib.error.HTTPError as exc:raise RuntimeError(json.load(exc)['error']) from None

def connect():return Connection()
