"""Local-only cursor adapter, explicitly selected by isolated tests."""
import json
import urllib.request
import urllib.error
import threading

LOCK=threading.RLock()


class Cursor:
    def __init__(self):self.rows=[];self.rowcount=0
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def execute(self,sql,args=()):
        parts=sql.split('%s');sql=parts[0]+''.join('$'+str(i)+p for i,p in enumerate(parts[1:],1))
        request=urllib.request.Request('http://127.0.0.1:8874',data=json.dumps({'sql':sql,'args':args or []},default=str).encode(),headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=30) as response:result=json.load(response)
        except urllib.error.HTTPError as exc:
            with exc:message=json.load(exc)['error']
            raise RuntimeError(message) from None
        self.rows=result.get('rows',[]);self.rowcount=result.get('affectedRows',len(self.rows))
        return self
    def fetchone(self):return self.rows[0] if self.rows else None
    def fetchall(self):return self.rows


class Connection:
    def __enter__(self):LOCK.acquire();self.cursor().execute('BEGIN');return self
    def __exit__(self,typ,*args):
        try:self.rollback() if typ else self.commit()
        finally:LOCK.release()
    def cursor(self):return Cursor()
    def commit(self):self.cursor().execute('COMMIT')
    def rollback(self):self.cursor().execute('ROLLBACK')
    def close(self):pass


def connect():return Connection()
