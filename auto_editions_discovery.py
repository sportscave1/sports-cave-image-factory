"""Durable, bounded PSD discovery. Existing mappings and matching rules are authority.

Only original-folder metadata is cached. No file contents, artwork, allocation,
Shopify, visual approval or fulfilment records are written here.
"""
import json
import logging
import os
import re
import uuid

import auto_editions as ae
import psd_directory as psd
from auto_editions_onboarding_store import Queue
from psd_mapping_store import PostgresMappings, _record

ACTOR = 'auto-editions-v15'
LOG = logging.getLogger(__name__)


def enabled():
    return os.getenv('AUTO_EDITIONS_V15_ENABLED', '').lower() == 'true'


def register(cur, products, event_id):
    """Inside the existing registration transaction; never a network request.

    Rollout is opt-in. A missing schema when enabled fails the receipt so the
    authenticated webhook's existing retry mechanism retains the handoff.
    """
    if not enabled():
        return
    # Same order as reconciliation: Edition registration already holds its
    # table lock, then cursor, then discovery rows. Never invert these locks.
    if products:
        cur.execute('UPDATE auto_edition_discovery_cursor SET next_poll_at=LEAST(next_poll_at,now()) WHERE id=1')
    for product in products:
        pid = psd.product_id(product)
        if not pid:
            raise ValueError('Exact Shopify product identity required.')
        cur.execute("""INSERT INTO auto_edition_discovery(product_gid,event_id)
            VALUES(%s,%s) ON CONFLICT(product_gid) DO UPDATE SET
            event_id=excluded.event_id,next_check_at=now(),updated_at=now()
            WHERE auto_edition_discovery.event_id<>excluded.event_id""", (pid, event_id))


class Discovery:
    def __init__(self, connect):
        self.connect = connect
        self.queue = Queue(connect)

    def claim(self):
        token = str(uuid.uuid4())
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("""UPDATE auto_edition_discovery_cursor SET lease_token=%s,
                lease_until=now()+interval '5 minutes'
                WHERE id=1 AND next_poll_at<=now()
                AND (lease_until IS NULL OR lease_until<=now()) RETURNING *""", (token,))
            row = cur.fetchone()
            return dict(row) if row else None

    @staticmethod
    def fence(cur, token):
        cur.execute("""SELECT id FROM auto_edition_discovery_cursor
            WHERE id=1 AND lease_token=%s AND lease_until>now() FOR UPDATE""", (token,))
        if not cur.fetchone():
            raise ValueError('Discovery lease expired or superseded.')

    def page(self, token, page):
        """Cursor and metadata commit together; incomplete inventories cannot map."""
        if not page.get('cursor') or type(page.get('has_more')) is not bool:
            raise ValueError('Incomplete Dropbox inventory response.')
        with self.connect() as conn, conn.cursor() as cur:
            self.fence(cur, token)
            changed = False
            for entry in page.get('entries', []):
                path = str(entry.get('path_lower') or entry.get('path_display') or '').casefold()
                # Deleted/moved originals invalidate metadata only, never mappings.
                if entry.get('.tag') == 'deleted':
                    cur.execute('DELETE FROM auto_edition_source_inventory WHERE path_lower=%s', (path,))
                    changed = True
                elif psd.approved_file(entry):
                    cur.execute("""INSERT INTO auto_edition_source_inventory(file_id,name_key,path_lower,metadata)
                        VALUES(%s,%s,%s,%s::jsonb) ON CONFLICT(file_id) DO UPDATE SET
                        name_key=excluded.name_key,path_lower=excluded.path_lower,metadata=excluded.metadata""",
                        (entry['id'], psd.filename_key(entry['name'][:-4]), path, json.dumps(entry)))
                    changed = True
            cur.execute("""UPDATE auto_edition_discovery_cursor SET cursor=%s,complete=%s WHERE id=1""",
                        (page['cursor'], not page['has_more']))
            if changed:
                cur.execute("""UPDATE auto_edition_discovery SET next_check_at=now()
                    WHERE status<>'Mapped'""")

    def pending(self, token, limit=10):
        with self.connect() as conn, conn.cursor() as cur:
            self.fence(cur, token)
            cur.execute("""SELECT * FROM auto_edition_discovery WHERE status<>'Mapped'
                AND next_check_at<=now() ORDER BY next_check_at,product_gid LIMIT %s""", (limit,))
            return [dict(r) for r in cur.fetchall()]

    def reset_inventory(self, token):
        """A Dropbox reset rebuilds metadata only; partial inventories stay disabled."""
        with self.connect() as conn, conn.cursor() as cur:
            self.fence(cur,token)
            cur.execute('DELETE FROM auto_edition_source_inventory')
            cur.execute("UPDATE auto_edition_discovery_cursor SET cursor='',complete=false WHERE id=1")

    def seed_existing(self, limit=20):
        """One bounded bootstrap of missing historical handoffs; never rematch.

        Existing queue/prepared checkpoints are excluded. The deferred backlog
        retains priority zero until commerce signals or Prepare Now promote it.
        """
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute('SELECT seed_finished FROM auto_edition_discovery_cursor WHERE id=1 FOR UPDATE')
            if cur.fetchone()['seed_finished']:return 0
            cur.execute("""SELECT m.shopify_product_gid,m.dropbox_file_id FROM product_psd_mappings m
                WHERE NOT EXISTS(SELECT 1 FROM auto_edition_onboarding q WHERE q.product_gid=m.shopify_product_gid)
                ORDER BY m.shopify_product_gid LIMIT %s""",(max(1,min(int(limit),20)),))
            rows=cur.fetchall()
            for row in rows:
                self.queue.enqueue_cursor(cur,row['shopify_product_gid'],row['dropbox_file_id'],ACTOR,newly_linked=False)
            if not rows:cur.execute('UPDATE auto_edition_discovery_cursor SET seed_finished=true WHERE id=1')
            return len(rows)

    @staticmethod
    def candidate(cur, pid):
        # One DB snapshot only for due discovery, never on a UI load/host claim.
        # Full authoritative identities are needed to reject competing titles
        # and handles, including products that predate V15.
        cur.execute('SELECT shopify_product_gid,shopify_product_id,product_title,shopify_handle FROM edition_products')
        products = [dict(r) for r in cur.fetchall()]
        product = [r for r in products if psd.product_id(r) == pid]
        if len(product) != 1:
            return None, 'Needs mapping review', 'Product identity missing or ambiguous.'
        keys = list(psd.title_filename_keys(product[0]['product_title']))
        cur.execute('SELECT metadata FROM auto_edition_source_inventory WHERE name_key=ANY(%s)', (keys,))
        entries = [r['metadata'] for r in cur.fetchall()]
        cur.execute('SELECT * FROM product_psd_mappings WHERE dropbox_file_id=ANY(%s)',
                    ([e['id'] for e in entries],))
        owners = {r['shopify_product_gid']: _record(r) for r in cur.fetchall()}
        match = psd.reconcile(products, entries, owners).get(pid, {})
        if not match.get('verified') or match.get('state') != 'Linked':
            state = match.get('state', 'Not linked')
            return None, 'Needs mapping review' if state.startswith('Review:') else 'Waiting for PSD', state
        chosen = [e for e in entries if e['id'] == match['dropbox_file_id']]
        if len(chosen) != 1:
            return None, 'Needs mapping review', 'Duplicate Dropbox identity.'
        return chosen[0], 'Mapped', ''

    def reconcile(self, token, request, metadata=None):
        """Recheck under existing lock order; insert-only mapping + audit + queue.

        Returns candidate metadata for an external freshness read when necessary.
        Existing mappings bypass matching entirely and reuse their checkpoints.
        """
        pid = request['product_gid']
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute('LOCK TABLE edition_products IN SHARE ROW EXCLUSIVE MODE')
            cur.execute('LOCK TABLE product_psd_mappings IN SHARE ROW EXCLUSIVE MODE')
            self.fence(cur, token)
            cur.execute('SELECT * FROM auto_edition_discovery WHERE product_gid=%s FOR UPDATE', (pid,))
            current = cur.fetchone()
            if not current or current['event_id'] != request['event_id']:
                return None
            cur.execute('SELECT * FROM product_psd_mappings WHERE shopify_product_gid=%s', (pid,))
            existing = cur.fetchone()
            if existing:
                file_id = existing['dropbox_file_id']
                status, reason, identity = 'Mapped', '', None
                self.queue.enqueue_cursor(cur,pid,file_id,ACTOR)
            else:
                candidate, status, reason = self.candidate(cur, pid)
                identity = None
                if candidate and metadata is None:
                    return candidate
                if candidate:
                    try:
                        identity = ae.source_identity(pid, metadata)
                        if (not psd.approved_file(metadata) or
                                ae.source_identity(pid, candidate) != identity or
                                candidate['name'] != metadata['name'] or
                                (candidate.get('path_display') or candidate.get('path_lower')).casefold() !=
                                (metadata.get('path_display') or metadata.get('path_lower') or '').casefold()):
                            raise ValueError('Source changed during discovery.')
                    except (ValueError, TypeError, KeyError):
                        status, reason = 'Needs mapping review', 'Dropbox identity, revision or approved location changed.'
                        candidate = None
                if candidate:
                    file_id = metadata['id']
                    cur.execute("""INSERT INTO product_psd_mappings
                        (shopify_product_gid,dropbox_file_id,file_path,namespace_path,source,actor_id)
                        VALUES(%s,%s,%s,%s,'automatic',%s) RETURNING *""",
                        (pid,file_id,metadata.get('path_display') or metadata['path_lower'],
                         metadata.get('namespace_path') or '',ACTOR))
                    after = _record(cur.fetchone())
                    PostgresMappings._audit(cur,pid,'automatic',ACTOR,None,{**after,'verified_source':identity})
                    self.queue.enqueue_cursor(cur,pid,file_id,ACTOR,expected_source=identity)
                    Queue.audit(cur,pid,ACTOR,'mapping_confirmed',identity)
            cur.execute("""UPDATE auto_edition_discovery SET status=%s,reason=%s,
                source_identity=COALESCE(%s::jsonb,source_identity),
                next_check_at=now()+interval '15 minutes',updated_at=now() WHERE product_gid=%s""",
                (status,reason,json.dumps(identity) if identity else None,pid))
        return None

    def finish(self, token, more=False):
        with self.connect() as conn, conn.cursor() as cur:
            self.fence(cur, token)
            cur.execute("""UPDATE auto_edition_discovery_cursor SET lease_token=NULL,lease_until=NULL,
                next_poll_at=now()+(%s * interval '1 second') WHERE id=1""", (2 if more else 300,))

    def tick(self, list_page, read_metadata):
        claim = self.claim()
        if not claim:
            return False
        token = claim['lease_token']
        try:
            page = list_page(claim['cursor'])
            self.page(token,page)
            pending = [] if page['has_more'] else self.pending(token)
            for request in pending:
                candidate = self.reconcile(token,request)
                if candidate:
                    self.reconcile(token,request,read_metadata(candidate['id']))
            self.finish(token,page['has_more'] or len(pending)==10)
            return True
        except Exception as error:
            # Keep durable requests/cursor; an expired lease resumes safely.
            if getattr(error,'cursor_reset',False):
                self.reset_inventory(token)
            self.finish(token)
            raise


def run(stop):
    """One background thread in the existing worker, opt-in after migration."""
    import supabase_backend as db
    import dropbox_integration as dropbox
    from auto_editions_priority import refresh
    discovery = Discovery(db.connect)
    while not stop.is_set():
        try:
            auth = None
            def context():
                nonlocal auth
                if auth is None:
                    auth = dropbox.resolve_server_auth()['access_token']
                return auth
            discovery.tick(
                lambda cursor: dropbox.list_folder_page(context(),psd.ROOT,cursor=cursor,limit=200,include_deleted=True),
                lambda fid: dropbox.psd_open_metadata(context(),fid,include_preview=False))
        except Exception as error:
            LOG.warning('auto_editions_discovery_failed error_type=%s',type(error).__name__)
        try:
            discovery.seed_existing()
            refresh(discovery.queue,ACTOR,limit=100)
        except Exception as error:
            LOG.warning('auto_editions_priority_failed error_type=%s',type(error).__name__)
        stop.wait(60)


def inspect_prepared_receipts(records, read_metadata, *, offset=0, limit=20):
    """Read-only orphan/discrepancy report by recorded IDs, never folder names.

    Caller supplies a bounded batch of stored receipts. No automatic approval,
    asset deletion or source discovery occurs, even for an orphan preparation.
    """
    issues = []
    assets = []
    for record in records:
        receipts=record.get('receipts',{}).get('assets',[])
        if not receipts:
            issues.append({'preparation_hash':record['hash'],'reason':'Recorded asset identities missing'})
        assets.extend((record['hash'],r) for r in receipts)
        if not record.get('mapped'):
            issues.append({'preparation_hash':record['hash'],'reason':'Orphan preparation; review required'})
    limit=max(1,min(int(limit),20));offset=max(0,int(offset))
    for digest,receipt in assets[offset:offset+limit]:
        try:
            current=read_metadata(receipt['file_id'])
            from auto_editions_cloud import DropboxAssets
            expected_path=DropboxAssets.path(digest,receipt['name'])
            if (current.get('id')!=receipt['file_id'] or current.get('rev')!=receipt.get('revision')
                    or (receipt.get('bytes') is not None and current.get('size')!=receipt['bytes'])
                    or current.get('name')!=receipt['name']
                    or str(current.get('path_display') or current.get('path_lower') or '').casefold()!=expected_path.casefold()):
                issues.append({'preparation_hash':digest,'file_id':receipt['file_id'],'reason':'Recorded asset differs'})
            elif receipt.get('bytes') is None:
                issues.append({'preparation_hash':digest,'file_id':receipt['file_id'],'reason':'Legacy receipt has no size evidence; verification incomplete'})
        except Exception:
            issues.append({'preparation_hash':digest,'file_id':receipt.get('file_id'),'reason':'Recorded asset unavailable'})
    return {'issues':issues,'next_offset':offset+limit if offset+limit<len(assets) else None}


def waiting_rows(connect):
    """Status reads only; never discovery or Dropbox I/O on page load."""
    with connect() as conn,conn.cursor() as cur:
        cur.execute("""SELECT d.product_gid,p.product_title,d.status,d.reason
            FROM auto_edition_discovery d JOIN edition_products p
            ON COALESCE(NULLIF(p.shopify_product_gid,''),p.shopify_product_id)=d.product_gid
            WHERE d.status<>'Mapped' AND NOT EXISTS
            (SELECT 1 FROM auto_edition_onboarding q WHERE q.product_gid=d.product_gid)
            ORDER BY d.updated_at LIMIT 500""")
        return [{**dict(r),'preparation_hash':None,'attempts':0,'priority':0} for r in cur.fetchall()]


def prepared_report(connect, read_metadata, digest, offset=0):
    """Explicit read-only diagnostic for one stored preparation, 20 IDs per call."""
    if not re.fullmatch(r'[a-f0-9]{64}',digest):
        raise ValueError('Exact immutable preparation hash required.')
    with connect() as conn,conn.cursor() as cur:
        cur.execute("""SELECT p.hash,p.receipts,EXISTS
            (SELECT 1 FROM product_psd_mappings m WHERE m.shopify_product_gid=p.manifest->'source'->>'product_gid'
             AND m.dropbox_file_id=p.manifest->'source'->>'file_id') AS mapped
            FROM auto_edition_preparations p WHERE p.hash=%s""",(digest,))
        row=cur.fetchone()
        if not row:raise ValueError('Stored preparation unavailable.')
    return inspect_prepared_receipts([dict(row)],read_metadata,offset=offset)
