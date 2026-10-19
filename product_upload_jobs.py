"""Bounded application-thread jobs, following the existing PostingJobs pattern.

Workers never touch Streamlit/session state. The intake/source and preparation
receipt remain authoritative; process loss is retryable, never fake success.
"""
from concurrent.futures import ThreadPoolExecutor, CancelledError
from copy import deepcopy
from threading import RLock, Lock
from time import monotonic
import uuid
from pathlib import Path
import logging


class Jobs:
    def __init__(self):
        self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='product-upload')
        self.lock=RLock();self.preparation=Lock();self.jobs={}

    def submit(self,key,actor,operation,fingerprint,work):
        identity=(str(actor),str(key),operation)
        with self.lock:
            old=self.jobs.get(identity)
            if old and old['fingerprint']==fingerprint and old['state'] in ('Queued','Running'):return self.snapshot(key,actor,operation)
            if old and old['state'] in ('Queued','Running'):
                raise ValueError('This design already has work running. Wait or change the selected PSD.')
            for item,job in list(self.jobs.items()):
                if job['state'] not in ('Queued','Running') and job['future'].done() and (len(self.jobs)>=16 or monotonic()-job['submitted']>1800):
                    del self.jobs[item]
            if len(self.jobs)>=16:raise ValueError('Artwork processing is busy. Retry shortly; no duplicate job was queued.')
            token=uuid.uuid4().hex
            job=dict(token=token,fingerprint=deepcopy(fingerprint),state='Queued',stage='Waiting to start',submitted=monotonic(),stages=[],completed=0,total=None,previews=[])
            self.jobs[identity]=job
            def progress(stage,completed=None,total=None,preview=None):
                with self.lock:
                    if self.jobs.get(identity) is not job or job['state']=='Cancelled':raise CancelledError()
                    if stage!=job['stage']:
                        job['stages'].append(dict(stage=stage,elapsed_ms=round((monotonic()-job['submitted'])*1000,2)))
                    job.update(stage=stage,completed=completed,total=total)
                    if preview:
                        job['previews'].append(str(preview))
                        job.setdefault('asset_events',[]).append(dict(completed=completed,elapsed_ms=round((monotonic()-job['submitted'])*1000,2)))
            def run():
                result=None
                try:
                    with self.lock:
                        if job['state']=='Cancelled':raise CancelledError()
                        job['state']='Running';job['started_ms']=round((monotonic()-job['submitted'])*1000,2)
                    result=work(progress)
                    with self.lock:
                        if self.jobs.get(identity) is not job or job['state']=='Cancelled':raise CancelledError()
                        job.update(state='Ready',stage='Ready',result=result,elapsed_ms=round((monotonic()-job['submitted'])*1000,2))
                        logging.getLogger(__name__).info('product_upload_job_ready workflow=%s operation=%s elapsed_ms=%s stages=%s',key,operation,job['elapsed_ms'],job['stages'])
                except CancelledError:
                    with self.lock:job['state']='Cancelled'
                    if isinstance(result,dict) and result.get('_product_upload_intake'):
                        from product_upload_mockups import release_transient
                        release_transient(result)
                except Exception as error:
                    from product_upload_artwork import PreparationError
                    # Arbitrary SDK/provider messages must never reach the UI.
                    message=str(error) if isinstance(error,(PreparationError,ValueError)) else 'Processing failed. Retry; the selected PSD and product details are retained.'
                    logging.getLogger(__name__).error('product_upload_job_failed workflow=%s operation=%s error_type=%s',key,operation,type(error).__name__)
                    with self.lock:job.update(state='Failed',stage='Error',error=message,elapsed_ms=round((monotonic()-job['submitted'])*1000,2))
            try:job['future']=self.pool.submit(run)
            except Exception:
                self.jobs.pop(identity,None);raise
            return self.snapshot(key,actor,operation)

    def snapshot(self,key,actor,operation):
        with self.lock:
            job=self.jobs.get((str(actor),str(key),operation))
            if not job:return None
            return deepcopy({k:v for k,v in job.items() if k not in ('future','result')})

    def result(self,key,actor,operation,token):
        with self.lock:
            job=self.jobs.get((str(actor),str(key),operation))
            return job.get('result') if job and job['state']=='Ready' and job['token']==token else None

    def cancel(self,key,actor):
        with self.lock:
            for identity,job in self.jobs.items():
                if identity[:2]==(str(actor),str(key)) and job['state'] in ('Queued','Running'):
                    job['state']='Cancelled'
                    job['future'].cancel()


JOBS=Jobs()


def prepare(connect,key,actor,provider_factory):
    from product_upload_intake import Intakes
    from product_upload_artwork import prepare as process,source,PreparationBusyError
    row=Intakes(connect).read(key,actor)
    if not row:raise ValueError('Select an exact Dropbox PSD first.')
    def work(progress):
        with JOBS.preparation:
            import time
            deadline=monotonic()+300
            while True:
                progress('Checking prepared artwork')
                try:return process(connect,None,key,actor,provider_factory=provider_factory,progress=progress)
                except PreparationBusyError:
                    progress('Waiting for source preparation')
                    if monotonic()>deadline:raise ValueError('Source preparation is still active. Retry shortly; the selected PSD is retained.')
                    time.sleep(.5)
    return JOBS.submit(key,actor,'prepare',source(row),work)


def generate(connect,row,actor,name,sport,provider_factory,base_dir,semaphore,prompts,*,reset_exports=False,finalize=None):
    from product_upload_artwork import source,prepared,current
    import image_factory as factory
    key=str(row['id']);identity=source(row)
    def work(progress):
        result=None;created_run=None
        progress('Waiting for renderer')
        with semaphore:
            try:
                progress('Checking prepared artwork')
                factory.cleanup_stale_temp_runs()
                if reset_exports:
                    from product_upload_intake import Intakes
                    with Intakes(connect).locked(key,actor) as (value,cur):
                        if value['data'].get('product_gid'):raise ValueError('This PSD is already linked to Shopify. Start a separate design workflow.')
                        value['data'].update(mockups_exported=False,mockups_context=None,copied=False,lookup='',choices=[])
                provider=provider_factory()
                completed=0
                def asset(record,job,**kwargs):
                    nonlocal completed,created_run
                    created_run=kwargs.get('run_dir')
                    completed+=1
                    progress('Generating mockups',completed,5,record['preview_path'])
                with prepared(row,connect,provider) as (ready_row,folder):
                    progress('Generating mockups',0,5)
                    result=factory.generate_product_images(name,sport,folder/'artwork.png',base_dir=base_dir,
                        output_root=factory.create_temp_run_parent(),final_prompt_items=prompts(name,sport),
                        asset_completed_callback=asset)
                progress('Checking completed mockups',5,5)
                if finalize:
                    progress('Finalising mockups')
                    result=finalize(result)
                current(provider,ready_row)
                from product_upload_intake import Intakes
                latest=Intakes(connect).read(key,actor)
                if not latest or source(latest)!=identity:raise ValueError('Selected PSD changed. Reselect it before generating mockups.')
                if len(result['assets'])!=5 or any(not Path(a[field]).is_file() for a in result['assets'] for field in ('review_path','preview_path','jpg_path','webp_path')):raise ValueError('Mockup outputs are incomplete. Retry generation.')
                result.update(_product_upload_intake=key,_product_upload_actor_id=str(actor),_product_upload_source_hash=row['data']['source']['content_hash'])
                return result
            except BaseException:
                if result or created_run:
                    result=result or dict(run_dir=created_run)
                    result['_product_upload_intake']=key
                    from product_upload_mockups import release_transient
                    release_transient(result)
                raise
    return JOBS.submit(key,actor,'generate',dict(source=identity,name=name,sport=sport),work)
