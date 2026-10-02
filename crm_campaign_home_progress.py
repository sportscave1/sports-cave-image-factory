"""Small durable progress reads, independent of campaign analytics/history."""
import logging
from crm_campaign_progress import read_progress, summarize, POLL_SECONDS, polling_seconds
from crm_campaign_home_cache import job, resolve

LOG = logging.getLogger(__name__)


def merge_progress(items, progress):
    """Never mutate cached analytics; newer durable status wins over list refreshes."""
    merged=[]
    for item in items:
        current=progress.get(str(item['id']))
        if current:
            # Evaluate elapsed time from the last durable timestamp even while
            # a refresh fails; never fabricate counters or mutate the receipt.
            current=summarize(current)
            item={**item,'status':current['status'],'delivery_status':current['status'],
                  'progress':current,'submitted':current['submitted'],'planned':current['total']}
        merged.append(item)
    return merged


def live_rows(state,store,items):
    latest=state.setdefault('campaign_home_progress',{})
    items=merge_progress(items,latest)
    ids=tuple(sorted(str(r['id']) for r in items if r.get('in_page') and
        r.get('delivery_status',r['status']) in ('SENDING','BUILDING','SCHEDULED','QUEUED')))
    if not ids:
        state['campaign_home_dispatch_active']=False
        state.setdefault('campaign_home_activity',{}).pop('progress',None)
        return items
    cadence=min(polling_seconds(r.get('progress') or r) for r in items if str(r['id']) in ids)
    key=('progress',ids)
    future=job(state,store,key,lambda:list(read_progress(store,ids).values()),ttl=cadence)
    result,status=resolve(state,store,key,future)
    state.setdefault('campaign_home_activity',{})['progress']=status
    if result is not None:
        for row in result:
            identity=str(row['id'])
            previous=latest.get(identity)
            # One registered future per identity set, plus timestamp protection
            # when switching views while another set is still in flight.
            if previous and previous.get('last_progress_at') and row.get('last_progress_at'):
                if row['last_progress_at'] < previous['last_progress_at']:continue
            if previous != row:
                LOG.info('campaign_progress campaign_id=%s send_id=%s job_status=%s total=%s processed=%s submitted=%s skipped=%s failed=%s held=%s worker_started_at=%s last_progress_at=%s completed_at=%s',
                    identity,row.get('send_id'),row['status'],row['total'],row['processed'],row['submitted'],row['skipped'],row['failed'],row['held'],row.get('worker_started_at'),row.get('last_progress_at'),row.get('sent_at'))
                if row['complete'] and not (previous or {}).get('complete'):
                    for group in ('counts','delivery'):
                        state.get('campaign_home_cache',{}).pop((store.connect,(group,)),None)
            latest[identity]=row
        poll_count=state.get('campaign_home_status_poll_count',0)
        if state.get('campaign_home_status_future') is not future:
            state['campaign_home_status_future']=future
            state['campaign_home_status_poll_count']=poll_count+1
            LOG.info('campaign_progress status_poll_count=%s visible_sends=%s',poll_count+1,len(ids))
    items=merge_progress(items,latest)
    state['campaign_home_dispatch_active']=any(r.get('in_page') and r['status'] in ('SENDING','QUEUED','BUILDING','SCHEDULED') and polling_seconds(r.get('progress') or r)==POLL_SECONDS for r in items)
    return items


def accepted_home(state,receipt,editor):
    """Receipt follows DB commit; retain the composer and seed only known fields."""
    from crm_logic import now
    doc=editor['document']
    state['campaign_home_accepted']={
        'id':receipt['id'],'name':editor['name'],'subject':doc.get('content',{}).get('subject',''),
        'status':receipt['status'],'delivery_status':receipt['status'],
        'market':doc.get('market'),'updated_at':now(),'recipients':receipt.get('recipients'),
        'in_page':True,'version':editor.get('version'),'archived_at':None,'deletable':False}
    state['campaign_home_notice']={'SCHEDULED':'Campaign scheduled','SENT':'Campaign already sent',
        'PAUSED':'Campaign paused','CANCELLED':'Campaign cancelled'}.get(receipt['status'],'Campaign queued for sending')
    # Navigation must not retain a Draft-only filter that hides the accepted job.
    for key in ('campaign_home_tab','campaign_home_last_tab','campaign_home_search',
                'campaign_home_market','campaign_home_status','campaign_home_sort','campaign_home_filters'):
        state.pop(key,None)
    state['campaign_home_offset']=0
    for key in ('campaign_send_dialog_id','campaign_send_progress','campaign_progress_cache','campaign_pending_open'):
        state.pop(key,None)
