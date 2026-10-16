"""Synthetic browser fixture state. No production data or integrations."""
stage='Queued'
review_jobs={}


def rows(ids):
    result=[dict(product_gid=pid,status=stage,icon='◷' if stage=='Queued' else '↻',reason='',
                 checkpoint=stage,checkpoint_at='2026-10-15T00:00:00Z',preparation_hash=None,actions=[],reset_allowed=True) for pid in ids]
    for row in result:
        job=review_jobs.get(row['product_gid'])
        if job:
            row.update(status='Review',preparation_hash=job['hash'],review_operation=dict(label=job['label'],reason=job.get('reason',''),job_id=row['product_gid']))
    return result
