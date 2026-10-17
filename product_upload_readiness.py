"""Technical TEST readiness for an explicitly bound intake; never visual approval."""
import json
import re
import auto_editions as ae

METHOD = 'product-upload-technical-v1'


def current(approval, manifest):
    from product_upload_services import enabled
    return bool(enabled() and approval and approval.get('method') == METHOD
                and approval.get('preparation_hash') == ae.fingerprint(manifest)
                and approval.get('source') == manifest['source']
                and approval.get('edition_total') == manifest['edition_total']
                and approval.get('technical_validated') is True and approval.get('test_only') is True
                and approval.get('pixel_exact') is True and approval.get('actor_id')
                and re.fullmatch(r'[a-f0-9-]{36}', str(approval.get('intake_id',''))))


def complete(connect, pid):
    """Replayable after package import or partial handoff; no provider writes.

    Return false for ordinary/manual jobs. Fail closed for stale sources, active
    replacements and conflicting/restricted layouts. Existing manual tools remain.
    """
    from product_upload_services import enabled
    if not enabled():
        return False
    # The released technical pipeline already verifies native assets and remote
    # receipts asynchronously. Do not bypass it with an intake-only approval.
    from auto_editions_technical import enabled as technical_enabled
    if technical_enabled():
        return False
    from product_upload_intake import Intakes
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id,actor_id FROM product_upload_intakes WHERE data->>'product_gid'=%s ORDER BY created_at DESC LIMIT 1", (pid,))
        intake = cur.fetchone()
    if not intake:
        return False
    with Intakes(connect).locked(str(intake['id']), intake['actor_id']) as (row, cur):
        d = row['data']
        # Match the normal mapping -> preparation -> layout lock order.
        cur.execute('LOCK TABLE product_psd_mappings IN SHARE ROW EXCLUSIVE MODE')
        cur.execute('''SELECT q.*,p.hash,p.manifest,p.proofs,p.receipts,m.dropbox_file_id,ep.edition_total AS current_total,si.metadata AS inventoried_source
            FROM auto_edition_onboarding q JOIN auto_edition_preparations p ON p.hash=q.preparation_hash
            JOIN product_psd_mappings m ON m.shopify_product_gid=q.product_gid
            LEFT JOIN auto_edition_source_inventory si ON si.file_id=m.dropbox_file_id
            JOIN edition_products ep ON COALESCE(NULLIF(ep.shopify_product_gid,''),ep.shopify_product_id)=q.product_gid
            WHERE q.product_gid=%s FOR UPDATE OF q''', (pid,))
        q = cur.fetchone()
        if not q or q['status'] not in ('Blocked','Cloud Ready'):
            return False
        if q.get('replacement') or q.get('reset_cancellation'):
            return False
        from auto_editions_bulk import evidence
        m = evidence(q)
        if (m['source'] != d.get('bound_source') or q['source'] != m['source']
                or q['dropbox_file_id'] != m['source']['file_id'] or q['current_total'] != m['edition_total']
                or q.get('inventoried_source') and ae.source_identity(pid,q['inventoried_source']) != m['source']):
            raise ValueError('Source or edition limit changed before technical completion.')
        from auto_editions_onboarding import detect
        inspection = m.get('source_inspection')
        if not inspection:
            raise ValueError('Native PSD inspection, editable numbering and font evidence are required.')
        detect(inspection, m['edition_total'], colour_policy=(m.get('colour_evidence') or {}).get('policy'))
        if not (m.get('colour_evidence') or {}).get('icc_sha256'):
            raise ValueError('Saved output colour evidence is required.')
        approval = dict(method=METHOD, intake_id=str(row['id']), actor_id=row['actor_id'],
                        preparation_hash=q['hash'], source=m['source'], edition_total=m['edition_total'],
                        technical_validated=True, pixel_exact=True, test_only=True)
        cur.execute('LOCK TABLE auto_edition_layouts IN SHARE ROW EXCLUSIVE MODE')
        cur.execute('SELECT * FROM auto_edition_layouts WHERE product_gid=%s', (pid,))
        layouts = cur.fetchall()
        if any(l['preparation_hash'] != q['hash'] or l['approval'].get('allocation_ids') is not None for l in layouts):
            raise ValueError('An existing layout has a different or restricted scope. Use the established manual review/reset workflow.')
        if (d.get('technical_completion') == q['hash'] and q['status']=='Cloud Ready'
                and any(l['variant_id']=='*' for l in layouts)):
            return True
        if not any(l['variant_id'] == '*' for l in layouts):
            cur.execute('INSERT INTO auto_edition_layouts(product_gid,variant_id,preparation_hash,approval) VALUES(%s,\'*\',%s,%s::jsonb)',
                        (pid,q['hash'],json.dumps(approval)))
        cur.execute("UPDATE auto_edition_onboarding SET status='Cloud Ready',reason='Product Uploads technical TEST validation completed',updated_at=now() WHERE product_gid=%s", (pid,))
        if d.get('technical_completion') != q['hash']:
            from auto_editions_onboarding_store import Queue
            Queue.audit(cur,pid,row['actor_id'],'product_upload_technical_complete',dict(intake_id=str(row['id']),preparation_hash=q['hash']))
        d['technical_completion'] = q['hash']
        return True
