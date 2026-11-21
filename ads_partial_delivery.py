"""Collect existing successful exports after a rejection, without generation."""
import time


def saved_count(value):
    import design_publish_ad as ads
    return sum(name in (value.get('artifacts') or {}) for name in ads.COVERS.values())


def posting_routes(value):
    """Freeze two original successful routes, never substitute an archive image."""
    import design_publish_ad as ads
    blocker = value.get('blocked_collection') or {}
    selected = value.get('partial_routes') or []
    if (not value.get('partial_posting') or blocker.get('state') != 'saved'
            or len(selected) != 2 or len(set(selected)) != 2
            or any(route not in ads.COVERS or ads.COVERS[route] in blocker.get('excluded', []) for route in selected)):
        raise ValueError('Partial posting requires two saved original, non-rejected routes.')
    return [(route, ads.COVERS[route]) for route in ads.COVERS if route in selected]


def prepare_available(value):
    import design_publish_ad as ads
    receipts = value.get('artifacts') or {}
    excluded = value['blocked_collection']['excluded']
    routes = [route for route, name in ads.COVERS.items() if name not in excluded and name in receipts]
    names = ['ad_copy.csv', *(ads.COVERS[route] for route in routes)]
    if len(routes) != 2 or any(not all(receipts.get(name, {}).get(k) for k in ('id','rev','hash','size')) for name in names):
        return False
    if len({receipts[ads.COVERS[route]]['hash'] for route in routes}) != 2:
        return False
    value.update(partial_posting=True, partial_routes=routes)
    return True


def begin(value, reason):
    import design_publish_ad as ads
    # Only an exact saved chat and named missing slots authorize collection.
    # An unknown blocker retains the normal terminal review behavior.
    excluded = [name for name in ads.COVERS.values() if name in reason]
    if (value.get('posting_id') or not value.get('folder') or not excluded
            or not ads.CHAT.fullmatch(value.get('chat_url', ''))):
        return False
    value.setdefault('blocked_collection', dict(reason=reason, excluded=excluded,
                                               started_at=time.time()))
    value.update(stage='generating', collect_only=True, chat_generating=False)
    value.pop('prompt', None)
    return True


def advance(value, event):
    import design_publish_ad as ads
    from ads_companion_transfer import delivery
    blocker = value['blocked_collection']
    # Queued collection starts its deadline when it first owns the worker slot.
    blocker.setdefault('started_at', time.time())
    payload = delivery(value)
    if not payload['missing'] or event.get('transfer_failed') is True or time.time()-blocker['started_at'] > 600:
        blocker['state'] = 'saved' if not payload['missing'] else 'needs_download_review'
        if not payload['missing'] and prepare_available(value):
            value['detail'] = 'Continuing with two saved covers; the rejected slot still needs provider review.'
            ads.write(ads.PREFIX+value['upload'], value)
            return None  # Continue only the two unaffected original ads.
        value.update(stage='failed', recovery_checked_version=1,
            detail=blocker['reason'] + (' Completed exports saved; missing images require review.'
                if not payload['missing'] else ' Existing export collection needs review; saved files retained.'))
        ads.write(ads.PREFIX+value['upload'], value)
        return {}
    value['detail'] = 'Saving available images and CSV; rejected slots remain blocked for review.'
    ads.write(ads.PREFIX+value['upload'], value)
    return payload
