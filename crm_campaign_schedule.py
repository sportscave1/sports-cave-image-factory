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

def validate(value):
    if not isinstance(value,dict) or value.get('mode') not in ('now','schedule'):raise ValueError('Choose Send now or Schedule.')
    if value['mode']=='now':
        if set(value)!={'mode'}:raise ValueError('Invalid immediate timing.')
        return
    if set(value)!={'mode','date','time'}:raise ValueError('Choose a schedule date and local time.')
    try:
        datetime.strptime(value['date'],'%Y-%m-%d');datetime.strptime(value['time'],'%H:%M')
    except (ValueError,TypeError):raise ValueError('Choose a valid schedule date and local time.') from None

def due(value,zone):
    validate(value)
    naive=datetime.strptime(value['date']+' '+value['time'],'%Y-%m-%d %H:%M')
    local=naive.replace(tzinfo=ZoneInfo(zone),fold=0)
    utc=local.astimezone(timezone.utc)
    # Never silently shift a nonexistent spring-forward wall time.
    if utc.astimezone(ZoneInfo(zone)).replace(tzinfo=None)!=naive:raise ValueError('Selected local time does not exist during daylight-saving change. Choose another time.')
    return utc  # Ambiguous fall-back time deliberately uses the first occurrence.

def plan(doc,state,at):
    timing=doc.get('send_timing',{'mode':'now'});validate(timing)
    if timing['mode']=='now':return {}
    jobs={}
    for r in state['recipients']:
        zone,reason=resolve(state['profiles'][r['id']]);instant=due(timing,zone)
        if instant<=at:raise ValueError('Schedule missed — reschedule required. Choose a future local date and time for every recipient.')
        jobs[r['hash']]={'timezone':zone,'reason':reason,'due_at':instant.isoformat()}
    return jobs

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
        store.q("""UPDATE crm_marketing_sends s SET status='BLOCKED',error_code=%s,updated_at=now(),lease_until=NULL
          FROM crm_template_versions v WHERE v.template_id=s.template_id AND v.version=s.template_version
          AND v.content->>'format'='campaign_delivery_v1' AND v.content->'document'->'send_timing'->>'mode'='schedule'
          AND NOT s.test_send AND s.status IN ('PENDING','CLAIMED') AND s.due_at<=%s""",(code,boundary))
    if enabled:
        store.q("UPDATE crm_marketing_sends SET error_code='schedule_missed',updated_at=now() WHERE status='BLOCKED' AND error_code='marketing_off_schedule'")
    store.set_state('campaign_schedule_health',{'enabled':bool(enabled),'checked_at':at.isoformat()})

def overdue_reason(snapshot,row,at):
    job=snapshot.get('schedule',{}).get(row['recipient_hash'])
    if job and at-datetime.fromisoformat(job['due_at'])>timedelta(minutes=5):return 'schedule_missed'
    return ''
