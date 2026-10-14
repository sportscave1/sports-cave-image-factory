"""One serial cloud worker in the existing web service; disabled by default."""
import logging
import os
import threading
import time

from auto_editions_cloud import DropboxAssets,PreparationBlocked,confirmed_job,execute
from auto_editions_jobs import Jobs
from auto_editions_store import Preparations

LOG=logging.getLogger(__name__)
_thread=None
_lock=threading.Lock()
_wake=threading.Event()


def enabled():return os.getenv('SPORTS_CAVE_AUTO_EDITIONS_V6','').lower()=='true'


def stores():
    from auto_editions_connections import connect
    return Preparations(connect),Jobs(connect)


def storage():
    import dropbox_integration as dbx
    from files_upload_api import _dropbox_context
    return DropboxAssets(_dropbox_context()['access_token'],dbx)


def context(allocation_id):
    registry,_=stores()
    unit,mapping=registry.unit(allocation_id)
    if not mapping:raise PreparationBlocked('Link the PSD using the existing Add workflow first.')
    assets=storage()
    metadata=assets.integration.psd_open_metadata(assets.token,mapping['dropbox_file_id'],include_preview=False)
    return unit,mapping,metadata,assets


def job_for(allocation_id):
    from concurrent.futures import ThreadPoolExecutor
    registry,_=stores()
    # Independent authenticated reads may overlap; all identity/approval checks
    # still complete before a job can be enqueued or an output accepted.
    with ThreadPoolExecutor(max_workers=2,thread_name_prefix='edition-identity') as pool:
        allocation=pool.submit(registry.unit,allocation_id)
        assets=storage()
        unit,mapping=allocation.result()
        if not mapping:raise PreparationBlocked('Link the PSD using the existing Add workflow first.')
        preparation=pool.submit(registry.for_unit,unit)
        metadata=assets.integration.psd_open_metadata(assets.token,mapping['dropbox_file_id'],include_preview=False)
        return confirmed_job(unit,mapping,metadata,preparation.result()),assets


def run_one(jobs,resolver=job_for):
    started=time.monotonic()
    record=jobs.claim()
    if not record:return False
    result=None
    saved=False
    timings={'claim_database_ms':round((time.monotonic()-started)*1000,3)}
    if record.get('attempts')==1 and record.get('created_at') and record.get('updated_at'):
        timings['initial_queue_wait_ms']=round(max(0,(record['updated_at']-record['created_at']).total_seconds()*1000),3)
    try:
        phase=time.monotonic()
        current,assets=resolver(record['payload']['identity']['allocation_id'])
        timings['worker_identity_ms']=round((time.monotonic()-phase)*1000,3)
        if current['id']!=record['id']:raise PreparationBlocked('source_changed')
        current['archive_labels']=record['payload'].get('archive_labels',current.get('archive_labels',{}))
        result=execute(current,assets)
        # Fence changes made while image transfer/rendering was in progress.
        phase=time.monotonic();verified,_=resolver(current['identity']['allocation_id'])
        timings['final_identity_ms']=round((time.monotonic()-phase)*1000,3)
        if verified['id']!=current['id']:raise PreparationBlocked('source_changed')
        result['timings'].update(timings)
        result['timings'].update(record['payload'].get('request_timings',{}))
        phase=time.monotonic();jobs.finish(record['id'],record['lease_token'],result=result)
        LOG.info('AUTO_EDITIONS_TIMINGS job=%s finish_database_ms=%.3f elapsed_ms=%.3f stages=%s',
                 record['id'],(time.monotonic()-phase)*1000,(time.monotonic()-started)*1000,result['timings'])
        saved=True
    except PreparationBlocked:
        jobs.finish(record['id'],record['lease_token'],error_code='source_changed')
    except (ValueError,KeyError):
        jobs.finish(record['id'],record['lease_token'],error_code='asset_invalid')
    except Exception:
        jobs.finish(record['id'],record['lease_token'],error_code='worker_unavailable')
        if record['attempts']<3:jobs.retry(record['id'],'cloud-worker')
        LOG.warning('AUTO_EDITIONS retryable worker failure job=%s',record['id'])
    finally:
        if result and not saved:
            try:assets.discard_cache(record['id'],result['output'])
            except Exception:LOG.warning('AUTO_EDITIONS failed-result cache cleanup needs retry job=%s',record['id'])
    return True


def _loop():
    last_cleanup=0
    while enabled():
        try:
            _,jobs=stores()
            if time.monotonic()-last_cleanup>60:
                expired=jobs.expired()
                if expired:
                    assets=storage()
                    for row in expired:
                        assets.discard_cache(row['id'],row['result']['output'])
                        jobs.forget_expired_output(row['id'])
                last_cleanup=time.monotonic()
            if run_one(jobs):continue
        except Exception:
            LOG.warning('AUTO_EDITIONS queue temporarily unavailable')
        _wake.wait(15);_wake.clear()


def start_worker():
    global _thread
    if not enabled():return
    with _lock:
        if not _thread or not _thread.is_alive():
            _thread=threading.Thread(target=_loop,name='auto-editions-v6',daemon=True)
            _thread.start()
    _wake.set()


def download_links(rows):
    if not enabled():return {}
    try:
        import psd_directory
        registry,jobs=stores()
        def variant(value):return str(value or '').removeprefix('gid://shopify/ProductVariant/')
        raw_index=registry.index()
        index={(product,variant(v)):(raw_index[(product,v)] if isinstance(raw_index,dict) else None) for product,v in raw_index}
        links={}
        for row in rows:
            allocation=str(row.get('edition_order_id') or row.get('id') or '')
            key=(psd_directory.product_id(row),variant(row.get('shopify_variant_id') or row.get('variant_id')))
            if key not in index:key=(key[0],'*')
            if not allocation.isdigit() or key not in index:continue
            if index[key] is not None and int(allocation) not in index[key]:continue
            links[allocation]='/auto-editions/download?allocation_id='+allocation+'#Download JPG'
        summaries=jobs.summaries(list(links)) if jobs else {}
        for key,row in summaries.items():
            if row['status']=='Ready':
                # Opening performs current permission/allocation and exact saved
                # revision checks. Listing Orders must not serially query Dropbox
                # once for every archived row before the table becomes usable.
                links[key]='/auto-editions/open?allocation_id='+key+'&job_id='+row['id']+'#Open'
            elif row['status'] in ('Queued','Generating'):links[key]='/auto-editions/download?allocation_id='+key+'#Generating'
            elif row['status']=='Blocked':links[key]='/auto-editions/download?allocation_id='+key+'#Retry'
        return links
    except Exception:
        return {} # Existing V4 availability remains intact if V6 storage is down.


def link_label(url):
    return {'Retry Open':'Retry Open','Open':'Open','View':'Open','Generating':'Generating...','Retry':'Retry'}.get(url.rsplit('#',1)[-1],'Download JPG')
