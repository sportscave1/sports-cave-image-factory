"""Inbox Companion: private durable requests; no cancel, variant, payment or resume."""
from copy import deepcopy
import hmac
import json
import os
import secrets
import threading
import uuid
import prodigi_preparation as prep
import inbox_companion_policy as policy

SETTING='inbox_companion_settings'
PREFIX='inbox_companion_request:'
FLAG='inbox_companion_order:'
_gate=threading.Lock()

def available():return os.getenv('SPORTS_CAVE_INBOX_COMPANION_ENABLED','').lower()=='true'

def order_identity(value):
    value=str(value or '').strip()
    if value.startswith('gid://shopify/Order/'):value=value.rsplit('/',1)[-1]
    return value if value.isascii() and value.isdigit() and len(value)<=30 else ''

def read(key,cur=None):
    if cur is None:
        with prep.connect() as c,c.cursor() as q:return read(key,q)
    cur.execute('SELECT value FROM app_settings WHERE key=%s',(key,))
    row=cur.fetchone()
    return deepcopy(row['value']) if row else {}

def save(q,key,value):
    q.execute('INSERT INTO app_settings(key,value,updated_at) VALUES(%s,%s::jsonb,now()) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=now()',
              (key,json.dumps(value,default=str)))

def configure(actor,enabled):
    import os_accounts
    prep.require_user(actor)
    if not os_accounts.can_access_page(actor,'Email'):raise PermissionError('Email access required.')
    if enabled and not available():raise ValueError('Inbox Companion has not been released and enabled on this server.')
    if enabled and not os.getenv('SPORTS_CAVE_INBOX_AUTH_SERVERS','').strip():
        raise ValueError('Verify and configure the receiving mailbox authentication authority before enabling Inbox Companion.')
    old=read(SETTING)
    baseline=None
    if enabled and not old.get('enabled'):
        # Establish the cursor before activation, including the first desktop alarm gap.
        from support_email_provider import ImapProvider,load_configuration
        snapshot=ImapProvider(load_configuration(),background=True).notification_snapshot(None)
        baseline={k:snapshot[k] for k in ('uidvalidity','last_uid')}
    with prep.connect() as c,c.cursor() as q:
        q.execute('SELECT value FROM app_settings WHERE key=%s FOR UPDATE',(SETTING,))
        row=q.fetchone()
        if (row['value'] if row else {})!=old:raise ValueError('Inbox settings changed; refresh before activating.')
        save(q,SETTING,{**old,'enabled':bool(enabled),'actor':str(actor['id']),'changed_at':prep.now(),
                       **({'cursor':baseline} if baseline is not None else {})})

def blocked(shopify_id):
    # Existing Orders behaviour has no additional I/O while the feature is off.
    return available() and bool(order_identity(shopify_id)) and read(FLAG+order_identity(shopify_id)).get('blocking') is True

def submission_guard(value):
    identity=value.get('snapshot',{}).get('identity',{})
    if blocked(identity.get('order_id')):raise ValueError('Paused customer request — review the Inbox Companion flag before submission.')

def flag(q,job,message,blocking=True):
    key=FLAG+str(job['shopify_order_id']);old=read(key,q)
    if (old.get('request') not in (None,job['key']) and old.get('received_validity')==job['header']['uidvalidity']
        and old.get('received_uid',0)>int(job['header']['uid'])):return
    save(q,key,dict(request=job['key'],received_uid=int(job['header']['uid']),blocking=blocking,
                    received_validity=job['header']['uidvalidity'],
                    paused=job['kind']=='hold' and job['state']=='done',
                    label=message,updated_at=prep.now(),kind=job['kind']))

def preparations(shopify_id):
    identity=order_identity(shopify_id)
    if not identity:return []
    with prep.connect() as c,c.cursor() as q:
        q.execute("SELECT key,value FROM app_settings WHERE key LIKE 'prodigi_prepare:%%' AND value->'snapshot'->'identity'->>'order_id'=ANY(%s)",([identity,'gid://shopify/Order/'+identity],))
        return [r['value'] for r in q.fetchall() if not r['value'].get('hidden')]

def scan(config,imap,orders_loader):
    current=imap.notification_snapshot(config.get('cursor'))
    cursor={k:current[k] for k in ('uidvalidity','last_uid')}
    # First activation and UIDVALIDITY rotation establish a baseline. Never act on old mail.
    if not config.get('cursor') or config['cursor']['uidvalidity']!=current['uidvalidity']:
        with prep.connect() as c,c.cursor() as q:save(q,SETTING,{**config,'cursor':cursor})
        return
    messages=sorted(current['messages'],key=lambda h:int(h['uid']))
    for short in messages[:5]:
        header=imap.notification_target(short['uidvalidity'],short['uid'],short.get('message_id',''))
        if not header:continue
        identity=header.get('message_id') or [header['uidvalidity'],header['uid']]
        key=PREFIX+prep.digest([imap.configuration.address.casefold(),identity])
        if read(key):continue
        body=imap.read_message(header,load_inline_images=False)
        request=policy.classify(header.get('subject',''),body.get('text',''),is_reply=bool(header.get('in_reply_to') or header.get('references')))
        if request['kind']=='ignore' or body.get('warnings'):continue
        orders=orders_loader(emails=[header['sender']['email'].casefold()])
        matched=policy.match_order(header,request['text'],orders)
        if not matched or not order_identity(matched['shopify_order_id']):continue
        job=dict(key=key,header=header,shopify_order_id=order_identity(matched['shopify_order_id']),
                 order_name=matched['order_name'],kind=request['kind'],state='pending',
                 sender_verified=header.get('sender_verified') is True,
                 proposed=policy.proposed_address(request['text']) if request['kind']=='address' else None,
                 targets={},actor=config['actor'],created_at=prep.now())
        with prep.connect() as c,c.cursor() as q:
            if not read(key,q):
                save(q,key,job)
                # Block all submissions until the request has been classified against supplier state.
                flag(q,job,'Customer request · checking shipping address' if job['kind']=='address' else 'Paused customer request')
    if len(messages)>5:cursor['last_uid']=int(messages[4]['uid'])
    with prep.connect() as c,c.cursor() as q:
        latest=read(SETTING,q)
        if latest.get('enabled') and latest.get('changed_at')==config.get('changed_at'):save(q,SETTING,{**latest,'cursor':cursor})

def supplier(job,order_id):
    from prodigi_client import Client
    provider=Client()
    order=provider.order(order_id)
    units=preparations(job['shopify_order_id'])
    if str(order.get('id'))!=str(order_id) or not any(str(v.get('order_id'))==str(order_id) for v in units):
        raise ValueError('The matched supplier order changed.')
    # Require a known reference and exact full item membership; never edit a merged unrelated customer.
    expected={str(v['item_id']) for v in units if str(v.get('order_id'))==str(order_id) and v.get('item_id')}
    if not expected or len(order.get('items',[]))!=len(expected) or {str(i.get('id')) for i in order.get('items',[])}!=expected:
        raise ValueError('Supplier item membership needs review.')
    references={job['shopify_order_id'],'gid://shopify/Order/'+job['shopify_order_id']}
    for unit in units:
        source=unit.get('snapshot',{})
        reference=str(source.get('order_reference') or '')
        identity=str(source.get('identity',{}).get('order_id') or '')
        references.update((reference,reference.lstrip('#'),identity,order_identity(identity)))
    references.discard('')
    if str(order.get('merchantReference')) not in references:
        raise ValueError('Supplier reference needs review.')
    if str(order.get('recipient',{}).get('email','')).casefold()!=job['header']['sender']['email'].casefold():
        raise ValueError('Supplier recipient differs from the customer email.')
    return order

def pending():
    with prep.connect() as c,c.cursor() as q:
        q.execute("SELECT value FROM app_settings WHERE key LIKE 'inbox_companion_request:%%' AND value->>'state' IN ('pending','working') ORDER BY updated_at LIMIT 20")
        return [r['value'] for r in q.fetchall()]

def plan(job):
    if read(FLAG+job['shopify_order_id']).get('request')!=job['key']:
        job.update(state='superseded',message='A newer customer request is awaiting review.')
        with prep.connect() as c,c.cursor() as q:save(q,job['key'],job)
        return None
    if job.get('sender_verified') is not True:
        job.update(state='review',message='Customer request · sender verification required')
        with prep.connect() as c,c.cursor() as q:save(q,job['key'],job);flag(q,job,job['message'])
        return None
    units=preparations(job['shopify_order_id'])
    ids=sorted({str(v['order_id']) for v in units if v.get('order_id')})
    if not ids:return None
    # An in-flight native operation must finish before this separate handoff.
    busy={'Selecting product','Browser uploading','Checking dashboard QA','Submitting','Certificate browser uploading'}
    if any(v.get('status') in busy for v in units):return None
    # Preflight every split supplier order before changing any of them.
    orders={order_id:supplier(job,order_id) for order_id in ids}
    if any(o.get('status') not in ('paused','on_hold') for o in orders.values()):
        draft=any(o.get('status')=='draft' for o in orders.values())
        job.update(state='review',message='Paused customer request · supplier draft retained for review' if draft else 'Customer request · supplier is no longer editable; review required')
        with prep.connect() as c,c.cursor() as q:save(q,job['key'],job);flag(q,job,job['message'])
        return None
    proposed=job.get('proposed')
    if job['kind']=='address' and (not proposed or any(proposed['address']['countryCode']!=o.get('recipient',{}).get('address',{}).get('countryCode') for o in orders.values())):
        if any(t.get('state')=='confirmed' and t.get('action')=='address' for t in job['targets'].values()):
            job.update(state='review',message='Customer request · split address update needs review')
            with prep.connect() as c,c.cursor() as q:save(q,job['key'],job);flag(q,job,job['message'])
            return None
        job['kind']='hold'
    for order_id in ids:
        if job['targets'].get(order_id,{}).get('state')=='confirmed':continue
        order=orders[order_id]
        target=job['targets'].get(order_id)
        if target and target.get('state') in ('claimed','started','uncertain'):
            # Never replay a possibly saved change. Operator can inspect the exact order.
            job.update(state='review',message='Customer request · previous action needs verification')
            with prep.connect() as c,c.cursor() as q:save(q,job['key'],job);flag(q,job,job['message'])
            return None
        proposed=job.get('proposed')
        old=order.get('recipient',{})
        updated=({**old,'name':proposed.get('name') or old.get('name',''),'address':proposed['address']}
                 if job['kind']=='address' and proposed and proposed['address']['countryCode']==old.get('address',{}).get('countryCode') else None)
        action='address' if updated else 'hold'
        if job['kind']=='address' and not updated:job['kind']='hold'
        token=secrets.token_urlsafe(32)
        job['targets'][order_id]=dict(state='claimed',token_hash=prep.digest(token),before=order,
                                     recipient=updated,action=action,claimed_at=prep.now())
        job['state']='working'
        with prep.connect() as c,c.cursor() as q:save(q,job['key'],job)
        return dict(key=job['key'],token=token,order_id=order_id,reference=str(order['merchantReference']),
                    order_url='https://dashboard.prodigi.com/orders/'+order_id+'/detail',action=action,
                    recipient=updated,before_recipient=order.get('recipient',{}))
    confirm(job)
    return None

def authorised(key,token,order_id):
    if not key.startswith(PREFIX) or len(key)!=len(PREFIX)+64:raise ValueError('Invalid Inbox request.')
    job=read(key);target=job.get('targets',{}).get(str(order_id),{})
    if not target or not hmac.compare_digest(target.get('token_hash',''),prep.digest(token)):
        raise PermissionError('Retired Inbox handoff.')
    if read(FLAG+job['shopify_order_id']).get('request')!=key:raise ValueError('A newer customer request needs review.')
    return job,target

def permit(key,token,order_id):
    job,target=authorised(key,token,order_id)
    if target['state']!='claimed':raise ValueError('Inbox write permit already used.')
    order=supplier(job,order_id)
    if order.get('status') not in ('paused','on_hold') or prep.digest(order)!=prep.digest(target['before']):
        raise ValueError('Supplier state changed before the customer request.')
    with prep.connect() as c,c.cursor() as q:
        q.execute('SELECT value FROM app_settings WHERE key=%s FOR UPDATE',(key,));fresh=q.fetchone()['value']
        current=fresh['targets'][order_id]
        if current!=target:raise ValueError('Inbox handoff already changed.')
        if read(FLAG+job['shopify_order_id'],q).get('request')!=key:raise ValueError('Newer customer request arrived.')
        current['state']='started';current['permitted_at']=prep.now();save(q,key,fresh)
    return dict(permitted=True,action=target['action'],order_id=order_id)

def finish(key,token,order_id,evidence=None,error=''):
    job,target=authorised(key,token,order_id)
    if target['state']=='confirmed':return {'confirmed':True}
    order=supplier(job,order_id)
    if not error and target['action']=='address' and target['state']=='started':
        import time
        # Supplier persistence may trail the closed dialog; retry only GET readback.
        for _ in range(3):
            if policy.same_address(target['recipient'],order.get('recipient',{})):break
            time.sleep(.5);order=supplier(job,order_id)
    ok=(not error and target['state']=='started' and isinstance(evidence,dict)
        and order.get('status') in ('paused','on_hold') and policy.unchanged_order(target['before'],order))
    if target['action']=='address':
        ok=ok and policy.same_address(target['recipient'],order.get('recipient',{})) and evidence.get('address_saved') is True
        # Contact details must be preserved; the form never edits phone/email.
        old_recipient=target['before'].get('recipient',{});new_recipient=order.get('recipient',{})
        ok=ok and all(new_recipient.get(k)==old_recipient.get(k) for k in (old_recipient.keys()|new_recipient.keys())-{'name','address'})
    else:ok=ok and evidence.get('indefinite_hold') is True and order.get('recipient')==target['before'].get('recipient')
    target.update(state='confirmed' if ok else 'uncertain',checked_at=prep.now())
    if not ok:job.update(state='review',message='Customer request · saved action not confirmed; review required')
    with prep.connect() as c,c.cursor() as q:
        save(q,key,job)
        if not ok:flag(q,job,job['message'])
    if ok:confirm(job)
    return {'confirmed':bool(ok)}

def confirm(job):
    if read(FLAG+job['shopify_order_id']).get('request')!=job['key']:return
    ids={str(v['order_id']) for v in preparations(job['shopify_order_id']) if v.get('order_id')}
    if not ids or any(job['targets'].get(i,{}).get('state')!='confirmed' for i in ids):return
    if job['kind']=='address':
        # Existing durable SMTP outbox owns sending and Sent-copy reconciliation.
        from support_email_provider import load_configuration
        from support_email_store import load_email_settings
        from support_email_compose import new_draft,build_mime,plain_html
        from support_email_durable import REGISTRY
        mailbox=load_configuration().address
        settings,_=load_email_settings(mailbox,job['actor'])
        draft=new_draft(mailbox,mode='reply',header=job['header'],signature='nathan')
        operation=str(uuid.uuid5(uuid.NAMESPACE_URL,'sports-cave-inbox:'+job['key']))
        draft.update(id=operation,operation_id=operation,include_quote=False,
                     html=plain_html('Your shipping address has been updated for order '+job['order_name']+'.'))
        mime=build_mime(draft,mailbox,settings['sender_name'],settings['signatures'])
        # prepare is deduplicated by operation ID, and unknown SMTP results are never resent.
        REGISTRY.store.prepare(mailbox,operation,mime,actor=job['actor'],
                               folder=settings.get('folder_mapping',{}).get('sent',''),policy='append')
        label='Shipping address updated · confirmation queued'
    else:label='Paused customer request · review required'
    job.update(state='done',message=label,completed_at=prep.now())
    with prep.connect() as c,c.cursor() as q:save(q,job['key'],job);flag(q,job,label,blocking=job['kind']!='address')

def tick(actor,*,scan_only=False):
    import os_accounts
    prep.require_user(actor)
    if not os_accounts.can_access_page(actor,'Email'):raise PermissionError('Email access required.')
    if not available():return {'enabled':False}
    config=read(SETTING)
    if not config.get('enabled'):return {'enabled':False}
    if not _gate.acquire(blocking=False):return {'enabled':True,'busy':True}
    try:
        from support_email_provider import ImapProvider,load_configuration,MailboxError
        from support_email_runtime import Deferred
        from prodigi_client import ProdigiError
        from support_email_store import load_orders
        imap=ImapProvider(load_configuration(),background=True)
        try:scan(config,imap,load_orders)
        except (MailboxError,Deferred):pass # Durable requests can progress during a mailbox reconnect.
        if scan_only:return {'enabled':True}
        for job in pending():
            try:browser=plan(job)
            except ProdigiError:continue # A supplier outage must not starve another ready customer request.
            except ValueError:
                job.update(state='review',message='Customer request · order identity needs review')
                with prep.connect() as c,c.cursor() as q:save(q,job['key'],job);flag(q,job,job['message'])
                continue
            if browser:return {'enabled':True,'browser':browser}
        return {'enabled':True}
    finally:_gate.release()

def review(actor,key):
    import os_accounts
    prep.require_user(actor)
    if not os_accounts.can_access_page(actor,'Email'):raise PermissionError('Email access required.')
    with prep.connect() as c,c.cursor() as q:
        q.execute('SELECT value FROM app_settings WHERE key=%s FOR UPDATE',(key,))
        row=q.fetchone()
        if not row or not key.startswith(PREFIX):raise ValueError('Unknown Inbox request.')
        job=row['value'];current=read(FLAG+job['shopify_order_id'],q)
        if job['state'] not in ('review','done') or current.get('request')!=key:
            raise ValueError('Wait for the current request to finish before reviewing.')
        job.update(state='reviewed',reviewed_by=str(actor['id']),reviewed_at=prep.now())
        save(q,key,job);flag(q,job,'Customer request reviewed · supplier hold unchanged',blocking=False)
