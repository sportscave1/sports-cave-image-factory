"""Resumable, memory-only audience counts. Never writes customer membership."""
from copy import deepcopy
from crm_logic import eligibility, recipient_hash, LiveFacts, matches, now


def count_page(shop, store, source, previous=None):
    state=deepcopy(previous) if previous else dict(cursor=None,scanned=0,members=0,eligible=0,hashes=set(),excluded={},complete=False,checked_at=now().isoformat())
    if state['complete']:return state
    kind,definition=source
    page=shop.members(definition['id'],after=state['cursor'],fresh=True) if kind=='Shopify' else shop.customers(after=state['cursor'],fresh=True)
    for customer in page['nodes']:
        state['scanned']+=1
        if kind!='Shopify' and not matches(definition['rules'],LiveFacts(shop,customer,store.editions,fresh=True)):continue
        state['members']+=1
        hashed=recipient_hash(customer.get('email'))
        allowed,reason=eligibility(customer,store.suppressed(customer['id'],hashed))
        if allowed and hashed in state['hashes']:allowed,reason=False,'duplicate'
        if allowed:
            state['hashes'].add(hashed);state['eligible']+=1
        else:
            state.setdefault('excluded',{})[reason]=state.setdefault('excluded',{}).get(reason,0)+1
    if len(state['hashes'])>100000:raise ValueError('Interactive audience limit reached. Use a narrower Shopify segment.')
    more=page['pageInfo'].get('hasNextPage',False);cursor=page['pageInfo'].get('endCursor')
    if more and (not cursor or cursor==state['cursor']):raise ValueError('Shopify pagination did not advance.')
    state.update(cursor=cursor,complete=not more,checked_at=now().isoformat())
    return state
