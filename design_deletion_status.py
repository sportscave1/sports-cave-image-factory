"""Bounded shared deletion observations; never authorize a redo from this cache."""
from display_snapshot import Snapshots

CACHE = Snapshots(workers=1, limit=8, ttl=30, retry=10, max_age=60, byte_limit=128_000)


def snapshot(jobs, posted, *, refresh=False, force=False):
    from morning_design_queue import _deleted_designs
    candidates = [dict(job) for job in jobs if job['id'] not in posted
                  and job['stage'] in (4, 5) and (job['file_id'] or job['file_path'])]
    if not candidates:
        return dict(deleted=set(), state='ready')
    key = tuple(sorted((str(j['id']), j['stage'], j['file_id'], j['file_rev'], j['file_path'])
                       for j in candidates))
    if refresh:
        key = ('refresh',) + key
    def load():
        missing = (_deleted_designs(candidates, set(), exact_live_identity=True) if refresh
                   else _deleted_designs(candidates, set()))
        return [str(value) for value in missing]
    if force:
        CACHE.invalidate(key)
    result = CACHE.read(key, load)
    observed = set(result['value'] or ())
    return dict(deleted={job['id'] for job in candidates if str(job['id']) in observed}, state=result['state'])


def deleted(jobs, posted):
    return snapshot(jobs, posted)['deleted']


def invalidate():
    CACHE.invalidate_matching(lambda _: True)
    # Clear only affected display lanes; pending loaders cannot republish removed rows.
    from home_fast import SNAPSHOTS
    SNAPSHOTS.invalidate_matching(lambda key: key[-1] == 'Sports Updates')
    from companion_display import CACHE as companion
    companion.invalidate_matching(lambda _: True)
