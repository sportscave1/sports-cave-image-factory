"""Durable resumable packages on existing PostgreSQL + Dropbox upload sessions.

Acknowledgements require a committed SQL offset backed by provider-accepted data.
The session row itself is the processing queue: no enqueue/commit crash window.
"""
from contextlib import contextmanager
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import tempfile
import time
import auto_editions as ae
from companion_package_identity import CHUNK,BLOCK,validate


class Sessions:
    def __init__(self,connect,provider):self.connect=connect;self.provider=provider

    @contextmanager
    def locked(self,key,owner,host):
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute("SET LOCAL idle_in_transaction_session_timeout='10min'")
            cur.execute('SELECT * FROM companion_package_uploads WHERE id=%s AND owner_id=%s AND host_hash=%s FOR UPDATE',(key,owner,host))
            row=cur.fetchone()
            if not row:raise PermissionError('Upload session is unavailable to this host.')
            row=dict(row)
            yield row,cur
            cur.execute('UPDATE companion_package_uploads SET state=%s,data=%s::jsonb,result=%s::jsonb,updated_at=now() WHERE id=%s',
                (row['state'],json.dumps(row['data']),json.dumps(row.get('result')),key))

    @staticmethod
    def live(row):
        if row['state']=='Expired' or row['expires_at']<=datetime.now(timezone.utc):raise ValueError('Upload session expired; no accepted progress was resurrected.')

    @staticmethod
    def public(row):
        return dict(protocol=1,id=row['id'],state=row['state'],offset=row['data']['offset'],
                    bytes=row['descriptor']['bytes'],sha256=row['descriptor']['sha256'],
                    preparation_hash=row['descriptor']['preparation_hash'],generation=row['descriptor']['generation'],result=row.get('result'))

    def create(self,owner,host,shop,context,descriptor,correlation=None):
        validate(descriptor,context)
        key=ae.fingerprint(dict(owner=owner,host=host,shop=shop,context=context,descriptor=descriptor))
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('companion-package:'+ae.fingerprint(dict(owner=owner,host=host,context=context)),))
            cur.execute('SELECT * FROM companion_package_uploads WHERE id=%s',(key,))
            row=cur.fetchone()
            if row:
                self.live(row);return self.public(row)
            # One bounded live receiving session per host. Never abandon one to
            # silently start another full copy with a different fingerprint.
            cur.execute("SELECT id FROM companion_package_uploads WHERE host_hash=%s AND owner_id=%s AND context=%s::jsonb AND state IN ('Receiving','Queued') AND expires_at>now() LIMIT 1",(host,owner,json.dumps(context)))
            if cur.fetchone():raise ValueError('An unfinished package already belongs to this host; finish or expire it explicitly.')
            data=dict(provider_session=self.provider.start(),offset=0,blocks=[],chunk_hashes=[],destination=self.provider.destination(key))
            if correlation:data['correlation_id']=correlation
            cur.execute('''INSERT INTO companion_package_uploads(id,owner_id,host_hash,shop_origin,context,descriptor,data)
                VALUES(%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb) RETURNING *''',
                (key,owner,host,shop,json.dumps(context),json.dumps(descriptor),json.dumps(data)))
            return self.public(cur.fetchone())

    def status(self,key,owner,host):
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute('SELECT * FROM companion_package_uploads WHERE id=%s AND owner_id=%s AND host_hash=%s',(key,owner,host))
            row=cur.fetchone()
            if not row:raise PermissionError('Upload session is unavailable to this host.')
            self.live(row);return self.public(row)

    def chunk(self,key,owner,host,offset,content,digest):
        if type(offset) is not int or offset<0 or offset%CHUNK:raise ValueError('Invalid chunk position.')
        if not 0<len(content)<=CHUNK or hashlib.sha256(content).hexdigest()!=digest:raise ValueError('Chunk integrity check failed.')
        with self.locked(key,owner,host) as (row,cur):
            self.live(row);d=row['data'];desc=row['descriptor'];index=offset//CHUNK
            if index>=len(desc['chunks']) or desc['chunks'][index]!=digest or len(content)!=min(CHUNK,desc['bytes']-offset):
                raise ValueError('Chunk differs from the bound package.')
            if offset<d['offset']:
                if offset+len(content)>d['offset'] or d['chunk_hashes'][index]!=digest:raise ValueError('Conflicting repeated chunk.')
                return self.public(row)
            if row['state']!='Receiving' or offset!=d['offset']:raise ValueError('Resume from the server-confirmed position.')
            try:self.provider.append(d['provider_session'],offset,content)
            except Exception as error:
                # Provider committed append before its response/SQL commit was
                # lost. Exact final provider hash and full SHA still gate import.
                if getattr(error,'correct_offset',None)!=offset+len(content):raise
            d['blocks'].extend(hashlib.sha256(content[i:i+BLOCK]).hexdigest() for i in range(0,len(content),BLOCK))
            d['chunk_hashes'].append(digest);d['offset']+=len(content)
            return self.public(row)

    def finalize(self,key,owner,host):
        current=self.status(key,owner,host)
        if current['state']!='Receiving':return current
        with self.locked(key,owner,host) as (row,cur):
            self.live(row);d=row['data'];desc=row['descriptor']
            if row['state']!='Receiving':return self.public(row)
            if d['offset']!=desc['bytes'] or d['chunk_hashes']!=desc['chunks']:raise ValueError('Package is incomplete.')
            expected=hashlib.sha256(b''.join(bytes.fromhex(h) for h in d['blocks'])).hexdigest()
            meta=self.provider.metadata_if_present(d['destination'])
            if meta is None:
                self.provider.finish(d['provider_session'],desc['bytes'],d['destination'])
                meta=self.provider.metadata_if_present(d['destination'])
            if not meta or meta.get('size')!=desc['bytes'] or meta.get('content_hash')!=expected or not meta.get('id') or not meta.get('rev'):
                raise ValueError('Durable package receipt differs.')
            d['receipt']={k:meta[k] for k in ('id','rev','size','content_hash')}
            d.pop('provider_session',None)
            row['state']='Queued' # Same transaction/row is both receipt and job.
            return self.public(row)

    def run_one(self,process,recover=None):
        # The row lock fences publication across processes, not just threads.
        # A DB/process crash rolls Queued back; immutable provider receipts make
        # repeating partially completed publication safe in the shared importer.
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute("SET LOCAL idle_in_transaction_session_timeout='10min'")
            cur.execute("SELECT * FROM companion_package_uploads WHERE state='Queued' AND expires_at>now() AND retry_at<=now() AND attempts<3 ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1")
            row=cur.fetchone()
            if not row:return False
            row=dict(row)
            try:
                result=recover(row) if recover else None
                if result is None:
                    with tempfile.TemporaryDirectory(prefix='sc-resumable-') as folder:
                        archive=Path(folder)/'package.zip'
                        started=time.monotonic();self.provider.download(row['data']['receipt'],archive)
                        downloaded=time.monotonic()-started;started=time.monotonic()
                        if archive.stat().st_size!=row['descriptor']['bytes'] or ae.file_hash(archive)!=row['descriptor']['sha256']:
                            raise ValueError('Complete package SHA-256 differs; import refused.')
                        hashed=time.monotonic()-started
                        result=process(row,archive)
                        result.setdefault('timings',{}).update(durable_package_download_seconds=round(downloaded,6),complete_package_hash_seconds=round(hashed,6))
                if result.get('preparation_hash')!=row['descriptor']['preparation_hash']:raise ValueError('Preparation fingerprint changed during verification.')
                cur.execute("UPDATE companion_package_uploads SET state='Complete',result=%s::jsonb,updated_at=now() WHERE id=%s",(json.dumps(result),row['id']))
            except Exception as error:
                terminal=isinstance(error,(ValueError,PermissionError)) or row['attempts']>=2
                cur.execute("UPDATE companion_package_uploads SET state=%s,attempts=attempts+1,retry_at=now()+interval '30 seconds',result=%s::jsonb,updated_at=now() WHERE id=%s",
                    ('Blocked' if terminal else 'Queued',json.dumps(dict(error='Package verification rejected.' if terminal else 'Durable processing retry pending.',error_type=type(error).__name__)),row['id']))
            return True

    def cleanup(self,limit=2):
        # Retain small tombstones so an expired ID cannot silently start over.
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute("SELECT * FROM companion_package_uploads WHERE expires_at<=now() AND state<>'Expired' ORDER BY expires_at FOR UPDATE SKIP LOCKED LIMIT %s",(limit,))
            rows=cur.fetchall()
            for row in rows:
                d=row['data'];receipt=d.get('receipt')
                # A provider finish can commit before its SQL receipt does.
                # Recover only the exact complete immutable staging object.
                if not receipt and d['offset']==row['descriptor']['bytes']:
                    meta=self.provider.metadata_if_present(d['destination'])
                    expected=hashlib.sha256(b''.join(bytes.fromhex(h) for h in d['blocks'])).hexdigest()
                    if meta and meta.get('size')==row['descriptor']['bytes'] and meta.get('content_hash')==expected:
                        receipt={k:meta[k] for k in ('id','rev','size','content_hash')}
                if receipt:self.provider.discard(d['destination'],receipt)
                cur.execute("UPDATE companion_package_uploads SET state='Expired',data=%s::jsonb,updated_at=now() WHERE id=%s",(json.dumps(dict(offset=d['offset'])),row['id']))
            return len(rows)
