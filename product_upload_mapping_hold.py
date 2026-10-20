"""Scoped preparation exclusion for an explicitly requested upload mapping.

Preparation is admitted only after finalisation. Database guards also protect older
discovery/Companion processes during a rolling release.
"""

TABLE = 'public.product_upload_mapping_holds'
GUARDS = ('upload_hold_onboarding', 'upload_hold_discovery', 'upload_hold_inventory',
          'upload_hold_mapping', 'upload_hold_render')


def held(cur, pid=None, file_id=None):
    # Existing workflows remain usable before this additive migration is applied.
    cur.execute("SELECT to_regclass(%s) AS name", (TABLE,))
    if not cur.fetchone()['name']:
        return False
    cur.execute('SELECT 1 FROM '+TABLE+' WHERE product_gid=%s OR file_id=%s', (pid, file_id))
    matched=bool(cur.fetchone())
    if not matched:return False
    cur.execute("SELECT to_regprocedure('public.product_upload_mapping_complete(uuid,text,text)') AS name")
    if not cur.fetchone()['name']:return True
    cur.execute('SELECT 1 FROM '+TABLE+' WHERE (product_gid=%s OR file_id=%s) AND NOT public.product_upload_mapping_complete(operation_id,product_gid,file_id)',(pid,file_id))
    return bool(cur.fetchone())


def assert_ready(cur):
    cur.execute("SELECT to_regprocedure('public.product_upload_mapping_complete(uuid,text,text)') AS name")
    if not cur.fetchone()['name']:
        raise ValueError('Coordinated Map migration is required before moving a PSD.')
    cur.execute("SELECT count(*) AS n FROM pg_trigger WHERE tgname=ANY(%s) AND tgenabled='O' AND NOT tgisinternal", (list(GUARDS),))
    if cur.fetchone()['n'] != len(GUARDS):
        raise ValueError('Sync & Map requires the mapping-only preparation guards migration. No PSD was moved.')


def acquire(connect, key, actor, pid, file_id):
    with connect() as conn, conn.cursor() as cur:
        assert_ready(cur)
        # Same order as discovery/mapping. Serialize admission against old and
        # new enqueue/claim paths before the source enters the live folder.
        cur.execute('LOCK TABLE edition_products IN SHARE ROW EXCLUSIVE MODE')
        cur.execute('LOCK TABLE product_psd_mappings IN SHARE ROW EXCLUSIVE MODE')
        cur.execute('LOCK TABLE auto_edition_onboarding,auto_edition_jobs IN SHARE ROW EXCLUSIVE MODE')
        cur.execute('SELECT * FROM '+TABLE+' WHERE operation_id=%s OR product_gid=%s OR file_id=%s', (key, pid, file_id))
        rows = cur.fetchall()
        if rows:
            if len(rows) != 1 or any(str(rows[0][k]) != str(v) for k,v in
                    dict(operation_id=key, actor_id=actor, product_gid=pid, file_id=file_id).items()):
                error = ValueError('Another upload owns the preparation hold for this product or PSD. Nothing was replaced.')
                if len(rows)==1 and all(str(rows[0][k])==str(v) for k,v in
                        dict(actor_id=actor,product_gid=pid,file_id=file_id).items()):
                    error = ValueError('This PSD has an earlier saved mapping attempt. Open that attempt and retry to resume its retained progress; no files or holds were replaced.')
                    error.resume_upload_id = str(rows[0]['operation_id'])
                raise error
        cur.execute("SELECT 1 FROM auto_edition_onboarding WHERE (product_gid=%s OR file_id=%s)", (pid,file_id))
        if cur.fetchone():
            raise ValueError('This product or PSD already has preparation work. Resolve that existing work before mapping; it was not changed.')
        cur.execute("SELECT 1 FROM auto_edition_jobs WHERE (payload->'identity'->'source'->>'product_gid'=%s OR payload->'identity'->'source'->>'file_id'=%s) AND status IN ('Queued','Generating')", (pid,file_id))
        if cur.fetchone():
            raise ValueError('This product already has rendering work. It was not changed.')
        cur.execute("SELECT 1 FROM auto_edition_preparations WHERE manifest->'source'->>'product_gid'=%s OR manifest->'source'->>'file_id'=%s", (pid,file_id))
        if cur.fetchone():
            raise ValueError('This product or PSD has retained preparation assets. Review that existing workflow before Sync & Map; it was not changed.')
        cur.execute('INSERT INTO '+TABLE+'(operation_id,actor_id,product_gid,file_id) VALUES(%s,%s,%s,%s) ON CONFLICT(operation_id) DO NOTHING', (key,str(actor),pid,file_id))
        # Remove only disposable discovery metadata for this held operation.
        cur.execute('DELETE FROM auto_edition_discovery WHERE product_gid=%s', (pid,))
        cur.execute('DELETE FROM auto_edition_source_inventory WHERE file_id=%s', (file_id,))


def verify(cur, key, pid, file_id):
    assert_ready(cur)
    cur.execute('SELECT 1 FROM '+TABLE+' WHERE operation_id=%s AND product_gid=%s AND file_id=%s', (key,pid,file_id))
    if not cur.fetchone():
        raise ValueError('Automatic preparation is not held for this exact upload.')
    if not held(cur,pid,file_id):return
    cur.execute("SELECT 1 FROM auto_edition_onboarding WHERE (product_gid=%s OR file_id=%s)", (pid,file_id))
    if cur.fetchone():
        raise ValueError('Unexpected preparation work exists for this upload. Success cannot be confirmed.')
