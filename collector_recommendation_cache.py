"""Private ranked IDs only; ownership and eligibility are never cached here."""
import hashlib
import json

from collector_preview_cache import ByteCache, PreviewBusyError


CANDIDATES = ByteCache(max_bytes=2 * 1024 * 1024, max_entries=128, ttl=120, max_pending=8)


def ranked_candidates(shop, customer_id, owned, seed, country, load):
    from collector_vault import CollectorVaultUnavailableError
    identity = {
        'recipe': 'collection-ranking-v1',
        'shop': str(shop.namespace),
        'source_cache': id(shop.cache),
        'generation': shop.cache.generation,
        'owner': str(customer_id),
        'owned': sorted(owned),
        'seed': seed,
        'country': country,
    }
    key = hashlib.sha256(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()
    try:
        content = CANDIDATES.get_or_load(key, lambda: json.dumps(load(), separators=(',', ':')).encode())
    except (PreviewBusyError, TimeoutError):
        raise CollectorVaultUnavailableError('Recommendations are temporarily busy. Please retry.') from None
    # Return a new value so a caller cannot mutate another request's cached IDs.
    return json.loads(content)
