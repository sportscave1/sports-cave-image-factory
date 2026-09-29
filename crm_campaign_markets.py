"""Market audiences on the existing Shopify authority; no persistent customer copy."""
import time
from crm_audience import evaluate_profiles
from crm_logic import recipient_hash, now

MARKET_LABELS={'AU':'AU','US':'USA','UK':'UK','Global':'GLOBAL'}
COUNTRIES={'AU':'AU','US':'US','UK':'GB'}

def country(customer):
    address=customer.get('defaultAddress') or {}
    raw=str(address.get('countryCodeV2') or address.get('countryCode') or address.get('country') or customer.get('country') or '').strip().upper()
    return {'AUSTRALIA':'AU','AUS':'AU','USA':'US','UNITED STATES':'US','UNITED STATES OF AMERICA':'US','UK':'GB','UNITED KINGDOM':'GB','GREAT BRITAIN':'GB','GBR':'GB'}.get(raw,raw)

def audience(market):
    rules=[{'field':'consent','op':'eq','value':'SUBSCRIBED'}]
    if market in COUNTRIES:rules.append({'field':'country','op':'eq','value':COUNTRIES[market]})
    return {'kind':'Rules','name':'Subscribed · '+MARKET_LABELS[market],'rules':{'all':rules}}

def calculate(shop,store,hours=16,*,clock=time.monotonic):
    """One paginated authority pass for all four markets, including consent conflicts.

    All profiles must be checked for conflicting consent; only eligible recipients
    are returned. Raw profiles remain transient and never enter draft storage.
    """
    start=clock();cursor=None;profiles={};seen=set()
    while True:
        if clock()-start>30:raise ValueError('Subscriber counts timed out. Review again before sending.')
        page=shop.customers(after=cursor,fresh=True)
        if page.get('complete') is False:raise ValueError('Subscriber records are incomplete.')
        profiles.update({c['id']:c for c in page['nodes']})
        if len(profiles)>20000:raise ValueError('Subscriber calculation limit reached; review required.')
        if not page['pageInfo'].get('hasNextPage'):break
        cursor=page['pageInfo'].get('endCursor')
        if not cursor or cursor in seen:raise ValueError('Subscriber pagination did not advance.')
        seen.add(cursor)
    suppressed,ids=store.active_suppression_hashes();recent=store.recent_marketing_hashes(hours)
    states={}
    for c in profiles.values():states.setdefault(recipient_hash(c.get('email')),set()).add((c.get('emailMarketingConsent') or {}).get('marketingState','NOT_SUBSCRIBED'))
    conflicts={h for h,s in states.items() if len(s)>1}
    results={}
    for market in MARKET_LABELS:
        rows=[c for c in profiles.values() if market=='Global' or country(c)==COUNTRIES[market]]
        safe=[c for c in rows if recipient_hash(c.get('email')) not in conflicts]
        result=evaluate_profiles(safe,set(),set(),suppressed,ids,recent,recipients=True)
        conflict_count=len(rows)-len(safe)
        if conflict_count:result['excluded']['conflicting_consent']=conflict_count
        result.update(members=len(rows),complete=True,checked_at=now().isoformat())
        result['profiles']={r['id']:profiles[r['id']] for r in result['recipients']}
        results[market]=result
    return results
