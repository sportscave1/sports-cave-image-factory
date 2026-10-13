"""Session-pinned real lifecycle examples. Read-only; no enrollment or delivery."""
from copy import deepcopy
from types import SimpleNamespace
from crm_logic import now,eligibility,recipient_hash
from crm_automation_preview_cache import digest
import time
from queue import Queue,Empty
from datetime import timedelta

TTL=300
MAX_PINS=8


def preview_key(data):
    """Verified snapshots get one fingerprint, not repeated full-history JSON."""
    return data.get('_preview_token') or data


def fingerprint(data):
    data['_preview_token']=digest({k:v for k,v in data.items() if k!='_preview_token'})
    return data


def document_key(doc,data):
    return digest([doc,data['key'],data['_customer']['id']])


class PreviewReads:
    """Request-local SELECT memoisation; never used by send verification."""
    def __init__(self,store):self.store=store;self.cache={}
    def __getattr__(self,name):return getattr(self.store,name)
    def _read(self,name,*args,**kwargs):
        key=digest([name,args,kwargs])
        if key not in self.cache:self.cache[key]=getattr(self.store,name)(*args,**kwargs)
        return deepcopy(self.cache[key])
    def state(self,*a,**k):return self._read('state',*a,**k)
    def q(self,*a,**k):return self._read('q',*a,**k)
    def suppressed(self,*a,**k):return self._read('suppressed',*a,**k)


class PreviewShop:
    """One session/customer revision's visual reads, never used for sending."""
    def __init__(self,shop):
        from threading import RLock
        self.shop=shop;self.cache={};self.lock=RLock();self.failures=0
    def __getattr__(self,name):return getattr(self.shop,name)
    def _read(self,name,*a,**k):
        key=digest([name,a,k])
        with self.lock:
            if key not in self.cache:
                from crm_collector_transport import bounded
                try:self.cache[key]=getattr(bounded(self.shop),name)(*a,**k)
                except Exception:self.failures+=1;raise
                while len(self.cache)>64:self.cache.pop(next(iter(self.cache)))
            return deepcopy(self.cache[key])
    def query(self,*a,**k):return self._read('query',*a,**k)
    def products(self,*a,**k):return self._read('products',*a,**k)
    def line_page(self,*a,**k):return self._read('line_page',*a,**k)
    def campaign_images(self,*a,**k):return self._read('campaign_images',*a,**k)


class NoPreviewCustomer(ValueError):
    pass


def flow_row(store):
    row=getattr(store,'preview_row',None) or store.flow(store.draft_identity)
    return {**row,'config':{**row['config'],'draft':getattr(store,'preview_flow',None) or row['config']['draft']}}


def candidates(store,row):
    kind=row['config']['draft']['trigger']
    if kind=='welcome':
        return store.q("""SELECT c.customer_id AS key,c.customer_id,c.name,c.email,c.profile,c.verified_at,c.subscribed_at
          FROM crm_lifecycle_customers c WHERE c.consent='SUBSCRIBED' AND c.subscribed_at IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM crm_suppressions s WHERE s.shopify_customer_id=c.customer_id OR s.recipient_hash=c.recipient_hash)
          AND c.customer_id NOT IN (SELECT COALESCE(NULLIF(o.shopify_customer_id,''),o.customer_id)
            FROM shopify_orders o WHERE upper(o.financial_status) IN ('PAID','PARTIALLY_REFUNDED') AND o.cancelled_at IS NULL
            AND COALESCE(NULLIF(o.shopify_customer_id,''),o.customer_id) IS NOT NULL)
          ORDER BY c.subscribed_at DESC,c.customer_id LIMIT 50""")
    # Existing consent/order ledgers only supply candidates. Fresh Shopify facts
    # below remain authority, including consent, suppressions and inactivity.
    sql="""WITH order_events AS (SELECT object_id,
        min(occurred_at) FILTER (WHERE topic='orders/paid') AS paid_at,
        max(occurred_at) FILTER (WHERE topic='orders/fulfilled') AS fulfilled_at
        FROM crm_webhook_events WHERE provider='shopify' AND topic IN ('orders/paid','orders/fulfilled') GROUP BY object_id)
      SELECT o.shopify_order_id AS key,c.customer_id,c.name,c.email,c.profile,c.verified_at,c.subscribed_at,
      to_jsonb(o) AS order_record,p.paid_at,p.fulfilled_at
      FROM shopify_orders o JOIN crm_lifecycle_customers c
      ON COALESCE(NULLIF(o.shopify_customer_id,''),o.customer_id)=c.customer_id
      LEFT JOIN order_events p ON p.object_id=o.shopify_order_id
      WHERE c.consent='SUBSCRIBED' AND upper(o.financial_status)='PAID' AND o.cancelled_at IS NULL
      AND NOT EXISTS (SELECT 1 FROM crm_suppressions s WHERE s.shopify_customer_id=c.customer_id OR s.recipient_hash=c.recipient_hash)
      """
    args=()
    if kind=='win_back':
        from datetime import timedelta
        sql+=" AND COALESCE(p.paid_at,o.created_at)<=%s AND NOT EXISTS (SELECT 1 FROM shopify_orders newer WHERE COALESCE(NULLIF(newer.shopify_customer_id,''),newer.customer_id)=c.customer_id AND upper(newer.financial_status) IN ('PAID','PARTIALLY_REFUNDED') AND newer.cancelled_at IS NULL AND newer.created_at>o.created_at)"
        args=(now()-timedelta(days=row['config']['draft'].get('inactive_days',180)),)
    if kind=='fulfilled':sql+=" AND upper(o.fulfillment_status)='FULFILLED'"
    sort='p.fulfilled_at,p.paid_at,o.created_at' if kind=='fulfilled' else 'p.paid_at,o.created_at'
    sql+=" ORDER BY COALESCE("+sort+") DESC,o.shopify_order_id DESC LIMIT 50"
    return store.q(sql,args)


def cached_candidate(row,candidate):
    """Previously verified local facts are display-only, never send authority."""
    from crm_logic import date
    from crm_lifecycle_policy import order_from_ledger,qualifying
    profile=candidate.get('profile') or {}
    if not candidate.get('verified_at') or profile.get('id')!=candidate['customer_id'] or not eligibility(profile,False)[0]:return None
    kind=row['config']['draft']['trigger'];orders=[];order={}
    record=candidate.get('order_record')
    if kind!='welcome':
        if not record:return None
        events=[{'topic':'orders/paid','occurred_at':candidate['paid_at']}] if candidate.get('paid_at') else []
        if candidate.get('fulfilled_at'):events.append({'topic':'orders/fulfilled','occurred_at':candidate['fulfilled_at']})
        order=order_from_ledger(record,events)
        if not qualifying(order) or not order.get('paid_at'):return None
        raw=record.get('raw_json') or record.get('raw') or {}
        # A contradictory raw event is not a verified customer/order snapshot.
        if raw.get('id') and raw['id']!=candidate['key']:return None
        if (raw.get('customer') or {}).get('id') not in (None,profile['id']):return None
        lines=raw.get('lineItems')
        if not isinstance(lines,dict):return None  # Never invent missing line facts.
        order.update(customer={'id':profile['id']},lineItems=deepcopy(lines),totalPriceSet=raw.get('totalPriceSet'))
        orders=[order]
        if kind=='fulfilled' and not order.get('fulfilled_at'):return None
        if kind=='win_back' and date(order['paid_at'])>now()-timedelta(days=row['config']['draft'].get('inactive_days',180)):return None
    from crm_automation_definition import qualifies
    from crm_automation_rule_facts import order_facts
    # Rules requiring paginated data wait for fresh verification instead.
    if (order.get('lineItems') or {}).get('pageInfo',{}).get('hasNextPage'):return None
    facts=order_facts(None,order,row['config']['draft']['rules']) if kind in ('post_purchase','fulfilled') else {}
    if not qualifies(row['config']['draft'],profile,facts):return None
    return dict(key=candidate['key'],label=' '.join(filter(None,[profile.get('firstName'),profile.get('lastName')])) or candidate.get('name') or 'Eligible customer',
                _customer=profile,_order=order,_lifecycle_orders=orders,_cached=True)


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
    policy['config'].pop('published_flow',None)  # Editor previews follow draft rules.
    if kind=='win_back':policy['config']['draft'].setdefault('inactive_days',180)
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
    pins=state.setdefault('_automation_flow_pins',{})
    pin=state.get('_automation_flow_pin')
    if not pin or pin['scope']!=scope:
        pin=pins.get(scope) or dict(scope=scope,options=[],selected=None,error='',loaded_at=0,verified={},renders={})
        pins[scope]=pin;state['_automation_flow_pin']=pin
        if len(pins)>MAX_PINS:
            victim=next((s for s,p in pins.items() if s!=scope and not p.get('future')),None)
            if victim:pins.pop(victim)
    events=pin.get('events')
    if events:
        while True:
            try:seed=events.get_nowait()
            except Empty:break
            if not pin.get('target'):
                pin['options']=seed['options']
                if not pin.get('selected') and seed.get('selected'):pin['selected']=fingerprint(seed['selected'])
    future=pin.get('future')
    if future and future.done():
        try:result=future.result()
        except Exception:result=dict(error='Customer verification unavailable. Open Diagnostics for details.',selected=None,options=pin['options'])
        chosen=result.get('selected')
        if chosen:
            chosen['_preview_revision']=pin.get('revision',0)
            fingerprint(chosen)
            completed=result.get('_completed_at',time.monotonic())
            pin.update(selected=chosen,error='',loaded_at=completed)
            pin['verified'][chosen['key']]=(completed,chosen)
        else:
            # Retain a valid preview on an optional refresh failure. Keep genuine
            # errors available in the compact diagnostics popover.
            pin['error']=result.get('error','')
            if not pin.get('selected'):pin['error']=pin['error'] or 'No eligible example customer found.'
            pin['loaded_at']=time.monotonic()  # No automatic failure/retry loop.
        if result.get('options'):pin['options']=result['options']
        pin.pop('future',None);pin.pop('target',None)
    if not pin.get('future') and (refresh or not pin['loaded_at'] or time.monotonic()-pin['loaded_at']>=TTL):
        pin['revision']=pin.get('revision',0)+1
        pin.pop('render_error',None)
        preferred=(pin.get('selected') or {}).get('key')
        _start(pin,lambda notify:examples(store,shop,deepcopy(row),on_seed=notify,selected_key=preferred))
        if pin.get('future') and pin['future'].done():return context(state,store)
    return pin


def _start(pin,load):
    from crm_campaign_home_cache import POOL,CAPACITY
    if pin.get('future'):return
    if not CAPACITY.acquire(blocking=False):
        pin.update(error='Customer examples are busy. Retry refresh.',loaded_at=time.monotonic());return
    events=Queue();pin['events']=events;pin['error']='';pin['paint_until']=time.monotonic()+.5
    def work():
        try:
            result=load(events.put);result['_completed_at']=time.monotonic();return result
        finally:CAPACITY.release()
    try:pin['future']=POOL.submit(work)
    except RuntimeError:
        CAPACITY.release();pin.update(error='Customer verification is temporarily unavailable.',loaded_at=time.monotonic())


def choose(state,store,identity):
    pin=context(state,store)
    if pin.get('future'):return  # Never replace an in-flight selection job.
    candidate=next((c for c in pin['options'] if c['key']==identity),None)
    if candidate is None:raise ValueError('Example customer changed. Refresh the list.')
    verified=pin.setdefault('verified',{}).get(identity)
    if verified and time.monotonic()-verified[0]<TTL:
        pin.update(selected=deepcopy(verified[1]),error='');return
    seed=cached_candidate(flow_row(store),candidate)
    # A different recipient cannot inherit the previous recipient's visual.
    pin['selected']=fingerprint(seed) if seed else None
    pin['target']=identity
    def load(notify):
        try:data=verify(PreviewReads(store),store.preview_shop,flow_row(store),candidate)
        except ValueError as exc:return dict(selected=None,error=str(exc))
        return dict(selected=data,error='')
    _start(pin,load)


def examples(store,shop,row,*,on_seed=None,selected_key=None):
    result=dict(options=[],selected=None,error='')
    try:
        store=PreviewReads(store)
        rows=candidates(store,row)
        result['options']=rows
        if selected_key:
            rows=[c for c in rows if c['key']==selected_key]
            if not rows:raise ValueError('Selected example is no longer eligible. Choose another customer.')
        if on_seed and rows:
            seed=cached_candidate(row,rows[0])
            if seed:on_seed(dict(options=rows,selected=seed))
        scopes=set(store.state('shopify_automation_capabilities').get('scopes',[]))
        if not {'read_customers','read_orders','read_all_orders'}.issubset(scopes):
            raise ValueError('Customer examples require verified read_customers, read_orders and read_all_orders access.')
        from crm_collector_transport import bounded
        shop=bounded(shop,seconds=12)
        started=time.monotonic()
        seen=set()
        for candidate in rows:
            if time.monotonic()-started>10:
                if result['selected'] is None:result['error']='Customer verification timed out. Refresh to retry.'
                break
            if candidate['customer_id'] in seen:continue
            # First candidate per customer is the latest relevant event.
            seen.add(candidate['customer_id'])
            try:data=verify(store,shop,row,candidate)
            except ValueError as exc:
                result['error']=str(exc);continue
            result.update(selected=data,error='')
            break  # Verify the chosen example, not an entire dropdown eagerly.
    except ValueError as exc:result['error']=str(exc)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning('automation_preview_verification_failed class=%s',type(exc).__name__)
        result['error']='Customer verification failed ('+type(exc).__name__+'). Check Shopify access and connectivity; the cached preview is retained.'
    return result


def selected(state,store,*,fresh=False):
    pin=context(state,store)
    data=pin['selected']
    if not data:raise NoPreviewCustomer('Loading eligible example customers…' if pin.get('future') else pin['error'] or 'No eligible customer found in the latest 50 records. Refresh after customer/order data is synced.')
    if fresh:
        candidate=next(c for c in pin['options'] if c['key']==data['key'])
        data=verify(store,store.preview_shop,flow_row(store),candidate)
        display={k:v for k,v in pin['selected'].items() if k not in ('_cached','_preview_revision','_preview_token')}
        if digest(data)!=digest(display):raise ValueError('Example customer/order changed. Refresh the preview before sending a test.')
        data['_preview_revision']=pin['selected'].get('_preview_revision',0)
        if pin['selected'].get('_preview_token'):data['_preview_token']=pin['selected']['_preview_token']
    return data


def artwork_key(doc,data):
    from crm_collector_images import configurations
    return digest([configurations(doc),preview_key(data)])


def pending(state):
    pin=state.get('_automation_flow_pin') or {}
    return bool(pin.get('future') or any(not f.done() for f in pin.get('renders',{}).values()))


def hydrate(state,store,doc,*,fresh=False):
    """Visual network work runs off-thread. Send tests always reverify directly."""
    if fresh:return _hydrate(state,store,doc,fresh=True)
    data=selected(state,store);pin=context(state,store)
    token=digest([doc,preview_key(data)]);cache=state.setdefault('_automation_flow_hydrations',{})
    jobs=pin.setdefault('renders',{})
    for identity,future in list(jobs.items()):
        if not future.done():continue
        jobs.pop(identity)
        owner=pin.setdefault('render_customers',{}).pop(identity,None)
        pin.setdefault('render_dependencies',{}).pop(identity,None)
        current=pin.get('selected') or {}
        relevant=owner is None or owner==((current.get('_customer') or {}).get('id'),current.get('key'))
        try:result,local,completed_document_key=future.result()
        except Exception as exc:
            if relevant:pin['render_error']=(identity,str(exc) if isinstance(exc,ValueError) else 'Artwork verification unavailable. Retry refresh.')
            continue
        for name in ('_automation_flow_facts','_automation_flow_values','_automation_flow_recommendations'):
            state.setdefault(name,{}).update(local.get(name,{}))
            while len(state[name])>64:state[name].pop(next(iter(state[name])))
        state.setdefault('_automation_flow_hydrations',{}).update(local.get('_automation_flow_hydrations',{}))
        if relevant:
            pin['render_revision']=pin.get('render_revision',0)+1
        previous=pin.setdefault('last_documents',{});previous[completed_document_key]=result[0]
        facts=local.get('_automation_selected_artwork')
        if facts:
            pin.setdefault('last_artwork',{})[completed_document_key]=deepcopy(facts)
            while len(pin['last_artwork'])>8:pin['last_artwork'].pop(next(iter(pin['last_artwork'])))
        while len(previous)>8:previous.pop(next(iter(previous)))
        if pin.get('render_error',(None,))[0]==identity:pin.pop('render_error',None)
    if token in cache:return _hydrate(state,store,doc,data=data)
    from crm_collector_images import configurations
    from crm_personalisation import TOKEN
    from crm_lifecycle_products import selected as recommendations
    from crm_checkout_preview import needs_checkout
    configs=configurations(doc);wanted=set(TOKEN.findall(doc['content']['subject'])+TOKEN.findall(doc['content']['preheader']))
    rec=recommendations(doc)
    rec_ready=not rec or digest([rec.get('products'),doc['market'],preview_key(data)]) in state.get('_automation_flow_recommendations',{})
    ready=(not configs or artwork_key(doc,data) in state.get('_automation_flow_facts',{})) and rec_ready and not needs_checkout(doc)
    ready=ready and (not wanted-{'first_name'} or digest([sorted(wanted),preview_key(data)]) in state.get('_automation_flow_values',{}))
    if ready:return _hydrate(state,store,doc,data=data)
    failed=pin.get('render_error')
    if failed and failed[0]==token:
        previous=pin.get('last_documents',{}).get(document_key(doc,data))
        if previous:
            store.preview_warning=failed[1]
            return deepcopy(previous),data['label']
        raise NoPreviewCustomer(failed[1])
    if token not in jobs:
        dependency=digest([configs,sorted(wanted),rec and [rec.get('products'),doc['market']],needs_checkout(doc),preview_key(data)])
        # Text edits during an image request wait for the same facts rather than
        # launching another identical Shopify lookup for a different document.
        if any(d==dependency for k,d in pin.setdefault('render_dependencies',{}).items() if k in jobs):
            previous=pin.get('last_documents',{}).get(document_key(doc,data))
            if previous:return deepcopy(previous),data['label']
            raise NoPreviewCustomer('Loading customer artwork…')
        from crm_campaign_home_cache import POOL,CAPACITY
        if not CAPACITY.acquire(blocking=False):raise NoPreviewCustomer('Artwork preview is busy. Retry refresh.')
        local={name:deepcopy(state.get(name,{})) for name in ('_automation_flow_facts','_automation_flow_values','_automation_flow_recommendations')}
        reads=state.setdefault('_automation_flow_visual_reads',{})
        read_key=digest(preview_key(data))
        if read_key not in reads:
            reads[read_key]=PreviewShop(store.preview_shop)
            while len(reads)>MAX_PINS:reads.pop(next(iter(reads)))
        local['_automation_flow_visual_shop']=reads[read_key]
        snapshot=deepcopy(doc);data=deepcopy(data)
        scoped=PreviewReads(store);scoped.preview_row=deepcopy(flow_row(store));scoped.preview_flow=scoped.preview_row['config']['draft']
        snapshot_key=document_key(doc,data)
        def load():
            try:return _hydrate(local,scoped,snapshot,data=data),local,snapshot_key
            finally:CAPACITY.release()
        try:
            jobs[token]=POOL.submit(load)
            pin['render_dependencies'][token]=dependency
            pin.setdefault('render_customers',{})[token]=(data['_customer']['id'],data['key'])
        except RuntimeError:CAPACITY.release();raise NoPreviewCustomer('Artwork preview is temporarily unavailable.')
        pin['paint_until']=time.monotonic()+.5
    if jobs[token].done():return hydrate(state,store,doc)
    # Reuse only the same customer's prior verified visual during refresh.
    previous=pin.get('last_documents',{}).get(document_key(doc,data))
    if previous:return deepcopy(previous),data['label']
    raise NoPreviewCustomer('Loading customer artwork…')


def _hydrate(state,store,doc,*,fresh=False,data=None):
    from crm_collector_resolver import resolve
    from crm_collector_images import render,configurations,marker
    from crm_personalisation import resolve as values,render as personalise,present,TOKEN
    from crm_lifecycle_products import selected as recommendations,recommend,hydrate as hydrate_products
    from crm_recovery_discount import substitute
    data=selected(state,store,fresh=fresh) if data is None else data
    row=flow_row(store);kind=row['config']['draft']['trigger']
    token=digest([doc,preview_key(data)]);cache=state.setdefault('_automation_flow_hydrations',{})
    if not fresh and token in cache:
        store.preview_warning=cache[token][1]
        configs=configurations(doc)
        if configs:
            facts=state.get('_automation_flow_facts',{}).get(digest([configs,preview_key(data)]))
            if facts:state['_automation_selected_artwork']=facts['blocks']
        return deepcopy(cache[token][0]),data['label']
    store.preview_warning=''
    result=substitute(doc,preview=not fresh)
    if configurations(result):
        fact_key=digest([configurations(result),preview_key(data)])
        fact_cache=state.setdefault('_automation_flow_facts',{})
        if fresh and (state.get('_automation_flow_pin') or {}).get('render_error') and fact_key not in fact_cache and any(c['source'] not in ('No Image','Static Selected Image') for c in configurations(result)):
            raise ValueError('Artwork preview is stale after a verification failure. Refresh the preview before sending a test.')
        facts=None if fresh else fact_cache.get(fact_key)
        if facts is None:
            if data.get('_cached'):
                configs=configurations(result)
                if any(c['source'] not in ('Products Purchased','Actual Purchased Product','No Image','Static Selected Image') for c in configs):raise NoPreviewCustomer('Verifying collection artwork…')
                from crm_collector_images import purchased
                ids=list(dict.fromkeys((line.get('product') or {}).get('id') for line in data['_order']['lineItems']['nodes']))
                rows=store.q('SELECT shopify_product_id,online_store_url,image_url FROM shopify_products WHERE shopify_product_id=ANY(%s)',([i for i in ids if i],))
                products=[dict(id=r['shopify_product_id'],onlineStoreUrl=r.get('online_store_url'),featuredImage={'url':r.get('image_url')}) for r in rows]
                owned=purchased(data['_order'],data['_customer']['id'],products)
                facts={'recipient':data['_customer']['id'],'blocks':{marker(c):owned[:c['count']] for c in configs if c['source'] in ('Products Purchased','Actual Purchased Product')}}
            else:
                shop=store.preview_shop if fresh else state.get('_automation_flow_visual_shop',store.preview_shop)
                before=shop.failures if isinstance(shop,PreviewShop) else None
                facts=resolve(shop,store,result,data,data['_customer']['id'],now())
                if before is not None and shop.failures>before:raise NoPreviewCustomer('Artwork verification unavailable. Last valid preview retained; refresh to retry.')
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
        if data.get('_cached'):raise NoPreviewCustomer('Verifying recommendation artwork…')
        section=recommendations(result);rec_key=digest([section.get('products'),result['market'],preview_key(data)])
        rec_cache=state.setdefault('_automation_flow_recommendations',{})
        if fresh and (state.get('_automation_flow_pin') or {}).get('render_error') and rec_key not in rec_cache:
            raise ValueError('Recommendation preview is stale after a verification failure. Refresh before sending a test.')
        products=None if fresh else rec_cache.get(rec_key)
        if products is None:
            products=recommend(store,store.preview_shop if fresh else state.get('_automation_flow_visual_shop',store.preview_shop),result,data['_lifecycle_orders'],now());rec_cache[rec_key]=products
        result=hydrate_products(result,products)
    if present(result):
        wanted=set(TOKEN.findall(result['content']['subject'])+TOKEN.findall(result['content']['preheader']))
        values_key=digest([sorted(wanted),preview_key(data)]);values_cache=state.setdefault('_automation_flow_values',{})
        personal=None if fresh else values_cache.get(values_key)
        if personal is None:
            personal=values(data['_order'],data['_customer'],trigger=kind,wanted=wanted);values_cache[values_key]=personal
        result=personalise(result,personal,trigger=kind)
    # Optional checkout-style product/lifestyle elements also use the order.
    from crm_checkout_preview import needs_checkout,document
    if needs_checkout(result):result=document(result,checkout_data(data),shop=store.preview_shop if fresh else state.get('_automation_flow_visual_shop',store.preview_shop))[0]
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
    options=pin['options'];ids=[c['key'] for c in options]
    current=pin.get('target') or (pin['selected'] or {}).get('key')
    field=key+'flow_example'
    state[field]=current if current in ids else None
    labels={c['key']:(c.get('name') or c.get('email') or 'Customer')+' · '+c['key'].rsplit('/',1)[-1] for c in options}
    def changed():
        if state.get(field):choose(state,store,state[field])
    st.selectbox('Example customer',ids,format_func=lambda i:labels[i],key=field,placeholder='No eligible example selected',disabled=not ids or bool(pin.get('future')),label_visibility='collapsed',on_change=changed)
