"""Session-pinned real lifecycle examples. Read-only; no enrollment or delivery."""
from copy import deepcopy
from types import SimpleNamespace
from crm_logic import now,eligibility,recipient_hash
from crm_automation_preview_cache import digest
import time


class NoPreviewCustomer(ValueError):
    pass


def flow_row(store):
    row=getattr(store,'preview_row',None) or store.flow(store.draft_identity)
    return {**row,'config':{**row['config'],'draft':getattr(store,'preview_flow',None) or row['config']['draft']}}


def candidates(store,row):
    kind=row['config']['draft']['trigger']
    if kind=='welcome':
        return store.q("SELECT customer_id AS key,customer_id,name,email FROM crm_lifecycle_customers WHERE consent='SUBSCRIBED' AND subscribed_at IS NOT NULL ORDER BY subscribed_at DESC,customer_id LIMIT 50")
    # Existing consent/order ledgers only supply candidates. Fresh Shopify facts
    # below remain authority, including consent, suppressions and inactivity.
    sql="""WITH paid AS (SELECT object_id,min(occurred_at) AS paid_at
      FROM crm_webhook_events WHERE provider='shopify' AND topic='orders/paid' GROUP BY object_id),
      fulfilled AS (SELECT object_id,max(occurred_at) AS fulfilled_at FROM crm_webhook_events
      WHERE provider='shopify' AND topic='orders/fulfilled' GROUP BY object_id)
      SELECT o.shopify_order_id AS key,c.customer_id,c.name,c.email
      FROM shopify_orders o JOIN crm_lifecycle_customers c
      ON COALESCE(NULLIF(o.shopify_customer_id,''),o.customer_id)=c.customer_id
      LEFT JOIN paid p ON p.object_id=o.shopify_order_id
      LEFT JOIN fulfilled f ON f.object_id=o.shopify_order_id
      WHERE c.consent='SUBSCRIBED' AND upper(o.financial_status)='PAID' AND o.cancelled_at IS NULL
      """
    args=()
    if kind=='win_back':
        from datetime import timedelta
        sql+=" AND COALESCE(p.paid_at,o.created_at)<=%s AND NOT EXISTS (SELECT 1 FROM shopify_orders newer WHERE COALESCE(NULLIF(newer.shopify_customer_id,''),newer.customer_id)=c.customer_id AND upper(newer.financial_status) IN ('PAID','PARTIALLY_REFUNDED') AND newer.cancelled_at IS NULL AND newer.created_at>o.created_at)"
        args=(now()-timedelta(days=row['config']['draft'].get('inactive_days',90)),)
    if kind=='fulfilled':sql+=" AND upper(o.fulfillment_status)='FULFILLED'"
    sort='f.fulfilled_at,p.paid_at,o.created_at' if kind=='fulfilled' else 'p.paid_at,o.created_at'
    sql+=" ORDER BY COALESCE("+sort+") DESC,o.shopify_order_id DESC LIMIT 50"
    return store.q(sql,args)


def verify(store,shop,row,candidate):
    from crm_lifecycle_runtime import verified_plan
    from crm_lifecycle_policy import latest_paid
    from crm_automation_definition import qualifies
    from crm_automation_rule_facts import order_facts
    customer=shop.customer(candidate['customer_id'],fresh=True)
    if not customer or customer.get('id')!=candidate['customer_id']:raise ValueError('Preview customer verification failed.')
    if not eligibility(customer,store.suppressed(customer['id'],recipient_hash(customer.get('email'))))[0]:raise ValueError('Preview customer is no longer eligible.')
    kind=row['config']['draft']['trigger']
    policy=deepcopy(row);policy['trigger_type']=kind
    # The existing Post Purchase policy supplies paid/latest-order verification;
    # fulfilled additionally requires fresh confirmed fulfillment facts.
    if kind=='fulfilled':
        policy['trigger_type']='post_purchase';policy['config']['draft']['trigger']='post_purchase'
    # Candidate selection evaluates entry eligibility, not stage delivery timing.
    # Native scratch emails have no lifecycle anchor; never mutate those drafts.
    policy['config']['draft']['emails']=[]
    engine=SimpleNamespace(store=store,shop=shop,clock=now)
    plan=verified_plan(engine,policy,customer)
    if not plan['eligible']:raise ValueError('No eligible example: '+plan['reason'])
    order=next((o for o in plan['orders'] if o['id']==candidate['key']),{}) if kind=='fulfilled' else latest_paid(plan['orders']) or {}
    if kind=='post_purchase' and order.get('id')!=candidate['key']:raise ValueError('Preview order was superseded.')
    if kind=='fulfilled' and not order.get('fulfilled_at'):raise ValueError('Preview order is not fulfilled.')
    facts=order_facts(shop,order,row['config']['draft']['rules']) if kind in ('post_purchase','fulfilled') else {}
    if not qualifies(row['config']['draft'],customer,facts):raise ValueError('Preview customer does not match flow rules.')
    return dict(key=candidate['key'],label=' '.join(filter(None,[customer.get('firstName'),customer.get('lastName')])) or candidate.get('name') or 'Eligible customer',
                _customer=customer,_order=order,_lifecycle_orders=plan['orders'])


def context(state,store,*,refresh=False):
    row=flow_row(store);flow=row['config']['draft'];shop=store.preview_shop
    scope=digest([str(row['id']),flow['trigger'],flow.get('rules'),flow.get('inactive_days'),getattr(shop,'namespace','configured')])
    pin=state.get('_automation_flow_pin')
    if refresh or not pin or pin['scope']!=scope:
        pin=dict(scope=scope,options=[],selected=None,error='');state['_automation_flow_pin']=pin
        from crm_campaign_home_cache import POOL,CAPACITY
        if CAPACITY.acquire(blocking=False):
            def load():
                try:return examples(store,shop,row)
                finally:CAPACITY.release()
            pin['future']=POOL.submit(load)
        else:pin['error']='Customer examples are busy. Refresh to retry.'
    future=pin.get('future')
    if future and future.done():
        pin.update(future.result());pin.pop('future',None)
    return pin


def examples(store,shop,row):
    result=dict(options=[],selected=None,error='')
    try:
        scopes=set(store.state('shopify_automation_capabilities').get('scopes',[]))
        if not {'read_customers','read_orders','read_all_orders'}.issubset(scopes):
            raise ValueError('Customer examples require verified read_customers, read_orders and read_all_orders access.')
        from crm_collector_transport import bounded
        shop=bounded(shop,seconds=12)
        started=time.monotonic()
        rows=candidates(store,row)
        seen=set()
        for candidate in rows:
            if time.monotonic()-started>10:
                if result['selected'] is None:result['error']='Customer verification timed out. Refresh to retry.'
                break
            if candidate['customer_id'] in seen:continue
            # First candidate per customer is the latest relevant event.
            seen.add(candidate['customer_id'])
            try:data=verify(store,shop,row,candidate)
            except ValueError:continue
            result['options'].append(candidate)
            if result['selected'] is None:result['selected']=data
            if len(result['options'])>=8:break
    except ValueError as exc:result['error']=str(exc)
    except Exception:result['error']='Customer examples could not be verified. Refresh to retry.'
    return result


def selected(state,store,*,fresh=False):
    pin=context(state,store)
    data=pin['selected']
    if not data:raise NoPreviewCustomer('Loading eligible example customers…' if pin.get('future') else pin['error'] or 'No eligible customer found in the latest 50 records. Refresh after customer/order data is synced.')
    if fresh:
        candidate=next(c for c in pin['options'] if c['key']==data['key'])
        data=verify(store,store.preview_shop,flow_row(store),candidate)
        if digest(data)!=digest(pin['selected']):raise ValueError('Example customer/order changed. Refresh the preview before sending a test.')
    return data


def hydrate(state,store,doc,*,fresh=False):
    from crm_collector_resolver import resolve
    from crm_collector_images import render,configurations,marker
    from crm_personalisation import resolve as values,render as personalise,present,TOKEN
    from crm_lifecycle_products import selected as recommendations,recommend,hydrate as hydrate_products
    from crm_recovery_discount import substitute
    data=selected(state,store,fresh=fresh);row=flow_row(store);kind=row['config']['draft']['trigger']
    token=digest([doc,data]);cache=state.setdefault('_automation_flow_hydrations',{})
    if not fresh and token in cache:
        store.preview_warning=cache[token][1]
        configs=configurations(doc)
        if configs:
            facts=state.get('_automation_flow_facts',{}).get(digest([configs,data]))
            if facts:state['_automation_selected_artwork']=facts['blocks']
        return deepcopy(cache[token][0]),data['label']
    store.preview_warning=''
    result=substitute(doc,preview=not fresh)
    if configurations(result):
        fact_key=digest([configurations(result),data])
        fact_cache=state.setdefault('_automation_flow_facts',{})
        facts=None if fresh else fact_cache.get(fact_key)
        if facts is None:
            facts=resolve(store.preview_shop,store,result,data,data['_customer']['id'],now())
            previous=fact_cache.get(fact_key)
            if fresh and previous is not None and digest(previous)!=digest(facts):
                raise ValueError('Artwork availability changed. Refresh the preview before sending a test.')
            fact_cache[fact_key]=facts
            while len(fact_cache)>16:fact_cache.pop(next(iter(fact_cache)))
        state['_automation_selected_artwork']=facts['blocks']
        if any(c['source'] not in ('No Image','Static Selected Image') and not facts['blocks'].get(marker(c)) for c in configurations(result)):
            store.preview_warning='Some product galleries have no verified available artwork for this customer.'
        result=render(result,facts['blocks'])
    if recommendations(result):
        products=recommend(store,store.preview_shop,result,data['_lifecycle_orders'],now())
        result=hydrate_products(result,products)
    if present(result):
        wanted=set(TOKEN.findall(result['content']['subject'])+TOKEN.findall(result['content']['preheader']))
        result=personalise(result,values(data['_order'],data['_customer'],trigger=kind,wanted=wanted),trigger=kind)
    # Optional checkout-style product/lifestyle elements also use the order.
    from crm_checkout_preview import needs_checkout,document
    if needs_checkout(result):result=document(result,checkout_data(data),shop=store.preview_shop)[0]
    cache[token]=(deepcopy(result),store.preview_warning)
    while len(cache)>8:cache.pop(next(iter(cache)))
    return result,data['label']


def checkout_data(data):
    """Adapter for the existing inline editor's product/lifestyle elements."""
    items=[]
    for line in (data['_order'].get('lineItems') or {}).get('nodes',[]):
        variant=line.get('variant') or {};product=line.get('product') or {}
        items.append(dict(title=line.get('title',''),product_id=product.get('id',''),quantity=line.get('quantity',1),
                          image=(variant.get('image') or {}).get('url',''),variant=line.get('variantTitle',''),url='',currency='',amount=None,edition=None))
    return dict(items=items,label=data['label'],recovery_url='',preview_only=False)


def control(state,store,key):
    import streamlit as st
    pin=context(state,store)
    with st.container(horizontal=True,vertical_alignment='center'):
        options=pin['options'];ids=[c['key'] for c in options];current=(pin['selected'] or {}).get('key')
        labels={c['key']:(c.get('name') or c.get('email') or 'Customer')+' · '+c['key'].rsplit('/',1)[-1] for c in options}
        choice=st.selectbox('Example customer',ids,index=ids.index(current) if current in ids else None,format_func=lambda i:labels[i],key=key+'flow_example',placeholder='No eligible example selected',disabled=not ids)
        if st.button('',icon=':material/refresh:',help='Refresh example customers',key=key+'flow_example_refresh'):
            context(state,store,refresh=True);state.pop(key+'flow_example',None);st.rerun(scope='app')
    if choice and choice!=current:
        try:
            pin['selected']=verify(store,store.preview_shop,flow_row(store),next(c for c in options if c['key']==choice))
            pin['error']='';st.rerun(scope='app')
        except ValueError as exc:
            pin['selected']=None;pin['error']=str(exc)
    if pin['error']:st.caption(pin['error'])
