"""Supplemental conversion-hour evidence; never infer timestamps from totals."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import re
from meta_review_benchmarks import action

HOURLY='hourly_stats_aggregated_by_advertiser_time_zone'


def load(config, identity, level, account_timezone='Australia/Sydney', now=None):
    from meta_review_live import Reader, safe_error, date_params
    now=now or datetime.now(timezone.utc)
    try:
        tz=ZoneInfo(account_timezone)
        start=now.astimezone(tz).date()-timedelta(days=3)
        rows=Reader(config,max_pages=30,seconds=45).pages(str(identity)+'/insights',{
            'level':level,'fields':level+'_id,date_start,date_stop,actions',
            'breakdowns':HOURLY,'time_increment':1,'action_report_time':'conversion',
            'use_unified_attribution_setting':'true',**date_params(start,now.astimezone(tz).date())})
        latest={}
        for row in rows:
            if not (action(row,'actions','purchase',0) or 0)>0: continue
            key=str(row.get(level+'_id') or '')
            match=re.fullmatch(r'(\d{2}):00:00 - (\d{2}):59:59',str(row.get(HOURLY) or ''))
            if not key or not match or match[1]!=match[2] or row.get('date_start')!=row.get('date_stop'):
                raise ValueError('Hourly purchase response lacks an unambiguous date/hour.')
            date=datetime.fromisoformat(row['date_start']).date()
            local=datetime.combine(date,datetime.min.time()).replace(hour=int(match[1]),tzinfo=tz)
            if local.replace(fold=0).utcoffset()!=local.replace(fold=1).utcoffset():
                raise ValueError('Purchase hour crosses an ambiguous daylight-saving transition.')
            begin=local.astimezone(timezone.utc)
            end=begin+timedelta(hours=1)
            if begin>now: raise ValueError('Meta returned a future purchase hour.')
            if key not in latest or begin>datetime.fromisoformat(latest[key]['start']):
                latest[key]={'start':begin.isoformat(),'end':min(end,now).isoformat()}
        return {'available':True,'latest':latest,'window_start':datetime.combine(start,datetime.min.time(),tz).astimezone(timezone.utc).isoformat(),
                'checked_at':now.isoformat(),'error':''}
    except Exception as error:
        return {'available':False,'latest':{},'error':safe_error(error)}


def signal(row, evidence, now=None):
    now=now or datetime.now(timezone.utc)
    benchmark=(row.get('benchmark') or {}).get('recommendation','NO DATA')
    status=row.get('effective_status') or row.get('status') or ''
    base=status if status in ('PAUSED','ARCHIVED') else benchmark
    result={'text':'Unavailable','band':'NEUTRAL','action':base}
    if not evidence or not evidence.get('available'): return result
    # Recommendations use the observation time, not aging cached evidence into STOP.
    checked=datetime.fromisoformat(evidence['checked_at'])
    if (now-checked).total_seconds()>180: return result
    key=str(row.get('ad_id') or row.get('campaign_id') or '')
    last=evidence['latest'].get(key)
    if last:
        low=max(0,(checked-datetime.fromisoformat(last['end'])).total_seconds()/3600)
        high=max(0,(checked-datetime.fromisoformat(last['start'])).total_seconds()/3600)
        band='GREEN' if high<24 else 'RED' if low>48 else 'AMBER' if low>=24 and high<=48 else 'NEUTRAL'
        result.update(text=f'≈{int(low)}–{int(high)+1}h ago',band=band)
    else:
        age=None
        if (row.get('metrics') or {}).get('purchases')==0 and row.get('start_time'):
            try:
                start=datetime.fromisoformat(row['start_time'].replace('Z','+00:00'))
                if start.tzinfo: age=(checked-start).total_seconds()/3600
            except (ValueError,TypeError): pass
        window=(checked-datetime.fromisoformat(evidence['window_start'])).total_seconds()/3600
        if age is not None and age>=0:
            band='NEUTRAL' if age<24 else 'AMBER' if age<=48 else 'RED'
            result.update(text=f'No sale yet · {int(age)}h live' if age<=48 else 'No sale yet · >48h live',band=band)
            if age<24 and status=='ACTIVE': result['action']='LEARNING'
        elif window>48 and ((row.get('metrics') or {}).get('purchases') or 0)>0:
            result.update(text='>48h · none reported',band='RED')
        else: return result
    if status=='ACTIVE':
        if result['band']=='RED': result['action']='STOP CAMPAIGN'
        elif result['band']=='AMBER' and base not in ('STOP / REPLACE','REFRESH CREATIVE','STOP CAMPAIGN'):
            result['action']='CONSIDER'
    elif status in ('PAUSED','ARCHIVED'):
        result.update(action=status,band='NEUTRAL')
    return result
