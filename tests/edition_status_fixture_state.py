"""Synthetic browser fixture state. No production data or integrations."""
stage='Queued'


def rows(ids):
    return [dict(product_gid=pid,status=stage,icon='◷' if stage=='Queued' else '↻',reason='',
                 checkpoint=stage,checkpoint_at='2026-10-15T00:00:00Z',preparation_hash=None,actions=[],reset_allowed=True) for pid in ids]
