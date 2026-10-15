"""One product's pending redo in the EXISTING preparation queue.

Active mapping/checkpoint stay intact until the existing import verifies a new
package. No orders, allocations, approvals, source files or assets are rewritten.
"""
import json
import uuid

import auto_editions as ae
import psd_directory as psd
from psd_mapping_store import PostgresMappings,_record
from auto_editions_onboarding_store import Queue

BUSY=('Discovering','Queued','Preparing')


def locks(cur):
    # V15 discovery/registration order. Never lock the queue before mappings.
    cur.execute('LOCK TABLE edition_products IN SHARE ROW EXCLUSIVE MODE')
    cur.execute('LOCK TABLE product_psd_mappings IN SHARE ROW EXCLUSIVE MODE')


def snapshot(row):
    return {k:row.get(k) for k in ('file_id','source','edition_total','status','preparation_hash')}


def save(cur,pid,pending):
    cur.execute('UPDATE auto_edition_onboarding SET replacement=%s::jsonb WHERE product_gid=%s',
                (json.dumps(pending,default=str),pid))


class Reset:
    def __init__(self,connect):self.connect=connect

    def request(self,pid,request_id,actor):
        from auto_editions_discovery import enabled
        if not enabled():raise ValueError('Automatic PSD discovery is disabled.')
        if (not psd.product_id({'shopify_product_gid':pid}) or not isinstance(request_id,str)
                or str(uuid.UUID(request_id))!=request_id):
            raise ValueError('Exact product and reset request identities are required.')
        if not actor:raise PermissionError('An identified administrator is required.')
        with self.connect() as conn,conn.cursor() as cur:
            locks(cur)
            PostgresMappings.product(cur,pid)
            # The reset must observe a Dropbox delta AFTER its request. An
            # in-flight discovery page is insufficient; remember its lease.
            cur.execute('SELECT * FROM auto_edition_discovery_cursor WHERE id=1 FOR UPDATE')
            cursor=cur.fetchone()
            if not cursor:raise ValueError('Automatic PSD discovery is unavailable.')
            cur.execute('SELECT * FROM product_psd_mappings WHERE shopify_product_gid=%s',(pid,))
            mapping=cur.fetchone()
            cur.execute('SELECT * FROM auto_edition_onboarding WHERE product_gid=%s FOR UPDATE',(pid,))
            row=cur.fetchone()
            # A delayed retry of an older completed request must never create
            # another redo after a newer reset has taken its place.
            if not row or (row.get('replacement') or {}).get('id')!=request_id:
                cur.execute("""SELECT event FROM auto_edition_onboarding_audit WHERE product_gid=%s
                    AND detail->>'request_id'=%s AND event LIKE 'reset_%%' ORDER BY id DESC LIMIT 1""",(pid,request_id))
                prior=cur.fetchone()
                if prior:
                    return {'reset_completed':'Complete','reset_failed':'Failed','reset_queued':'Queued'}.get(prior['event'],'Discovering')
            if row:
                pending=row.get('replacement') or {}
                if pending.get('id')==request_id:return pending['stage']
                if row['status']=='Preparing' or pending.get('stage') in BUSY:
                    raise ValueError('This design is already processing. Wait for it to finish.')
            else:
                if mapping:
                    Queue(self.connect).enqueue_cursor(cur,pid,mapping['dropbox_file_id'],actor)
                else:
                    cur.execute("INSERT INTO auto_edition_onboarding(product_gid,file_id,status) VALUES(%s,'','Blocked')",(pid,))
                cur.execute('SELECT * FROM auto_edition_onboarding WHERE product_gid=%s FOR UPDATE',(pid,))
                row=cur.fetchone()
            pending=dict(id=request_id,actor=actor,stage='Discovering',attempts=0,reason='',
                         inventory_lease=str(cursor.get('lease_token') or ''),
                         previous=snapshot(row),mapping_before=_record(mapping) if mapping else None)
            save(cur,pid,pending)
            cur.execute('UPDATE auto_edition_discovery_cursor SET next_poll_at=now() WHERE id=1')
            Queue.audit(cur,pid,actor,'reset_requested',dict(request_id=request_id,previous=snapshot(row)))
        return 'Discovering'

    def discover(self,token,read_metadata,limit=5):
        """Called only after a complete page by the existing discovery worker."""
        from auto_editions_discovery import Discovery
        with self.connect() as conn,conn.cursor() as cur:
            Discovery.fence(cur,token)
            cur.execute("""SELECT product_gid,to_jsonb(q)->'replacement' AS pending
                FROM auto_edition_onboarding q
                WHERE to_jsonb(q)->'replacement'->>'stage'='Discovering'
                AND COALESCE(to_jsonb(q)->'replacement'->>'inventory_lease','')<>%s
                ORDER BY created_at LIMIT %s""",(str(token),max(1,min(limit,5))))
            rows=cur.fetchall()
        for request in rows:
            pid=request['product_gid'];candidate=None;fresh=None
            with self.connect() as conn,conn.cursor() as cur:
                candidate,_,why=Discovery.candidate(cur,pid,rematch=True)
            if candidate:
                try:
                    fresh=read_metadata(candidate['id'])
                    if (not psd.approved_file(fresh) or fresh['id']!=candidate['id']
                            or fresh['name']!=candidate['name']
                            or (fresh.get('path_display') or fresh.get('path_lower')).casefold()!=
                               (candidate.get('path_display') or candidate.get('path_lower')).casefold()):
                        raise ValueError('Original PSD identity or location changed.')
                    ae.source_identity(pid,fresh)
                except Exception:
                    fresh=None;why='Original PSD verification failed. The working design is retained.'
            with self.connect() as conn,conn.cursor() as cur:
                locks(cur);Discovery.fence(cur,token)
                cur.execute('SELECT * FROM auto_edition_onboarding WHERE product_gid=%s FOR UPDATE',(pid,))
                row=cur.fetchone();pending=(row or {}).get('replacement') or {}
                if pending.get('id')!=request['pending']['id'] or pending.get('stage')!='Discovering':continue
                cur.execute('SELECT * FROM product_psd_mappings WHERE shopify_product_gid=%s',(pid,))
                mapping=cur.fetchone()
                same_mapping=json.dumps(_record(mapping) if mapping else None,sort_keys=True,default=str)==json.dumps(pending['mapping_before'],sort_keys=True,default=str)
                if not same_mapping or snapshot(row)!=pending['previous']:
                    fresh=None;why='The design changed while resetting. The current design is retained.'
                if fresh:
                    # Refresh just this exact, approved ID to its current revision;
                    # then rerun the unchanged validated filename/ownership rules.
                    cur.execute('UPDATE auto_edition_source_inventory SET metadata=%s::jsonb WHERE file_id=%s',
                                (json.dumps(fresh),fresh['id']))
                    chosen,_,why=Discovery.candidate(cur,pid,rematch=True)
                    if not chosen or chosen['id']!=fresh['id']:fresh=None
                if fresh:
                    pending.update(stage='Queued',source=ae.source_identity(pid,fresh),file_id=fresh['id'],reason='')
                else:pending.update(stage='Failed',reason=why or 'No unique verified original PSD. The working design is retained.')
                save(cur,pid,pending)
                Queue.audit(cur,pid,pending['actor'],'reset_'+pending['stage'].lower(),dict(request_id=pending['id'],reason=pending['reason'],verified_source=pending.get('source')))
        return len(rows)


def finish(cur,row,digest,actor,reason,metrics=None):
    """Atomic audited mapping/checkpoint switch AFTER verified package import."""
    pending=row['replacement'];pid=row['product_gid']
    cur.execute('SELECT manifest FROM auto_edition_preparations WHERE hash=%s',(digest,))
    prepared=cur.fetchone()
    if (not prepared or prepared['manifest'].get('reset_request_id')!=pending['id']
            or prepared['manifest']['source']!=pending['source']):
        raise ValueError('Replacement preparation does not match this reset.')
    cur.execute('SELECT * FROM product_psd_mappings WHERE shopify_product_gid=%s',(pid,))
    mapping=cur.fetchone()
    if json.dumps(_record(mapping) if mapping else None,sort_keys=True,default=str)!=json.dumps(pending['mapping_before'],sort_keys=True,default=str):
        raise ValueError('Mapping changed. The current design is retained.')
    if snapshot(row)!=pending['previous']:raise ValueError('Active preparation changed during replacement.')
    cur.execute('SELECT edition_total FROM edition_products WHERE shopify_product_gid=%s',(pid,))
    product=cur.fetchone()
    if not product or product['edition_total']!=prepared['manifest']['edition_total']:
        raise ValueError('Edition limit changed. The working design is retained.')
    # Use the verified inventory identity and existing transactional mapping audit.
    cur.execute('SELECT metadata FROM auto_edition_source_inventory WHERE file_id=%s',(pending['file_id'],))
    meta=cur.fetchone()
    if not meta or ae.source_identity(pid,meta['metadata'])!=pending['source'] or not psd.approved_file(meta['metadata']):
        raise ValueError('Original PSD changed during replacement.')
    meta=meta['metadata']
    from auto_editions_discovery import Discovery
    chosen,_,_=Discovery.candidate(cur,pid,rematch=True)
    if not chosen or ae.source_identity(pid,chosen)!=pending['source']:
        raise ValueError('Original PSD matching is now ambiguous. The working design is retained.')
    path=meta.get('path_display') or meta['path_lower']
    if not mapping or mapping['dropbox_file_id']!=pending['file_id'] or mapping['file_path']!=path:
        cur.execute("""INSERT INTO product_psd_mappings(shopify_product_gid,dropbox_file_id,file_path,namespace_path,source,actor_id)
            VALUES(%s,%s,%s,%s,'automatic',%s) ON CONFLICT(shopify_product_gid) DO UPDATE SET
            dropbox_file_id=excluded.dropbox_file_id,file_path=excluded.file_path,namespace_path=excluded.namespace_path,
            source=excluded.source,actor_id=excluded.actor_id,updated_at=now() RETURNING *""",
            (pid,pending['file_id'],path,meta.get('namespace_path') or '',pending['actor']))
        PostgresMappings._audit(cur,pid,'replace' if mapping else 'automatic',pending['actor'],
                               _record(mapping) if mapping else None,_record(cur.fetchone()))
    pending.update(stage='Complete',preparation_hash=digest,reason='')
    cur.execute("""UPDATE auto_edition_onboarding SET file_id=%s,source=%s::jsonb,edition_total=%s,
        preparation_hash=%s,status='Blocked',reason=%s,replacement=%s::jsonb,updated_at=now() WHERE product_gid=%s""",
        (pending['file_id'],json.dumps(pending['source']),prepared['manifest']['edition_total'],digest,reason,json.dumps(pending),pid))
    Queue.audit(cur,pid,actor,'reset_completed',dict(request_id=pending['id'],previous=pending['previous'],preparation_hash=digest))
    if metrics is not None:Queue.audit(cur,pid,actor,'preparation_metrics',dict(metrics,preparation_hash=digest))
