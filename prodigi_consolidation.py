"""Audited copy -> full QA -> cancel for separately purchased numbered units.

Original Shopify orders/allocations are never cancelled or reassigned. Only
unpaid supplier duplicates may be cancelled after the destination passes QA.
The retained order and global edit-window settings are never changed. The owner
explicitly authorised an indefinite hold on an already-submitted duplicate only
on 2026-11-22; no duration is parsed and no source is ever resumed automatically.
"""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import hmac,json,re,secrets,threading
import prodigi_preparation as prep
import prodigi_browser as browser
from prodigi_client import ProdigiError
from companion_poll_transaction import connection

PREFIX='prodigi_merge:'
LOCK=19721133
POLICY='same-shopify-customer-complete-address-v1'
ACTIVE={'Holding duplicate','Adding','Preparing artwork','QA','Cancelling','Cancellation uncertain'}
_commit_gate=threading.Lock()


def identifier(value,kind):
    text=str(value or '').strip()
    match=re.fullmatch(r'(?:gid://shopify/'+kind+r'/)?([1-9][0-9]*)',text)
    if not match:raise ValueError('Independent Shopify '+kind+' identity is missing.')
    return match[1]


def norm(value):
    return ' '.join(str(value or '').split()).casefold()


def destination(recipient,company=''):
    address=(recipient or {}).get('address') or {}
    fields=[(recipient or {}).get('name'),address.get('line1'),address.get('line2'),
        address.get('townOrCity'),address.get('stateOrCounty'),address.get('postalOrZipCode'),address.get('countryCode'),company]
    if any(not norm(fields[i]) for i in (0,1,3,5,6)) or not re.fullmatch('[A-Za-z]{2}',str(fields[6] or '')):
        raise ValueError('A complete shipping recipient, address, postcode and country are required.')
    if norm(fields[6]) in ('au','us','ca') and not norm(fields[4]):raise ValueError('A complete state/province is required for this destination.')
    return tuple(norm(v) for v in fields)


def origin(value):return identifier(value['snapshot']['identity']['order_id'],'Order')


def stable(order):
    result=browser.business(order,'')
    for item in result['items']:
        for field in ('unitPrice','lineTotal'):item.pop(field,None)
        for asset in item.get('assets') or []:asset.pop('status',None)
    return result


def customer_identity(raw,order_id,customer_id=None):
    expected=identifier(order_id,'Order');source=raw if isinstance(raw,dict) else {}
    nested=source.get('raw_payload')
    if isinstance(nested,dict) and not (source.get('shipping_address') or source.get('shippingAddress')):
        if identifier(nested.get('id') or nested.get('admin_graphql_api_id'),'Order')!=expected:
            raise ValueError('Shopify customer data belongs to a different order.')
        source=nested
    for field in ('id','shopify_order_id','admin_graphql_api_id'):
        if source.get(field) and identifier(source[field],'Order')!=expected:raise ValueError('Shopify mirror order identity differs.')
    customer=source.get('customer') or {}
    candidates={identifier(v,'Customer') for v in (source.get('shopify_customer_id'),source.get('customer_id'),customer.get('id'),customer_id) if v}
    if len(candidates)!=1:raise ValueError('Independent Shopify Customer identity is missing or inconsistent.')
    recipient=prep.shopify_recipient(source,expected)
    address=source.get('shipping_address') or source.get('shippingAddress') or {}
    return next(iter(candidates)),destination(recipient,address.get('company'))


def identities(values):
    ids=sorted({origin(v) for v in values})
    gids=['gid://shopify/Order/'+i for i in ids]
    with connection(prep.connect) as c,c.cursor() as q:
        q.execute('SELECT shopify_order_id,legacy_resource_id,customer_id,shopify_customer_id,raw_json FROM shopify_orders WHERE shopify_order_id=ANY(%s) OR legacy_resource_id=ANY(%s)',(ids+gids,ids))
        rows=q.fetchall()
    result={}
    for row in rows:
        oid=identifier(row.get('legacy_resource_id') or row.get('shopify_order_id'),'Order')
        if oid in result:raise ValueError('Several independent Shopify mirrors match this order.')
        try:
            columns={identifier(v,'Customer') for v in (row.get('customer_id'),row.get('shopify_customer_id')) if v}
            if len(columns)>1:continue
            result[oid]=customer_identity(row['raw_json'],oid,next(iter(columns),None))
        except ValueError:continue # Guests/incomplete mirrors remain separate.
    return result


def unpaid(order,*,source=False):
    allowed={'draft','paused'}
    if order.get('status') not in allowed or order.get('charges') or order.get('shipments') or order.get('issues'):
        raise ValueError('Merging requires an unpaid draft or paused order with no production, shipment or supplier issue.')
    if source and 'cancel' not in order.get('allowedActions',[]):raise ValueError('The redundant supplier order cannot be cancelled.')
    for event in order.get('statusHistory') or []:
        if not isinstance(event,dict):raise ValueError('Supplier production history is unavailable.')
        states=[event.get(k) for k in ('status','toStatus','fromStatus','stage')]
        if any(s in ('in_production','partially_shipped','shipped','completed') for s in states):
            raise ValueError('A supplier order that entered production cannot be merged.')


def exact_units(values,order):
    ids=[str(i.get('id')) for i in order.get('items') or []]
    if not ids or len(set(ids))!=len(ids) or len(values)!=len(ids):raise ValueError('Every supplier item needs exactly one numbered OS allocation.')
    if {str(v['item_id']) for v in values}!=set(ids):raise ValueError('Supplier items and numbered allocations differ.')
    from prodigi_order_group import manifest
    return manifest(order)


def guard(sources,targets,source_order,target_order,identity_map,resolver):
    unpaid(source_order,source=True);unpaid(target_order)
    if str(source_order['id'])==str(target_order['id']):raise ValueError('These units already share one supplier order.')
    a=datetime.fromisoformat(source_order['createdAt'].replace('Z','+00:00'))
    b=datetime.fromisoformat(target_order['createdAt'].replace('Z','+00:00'))
    if a.tzinfo is None or b.tzinfo is None:raise ValueError('Supplier creation timestamps must identify their timezone.')
    if b>=a:raise ValueError('Only the oldest eligible pending supplier order can be the destination.')
    exact_units(sources,source_order);exact_units(targets,target_order)
    if len(sources)+len(targets)>100:raise ValueError('The combined order exceeds Prodigi’s item limit.')
    expected=identity_map[origin(sources[0])]
    if len({v['allocation_id'] for v in sources+targets})!=len(sources+targets):raise ValueError('A numbered allocation appears twice.')
    from prodigi_dashboard_qa import intent
    service=intent(sources[0]['snapshot'].get('shipping'))
    for value in sources+targets:
        fresh=resolver(value['allocation_id'])
        if not prep.same_source(value['snapshot'],fresh):raise ValueError('A numbered source changed before consolidation.')
        if identity_map[origin(value)]!=expected:raise ValueError('Customer or complete shipping address differs; keep the orders separate.')
        if intent(fresh.get('shipping'))!=service:raise ValueError('Standard and Express orders cannot be combined.')
        from prodigi_qa import address_matches
        supplier=source_order if value in sources else target_order
        if not address_matches(fresh.get('recipient'),supplier.get('recipient')):raise ValueError('The supplier delivery address differs from its original Shopify order.')
        if not value.get('browser',{}).get('verified') or not value.get('browser',{}).get('full_image_fit_verified'):
            raise ValueError('Every existing numbered artwork must be independently verified first.')
        if value.get('status') not in ('Ready for manual payment','Submitted'):raise ValueError('Wait for the existing items to finish QA before merging.')
        if value['status']=='Submitted' and not value.get('submission',{}).get('confirmed'):raise ValueError('The original submission is not confirmed.')
        view=deepcopy(supplier);view['status']='draft';view['allowedActions']=list(set(view.get('allowedActions',[]))|{'update'})
        item=prep.validate_order(view,fresh,value['order_id'],value['item_id'],binding=value.get('consolidation_binding'))
        if len(item.get('assets') or [])!=1 or prep.digest(item['assets'][0].get('url'))!=value.get('url_hash'):
            raise ValueError('An existing numbered artwork differs from its verified upload.')
    return expected


def bound_order(order,snapshot,binding,item_id):
    """Narrow validation view for an audited item copied into another root.

The immutable original snapshot remains independent. Only the supplier root and
new item reference are translated for the existing per-unit validation code.
"""
    if (binding.get('policy')!=POLICY or str(order.get('id'))!=str(binding.get('order_id')) or
        str(order.get('merchantReference'))!=str(binding.get('reference')) or
        str(item_id)!=str(binding.get('item_id')) or prep.digest(snapshot)!=binding.get('snapshot_hash')):
        raise ValueError('Consolidated supplier item binding changed.')
    unpaid(order)
    from prodigi_qa import address_matches
    if not address_matches(snapshot.get('recipient'),order.get('recipient')):raise ValueError('Consolidated delivery address changed.')
    result=deepcopy(order)
    item=next((i for i in result.get('items',[]) if str(i.get('id'))==str(item_id)),None)
    if item is None or item.get('merchantReference')!=binding.get('item_reference'):raise ValueError('Consolidated item reference changed.')
    result['status']='draft';result['allowedActions']=list(set(result.get('allowedActions',[]))|{'update'})
    result['merchantReference']=str(snapshot['identity']['order_id'])
    item['merchantReference']=str(snapshot['identity']['line_id'])
    return result


def read_job(q,key):
    q.execute('SELECT value FROM app_settings WHERE key=%s',(key,));row=q.fetchone()
    if not row:raise ValueError('Consolidation handoff unavailable.')
    return row['value']


def save_job(q,key,job):
    job['updated_at']=prep.now()
    q.execute('INSERT INTO app_settings(key,value,updated_at) VALUES(%s,%s::jsonb,now()) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=now()', (key,json.dumps(job)))


def supported():
    with connection(prep.connect) as c,c.cursor() as q:
        q.execute("SELECT value FROM app_settings WHERE key='orders_merge_capability' AND updated_at>now()-interval '15 minutes'")
        row=q.fetchone()
    from prodigi_submission import setting
    return bool(row and row['value'].get('policy')==POLICY and setting().get('enabled'))


def seen(q):
    save_job(q,'orders_merge_capability',{'policy':POLICY})


def record_capability():
    with connection(prep.connect) as c,c.cursor() as q:seen(q)


def units(q,ids):
    q.execute("SELECT value FROM app_settings WHERE key=ANY(%s)",([prep.PREFIX+str(i) for i in ids],))
    rows=[r['value'] for r in q.fetchall()]
    if {v['allocation_id'] for v in rows}!=set(ids):raise ValueError('A consolidation allocation is unavailable.')
    return sorted(rows,key=lambda v:ids.index(v['allocation_id']))


def admit_pending():
    """Run before the submission transaction locks any unit. No supplier writes."""
    if not supported():return
    with connection(prep.connect) as c,c.cursor() as q:
        q.execute('SELECT pg_try_advisory_xact_lock(%s) AS acquired',(LOCK,))
        if not q.fetchone()['acquired']:return False
        from prodigi_submission import LOCK as submission_lock
        q.execute('SELECT pg_try_advisory_xact_lock(%s) AS acquired',(submission_lock,))
        if not q.fetchone()['acquired']:return False
        q.execute("SELECT value FROM app_settings WHERE key LIKE 'prodigi_prepare:%%' AND value->>'status' IN ('Ready for manual payment','Submitted') AND NOT COALESCE((value->>'hidden')::boolean,false) AND NOT value ? 'merge_pending' ORDER BY updated_at DESC LIMIT 200")
        values=[]
        for row in q.fetchall():
            value=row['value']
            try:
                origin(value)
                if value.get('order_id') and value.get('item_id'):values.append(value)
            except (KeyError,ValueError,TypeError):continue
        if len({v['order_id'] for v in values})<2:return
        identity_map=identities(values);groups={}
        for v in values:groups.setdefault(v['order_id'],[]).append(v)
        provider=prep.Client();orders={}
        def get(oid):
            if oid not in orders:orders[oid]=provider.order(oid)
            return orders[oid]
        for sid,sources in list(groups.items())[:10]:
            identity=identity_map.get(origin(sources[0]))
            if not identity:continue
            candidates=[]
            for tid,targets in groups.items():
                if tid==sid or any(identity_map.get(origin(v))!=identity for v in targets):continue
                try:
                    guard(sources,targets,get(sid),get(tid),identity_map,prep.resolve)
                    candidates.append((datetime.fromisoformat(get(tid)['createdAt'].replace('Z','+00:00')).astimezone(timezone.utc),tid,targets))
                except ProdigiError:raise # retry after an outage; don't lose a matching merge opportunity
                except (ValueError,KeyError):continue
            if not candidates:continue
            _,tid,targets=min(candidates)
            q.execute('SELECT value FROM app_settings WHERE key=ANY(%s)',(['prodigi_merge_source:'+sid,'prodigi_merge_target:'+tid],))
            if any(r['value'].get('active') for r in q.fetchall()):continue
            ids=[v['allocation_id'] for v in sources+targets]
            q.execute('SELECT value FROM app_settings WHERE key=ANY(%s) FOR UPDATE NOWAIT',([prep.PREFIX+str(i) for i in ids],))
            latest={r['value']['allocation_id']:r['value'] for r in q.fetchall()}
            # A status reader or submitter may have acquired the units while the
            # independent supplier/customer checks ran. Never overwrite its lease.
            if any(i not in latest for i in ids):return False
            for previous in sources+targets:
                current=latest[previous['allocation_id']]
                lease=current.get('submission',{}).get('lease_until')
                if (current.get('merge_pending') or current.get('status') not in ('Ready for manual payment','Submitted') or
                    any(current.get(k)!=previous.get(k) for k in ('order_id','item_id','snapshot','url_hash')) or
                    (lease and datetime.fromisoformat(lease)>datetime.now(timezone.utc))):return False
            sources=[latest[v['allocation_id']] for v in sources];targets=[latest[v['allocation_id']] for v in targets]
            import uuid
            key=PREFIX+uuid.uuid4().hex
            source,target=get(sid),get(tid)
            job=dict(policy=POLICY,phase='Holding duplicate' if source['status']=='paused' else 'Adding',source_order_id=sid,target_order_id=tid,
                source_units=[v['allocation_id'] for v in sources],target_units=[v['allocation_id'] for v in targets],
                source_before=deepcopy(source),target_before=deepcopy(target),
                customer_hash=prep.digest(identity),copies=[],created_at=prep.now())
            save_job(q,key,job)
            for fence in ('prodigi_merge_source:'+sid,'prodigi_merge_target:'+tid):save_job(q,fence,dict(active=True,key=key))
            for value in sources+targets:
                value.update(merge_pending=key,status='Merge preparing',message='Combining matching customer orders to the same complete shipping address; originals are preserved until full QA passes.')
                prep.save(q,value)
            return key


def fresh(job,values,provider,resolver):
    """Every native write gets fresh unpaid, original identity and source checks."""
    source=provider.order(job['source_order_id']);target=provider.order(job['target_order_id'])
    unpaid(source,source=True);unpaid(target)
    if source['status']=='paused' and not job.get('hold',{}).get('confirmed') and job['phase']!='Holding duplicate':
        raise ValueError('The duplicate entered a countdown. It must be held indefinitely before any further copy operation.')
    if stable(source)!=stable(job['source_before']):raise ValueError('The source supplier order changed; do not cancel it.')
    identity_map=identities(values)
    for value in values:
        if prep.digest(resolver(value['allocation_id']))!=prep.digest(value['snapshot']):raise ValueError('A numbered original changed during consolidation.')
        if prep.digest(identity_map.get(origin(value)))!=job['customer_hash']:raise ValueError('The independently saved customer/address changed during consolidation.')
    from prodigi_qa import address_matches
    if any(not address_matches(v['snapshot']['recipient'],target.get('recipient')) for v in values):raise ValueError('Destination supplier shipping address changed.')
    if target.get('merchantReference')!=job['target_before'].get('merchantReference'):raise ValueError('Destination supplier reference changed.')
    return source,target


def binding(key,job,value,item):
    return dict(policy=POLICY,key=key,order_id=job['target_order_id'],reference=job['target_before']['merchantReference'],
        item_id=str(item['id']),item_reference=item.get('merchantReference'),snapshot_hash=prep.digest(value['snapshot']))


def hold_qa(value):
    if not value.get('merge_pending'):return False
    with connection(prep.connect) as c,c.cursor() as q:job=read_job(q,value['merge_pending'])
    return job['phase']!='QA'


def check_write(value,provider,resolver):
    if not value.get('merge_pending'):return
    if not supported():raise ValueError('Consolidation is paused or its paired worker is unavailable.')
    with connection(prep.connect) as c,c.cursor() as q:
        job=read_job(q,value['merge_pending']);values=units(q,job['source_units']+job['target_units'])
    if job['phase'] not in ('Adding','Preparing artwork','QA'):raise ValueError('Consolidation is not accepting a supplier write.')
    fresh(job,values,provider,resolver)


def claim():
    """One Add permit at a time; existing upload/QA workers handle the artwork."""
    with connection(prep.connect) as c,c.cursor() as q:
        q.execute('SELECT pg_try_advisory_xact_lock(%s) AS acquired',(LOCK,))
        if not q.fetchone()['acquired']:return None
        q.execute("SELECT key,value FROM app_settings WHERE key LIKE 'prodigi_merge:%%' AND value->>'phase' IN ('Holding duplicate','Adding','Preparing artwork','QA','Cancelling','Cancellation uncertain') ORDER BY updated_at LIMIT 1")
        row=q.fetchone()
        if not row:return None
        key,job=row['key'],row['value']
        values=units(q,job['source_units']+job['target_units'])
        try:
            if job['phase']=='Holding duplicate':
                if job.get('hold'):return None
                source,_=fresh(job,values,prep.Client(),prep.resolve)
                token=secrets.token_urlsafe(32)
                job['hold']=dict(token_hash=prep.digest(token),started=False,before=deepcopy(source),claimed_at=prep.now())
                save_job(q,key,job)
                return dict(kind='merge-hold',key='mergehold:'+key,token=token,environment='live',
                    order_id=job['source_order_id'],order_url='https://dashboard.prodigi.com/orders/'+job['source_order_id']+'/detail',
                    reference=str(source['merchantReference']),sha256=prep.digest(stable(source)))
            if job['phase'] in ('QA','Cancelling','Cancellation uncertain'):
                return None # commit() runs outside this claim transaction.
            if job.get('add'):
                # A lost Select acknowledgement is only reconciled, never clicked twice.
                if job['add'].get('started'):return reconcile_add(q,key,job,values,prep.Client())
                return None # The paired worker still owns its issued handoff.
            _,target=fresh(job,values,prep.Client(),prep.resolve)
            prepared={c['allocation_id'] for c in job['copies']}
            for copy in job['copies']:
                unit=next(v for v in values if v['allocation_id']==copy['allocation_id'])
                if not unit.get('browser',{}).get('verified') or not unit.get('browser',{}).get('full_image_fit_verified'):return None
            remaining=[v for v in values if v['allocation_id'] in job['source_units'] and v['allocation_id'] not in prepared]
            if not remaining:
                job['phase']='QA';save_job(q,key,job)
                for value in values:
                    if value.get('dashboard_qa'):value.setdefault('dashboard_qa_history',[]).append(value.pop('dashboard_qa'))
                    value.update(status='Awaiting dashboard QA',message='Checking every combined edition, variant, shipping quote and insert before cancelling the duplicate supplier order.')
                    prep.save(q,value)
                return None
            value=remaining[0];token=secrets.token_urlsafe(32)
            job['add']=dict(allocation_id=value['allocation_id'],token_hash=prep.digest(token),started=False,before=deepcopy(target),claimed_at=prep.now())
            job['phase']='Adding';save_job(q,key,job)
            mapping=value['snapshot']['mapping']
            return dict(kind='merge-add',key='merge:'+key,token=token,environment='live',
                order_id=job['target_order_id'],order_url='https://dashboard.prodigi.com/orders/'+job['target_order_id']+'/detail',
                reference=str(target['merchantReference']),sku=mapping['prodigi_code'],
                colour='' if mapping['frame']=='Unframed' else mapping['prodigi_frame_colour'],sha256=prep.digest(value['snapshot']))
        except ValueError as error:
            stop(q,key,job,values,str(error))


def stop(q,key,job,values,message):
    job.update(phase='Needs review',message=message);save_job(q,key,job)
    for value in values:
        value.update(status='Needs review',message='Consolidation stopped: '+message)
        prep.record_failure(value,'consolidation',message);prep.save(q,value)


def authorised(q,key,token):
    if not re.fullmatch(r'(?:merge|mergehold):prodigi_merge:[a-f0-9]{32}',key):raise ValueError('Unknown consolidation handoff.')
    hold=key.startswith('mergehold:');raw=key.split(':',1)[1];job=read_job(q,raw)
    if not hmac.compare_digest(job.get('hold' if hold else 'add',{}).get('token_hash',''),prep.digest(token)):raise PermissionError('Consolidation token rejected.')
    return raw,job


def permit(key,token,sha256):
    holding=key.startswith('mergehold:')
    with connection(prep.connect) as c,c.cursor() as q:
        q.execute('SELECT pg_advisory_xact_lock(%s)',(LOCK,))
        key,job=authorised(q,key,token)
        if holding:
            hold=job['hold']
            if hold['started'] or job['phase']!='Holding duplicate' or not supported():raise ValueError('Duplicate hold permit unavailable.')
            if datetime.now(timezone.utc)-datetime.fromisoformat(hold['claimed_at'])>timedelta(minutes=10):raise ValueError('Duplicate hold permit expired.')
            values=units(q,job['source_units']+job['target_units']);source,_=fresh(job,values,prep.Client(),prep.resolve)
            if source['status']!='paused' or sha256!=prep.digest(stable(source)) or stable(source)!=stable(hold['before']):raise ValueError('The duplicate changed before its hold.')
            hold.update(started=True,permitted_at=prep.now());save_job(q,key,job)
            return {'permitted':True,'order_id':job['source_order_id'],'operation':'hold-duplicate'}
        add=job['add']
        if add['started'] or job['phase']!='Adding':raise ValueError('This Add product permit was already consumed.')
        if datetime.now(timezone.utc)-datetime.fromisoformat(add['claimed_at'])>timedelta(minutes=10):raise ValueError('Consolidation handoff expired.')
        values=units(q,job['source_units']+job['target_units'])
        _,target=fresh(job,values,prep.Client(),prep.resolve)
        unit=next(v for v in values if v['allocation_id']==add['allocation_id'])
        if not supported():raise ValueError('Consolidation is paused or unavailable.')
        if sha256!=prep.digest(unit['snapshot']) or stable(target)!=stable(add['before']):raise ValueError('Destination or numbered source changed before Add.')
        add.update(started=True,permitted_at=prep.now());save_job(q,key,job)
    return {'permitted':True,'order_id':job['target_order_id'],'operation':'add-item'}


def reconcile_add(q,key,job,values,provider):
    add=job['add'];_,target=fresh(job,values,provider,prep.resolve)
    old=add['before'];ids={str(i['id']) for i in old.get('items') or []}
    new=[i for i in target.get('items') or [] if str(i.get('id')) not in ids]
    # Remove precisely the one new blank item before comparing every old detail.
    stripped=deepcopy(target);stripped['items']=[i for i in target.get('items') or [] if str(i.get('id')) in ids]
    if not new and stable(stripped)==stable(old) and datetime.now(timezone.utc)-datetime.fromisoformat(add['permitted_at'])<timedelta(minutes=2):
        return None # Eventual-consistency readback only, never repeat Select.
    if stable(stripped)!=stable(old) or len(new)!=1:
        raise ValueError('Add product is not independently confirmed as exactly one new item. No retry or cancellation was made.')
    item=new[0];unit=next(v for v in values if v['allocation_id']==add['allocation_id']);mapping=unit['snapshot']['mapping']
    if (item.get('quantity')!=1 or item.get('sku')!=mapping['prodigi_code'] or browser.has_existing_artwork(item) or
        (mapping['frame']!='Unframed' and norm((item.get('attributes') or {}).get('color'))!=norm(mapping['prodigi_frame_colour']))):
        raise ValueError('The added item does not match the exact blank reference variant.')
    by_id={str(i['id']):i for i in target['items']}
    for value in values:
        if value['allocation_id'] in job['target_units']:
            value['consolidation_binding']=binding(key,job,value,by_id[str(value['item_id'])]);prep.save(q,value)
    unit.setdefault('consolidation_history',[]).append(dict(order_id=unit['order_id'],item_id=unit['item_id'],browser=unit.get('browser'),submission=unit.get('submission')))
    for field in ('browser','write_intent','url_hash','artwork_url','artwork_expires_at','md5','submission','dashboard_qa','qa','checks','product_browser'):
        unit.pop(field,None)
    unit.update(order_id=job['target_order_id'],item_id=str(item['id']),status=browser.WAITING,browser_requested=True,
        consolidation_binding=binding(key,job,unit,item),message='Matching customer/address verified. Uploading this original numbered edition to its added supplier item.')
    prep.save(q,unit)
    job['copies'].append(dict(allocation_id=unit['allocation_id'],item_id=unit['item_id'],added_at=prep.now()))
    job.pop('add');job['phase']='Preparing artwork';save_job(q,key,job)
    return None


def finish(key,token,stage='product-readback',error=''):
    holding=key.startswith('mergehold:')
    with connection(prep.connect) as c,c.cursor() as q:
        q.execute('SELECT pg_advisory_xact_lock(%s)',(LOCK,))
        key,job=authorised(q,key,token);values=units(q,job['source_units']+job['target_units'])
        try:
            if holding:
                source,_=fresh(job,values,prep.Client(),prep.resolve)
                if not job['hold'].get('started') or stage!='merge-hold-confirmed' or source['status']!='paused':
                    raise ValueError(error[:240] if error else 'The duplicate indefinite hold was not confirmed. No destination item was added; review the original duplicate.')
                job['hold'].update(confirmed=True,confirmed_at=prep.now(),basis='Owner-authorised paired-worker indefinite-hold readback and independent unpaid supplier readback')
                job['phase']='Adding';save_job(q,key,job)
                return {'status':'Adding'}
            if not job['add'].get('started'):
                _,target=fresh(job,values,prep.Client(),prep.resolve)
                if stable(target)!=stable(job['add']['before']):raise ValueError('Unpermitted Add product handoff changed unexpectedly.')
                raise ValueError('Add product stopped before permission. Close any unsaved product picker and review this handoff; the source supplier order is intact.')
            reconcile_add(q,key,job,values,prep.Client())
        except ValueError as exc:stop(q,key,job,values,str(exc))
    return {'status':job['phase']}


def verified_destination(job,values,order):
    """All numbered copies and the complete post-add QA manifest must agree."""
    from prodigi_dashboard_qa import CHECKS,POLICY as QA_POLICY,pinned_order
    from prodigi_order_group import manifest
    exact_units(values,order)
    pinned=pinned_order(order);pinned['shippingMethod']=order.get('shippingMethod')
    for value in values:
        qa=value.get('qa') or {};receipt=value.get('dashboard_qa') or {}
        if value.get('status')!='Ready for manual payment' or qa.get('policy')!=QA_POLICY or not all(qa.get('checks',{}).get(k) is True for k in CHECKS):
            raise ValueError('Every combined numbered item must pass the complete QA checklist.')
        if not receipt.get('verified') or receipt.get('validated_order_hash')!=prep.digest(pinned):raise ValueError('Combined order changed after its full QA pass.')
        if datetime.now(timezone.utc)-datetime.fromisoformat(receipt['checked_at'])>timedelta(minutes=5):raise ValueError('Combined QA needs a fresh pass before source cancellation.')
        item=prep.validate_order(order,value['snapshot'],value['order_id'],value['item_id'],binding=value.get('consolidation_binding'))
        if (not value.get('browser',{}).get('verified') or not value.get('browser',{}).get('full_image_fit_verified') or
            len(item.get('assets') or [])!=1 or prep.digest(item['assets'][0].get('url'))!=value.get('url_hash')):
            raise ValueError('A combined numbered artwork is not independently verified.')
    return manifest(order)


def commit_ready():
    """Commit one cancellation intent, then POST once outside the transaction."""
    if not supported():return
    may_cancel=False
    with connection(prep.connect) as c,c.cursor() as q:
        q.execute('SELECT pg_try_advisory_xact_lock(%s) AS acquired',(LOCK,))
        if not q.fetchone()['acquired']:return
        q.execute("SELECT key,value FROM app_settings WHERE key LIKE 'prodigi_merge:%%' AND value->>'phase' IN ('QA','Cancelling','Cancellation uncertain') ORDER BY updated_at LIMIT 1")
        row=q.fetchone()
        if not row:return
        key,job=row['key'],row['value'];values=units(q,job['source_units']+job['target_units'])
        if job['phase']=='QA':
            if any(v['status'] in ('Needs QA','Needs review') for v in values):
                stop(q,key,job,values,'Combined QA has an unresolved check. The source supplier order remains intact.');return
            if not all(v['status']=='Ready for manual payment' for v in values):return
            try:
                _,target=fresh(job,values,prep.Client(),prep.resolve)
                final_manifest=verified_destination(job,values,target)
                job.update(phase='Cancelling',cancel_intent=dict(at=prep.now(),target_manifest=final_manifest))
                save_job(q,key,job);may_cancel=True
            except ValueError as error:stop(q,key,job,values,str(error));return
    provider=prep.Client()
    if may_cancel:
        try:provider.cancel_unpaid_duplicate(job['source_order_id'])
        except ValueError:pass # Every acknowledgement, including timeout, is read back.
    try:source=provider.order(job['source_order_id'])
    except ValueError:return # durable intent forbids another POST on the next pass
    if source.get('status')!='cancelled':
        with connection(prep.connect) as c,c.cursor() as q:
            current=read_job(q,key)
            if current['phase'] not in ('Cancelling','Cancellation uncertain'):return
            current.update(phase='Cancellation uncertain',message='The redundant supplier cancellation is not confirmed. It will only be read back, never blindly repeated.')
            save_job(q,key,current)
        return
    target=provider.order(job['target_order_id'])
    with connection(prep.connect) as c,c.cursor() as q:
        q.execute('SELECT pg_advisory_xact_lock(%s)',(LOCK,))
        current=read_job(q,key)
        if current['phase'] not in ('Cancelling','Cancellation uncertain'):return
        values=units(q,current['source_units']+current['target_units'])
        try:adopt(q,key,current,values,source,target)
        except ValueError as error:stop(q,key,current,values,str(error))


def adopt(q,key,job,values,source,target):
    from prodigi_order_group import manifest
    if (str(source.get('id'))!=job['source_order_id'] or source.get('status')!='cancelled' or
        source.get('merchantReference')!=job['source_before'].get('merchantReference') or source.get('charges') or source.get('shipments')):
        raise ValueError('The exact unpaid source cancellation is not confirmed.')
    if (str(target.get('id'))!=job['target_order_id'] or target.get('merchantReference')!=job['target_before'].get('merchantReference') or
        manifest(target)!=job['cancel_intent']['target_manifest']):raise ValueError('Combined supplier manifest changed after QA; allocations were preserved for review.')
    if target.get('status') not in ('draft','paused','submitted','in_production','partially_shipped','shipped','completed'):
        raise ValueError('Combined supplier state requires review.')
    from prodigi_dashboard_qa import pinned_order
    for value in values:
        # A legitimate charge may appear after cancellation while the paused
        # order moves to production. All fulfilment/address/insert fields must
        # still match the saved final QA hash.
        final=deepcopy(target);final['charges']=(value['dashboard_qa'].get('before') or {}).get('charges')
        pinned=pinned_order(final);pinned['shippingMethod']=final.get('shippingMethod')
        if prep.digest(pinned)!=value['dashboard_qa'].get('validated_order_hash'):raise ValueError('Shipping, address or supplier inserts changed after combined QA.')
    leader=next(v for v in values if v['allocation_id'] in job['target_units'])
    receipt=deepcopy(leader.get('submission') or {})
    paused=job['target_before']['status']=='paused'
    if paused and not receipt.get('intent_at'):raise ValueError('The destination submission receipt is missing.')
    receipt.update(leader_allocation=leader['allocation_id'],items=manifest(target),confirmed=True,
        supplier_status=target.get('status'),checked_at=prep.now(),lease_until=prep.now())
    for value in values:
        value.pop('merge_pending',None);value.pop('last_failure',None)
        value.setdefault('consolidation_receipts',[]).append(dict(policy=POLICY,key=key,source_order_id=job['source_order_id'],target_order_id=job['target_order_id'],at=prep.now(),source_cancelled=True))
        if paused:value['submission']=deepcopy(receipt)
        else:value.pop('submission',None)
        value.update(status='Submitted' if paused else 'Ready for manual payment',
            message='Matching customer orders combined and all numbered items passed QA. Redundant unpaid supplier order cancellation confirmed.')
        prep.save(q,value)
    job.update(phase='Complete',completed_at=prep.now(),message='Combined order verified; source supplier cancellation confirmed. Original customer certificates remain per edition.')
    save_job(q,key,job)
    for fence in ('prodigi_merge_source:'+job['source_order_id'],'prodigi_merge_target:'+job['target_order_id']):save_job(q,fence,dict(active=False,key=key))


def kick_commit():
    if not _commit_gate.acquire(blocking=False):return
    def work():
        try:
            commit_ready()
            from prodigi_submission import kick
            kick()
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Consolidation readback delayed; no supplier action repeated')
        finally:_commit_gate.release()
    threading.Thread(target=work,daemon=True,name='orders-merge-commit').start()


def restart_qa(user,allocation_id):
    """One-click recovery without recopying an item or repeating cancellation."""
    prep.require_user(user)
    with connection(prep.connect) as c,c.cursor() as q:
        q.execute('SELECT pg_advisory_xact_lock(%s)',(LOCK,))
        value=browser.read(q,prep.PREFIX+str(int(allocation_id)))
        key=value.get('merge_pending')
        if not key:raise ValueError('This allocation has no active consolidation.')
        job=read_job(q,key);values=units(q,job['source_units']+job['target_units'])
        if job.get('cancel_intent'):
            job['phase']='Cancellation uncertain';save_job(q,key,job)
            return {'status':'Cancellation uncertain'} # the next tick reads back; no POST
        source=prep.Client().order(job['source_order_id'])
        if source.get('status')=='paused' and not job.get('hold',{}).get('confirmed'):
            # Owner authorised holding ONLY the duplicate on 2026-11-22. A retry
            # reads the current UI first; an existing indefinite hold is not toggled.
            job['phase']='Holding duplicate'
            fresh(job,values,prep.Client(),prep.resolve)
            if job.get('hold'):job.setdefault('hold_history',[]).append(job.pop('hold'))
            save_job(q,key,job)
            for unit in values:
                unit.update(status='Merge preparing',message='Verifying an indefinite hold on the duplicate only; the retained countdown is unchanged.');prep.save(q,unit)
            return {'status':'Merge preparing'}
        _,target=fresh(job,values,prep.Client(),prep.resolve)
        if job.get('add'):
            if job['add'].get('started'):
                reconcile_add(q,key,job,values,prep.Client())
                if job.get('add'):raise ValueError('An uncertain Add product is still not confirmed. It will not be clicked twice.')
            else:
                if stable(target)!=stable(job['add']['before']):raise ValueError('The unpermitted Add product changed; review the destination before retrying.')
                job.pop('add')
        values=units(q,job['source_units']+job['target_units'])
        all_copied=len(job['copies'])==len(job['source_units'])
        ready=all_copied and all(v.get('browser',{}).get('verified') and v.get('browser',{}).get('full_image_fit_verified') for v in values)
        if not ready and job['copies']:
            raise ValueError('A copied image Save still needs independent readback before restarting. Existing supplier items were preserved.')
        job['phase']='QA' if ready else 'Adding';job.pop('message',None);save_job(q,key,job)
        for unit in values:
            unit.pop('last_failure',None)
            if ready:
                if unit.get('dashboard_qa'):unit.setdefault('dashboard_qa_history',[]).append(unit.pop('dashboard_qa'))
            unit.update(status='Awaiting dashboard QA' if ready else 'Merge preparing',message='Consolidation requeued with original allocations and supplier items preserved.')
            prep.save(q,unit)
    return {'status':'Awaiting dashboard QA' if ready else 'Merge preparing'}
