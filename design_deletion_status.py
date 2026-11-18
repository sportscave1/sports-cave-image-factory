"""Bounded shared deletion observations; never authorize a redo from this cache."""
from display_snapshot import Snapshots

CACHE = Snapshots(workers=1, limit=8, ttl=30, retry=10, max_age=60, byte_limit=128_000)


def deleted(jobs, posted):
    from morning_design_queue import _deleted_designs
    candidates = [dict(job) for job in jobs if job['id'] not in posted
                  and job['stage'] in (4, 5) and (job['file_id'] or job['file_path'])]
    if not candidates:
        return set()
    key = tuple(sorted((str(j['id']), j['stage'], j['file_id'], j['file_rev'], j['file_path'])
                       for j in candidates))
    snapshot = CACHE.read(key, lambda: [str(value) for value in _deleted_designs(candidates, set())])
    observed = set(snapshot['value'] or ())
    return {job['id'] for job in candidates if str(job['id']) in observed}


def invalidate():
    CACHE.invalidate_matching(lambda _: True)
    # Clear only affected display lanes; pending loaders cannot republish removed rows.
    from home_fast import SNAPSHOTS
    SNAPSHOTS.invalidate_matching(lambda key: key[-1] == 'Sports Updates')
    from companion_display import CACHE as companion
    companion.invalidate_matching(lambda _: True)
