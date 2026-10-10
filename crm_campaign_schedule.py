"""Recipient-local schedules on existing persistent CRM queue rows."""
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from crm_campaign_markets import country

AU={'NSW':'Australia/Sydney','VIC':'Australia/Melbourne','QLD':'Australia/Brisbane','SA':'Australia/Adelaide','WA':'Australia/Perth','TAS':'Australia/Hobart','NT':'Australia/Darwin','ACT':'Australia/Sydney'}
US={}
for zone,states in {'America/New_York':'CT DE DC GA ME MD MA NH NJ NY NC OH PA RI SC VT VA WV',
 'America/Chicago':'AL AR IL IA LA MN MS MO OK WI', 'America/Denver':'CO MT NM UT WY',
 'America/Los_Angeles':'CA NV WA', 'America/Phoenix':'AZ','Pacific/Honolulu':'HI'}.items():
    US.update(dict.fromkeys(states.split(),zone))
STATE_NAMES={'NEW SOUTH WALES':'NSW','VICTORIA':'VIC','QUEENSLAND':'QLD','SOUTH AUSTRALIA':'SA','WESTERN AUSTRALIA':'WA','TASMANIA':'TAS','NORTHERN TERRITORY':'NT','AUSTRALIAN CAPITAL TERRITORY':'ACT','NEW YORK':'NY','ILLINOIS':'IL','COLORADO':'CO','CALIFORNIA':'CA'}
FALLBACK={'AU':'Australia/Sydney','US':'America/New_York','GB':'Europe/London'}

def resolve(customer):
    address=customer.get('defaultAddress') or {}
    explicit=address.get('timeZone') or customer.get('timezone') or customer.get('timeZone')
    if isinstance(explicit,str):
        try:ZoneInfo(explicit);return explicit,'address_timezone'
        except (ZoneInfoNotFoundError,ValueError):pass
    code=country(customer);state=str(address.get('provinceCode') or address.get('province') or '').strip().upper()
    state=STATE_NAMES.get(state,state)
    # Known cross-zone regions: don't pretend a state-only guess is precise.
    if code=='AU' and str(address.get('zip',''))=='2880':return 'Australia/Broken_Hill','postcode'
    zone=(AU if code=='AU' else US if code=='US' else {}).get(state)
    if zone:return zone,'state'
    if code=='GB':return 'Europe/London','country'
    return FALLBACK.get(code,'UTC'),'country_fallback' if code in FALLBACK else 'global_utc_fallback'

ZONES={
 'AU':tuple(dict.fromkeys(AU.values()))+('Australia/Broken_Hill',),
 'UK':('Europe/London',),'NZ':('Pacific/Auckland',),
 'US':tuple(dict.fromkeys(US.values()))+('America/Anchorage',),
 'CA':('America/Toronto','America/Vancouver','America/Edmonton','America/Winnipeg','America/Halifax','America/St_Johns','America/Regina')}
DEFAULTS={'AU':'Australia/Sydney','UK':'Europe/London','US':'America/New_York','NZ':'Pacific/Auckland'}

def validate(value):
    if not isinstance(value,dict) or value.get('mode') not in ('now','schedule'):raise ValueError('Choose Send now or Schedule.')
    if value['mode']=='now':
        if set(value)!={'mode'}:raise ValueError('Invalid immediate timing.')
        return
    legacy=set(value)=={'mode','date','time'}
    if not legacy:
        basis=value.get('time_basis')
        required={'mode','date','time','policy_version','time_basis'}|({'timezone'} if basis=='campaign_timezone' else set())
        if set(value)-{'ambiguity'}!=required or type(value.get('policy_version')) is not int or value['policy_version']!=2 or basis not in ('campaign_timezone','recipient_local'):
            raise ValueError('Choose a validated campaign timezone or explicit recipient-local schedule.')
        if value.get('ambiguity','reject') not in ('reject','earlier','later'):raise ValueError('Invalid daylight-saving ambiguity policy.')
        if basis=='campaign_timezone':
            try:ZoneInfo(value['timezone'])
            except (ZoneInfoNotFoundError,ValueError,TypeError):raise ValueError('Choose a valid IANA timezone.') from None
    try:
        day=datetime.strptime(value['date'],'%Y-%m-%d');hour=datetime.strptime(value['time'],'%H:%M')
        if day.strftime('%Y-%m-%d')!=value['date'] or hour.strftime('%H:%M')!=value['time']:raise ValueError()
    except (ValueError,TypeError):raise ValueError('Choose a valid schedule date and local time.') from None

def due(value,zone):
    validate(value)
    naive=datetime.strptime(value['date']+' '+value['time'],'%Y-%m-%d %H:%M')
    local=naive.replace(tzinfo=ZoneInfo(zone),fold=0)
    utc=local.astimezone(timezone.utc)
    # Never silently shift a nonexistent spring-forward wall time.
    if utc.astimezone(ZoneInfo(zone)).replace(tzinfo=None)!=naive:raise ValueError('Selected local time does not exist during daylight-saving change. Choose another time.')
    second=naive.replace(tzinfo=ZoneInfo(zone),fold=1).astimezone(timezone.utc)
    if second!=utc:
        # Old reviewed contracts keep their historical first-occurrence policy.
        policy=value.get('ambiguity','earlier' if 'policy_version' not in value else 'reject')
        if policy=='reject':raise ValueError('Selected local time is ambiguous during daylight-saving change. Choose earlier or later occurrence explicitly.')
        if policy=='later':return second
    return utc

def recipient_zone(customer):
    """Only address provenance and consistent geography can authorize local time.

    Shopify address timezone is not proof of where an operator wants a campaign
    sent. State-derived zones take priority; conflicting explicit values block.
    No customer/account/store-level timezone or global UTC fallback is trusted.
    """
    address=customer.get('defaultAddress') or {};code=country({'defaultAddress':address})
    # Customer/store country is not address provenance. Reject disagreement
    # between populated address fields instead of silently taking the first.
    countries={country({'defaultAddress':{'country':address[k]}}) for k in ('countryCodeV2','countryCode','country') if address.get(k)}
    if len(countries)>1:raise ValueError('conflicting_recipient_country')
    states={STATE_NAMES.get(str(address[k]).strip().upper(),str(address[k]).strip().upper()) for k in ('provinceCode','province') if address.get(k)}
    if len(states)>1:raise ValueError('conflicting_recipient_state')
    state=str(address.get('provinceCode') or address.get('province') or '').strip().upper()
    state=STATE_NAMES.get(state,state)
    explicit=address.get('timeZone')
    expected=(AU if code=='AU' else US if code=='US' else {}).get(state)
    postcode=str(address.get('zip') or '').strip()
    if code=='AU' and postcode:
        if len(postcode)!=4 or not postcode.isascii() or not postcode.isdigit():raise ValueError('invalid_recipient_postcode')
        # Conservative consistency check, not a postcode-to-location geocoder.
        # Cross-border and special regions need separately verified evidence.
        if postcode in {'0872','2406','2540','2611','2620','3644','3691','3707','4380','4377','4383','4385','4825','4828','2898','2899','6798','6799','6443'}:
            raise ValueError('unverified_recipient_postcode')
        ranges={'NSW':((1000,2599),(2619,2899),(2921,2999)), 'ACT':((200,299),(2600,2618),(2900,2920)),
                'VIC':((3000,3999),(8000,8999)), 'QLD':((4000,4999),(9000,9999)),
                'SA':((5000,5999),), 'WA':((6000,6999),), 'TAS':((7000,7999),), 'NT':((800,999),)}
        if state not in ranges or not any(lo<=int(postcode)<=hi for lo,hi in ranges[state]):raise ValueError('conflicting_recipient_postcode')
        if postcode=='2880':expected='Australia/Broken_Hill'
    country_zone={'GB':'Europe/London','NZ':'Pacific/Auckland'}.get(code)
    if country_zone:expected=country_zone
    allowed=ZONES.get('UK' if code=='GB' else code,())
    if explicit:
        try:ZoneInfo(explicit)
        except (ZoneInfoNotFoundError,ValueError,TypeError):raise ValueError('invalid_recipient_timezone') from None
        if explicit not in allowed or (expected and explicit!=expected):raise ValueError('conflicting_recipient_timezone')
        # A country alone cannot prove one zone within a multi-zone country.
        if not expected and code not in ('GB','NZ'):raise ValueError('unverified_recipient_timezone')
        if code=='AU' and not postcode:raise ValueError('incomplete_recipient_postcode')
        return explicit,'validated_address_timezone'
    if code=='AU' and expected and not postcode:raise ValueError('incomplete_recipient_postcode')
    if expected:return expected,'state' if state else 'country'
    raise ValueError('unknown_recipient_timezone')

def summary(timing,schedule=None):
    if timing.get('mode')!='schedule':return 'Send now'
    if timing.get('time_basis')!='campaign_timezone':
        label=timing['date']+' · '+timing['time']+' in each recipient’s own timezone'
        if schedule:
            stamps=sorted(j['due_at'] for j in schedule.values())
            label+=' · UTC window '+stamps[0]+' – '+stamps[-1]
        return label
    instant=due(timing,timing['timezone']);local=instant.astimezone(ZoneInfo(timing['timezone']))
    return local.strftime('%d %b, %I:%M %p').replace(', 0',', ')+' '+timing['timezone'].split('/')[-1].replace('_',' ')+' time ('+local.tzname()+')'

def plan(doc,state,at):
    timing=doc.get('send_timing',{'mode':'now'});validate(timing)
    if timing['mode']=='now':return {}
    jobs={};errors={}
    fixed=timing.get('time_basis')=='campaign_timezone'
    if fixed:
        allowed=ZONES.get(doc.get('market'))
        if allowed and timing['timezone'] not in allowed:raise ValueError('Selected timezone does not match the campaign market.')
        instant=due(timing,timing['timezone'])
    for r in state['recipients']:
        customer=state['profiles'][r['id']]
        from crm_campaign_segments import COUNTRIES
        if 'policy_version' in timing and doc.get('market') in COUNTRIES and country(customer)!=COUNTRIES[doc['market']]:
            errors['market_country_mismatch']=errors.get('market_country_mismatch',0)+1;continue
        if fixed:zone,reason=timing['timezone'],'campaign_timezone'
        elif 'policy_version' in timing:
            try:zone,reason=recipient_zone(customer)
            except ValueError as exc:
                code=str(exc);errors[code]=errors.get(code,0)+1;continue
            instant=due(timing,zone)
        else:zone,reason=resolve(customer);instant=due(timing,zone)
        if instant<=at:raise ValueError('Schedule missed — reschedule required. Choose a future local date and time for every recipient.')
        jobs[r['hash']]={'timezone':zone,'reason':reason,'due_at':instant.isoformat()}
    if errors:raise ValueError('Schedule blocked — recipient data needs review: '+', '.join(k+' ('+str(v)+')' for k,v in sorted(errors.items())))
    return jobs

def change_pending(store,user,identity,timing,operation_id,*,confirmed=False,clock=None,expected_operation_id=None):
    """Explicit schedule-only amendment of entirely untouched native campaigns.

    Lock campaign and every receipt before comparing state. Preserve immutable
    content/audience and all identities; never reset blocked or submitted jobs.
    A receipt in existing runtime storage makes retrying the action idempotent.
    """
    import json,uuid
    from crm_navigation import require
    from crm_logic import now,date
    from crm_resend import Config
    require(user,'crm_campaigns_manage')
    if not confirmed:raise ValueError('Explicit schedule confirmation required.')
    validate(timing)
    operation=str(uuid.UUID(str(operation_id)));identity=str(uuid.UUID(str(identity)))
    key='campaign-timing:'+identity;at=(clock or now)()
    with store.db() as conn:
        campaign=conn.execute('SELECT * FROM crm_campaigns WHERE id=%s FOR UPDATE',(identity,)).fetchone()
        if not campaign:raise ValueError('Campaign not found.')
        prior=conn.execute('SELECT value FROM crm_runtime_state WHERE key=%s',(key,)).fetchone()
        prior=prior['value'] if prior else {}
        operation_key='campaign-timing-operation:'+identity+':'+operation
        acknowledged=conn.execute('SELECT value FROM crm_runtime_state WHERE key=%s',(operation_key,)).fetchone()
        if acknowledged:
            receipt=acknowledged['value']
            if receipt.get('timing')!=timing:raise ValueError('Schedule operation changed; confirm again.')
            return receipt
        if prior.get('operation_id')==operation:
            if prior.get('timing')!=timing:raise ValueError('Schedule operation changed; confirm again.')
            return prior
        if prior.get('operation_id')!=expected_operation_id:raise ValueError('Schedule changed elsewhere. Reload before confirming.')
        if timing['mode']=='now':Config().require_send(False)
        if campaign['status']!='SCHEDULED' or not campaign.get('audience_snapshot_id'):raise ValueError('Only an untouched scheduled campaign can be changed.')
        rows=conn.execute('SELECT * FROM crm_marketing_sends WHERE campaign_id=%s AND NOT test_send FOR UPDATE',(identity,)).fetchall()
        initial_blocks={'local_suppression','consent_invalid','consent_not_subscribed','consent_pending','consent_unsubscribed','consent_redacted','recipient_changed','recipient_timezone_changed','invalid_recipient_timezone','market_country_mismatch','missing_shopify_marketing_unsubscribe_url','unsubscribe_url_size'}
        if not rows or any((r['status']!='PENDING' and not (r['status']=='BLOCKED' and r.get('error_code') in initial_blocks)) or r.get('attempts',0) or r.get('first_submitted_at') or r.get('provider_email_id') or r.get('lease_token') or r.get('request_hash') for r in rows):
            raise ValueError('Campaign has locked, blocked or attempted deliveries. No schedule was changed.')
        # Waiting for a claim lock must not leave the future-time check stale.
        at=(clock or now)()
        version=conn.execute('SELECT content FROM crm_template_versions WHERE template_id=%s AND version=%s',(campaign['template_id'],campaign['template_version'])).fetchone()
        doc=version['content']['document']
        pending=[r for r in rows if r['status']=='PENDING']
        if not pending:raise ValueError('No eligible queued recipients remain.')
        frozen=version['content'].get('schedule') or {}
        fixed_instant=None
        if timing['mode']=='schedule' and timing.get('time_basis')=='campaign_timezone':
            zone=timing['timezone']
            if doc.get('market') in ZONES and zone not in ZONES[doc['market']]:raise ValueError('Selected timezone does not match the campaign market.')
            fixed_instant=due(timing,zone)
            if fixed_instant<=at:raise ValueError('Choose a future schedule for every queued recipient.')
        updates=[]
        for row in pending:
            if timing['mode']=='schedule':
                if timing.get('time_basis')=='campaign_timezone':
                    zone=timing['timezone']
                else:
                    # Use the reviewed recipient timezone, never the operator's
                    # location or a fresh, potentially different audience.
                    reviewed_timing=doc.get('send_timing') or {}
                    evidence=frozen.get(row['recipient_hash']) or {}
                    # A legacy state/country mapping is usable without claiming
                    # that an unverified explicit timezone or fallback is valid.
                    sources={'validated_address_timezone','state','country','postcode'}
                    if reviewed_timing.get('time_basis')=='campaign_timezone' or evidence.get('reason') not in sources:
                        raise ValueError('Recipient-local timezone evidence was not validated. Review the recipient data before scheduling locally.')
                    zone=(frozen.get(row['recipient_hash']) or {}).get('timezone')
                    if not zone:raise ValueError('Reviewed recipient timezone missing. No schedule was changed.')
                instant=fixed_instant if fixed_instant is not None else due(timing,zone)
                if instant<=at:raise ValueError('Choose a future schedule for every queued recipient.')
            else:instant=at
            updates.append({'id':str(row['id']),'due_at':instant.isoformat()})
        # Outage-blocked rows are never released, including by Send now.
        if any(date(r['due_at'])<=at for r in pending):raise ValueError('Campaign is already due; recovery requires separate review.')
        receipt={'timing':timing,'operation_id':operation,'due_at':min(j['due_at'] for j in updates),'changed_at':at.isoformat()}
        conn.execute("""UPDATE crm_marketing_sends s SET due_at=j.due_at,updated_at=now()
          FROM jsonb_to_recordset(%s::jsonb) AS j(id uuid,due_at timestamptz)
          WHERE s.id=j.id AND s.status='PENDING'""",(json.dumps(updates),))
        # Original scheduled_at is part of the locked publication record. The
        # amendment supplies effective scheduling separately; never unlock it.
        conn.execute("UPDATE crm_campaigns SET status=%s,sending_started_at=%s,updated_at=now() WHERE id=%s",('SENDING' if timing['mode']=='now' else 'SCHEDULED',at if timing['mode']=='now' else None,identity))
        conn.execute('INSERT INTO crm_runtime_state(key,value) VALUES(%s,%s::jsonb) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=now()',(key,json.dumps(receipt)))
        conn.execute('INSERT INTO crm_runtime_state(key,value) VALUES(%s,%s::jsonb)',(operation_key,json.dumps(receipt)))
        draft=conn.execute('SELECT id,version FROM crm_campaign_drafts WHERE id=%s',(identity,)).fetchone()
        store._history(conn,{**draft,'schedule_amendment':receipt},'campaign_schedule_changed',str(user.get('id') or user.get('username') or ''),{'schedule_amendment':prior})
        return receipt


def activate_due(store,*,clock=None):
    """Worker-only transition; serialize with amendments before reading the due.

    The second statement gets a fresh READ COMMITTED snapshot after any wait.
    An optional clock supports deterministic disposable-data tests only.
    """
    at=clock() if clock else None
    with store.db() as conn:
        ids=[r['id'] for r in conn.execute("""SELECT c.id FROM crm_campaigns c
          WHERE c.status='SCHEDULED' AND c.audience_snapshot_id IS NOT NULL
          AND COALESCE((SELECT (r.value->>'due_at')::timestamptz FROM crm_runtime_state r
            WHERE r.key='campaign-timing:'||c.id::text),c.scheduled_at)<=COALESCE(%s::timestamptz,clock_timestamp())
          ORDER BY c.id FOR UPDATE""",(at,)).fetchall()]
        if not ids:return 0
        at=clock() if clock else None
        rows=conn.execute("""UPDATE crm_campaigns c SET status='SENDING',sending_started_at=now(),updated_at=now()
          WHERE c.id=ANY(%s::uuid[]) AND c.status='SCHEDULED'
          AND COALESCE((SELECT (r.value->>'due_at')::timestamptz FROM crm_runtime_state r
            WHERE r.key='campaign-timing:'||c.id::text),c.scheduled_at)<=COALESCE(%s::timestamptz,clock_timestamp())
          RETURNING c.id""",(ids,at)).fetchall()
        return len(rows)


def schedule_gate(store,enabled,at):
    """Worker lease serializes this checkpoint. Never catch up after an OFF gap.

    A >5 minute worker outage also fails closed for already-due work. Future
    jobs remain eligible. BLOCKED jobs are never reset to PENDING automatically.
    """
    previous=store.state('campaign_schedule_health') or {}
    stamp=previous.get('checked_at')
    try:last=datetime.fromisoformat(stamp) if stamp else None
    except ValueError:last=None
    continuous=bool(enabled and previous.get('enabled') and last and timedelta(0)<=at-last<=timedelta(minutes=5))
    boundary=None if continuous else at
    code='schedule_missed' if enabled else 'marketing_off_schedule'
    if boundary is not None:
        # Match native dispatch and schedule amendments: campaign before sends.
        # A separate statement after acquiring locks sees any committed override.
        with store.db() as conn:
            conn.execute("SELECT id FROM crm_campaigns WHERE audience_snapshot_id IS NOT NULL AND status IN ('SCHEDULED','SENDING') ORDER BY id FOR UPDATE").fetchall()
            conn.execute("""UPDATE crm_marketing_sends s SET status='BLOCKED',error_code=%s,updated_at=now(),lease_until=NULL
          FROM crm_template_versions v WHERE v.template_id=s.template_id AND v.version=s.template_version
          AND v.content->>'format'='campaign_delivery_v1'
          AND COALESCE((SELECT r.value->'timing'->>'mode' FROM crm_runtime_state r WHERE r.key='campaign-timing:'||s.campaign_id::text),v.content->'document'->'send_timing'->>'mode')='schedule'
          AND NOT s.test_send AND s.status IN ('PENDING','CLAIMED') AND s.due_at<=%s""",(code,boundary))
    if enabled:
        store.q("UPDATE crm_marketing_sends SET error_code='schedule_missed',updated_at=now() WHERE status='BLOCKED' AND error_code='marketing_off_schedule'")
    store.set_state('campaign_schedule_health',{'enabled':bool(enabled),'checked_at':at.isoformat()})

def overdue_reason(snapshot,row,at):
    # Native reviewed queues are admitted by schedule_gate on every worker tick.
    # Its OFF/outage checks still fail closed, but a healthy worker's own backlog
    # must not discard the tail of a large campaign five minutes after it starts.
    if snapshot.get('audience_snapshot_id'):return ''
    job=snapshot.get('schedule',{}).get(row['recipient_hash'])
    if job and at-datetime.fromisoformat(job['due_at'])>timedelta(minutes=5):return 'schedule_missed'
    return ''
