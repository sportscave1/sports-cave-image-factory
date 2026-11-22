"""Discover and rank engaged micro creators; send only into verified inbox threads."""
import os

from meta_social import CommunityError, assess_creator, reply_open, username
import social_community_store as ledger


def discover(api, handles=(), *, store=ledger):
    handles = sorted({username(handle) for handle in handles if str(handle).strip()}
                     | set(api.discover_engaged()))[:30]
    results, errors = [], []
    for handle in handles:
        try:
            profile = api.discover(handle)
            if not profile:
                raise CommunityError("Professional profile unavailable.")
            assessment = assess_creator(profile)
            store.save_creator(api.user, assessment)
            results.append(assessment)
        except CommunityError as exc:
            errors.append(f"@{handle}: {exc}")
    return results, errors


def eligible_threads(api, handles):
    handles = {username(handle) for handle in handles}
    matches = {}
    after = ""
    for _ in range(5):
        page = api.conversations("Instagram", after=after)
        for thread in page['data']:
            peers = [p for p in (thread.get('participants') or {}).get('data', [])
                     if str(p.get('id')) not in {api.instagram, api.page}]
            if len(peers) != 1:
                continue
            peer = api._request('GET', api_id(peers[0]['id']), params={'fields': 'username'})
            handle = str(peer.get('username') or '').lower()
            if handle in handles:
                messages = api.messages('Instagram', thread['id'])['data']
                if reply_open(messages, api.instagram):
                    matches[handle] = thread['id']
        if handles <= matches.keys():
            break
        after = page['after']
        if not after:
            break
    return matches


def eligible_thread(api, handle):
    return eligible_threads(api, [handle]).get(username(handle))


def api_id(value):
    from meta_social import identifier
    return identifier(value)


def invite(api, creator, *, store=ledger, eligible=None):
    if not api.writes:
        raise CommunityError("Invitations are disabled for this environment.")
    handle = creator['username']
    thread = eligible_thread(api, handle) if eligible is None else eligible.get(handle)
    if not thread:
        return "waiting_for_inbound"
    claimed = store.claim_invitation(api.user, handle)
    if not claimed:
        return "already_processed"
    try:
        result = api.send('Instagram', thread, claimed['draft'])
    except Exception:
        store.finish_invitation(api.user, handle, state='unknown')
        raise
    store.finish_invitation(api.user, handle, state='sent', message_id=result.get('message_id', ''))
    return "sent"


def run_automation(api, *, store=ledger):
    if not api.writes or os.environ.get('META_SOCIAL_AUTOMATION_ENABLED') != '1':
        raise CommunityError("Automatic outreach is disabled for this environment.")
    if not store.automation(api.user)['automation_enabled']:
        return {"sent": 0, "waiting_for_inbound": 0}
    discover(api, store=store)
    counts = {"sent": 0, "waiting_for_inbound": 0}
    candidates = [row for row in store.list_creators(api.user)
                  if row['fit'] and row['state'] in ('discovered', 'shortlisted')][:20]
    if not candidates:
        return counts
    eligible = eligible_threads(api, [row['username'] for row in candidates])
    for creator in candidates:
        state = invite(api, creator, store=store, eligible=eligible)
        if state in counts:
            counts[state] += 1
        if counts['sent'] >= 5:
            break
    return counts
