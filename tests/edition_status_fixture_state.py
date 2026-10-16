"""Synthetic browser fixture state. No production data or integrations."""
stage='Queued'
review_jobs={}
mapping_overrides={}


def rows(ids):
    result=[dict(product_gid=pid,status=stage,icon='◷' if stage=='Queued' else '↻',reason='',
                 checkpoint=stage,checkpoint_at='2026-10-15T00:00:00Z',preparation_hash=None,actions=[],reset_allowed=stage!='Cancelling'+chr(8230),cancelling=stage=='Cancelling'+chr(8230)) for pid in ids]
    for row in result:
        if row['product_gid'] in mapping_overrides:
            row['mapping_file_id']=mapping_overrides[row['product_gid']]
            if row['mapping_file_id'] is None:row.update(status='Not Connected',reason='Reset; manually Add the PSD to start again.',checkpoint='Reset — manually Add PSD')
        job=review_jobs.get(row['product_gid'])
        if job:
            row.update(status='Review',preparation_hash=job['hash'],review_operation=dict(label=job['label'],reason=job.get('reason',''),job_id=row['product_gid']))
    return result
