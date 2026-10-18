"""Owner-selected technical-only TEST readiness; never a visual/supplier approval.

Rollout is explicit. Reads never enqueue; the existing preparation worker drains
durable checkpoints. Network/file validation runs outside the commit transaction.
"""
import json
import logging
import os
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import auto_editions as ae

METHOD='auto-editions-technical-v1'
ACTOR='automatic:'+METHOD
_colour_snapshot=ContextVar('technical-colour-read-snapshot',default=None)


def enabled():
    return os.getenv('AUTO_EDITIONS_TECHNICAL_FLOW_ENABLED','').lower()=='true'


@contextmanager
def colour_snapshot(connect):
    """One policy read per status/layout batch, never one database read per row."""
    config=None
    if enabled():
        from auto_editions_colour_store import configuration
        config=configuration(connect)
    token=_colour_snapshot.set(config)
    try:yield
    finally:_colour_snapshot.reset(token)


def resolve_colour(source):
    from auto_editions_colour_policy import resolve
    config=_colour_snapshot.get()
    try:return resolve(source,policies=config['policies'],memberships=config['memberships'],default_group=config['default_group']) if config else resolve(source)
    except OSError as error:raise ValueError('Approved colour policy registry is unavailable. Restore the existing verified registry before retrying.') from error


def certificate(record):
    from auto_editions_bulk import evidence
    m=evidence(record)
    inspection=m.get('source_inspection') or {};doc=inspection.get('document') or {}
    if doc.get('mode') not in ('RGB','DocumentMode.RGB'):
        raise ValueError('Source colour mode is not verified RGB. CMYK conversion requires the existing explicit colour policy; no profile was reassigned.')
    policy=None
    if not doc.get('profile'):
        _,policy=resolve_colour(m['source'])
        if doc.get('mode') not in ('RGB','DocumentMode.RGB') or doc.get('bits_per_channel') not in (8,'BitsPerChannelType.EIGHT'):
            raise ValueError('Approved untagged policy requires verified legacy RGB8 source evidence. CMYK conversion is not authorised.')
    from auto_editions_onboarding import detect
    roles=detect(inspection,m['edition_total'],colour_policy=policy)
    if roles['number_layer']!=m.get('number_layer_name') or roles['plaque_layer']!=m.get('plaque_layer_name'):
        raise ValueError('Stored editable-number/plaque roles differ from the verified inspection.')
    return dict(method=METHOD,actor_id=ACTOR,preparation_hash=record['hash'],
                source=record['manifest']['source'],test_only=True,
                evidence_hash=ae.fingerprint(dict(proofs=record['proofs'],receipts=record['receipts'])),
                technical_verified=True,colour=record['manifest'].get('colour_evidence'),colour_policy=policy)


def current(value,manifest):
    """No visual_approved flag, AI evidence, production certificate or allocation."""
    return current_identity(value,ae.fingerprint(manifest),manifest['source'],manifest.get('colour_evidence'))


def current_identity(value,digest,source,colour_evidence):
    """Lightweight read projection; full manifests stay out of status polling."""
    if not enabled():return False
    if (value.get('method')!=METHOD or value.get('actor_id')!=ACTOR
            or value.get('preparation_hash')!=digest
            or value.get('source')!=source or value.get('test_only') is not True
            or value.get('technical_verified') is not True
            or value.get('colour')!=colour_evidence):return False
    import re
    if not re.fullmatch('[a-f0-9]{64}',str(value.get('evidence_hash',''))):return False
    colour=colour_evidence or {}
    policy=value.get('colour_policy') or colour.get('policy')
    if policy:
        try:
            if resolve_colour(source)[1]!=policy:return False
        except ValueError:return False
    return True


def project(row,valid,uploaded,*,writable=False,now=None):
    from datetime import datetime,timezone
    from auto_editions_status import reason
    now=now or datetime.now(timezone.utc)
    status=row.get('status');digest=row.get('preparation_hash');mapped=row.get('dropbox_file_id')
    job=row.get('technical_state');reset=row.get('replacement') or {};cancel=row.get('reset_cancellation') or {}
    state='Failed';why=reason(row.get('reason')) or 'Technical processing cannot proceed. Inspect Worker Diagnostics.';actions=[]
    stage=('Technical validation' if digest and status in ('Blocked','Awaiting preparation') else row.get('reason') or status or 'Not mapped')
    if not mapped:state='Not Mapped';why='Add a valid PSD mapping to start automatic processing.'
    elif row.get('file_id')!=mapped:why='Mapping and preparation identity differ. Reconnect the exact source.';actions=['connect']
    elif status=='Cloud Ready':
        cert=row.get('technical_approval')
        if valid and uploaded and row.get('hash_count')==1 and (row.get('approved') is True or (cert and current_identity(cert,digest,row.get('prepared_source'),row.get('technical_colour')))):state='Cloud Ready';why='Required technical checks and durable uploads verified. TEST downloads only.'
        else:why='Current source, technical evidence or immutable upload receipts are inconsistent.'
    elif status=='Awaiting preparation' and not digest:
        if row.get('priority',0)>0:state='Uploading';why='Durably queued for Companion preparation.'
        else:why='Deliberately deferred/excluded. Automatic processing is paused for this design.'
    elif status=='Preparing':
        until=row.get('lease_until')
        if isinstance(until,str):until=datetime.fromisoformat(until.replace('Z','+00:00'))
        if until and until>now:state='Uploading';why='Companion '+str(stage).lower()+'.'
        else:why='Companion lease expired. Owned recovery must complete before this design can continue.'
    elif digest and status in ('Blocked','Awaiting preparation'):
        if job=='Failed':why=reason(row.get('technical_reason')) or 'Technical verification failed.';actions=['retry']
        elif job=='Superseded':why=reason(row.get('technical_reason')) or 'Preparation changed during verification.'
        elif row.get('priority',0)<=0:why='Deliberately deferred/excluded; retained preparation is protected.'
        elif not valid:why='Current source, edition geometry or pixel proofs are incomplete or stale.'
        elif job in (None,'Pending','Processing'):
            until=row.get('technical_lease_until')
            if isinstance(until,str):until=datetime.fromisoformat(until.replace('Z','+00:00'))
            if job=='Processing' and (not until or until<=now):why='Technical verification lease expired. Recovery is pending.'
            else:state='Uploading';why='Verifying retained preparation and cloud receipts.';stage='Verifying' if job=='Processing' else 'Queued technical verification'
        else:why='Technical completion checkpoint differs from the current preparation.'
    elif status in ('Blocked','Needs PSD Repair'):actions=['retry']
    if state=='Failed':
        from worker_diagnostics import explain
        if explain(why)['code'] in ('PROFILE_MISSING','COLOUR_POLICY_PENDING','PROFILE_INSPECTOR_FAILURE','COLOUR_INCOMPATIBLE','ICC_MISMATCH'):actions+=['colour-review']
    if reset.get('stage') in ('Discovering','Queued','Preparing'):
        state='Uploading';stage=reset['stage'];why='Existing explicit reset/reprocess is running.';actions=[]
    elif reset.get('stage')=='Failed':
        state='Failed';stage=reset.get('failure_status') or 'Failed'
        why=reason(reset.get('reason')) or 'Native replacement failed; the retained preparation is protected.'
        actions=['retry']
    if cancel.get('stage') in ('Cancelling','Confirmed'):
        state='Uploading';stage='Cancelling';why='Waiting for owned Companion safe-stop acknowledgement.';actions=[]
    return dict(product_gid=row['product_gid'],status=state,icon='✓' if state=='Cloud Ready' else '',reason=why,
        substage=stage,uploaded=uploaded,preparation_hash=digest,approval_status=None,
        mapping_file_id=mapped,actions=(actions+(['preview'] if digest else [])) if writable else [],
        checkpoint=stage,checkpoint_at=str(row.get('technical_updated_at') or row.get('updated_at') or '') or None,
        reset_allowed=bool(writable and state!='Uploading'),cancelling=cancel.get('stage') in ('Cancelling','Confirmed'))


ELIGIBLE="""q.status IN ('Blocked','Awaiting preparation') AND q.preparation_hash IS NOT NULL AND q.priority>0
 AND m.dropbox_file_id=q.file_id AND q.source=p.manifest->'source'
 AND COALESCE(to_jsonb(q)->'replacement'->>'stage','') NOT IN ('Discovering','Queued','Preparing','Failed')
 AND COALESCE(to_jsonb(q)->'replacement'->>'manual_required','false')<>'true'
 AND COALESCE(to_jsonb(q)->'reset_cancellation'->>'stage','') NOT IN ('Cancelling','Confirmed')
 AND NOT EXISTS(SELECT 1 FROM auto_edition_review_jobs j WHERE j.product_gid=q.product_gid AND j.state IN ('Pending','Processing'))"""


def backlog(connect):
    """Read-only dry run. No provider access, claims, policy writes or enqueue."""
    with connect() as conn,conn.cursor() as cur:
        cur.execute("""SELECT q.product_gid,q.status,q.reason,q.priority,q.preparation_hash,
            to_jsonb(q)->'replacement' AS replacement,to_jsonb(q)->'reset_cancellation' AS reset_cancellation,
            m.dropbox_file_id,p.hash,p.manifest,p.proofs,p.receipts
            FROM auto_edition_onboarding q LEFT JOIN product_psd_mappings m ON m.shopify_product_gid=q.product_gid
            LEFT JOIN auto_edition_preparations p ON p.hash=q.preparation_hash ORDER BY q.product_gid""")
        rows=cur.fetchall()
    result=[]
    for row in rows:
        why='';group='Technical failure'
        if row['status']=='Cloud Ready':group='Protected Cloud Ready'
        elif row['status']=='Preparing' or (row.get('replacement') or {}).get('stage') in ('Discovering','Queued','Preparing'):group='Protected active'
        elif row['priority']==0:group='Protected deferred/excluded'
        elif (row.get('replacement') or {}).get('manual_required') or (row.get('reset_cancellation') or {}).get('stage') in ('Cancelling','Confirmed'):group='Protected reset'
        elif row['status']=='Awaiting preparation':group='Existing queue'
        elif row['status']=='Blocked' and row.get('hash'):
            try:
                if row['manifest']['source']['file_id']!=row['dropbox_file_id']:raise ValueError('Mapping differs from retained source.')
                certificate(row);group='Candidate for current-source / cloud verification'
            except (ValueError,KeyError,TypeError) as error:
                why=str(error)
                if why=='Complete immutable upload receipts required.':group='Requires immutable receipt recovery'
        result.append(dict(product_gid=row['product_gid'],status=row['status'],group=group,reason=why or row['reason'],hash=row['preparation_hash']))
    return result


class Technical:
    def __init__(self,connect):self.connect=connect

    def repair_exports(self,pid,actor,request_id):
        """Explicit failed-only repair; reuse the preserved replacement pipeline.

        Nothing is unlinked. The normal discovery, source, Photoshop, upload and
        final-generation fences still run before the retained package is replaced.
        """
        from auto_editions_store import Preparations
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute("""SELECT q.*,t.state AS technical_state,t.reason AS technical_reason
                FROM auto_edition_onboarding q JOIN auto_edition_technical_checks t
                ON t.product_gid=q.product_gid AND t.preparation_hash=q.preparation_hash AND t.checkpoint_at=q.updated_at
                WHERE q.product_gid=%s""",(pid,));row=cur.fetchone()
        if not row or row['status']!='Blocked' or row['technical_state']!='Failed' or row['priority']<=0:
            raise ValueError('Only an unsuccessful retained technical preparation can be repaired.')
        from worker_diagnostics import explain
        if explain(row['technical_reason'])['code'] not in ('PROFILE_MISSING','COLOUR_POLICY_PENDING','ICC_MISMATCH') and row['technical_reason']!='Embedded ICC profile required.':
            raise ValueError('This failure requires separate repair evidence.')
        record=Preparations(self.connect).read(row['preparation_hash'])
        if not record or record['manifest']['source']!=row['source']:raise ValueError('Repair preparation identity changed.')
        with colour_snapshot(self.connect):certificate(record)  # Exact existing policy, roles and preservation proofs.
        from auto_editions_reset import Reset
        return Reset(self.connect).request(pid,request_id,actor,expected_source=row['source'],expected_checkpoint=(row['preparation_hash'],row['updated_at']))

    def seed(self):
        if not enabled():return
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute("""INSERT INTO auto_edition_technical_checks(product_gid,preparation_hash,checkpoint_at)
                SELECT q.product_gid,q.preparation_hash,q.updated_at FROM auto_edition_onboarding q
                JOIN product_psd_mappings m ON m.shopify_product_gid=q.product_gid
                JOIN auto_edition_preparations p ON p.hash=q.preparation_hash WHERE """+ELIGIBLE+"""
                AND NOT EXISTS(SELECT 1 FROM auto_edition_technical_checks t WHERE t.product_gid=q.product_gid AND t.preparation_hash=q.preparation_hash AND t.checkpoint_at=q.updated_at)
                ORDER BY q.created_at,q.product_gid LIMIT 100 ON CONFLICT DO NOTHING""")

    def claim(self,pid=None):
        if not enabled():return None
        with self.connect() as conn,conn.cursor() as cur:
            from worker_health import control
            if control(cur)['paused']:return None
            cur.execute("""SELECT t.* FROM auto_edition_technical_checks t
                JOIN auto_edition_onboarding q ON q.product_gid=t.product_gid AND q.preparation_hash=t.preparation_hash AND q.updated_at=t.checkpoint_at
                JOIN product_psd_mappings m ON m.shopify_product_gid=q.product_gid
                JOIN auto_edition_preparations p ON p.hash=q.preparation_hash
                WHERE (t.state='Pending' AND t.retry_at<=now() OR t.state='Processing' AND t.lease_until<now())
                AND (%s::text IS NULL OR t.product_gid=%s) AND """+ELIGIBLE+" ORDER BY t.created_at,t.product_gid FOR UPDATE OF t SKIP LOCKED LIMIT 1",(pid,pid))
            row=cur.fetchone()
            if not row:return None
            if row['attempts']>=3:
                cur.execute("UPDATE auto_edition_technical_checks SET state='Failed',reason='Technical verification interrupted three times. Retry verification after checking connectivity.',lease_token=NULL,lease_until=NULL,updated_at=now() WHERE product_gid=%s AND preparation_hash=%s AND checkpoint_at=%s",(row['product_gid'],row['preparation_hash'],row['checkpoint_at']))
                return None
            cur.execute("""UPDATE auto_edition_technical_checks SET state='Processing',attempts=attempts+1,
                lease_token=%s,lease_until=now()+interval '45 minutes',updated_at=now()
                WHERE product_gid=%s AND preparation_hash=%s AND checkpoint_at=%s RETURNING *""",(str(uuid.uuid4()),row['product_gid'],row['preparation_hash'],row['checkpoint_at']))
            claimed=dict(cur.fetchone())
            from auto_editions_onboarding_store import Queue
            Queue.audit(cur,claimed['product_gid'],ACTOR,'technical_claimed',dict(hash=claimed['preparation_hash'],attempt=claimed['attempts'],lease=str(claimed['lease_token'])))
            return claimed

    def run_one(self,assets,*,pid=None,local_root=None):
        # The authorised technical rollout reuses the existing approved registry
        # even if this worker has no separate colour-registry environment flag.
        with colour_snapshot(self.connect):
            return self._run_one(assets,pid=pid,local_root=local_root)

    def _run_one(self,assets,*,pid=None,local_root=None):
        self.seed();job=self.claim(pid)
        if not job:return None
        pid=job['product_gid'];digest=job['preparation_hash']
        from auto_editions_store import Preparations
        record=Preparations(self.connect).read(digest)
        try:
            if not record:raise ValueError('Retained preparation is missing. Restore its package before retrying.')
            from auto_editions_bulk import evidence,validate_files,inspect_asset
            from auto_editions_cloud import DropboxAssets
            m=record['manifest'];ae.validate_manifest(m)
            # Missing receipts may be recovered only from actual immutable cloud
            # identities, followed by byte/ICC verification. Never invent a receipt.
            original=dict(record)
            try:evidence(record)
            except ValueError as error:
                if str(error)!='Complete immutable upload receipts required.':raise
                # Preserve all old records; only a missing/incomplete receipt can
                # be repaired by metadata lookup. Other checks still fail below.
                receipts=[]
                for asset in [m['master'],*m['patches'].values()]:
                    # The source metadata helper accepts immutable IDs only.
                    # Missing receipts require a bounded canonical package path
                    # lookup, followed by the normal byte/profile validation.
                    destination=DropboxAssets.path(digest,asset['name'])
                    client=assets.integration.team_space_client(assets.token)
                    meta=assets.integration._metadata_to_dict(client.files_get_metadata(destination))
                    if (meta.get('path_display') or meta.get('path_lower') or '').lower()!=destination.lower():
                        raise ValueError('Recovered upload receipt path differs from the retained package.')
                    receipts.append(dict(name=asset['name'],file_id=meta['id'],revision=meta['rev'],bytes=meta['size']))
                record={**record,'receipts':dict(preparation_hash=digest,assets=receipts)}
                evidence(record)
            value=certificate(record)
            expected=((m.get('colour_evidence') or {}).get('icc_sha256') or (value.get('colour_policy') or {}).get('icc_sha256'))
            if local_root is None:validate_files(record,assets,expected_icc=expected)
            else:
                # Import already published and checked these exact local bytes.
                # Reuse them; never re-download freshly imported full-size PNGs.
                def fetch(_,asset,dest):
                    import shutil
                    shutil.copyfile(Path(local_root)/asset['name'],dest)
                import tempfile
                with tempfile.TemporaryDirectory(prefix='sc-technical-') as folder:
                    r=m['number_region'];profile=None
                    for asset in [m['master'],*m['patches'].values()]:
                        icc=inspect_asset(Path(folder),asset,m['dimensions'] if asset==m['master'] else [r[2]-r[0],r[3]-r[1]],fetch,digest,record['receipts'],expected)
                        if profile is not None and profile!=icc:raise ValueError('ICC profiles differ.')
                        profile=icc;(Path(folder)/asset['name']).unlink()
            # Fetch current source immediately before the short fenced commit.
            meta=assets.integration.psd_open_metadata(assets.token,m['source']['file_id'],include_preview=False)
            import psd_directory
            if not psd_directory.approved_file(meta) or ae.source_identity(pid,meta)!=m['source']:raise ValueError('Source changed. Prepare the current mapped PSD before retrying.')
            value=certificate(record)
            return self.commit(job,record,original,value)
        except Exception as error:
            logging.getLogger(__name__).exception('technical_completion_failed product=%s hash=%s',pid,digest)
            # Only connection/rate-limit failures retry; validation never becomes success.
            from worker_diagnostics import explain
            detail=explain(str(error))
            import requests
            transient=(detail.get('code') in ('CONNECTION_INTERRUPTED','DOWNLOAD_INTERRUPTED','UPLOAD_INTERRUPTED')
                or isinstance(error,(TimeoutError,ConnectionError,requests.Timeout,requests.ConnectionError))
                or getattr(getattr(error,'response',None),'status_code',None) in (408,429,500,502,503,504)
                or getattr(error,'sqlstate',None) in ('40001','40P01','55P03'))
            self.fail(job,str(error) if isinstance(error,ValueError) else 'Cloud verification unavailable. Check Worker Diagnostics, then retry verification.',transient)
            return 'Pending' if transient and job['attempts']<3 else 'Failed'

    def commit(self,job,record,original,value):
        pid=job['product_gid'];digest=job['preparation_hash']
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout='2s'")
            cur.execute('SELECT edition_total FROM edition_products WHERE shopify_product_gid=%s FOR SHARE',(pid,));products=cur.fetchall()
            cur.execute('SELECT dropbox_file_id FROM product_psd_mappings WHERE shopify_product_gid=%s FOR SHARE',(pid,));mapping=cur.fetchone()
            cur.execute('SELECT * FROM auto_edition_onboarding WHERE product_gid=%s FOR UPDATE',(pid,));q=cur.fetchone()
            cur.execute('SELECT * FROM auto_edition_technical_checks WHERE product_gid=%s AND preparation_hash=%s AND lease_token=%s AND state=\'Processing\' AND lease_until>now() FOR UPDATE',(pid,digest,str(job['lease_token'])));owned=cur.fetchone()
            if not owned:return 'Superseded'
            if (not q or q['status'] not in ('Blocked','Awaiting preparation') or q['preparation_hash']!=digest or q['source']!=record['manifest']['source']
                    or q['updated_at']!=job['checkpoint_at'] or not mapping or mapping['dropbox_file_id']!=q['file_id'] or q['priority']<=0
                    or len(products)!=1 or products[0]['edition_total']!=record['manifest']['edition_total']
                    or (q.get('replacement') or {}).get('stage') in ('Discovering','Queued','Preparing','Failed')
                    or (q.get('reset_cancellation') or {}).get('stage') in ('Cancelling','Confirmed')):
                self.terminal(cur,job,'Superseded','Preparation, mapping, reset or queue state changed.');return 'Superseded'
            cur.execute('SELECT * FROM auto_edition_preparations WHERE hash=%s FOR UPDATE',(digest,));fresh=cur.fetchone()
            if not fresh or any(fresh[k]!=original[k] for k in ('manifest','proofs','receipts')):raise ValueError('Preparation evidence changed during verification.')
            with colour_snapshot(self.connect):
                certificate(record)  # Fresh policy check inside the final fence.
            cur.execute('LOCK TABLE auto_edition_layouts IN SHARE ROW EXCLUSIVE MODE')
            cur.execute('SELECT * FROM auto_edition_layouts WHERE product_gid=%s',(pid,));layouts=cur.fetchall()
            if any(l['preparation_hash']!=digest for l in layouts):raise ValueError('Conflicting retained layout. Use explicit reset/repair; no layout was replaced.')
            old=next((l for l in layouts if l['variant_id']=='*'),None)
            if old:
                if old['approval'].get('allocation_ids') is not None:raise ValueError('Restricted TEST layout retained. Explicit scope correction is required; its allowlist was not broadened.')
                if ae.status(record['manifest'],old['approval'])!='TEST READY':raise ValueError('Existing layout is restricted or invalid. Repair it explicitly.')
            elif layouts:raise ValueError('Restricted variant layout retained. Explicit scope correction is required.')
            else:
                cur.execute("INSERT INTO auto_edition_layouts(product_gid,variant_id,preparation_hash,approval) VALUES(%s,'*',%s,%s::jsonb)",(pid,digest,json.dumps(value)))
            if record['receipts']!=original['receipts']:
                cur.execute('UPDATE auto_edition_preparations SET receipts=%s::jsonb WHERE hash=%s',(json.dumps(record['receipts']),digest))
                from auto_editions_onboarding_store import Queue
                Queue.audit(cur,pid,ACTOR,'technical_receipts_recovered',dict(hash=digest,previous=original['receipts'],verified=record['receipts']))
            cur.execute("UPDATE auto_edition_onboarding SET status='Cloud Ready',reason='',updated_at=now() WHERE product_gid=%s",(pid,))
            self.terminal(cur,job,'Succeeded','Required technical checks and immutable cloud receipts verified.')
            from auto_editions_onboarding_store import Queue
            Queue.audit(cur,pid,ACTOR,'technical_cloud_ready',dict(hash=digest,method=METHOD,evidence_hash=value['evidence_hash'],test_only=True))
            return 'Cloud Ready'

    @staticmethod
    def terminal(cur,job,state,reason):
        cur.execute("""UPDATE auto_edition_technical_checks SET state=%s,reason=%s,lease_token=NULL,lease_until=NULL,updated_at=now()
            WHERE product_gid=%s AND preparation_hash=%s AND lease_token=%s
            AND state='Processing' AND lease_until>now()""",(state,reason[:500],job['product_gid'],job['preparation_hash'],str(job['lease_token'])))

    def fail(self,job,reason,transient=False):
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute("SELECT 1 FROM auto_edition_technical_checks WHERE product_gid=%s AND preparation_hash=%s AND lease_token=%s AND state='Processing' AND lease_until>now() FOR UPDATE",(job['product_gid'],job['preparation_hash'],str(job['lease_token'])))
            if not cur.fetchone():return
            self.terminal(cur,job,'Pending' if transient and job['attempts']<3 else 'Failed',reason)
            cur.execute("UPDATE auto_edition_technical_checks SET retry_at=now()+interval '60 seconds' WHERE product_gid=%s AND preparation_hash=%s AND checkpoint_at=%s AND state='Pending'",(job['product_gid'],job['preparation_hash'],job['checkpoint_at']))
            from auto_editions_onboarding_store import Queue
            Queue.audit(cur,job['product_gid'],ACTOR,'technical_verification_failed',dict(hash=job['preparation_hash'],attempt=job['attempts'],reason=reason[:500],retrying=transient and job['attempts']<3))

    def retry(self,pid,actor):
        if not actor:raise PermissionError('Identified administrator required.')
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute('SELECT edition_total FROM edition_products WHERE shopify_product_gid=%s FOR SHARE',(pid,));products=cur.fetchall()
            cur.execute('SELECT dropbox_file_id FROM product_psd_mappings WHERE shopify_product_gid=%s FOR SHARE',(pid,));mapping=cur.fetchone()
            cur.execute('SELECT * FROM auto_edition_onboarding WHERE product_gid=%s FOR UPDATE',(pid,));q=cur.fetchone()
            if not q or not q.get('preparation_hash'):return False
            if q['status'] not in ('Blocked','Awaiting preparation') or q['priority']<=0 or (q.get('replacement') or {}).get('stage') in ('Discovering','Queued','Preparing') or (q.get('reset_cancellation') or {}).get('stage') in ('Cancelling','Confirmed'):
                raise ValueError('Active, completed, reset or deliberately deferred preparation is protected.')
            cur.execute('SELECT manifest FROM auto_edition_preparations WHERE hash=%s',(q['preparation_hash'],));prepared=cur.fetchone()
            if (not mapping or mapping['dropbox_file_id']!=q['file_id'] or not prepared or q['source']!=prepared['manifest']['source']
                    or len(products)!=1 or products[0]['edition_total']!=prepared['manifest']['edition_total']):
                raise ValueError('Mapping, source or edition limit changed. Repair the current preparation before retrying verification.')
            cur.execute('SELECT state FROM auto_edition_technical_checks WHERE product_gid=%s AND preparation_hash=%s AND checkpoint_at=%s FOR UPDATE',(pid,q['preparation_hash'],q['updated_at']));job=cur.fetchone()
            if not job or job['state'] not in ('Failed','Pending','Processing'):raise ValueError('This technical checkpoint cannot be retried. Inspect its current preparation state.')
            cur.execute("""UPDATE auto_edition_technical_checks SET state='Pending',attempts=0,reason='',retry_at=now(),updated_at=now()
                WHERE product_gid=%s AND preparation_hash=%s AND checkpoint_at=%s AND state='Failed' RETURNING product_gid""",(pid,q['preparation_hash'],q['updated_at']))
            if cur.fetchone():
                from auto_editions_onboarding_store import Queue
                Queue.audit(cur,pid,actor,'technical_retry',dict(hash=q['preparation_hash']))
            return True
