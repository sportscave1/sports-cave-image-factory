"""Resumable, memory-only audience counts. Never writes customer membership."""
from copy import deepcopy
from crm_logic import eligibility, recipient_hash, LiveFacts, matches, now
import re


def validate_selection(audience):
    from crm_logic import validate_rules
    if set(audience)!={'kind','name','include','exclude'} or audience['kind']!='Selection' or not isinstance(audience['name'],str) or len(audience['name'])>300:raise ValueError('Invalid audience selection.')
    for key in ('include','exclude'):
        if not isinstance(audience[key],list) or len(audience[key])>10:raise ValueError('Choose up to ten segments per selection.')
        for source in audience[key]:
            if not isinstance(source,dict) or not isinstance(source.get('name'),str) or len(source['name'])>300:raise ValueError('Invalid audience reference.')
            if source.get('kind')=='Shopify':
                if set(source)!={'kind','name','id'} or not re.fullmatch(r'gid://shopify/Segment/\d+',source['id']):raise ValueError('Invalid Shopify segment reference.')
            elif source.get('kind')=='Rules':
                if set(source)!={'kind','name','rules'}:raise ValueError('Audience cannot contain customer records.')
                validate_rules(source['rules'])
            else:raise ValueError('Choose a saved segment or rules.')
    if not audience['include']:raise ValueError('Choose at least one included audience.')


def evaluate_profiles(profiles,excluded_ids,excluded_hashes,suppressed_hashes,suppressed_ids,recent_hashes, *, recipients=False):
    """Exclusive primary reasons; conflicting consent never resolves to SUBSCRIBED."""
    grouped={}
    for c in profiles:
        normalized=str(c.get('email') or '').strip().casefold()
        grouped.setdefault(normalized or 'missing:'+c['id'],[]).append(c)
    reasons={};allowed=[];selected=[];diagnostic={'conflicting_profiles':0}
    for address,rows in grouped.items():
        states={(c.get('emailMarketingConsent') or {}).get('marketingState','NOT_SUBSCRIBED') for c in rows}
        conflict=len(states)>1
        if conflict:diagnostic['conflicting_profiles']+=len(rows)
        accepted=False
        for c in rows:
            h=recipient_hash(c.get('email'))
            if c['id'] in excluded_ids or h in excluded_hashes:reason='excluded_segment'
            elif conflict:reason='conflicting_consent'
            else:
                ok,reason=eligibility(c,h in suppressed_hashes or c['id'] in suppressed_ids)
                if ok:
                    if h in recent_hashes:reason='smart_sending'
                    elif accepted:reason='duplicate'
                    else:reason='';accepted=True;allowed.append(h);selected.append({'id':c['id'],'hash':h})
            if reason:reasons[reason]=reasons.get(reason,0)+1
    result={'members':len(profiles),'eligible':len(allowed),'excluded':reasons,'diagnostics':diagnostic}
    if recipients:result['recipients']=selected
    return result


def selection_page(shop,store,audience,previous=None,*,smart_hours=16,recipients=False):
    """One bounded Shopify page per click; only aggregates leave session memory.

    Includes are unioned by customer ID; exclusions also apply by normalized email.
    A final all-customer consent pass detects conflicting profiles outside a segment.
    Partial calculations never report a dispatch-safe eligible count.
    """
    validate_selection(audience)
    state=deepcopy(previous) if previous else {'source':0,'cursor':None,'profiles':{},'excluded_ids':set(),'excluded_hashes':set(),'pages':0,'complete':False,'checked_at':now().isoformat()}
    if state['complete']:return state
    sources=[('include',s) for s in audience['include']]+[('exclude',s) for s in audience['exclude']]+[('consent',{'kind':'Rules'})]
    purpose,source=sources[state['source']]
    page=shop.members(source['id'],after=state['cursor'],fresh=True) if source['kind']=='Shopify' else shop.customers(after=state['cursor'],fresh=True)
    if page.get('complete') is False:raise ValueError('Shopify returned incomplete customer records; eligibility is unavailable.')
    if purpose=='consent':
        selected_hashes={recipient_hash(c.get('email')) for c in state['profiles'].values()}
        for c in page['nodes']:
            h=recipient_hash(c.get('email'))
            if h in selected_hashes:
                # Add outside profiles for conflict detection without expanding audience.
                state.setdefault('consent_profiles',{})[c['id']]=c
    else:
        for c in page['nodes']:
            if source['kind']=='Rules' and not matches(source['rules'],LiveFacts(shop,c,store.editions,fresh=True)):continue
            if purpose=='include':state['profiles'][c['id']]=c
            else:state['excluded_ids'].add(c['id']);state['excluded_hashes'].add(recipient_hash(c.get('email')))
    if len(state['profiles'])>20000 or state['pages']>=2000:raise ValueError('Interactive audience limit reached. Narrow the selection; no complete estimate was saved.')
    state['pages']+=1
    more=page['pageInfo'].get('hasNextPage');cursor=page['pageInfo'].get('endCursor')
    if more and (not cursor or cursor==state['cursor']):raise ValueError('Shopify pagination did not advance. Audience remains incomplete.')
    state['cursor']=cursor if more else None
    if not more:state['source']+=1
    state['checked_at']=now().isoformat();state['complete']=state['source']==len(sources)
    if state['complete']:
        if set(state['profiles'])-set(state.get('consent_profiles',{})):raise ValueError('Some selected customers could not be verified in current Shopify data. Eligibility is unavailable.')
        for cid in state['profiles']:state['profiles'][cid]=state['consent_profiles'][cid]
        suppressed,ids=store.active_suppression_hashes();recent=store.recent_marketing_hashes(smart_hours)
        conflicts=set();states={}
        for c in list(state['profiles'].values())+list(state.get('consent_profiles',{}).values()):
            states.setdefault(recipient_hash(c.get('email')),set()).add((c.get('emailMarketingConsent') or {}).get('marketingState','NOT_SUBSCRIBED'))
        conflicts={h for h,s in states.items() if len(s)>1}
        result=evaluate_profiles(list(state['profiles'].values()),state['excluded_ids'],state['excluded_hashes'],suppressed,ids,recent,recipients=recipients)
        # Re-evaluate affected selected profiles with the globally observed conflict.
        if conflicts:
            safe=[c for c in state['profiles'].values() if recipient_hash(c.get('email')) not in conflicts]
            result=evaluate_profiles(safe,state['excluded_ids'],state['excluded_hashes'],suppressed,ids,recent,recipients=recipients)
            for c in state['profiles'].values():
                if recipient_hash(c.get('email')) in conflicts:
                    reason='excluded_segment' if c['id'] in state['excluded_ids'] or recipient_hash(c.get('email')) in state['excluded_hashes'] else 'conflicting_consent'
                    result['excluded'][reason]=result['excluded'].get(reason,0)+1
            result['members']=len(state['profiles']);result['diagnostics']['conflicting_profiles']=sum(recipient_hash(c.get('email')) in conflicts for c in state['profiles'].values())
        state.update(result)
    else:state.update(members=len(state['profiles']),eligible=0,excluded={})
    return state


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
