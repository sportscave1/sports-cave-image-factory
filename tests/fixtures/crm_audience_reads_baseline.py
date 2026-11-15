"""Bounded transient reads for a selected native audience; no customer mirror."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import logging
import time

from crm_logic import email, recipient_hash, marketing_state

LOG = logging.getLogger(__name__)


@contextmanager
def timed(stage):
    started = time.monotonic()
    try:
        yield
    finally:
        LOG.info('campaign_review stage=%s duration_ms=%.1f', stage,
                 (time.monotonic() - started) * 1000)


def selected_profiles(shop, identities):
    identities = sorted(set(identities))
    if len(identities) > 20000:
        raise ValueError('Audience calculation limit reached.')
    profiles = {}
    deadline = time.monotonic() + 30
    with timed('profile_fetch'):
        for start in range(0, len(identities), 50):
            if time.monotonic() > deadline:
                raise ValueError('Selected profile verification timed out. Review again.')
            batch = identities[start:start + 50]
            rows = shop.customer_batch(batch, fresh=True)
            found = {c['id']: c for c in rows}
            if len(rows) != len(found) or set(found) != set(batch):
                raise ValueError('Shopify member profiles are incomplete.')
            profiles.update(found)
    with timed('conflict_validation'):
        addresses = {email(c.get('email')) for c in profiles.values()} - {''}
        related = shop.campaign_email_profiles(addresses) if addresses else []
        by_id = {c['id']: c for c in related}
        # Search indexing lag, missing profiles, or changed email/consent fails closed.
        for c in profiles.values():
            if not email(c.get('email')):
                continue  # Existing eligibility rejects invalid addresses.
            current = by_id.get(c['id'])
            if (not current or email(current.get('email')) != email(c.get('email'))
                    or marketing_state(current) != marketing_state(c)):
                raise ValueError('Selected Shopify identities changed during verification. Review again.')
        states = {}
        for c in related:
            if email(c.get('email')) in addresses:
                states.setdefault(recipient_hash(c.get('email')), set()).add(marketing_state(c))
        conflicts = {h for h, values in states.items() if len(values) > 1}
    return profiles, conflicts


def suppression_state(store, hours):
    with timed('suppression_reads'):
        suppressed, ids = store.active_suppression_hashes()
        return suppressed, ids, store.recent_marketing_hashes(hours)


def selected_reads(shop, store, identities, hours):
    # One Shopify lane, one independent DB lane. Shopify's global cost/semaphore
    # protections still govern all requests; no per-recipient tasks are created.
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix='review-local') as pool:
        local = pool.submit(suppression_state, store, hours)
        profiles, conflicts = selected_profiles(shop, identities)
        suppressed, ids, recent = local.result()
    return profiles, conflicts, suppressed, ids, recent
