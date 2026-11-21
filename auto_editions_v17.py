"""V17 continuous scheduling policy. Disabled until an owner-approved rollout."""
import os


def enabled():
    return os.getenv('AUTO_EDITIONS_V17_CONTINUOUS_ENABLED','').lower()=='true'


def unique_products(rows):
    """One displayed state per product, even if a legacy join repeats a row."""
    return list({row['product_gid']:row for row in rows}.values())


def dashboard(rows,mapped):
    counts={name:0 for name in ('Total mapped','Cloud Ready','Preparing','Queued','Needs Review','Needs PSD Repair','Failed','Remaining','Uploaded','Production Ready')}
    counts['Total mapped']=mapped
    for row in unique_products(rows):
        state=row.get('display_status',row.get('status','Unavailable'))
        key={'Review':'Needs Review','Needs Review':'Needs Review','Needs Repair':'Needs PSD Repair',
             'Needs PSD Repair':'Needs PSD Repair','Uploading':'Preparing','Recovering':'Preparing',
             'Deferred':'Queued' if enabled() else 'Deferred','Connect':'Queued'}.get(state,state)
        if key in counts:counts[key]+=1
        if row.get('uploaded') is True:counts['Uploaded']+=1
    counts['Remaining']=max(0,mapped-counts['Cloud Ready']-counts['Production Ready'])
    return counts


def receipt_sql(alias):
    # Expand patch names once per preparation, rather than once per receipt.
    # UNION keeps the name join one-to-one. Preserve the original NULL truth
    # table as well; full manifest/approval validation remains a separate fence.
    if alias not in ('p','prep'):raise ValueError('Fixed preparation SQL alias required.')
    total=f"(CASE WHEN {alias}.manifest->>'edition_total' ~ '^[1-9][0-9]{{0,3}}$' THEN ({alias}.manifest->>'edition_total')::int ELSE 0 END)"
    assets=f"CASE WHEN jsonb_typeof({alias}.receipts->'assets')='array' THEN {alias}.receipts->'assets' ELSE '[]'::jsonb END"
    return f"""COALESCE({alias}.receipts->>'preparation_hash'={alias}.hash AND
        (WITH allowed_names AS MATERIALIZED (
           SELECT {alias}.manifest->'master'->>'name' AS name
           UNION
           SELECT patch.value->>'name'
           FROM jsonb_each(CASE WHEN jsonb_typeof({alias}.manifest->'patches')='object'
             THEN {alias}.manifest->'patches' ELSE '{{}}'::jsonb END) patch
         )
         SELECT count(*)={total}+1 AND count(DISTINCT a->>'name')={total}+1
        AND count(DISTINCT a->>'file_id')={total}+1
        AND bool_and(left(COALESCE(a->>'file_id',''),3)='id:' AND COALESCE(a->>'revision','')<>''
            AND (allowed_names.name IS NOT NULL OR a->>'name'={alias}.manifest->'master'->>'name'))
         FROM jsonb_array_elements({assets}) a
         LEFT JOIN allowed_names ON allowed_names.name=a->>'name'),false)"""
