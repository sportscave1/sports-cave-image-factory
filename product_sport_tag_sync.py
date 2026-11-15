"""Tag-only Shopify adapter. Uses existing auth/transport and webhook retries.

Never creates products or replaces a product's tag array. A repeated delivery or
uncertain mutation response is reconciled by reading the same product again.
"""
import re
from product_sport_tags import classify_product, tag_list

PRODUCT_QUERY = '''query SportTagProduct($id: ID!, $after: String) {
  product(id: $id) {
    id title tags productType descriptionHtml
    collections(first: 100, after: $after) {
      nodes { id title handle }
      pageInfo { hasNextPage endCursor }
    }
  }
}'''
ADD_TAGS = '''mutation SportTagsAdd($id: ID!, $tags: [String!]!) {
  tagsAdd(id: $id, tags: $tags) { node { id } userErrors { field message } }
}'''


class SportTagSyncError(RuntimeError):
    pass


def product_gid(value):
    raw = str(value or '')
    if raw.isdigit(): raw = 'gid://shopify/Product/' + raw
    if not re.fullmatch(r'gid://shopify/Product/[1-9][0-9]*', raw):
        raise SportTagSyncError('Sport tagging requires an exact Shopify Product ID.')
    return raw


def read_product(gid, request):
    after, seen, collections, first = None, set(), [], None
    for _ in range(50):
        data = request(PRODUCT_QUERY, {'id': gid, 'after': after})
        product = data.get('product')
        if not isinstance(product, dict) or product.get('id') != gid or not isinstance(product.get('tags'), list):
            raise SportTagSyncError('Sport tagging readback missing/wrong product or tags: ' + gid)
        if first is None: first = product
        elif any(product.get(k) != first.get(k) for k in ('title', 'tags', 'productType', 'descriptionHtml')):
            raise SportTagSyncError('Product changed during collection pagination; retry with fresh evidence: ' + gid)
        connection = product.get('collections') or {}
        if not isinstance(connection.get('nodes'), list) or not isinstance(connection.get('pageInfo'), dict):
            raise SportTagSyncError('Sport tagging requires complete collection membership: ' + gid)
        collections.extend(connection['nodes'])
        page = connection['pageInfo']
        if not page.get('hasNextPage'):
            return {**first, 'collections': collections}
        after = page.get('endCursor')
        if not after or after in seen: break
        seen.add(after)
    raise SportTagSyncError('Collection pagination incomplete; no uncertain tags written: ' + gid)


def sync_product_sport_tags(product_id, *, config=None, request=None):
    """Return verified/review_required; raise on transient/API verification errors.

    At most two additive attempts. Each retry derives its tags from a fresh read.
    The caller's existing failed webhook receipt handles later retries. Collections
    and title are read from Shopify, never trusted from stale webhook payloads.
    """
    gid = product_gid(product_id)
    if request is None:
        from shopify_sync import graphql_request
        def request(query, variables):
            return graphql_request(query, variables=variables, timeout=10, config=config)[0]
    added = set()
    for attempt in range(2):
        try:
            current = read_product(gid, request)
            plan = classify_product(current)
            if not plan.ready:
                return {'status': 'review_required', 'product_id': gid,
                        'required_tags': list(plan.required_tags), 'review': list(plan.review),
                        'evidence': list(plan.evidence), 'added_tags': sorted(added)}
            if not plan.missing_tags:
                return {'status': 'verified', 'product_id': gid,
                        'required_tags': list(plan.required_tags), 'added_tags': sorted(added), 'review': []}
            response = request(ADD_TAGS, {'id': gid, 'tags': list(plan.missing_tags)})
            payload = response.get('tagsAdd') or {}
            if payload.get('userErrors'):
                messages = '; '.join(str(e.get('message') or 'Unknown error') for e in payload['userErrors'])
                raise SportTagSyncError('Shopify rejected sport tags for ' + gid + ': ' + messages)
            if (payload.get('node') or {}).get('id') != gid:
                raise SportTagSyncError('Sport tag mutation did not confirm the expected product: ' + gid)
            added.update(plan.missing_tags)
            observed = read_product(gid, request)
            if not set(plan.merged_tags) <= set(tag_list(observed['tags'])):
                raise SportTagSyncError('SPORT TAGGING UNVERIFIED: missing tags on fresh readback: ' + gid)
            fresh = classify_product(observed)
            if not fresh.ready or fresh.missing_tags:
                raise SportTagSyncError('Product evidence changed during sport tagging; fresh review required: ' + gid)
            return {'status': 'verified', 'product_id': gid,
                    'required_tags': list(fresh.required_tags), 'added_tags': sorted(added), 'review': []}
        except Exception as exc:
            # Even a timeout may have succeeded remotely. Retry from a fresh read,
            # never by creating/replacing a product or overwriting its tag array.
            if attempt:
                raise SportTagSyncError('SPORT TAGGING UNVERIFIED for ' + gid +
                                        '; retry the same product. ' + type(exc).__name__ +
                                        (': ' + str(exc) if isinstance(exc, SportTagSyncError) else '')) from exc
    raise AssertionError('unreachable')
