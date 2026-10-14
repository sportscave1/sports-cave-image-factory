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
    import supabase_backend
    return Preparations(supabase_backend.connect),Jobs(supabase_backend.connect)


def storage():
    import dropbox_integration as dbx
    return DropboxAssets(dbx.resolve_server_auth()['access_token'],dbx)


def context(allocation_id):
    registry,_=stores()
    unit,mapping=registry.unit(allocation_id)
    if not mapping:raise PreparationBlocked('Link the PSD using the existing Add workflow first.')
    assets=storage()
    metadata=assets.integration.psd_open_metadata(assets.token,mapping['dropbox_file_id'],include_preview=False)
    return unit,mapping,metadata,assets


def job_for(allocation_id):
    unit,mapping,metadata,assets=context(allocation_id)
    registry,_=stores()
    return confirmed_job(unit,mapping,metadata,registry.for_unit(unit)),assets


def run_one(jobs,resolver=job_for):
    record=jobs.claim()
    if not record:return False
    result=None
    saved=False
    try:
        current,assets=resolver(record['payload']['identity']['allocation_id'])
        if current['id']!=record['id']:raise PreparationBlocked('source_changed')
        result=execute(current,assets)
        # Fence changes made while image transfer/rendering was in progress.
        verified,_=resolver(current['identity']['allocation_id'])
        if verified['id']!=current['id']:raise PreparationBlocked('source_changed')
        jobs.finish(record['id'],record['lease_token'],result=result)
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
        registry,_=stores()
        def variant(value):return str(value or '').removeprefix('gid://shopify/ProductVariant/')
        index={(product,variant(v)) for product,v in registry.index()}
        return {str(r.get('edition_order_id') or r.get('id')):
                '/auto-editions/download?allocation_id='+str(r.get('edition_order_id') or r.get('id'))+'#Download JPG'
                for r in rows if str(r.get('edition_order_id') or r.get('id') or '').isdigit()
                and (psd_directory.product_id(r),
                     variant(r.get('shopify_variant_id') or r.get('variant_id'))) in index}
    except Exception:
        return {} # Existing V4 availability remains intact if V6 storage is down.
