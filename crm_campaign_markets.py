"""Market audiences on the existing Shopify authority; no persistent customer copy."""
import time
from crm_logic import marketing_state, eligibility
from crm_logic import recipient_hash, now

MARKET_LABELS={'AU':'AUSTRALIA','US':'USA','UK':'UK','Global':'ALL SUBSCRIBERS'}
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
        page=shop.campaign_subscribers(after=cursor)
        if page.get('complete') is False:raise ValueError('Subscriber records are incomplete.')
        profiles.update({c['id']:c for c in page['nodes']})
        if len(profiles)>20000:raise ValueError('Subscriber calculation limit reached; review required.')
        if not page['pageInfo'].get('hasNextPage'):break
        cursor=page['pageInfo'].get('endCursor')
        if not cursor or cursor in seen:raise ValueError('Subscriber pagination did not advance.')
        seen.add(cursor)
    suppressed,ids=store.active_suppression_hashes();recent=store.recent_marketing_hashes(hours)
    # Normalize/group once. Evaluate each profile once using the shared policy.
    # Segment-local dedup preserves existing country semantics when two profiles
    # share an address across countries; worldwide dedup still counts it once.
    groups={}
    for c in profiles.values():
        h=recipient_hash(c.get('email'))
        groups.setdefault(h,[]).append((c,country(c)))
    results={m:{'members':0,'eligible':0,'excluded':{},'diagnostics':{'conflicting_profiles':0},
        'recipients':[],'profiles':{},'complete':True,'checked_at':now().isoformat()} for m in MARKET_LABELS}
    reverse={code:m for m,code in COUNTRIES.items()}
    for h,rows in groups.items():
        conflict=len({marketing_state(c) for c,_ in rows})>1
        accepted=set()
        for c,code in rows:
            ok,reason=eligibility(c,h in suppressed or c['id'] in ids)
            if conflict:reason='conflicting_consent'
            elif ok and h in recent:reason='smart_sending'
            for market in (['Global',reverse[code]] if code in reverse else ['Global']):
                result=results[market];result['members']+=1
                why=reason or ('duplicate' if market in accepted else '')
                if why:result['excluded'][why]=result['excluded'].get(why,0)+1
                else:
                    accepted.add(market);result['eligible']+=1
                    result['recipients'].append({'id':c['id'],'hash':h});result['profiles'][c['id']]=c
    return results
