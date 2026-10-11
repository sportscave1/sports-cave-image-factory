"""Read-only sport intelligence; reuse the existing Shopify segment projection.

Never infer a sport from prose, names, productType or legacy interest: tags.
Snapshot definitions must match the inspected purchase/history grammar exactly.
"""
import re
from crm_buyer_segments import BUYER_NAMES, TTL, snapshot_key
from product_sport_tags import TAGS, MOTOR_CHILDREN


def classifications(product):
    tags = product.get('tags') or []
    if not isinstance(tags, list): return set()
    return {sport for sport, tag in TAGS.items() if tag in tags} - {'Apparel'}


def definition_sport(row):
    name = row.get('name', '')
    if name not in BUYER_NAMES: return None
    sport = name.removesuffix(' Buyers')
    if sport == 'Combat Sports': sport = 'Combat'
    tag = TAGS.get(sport)
    if not tag: return None
    history = 'SC_HIST_' + ('APPAREL' if sport == 'Apparel' else tag.removeprefix('SC_SPORT_'))
    query = re.sub(r'\s+', ' ', row.get('query', '').strip())
    base = "products_purchased MATCHES (tag CONTAINS '" + tag + "')"
    return sport if query in (base, base + " OR customer_tags CONTAINS '" + history + "'") else None


def segment_interests(shop, store, customer_id, at):
    """Fresh server-side, store-scoped sync only; never run sync from delivery."""
    try:
        state = store.state(snapshot_key(shop))
        if not isinstance(state, dict) or not 0 <= at.timestamp() - state.get('timestamp', 0) <= TTL:
            return set(), 'segment_snapshot_unavailable_or_stale'
        interests = set()
        for name, identity in state.get('bindings', {}).items():
            row = state.get('segments', {}).get(identity)
            if not isinstance(row, dict) or row.get('id') != identity: continue
            sport = definition_sport({**row, 'name': name})
            if sport and customer_id in row.get('members', []): interests.add(sport)
        return interests - {'Apparel'}, 'authoritative_segment_snapshot'
    except Exception:
        # An optional projection outage cannot block a consent-verified email.
        return set(), 'segment_snapshot_unavailable_or_stale'


def specific(interests):
    result = set(interests)
    if result & MOTOR_CHILDREN: result.discard('Motorsport')
    if 'WWE' in result: result.discard('Combat')
    return result


def relevance(interests, product):
    """0 exact, 1 conservative parent-only match, None unrelated/unclassified.

    Sibling motorsports are never a fallback for a precise discipline. V8 has
    no verified Australian-parent tag, so its fallback remains exact only.
    """
    wanted = specific(interests); actual = classifications(product)
    if wanted & actual: return 0
    if wanted & (MOTOR_CHILDREN - {'V8 Supercars'}) and 'Motorsport' in actual and not actual & MOTOR_CHILDREN:
        return 1
    if 'WWE' in wanted and 'Combat' in actual and 'WWE' not in actual: return 1
    return None


def search_tags(interests):
    sports = sorted(specific(interests))
    # Four bounded groups: precise disciplines precede optional broad fallback.
    if set(sports) & (MOTOR_CHILDREN - {'V8 Supercars'}): sports.append('Motorsport')
    if 'WWE' in sports: sports.append('Combat')
    return [TAGS[s] for s in dict.fromkeys(sports)][:4]
