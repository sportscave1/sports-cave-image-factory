"""Collect existing successful exports after a rejection, without generation."""
import time


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
        value.update(stage='failed', recovery_checked_version=1,
            detail=blocker['reason'] + (' Completed exports saved; missing images require review.'
                if not payload['missing'] else ' Existing export collection needs review; saved files retained.'))
        ads.write(ads.PREFIX+value['upload'], value)
        return {}
    value['detail'] = 'Saving available images and CSV; rejected slots remain blocked for review.'
    ads.write(ads.PREFIX+value['upload'], value)
    return payload
