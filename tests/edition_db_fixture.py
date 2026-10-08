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


def connect():
    import os
    url=os.getenv('EDITION_REAL_POSTGRES_URL','')
    if url:
        from urllib.parse import urlsplit
        if urlsplit(url).hostname not in ('localhost','127.0.0.1'):raise ValueError('Only disposable loopback PostgreSQL is allowed')
        import psycopg
        from psycopg.rows import dict_row
        return RealConnection(psycopg.connect(url,row_factory=dict_row))
    return Connection()


class RealCursor:
    def __init__(self,cursor):self.cursor=cursor
    def __enter__(self):return self
    def __exit__(self,*args):self.cursor.close()
    def execute(self,sql,args=()):
        import psycopg
        try:self.cursor.execute(sql,args);return self
        except psycopg.Error as exc:raise RuntimeError(str(exc)) from exc
    def fetchone(self):
        if self.cursor.description is None:return None
        row=self.cursor.fetchone()
        return json.loads(json.dumps(row,default=str)) if row else None
    def fetchall(self):return json.loads(json.dumps(self.cursor.fetchall(),default=str)) if self.cursor.description else []
    @property
    def rowcount(self):return self.cursor.rowcount

class RealConnection:
    def __init__(self,conn):self.conn=conn
    def __enter__(self):self.conn.__enter__();return self
    def __exit__(self,*args):return self.conn.__exit__(*args)
    def cursor(self):return RealCursor(self.conn.cursor())
    def rollback(self):self.conn.rollback()
    def commit(self):self.conn.commit()
    def close(self):self.conn.close()
