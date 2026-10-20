"""One bounded per-job measurement record; nested stages are never added."""
import hashlib
import math


def number(value):
    return round(value,6) if type(value) in (int,float) and math.isfinite(value) and 0<=value<=10**12 else None


def summary(row,result=None):
    supplied=result is not None
    result=result or {};local=row.get('timings',{});server=row.get('server_timings',{})
    attempts=row.get('transfer_attempts',[]);last=attempts[-1] if attempts else {}
    totals=row.get('transfer_totals',{})
    correlation=hashlib.sha256(str(row['folder'].name).encode()).hexdigest()[:32]
    candidate=last.get('correlation_id',correlation)
    import re
    if re.fullmatch('[a-f0-9]{32}',str(candidate)):correlation=candidate
    def fields(source,names):return {key:number(source.get(key)) for key in names}
    completion=('Cloud Ready' if result.get('status')=='Cloud Ready' else 'Uploaded, verifying') if supplied else row.get('completion_state')
    if completion not in ('Cloud Ready','Uploaded, verifying'):
        completion='Recovering' if row.get('status')=='Recovering' else 'Failed' if row.get('status')=='Blocked' else 'Cancelled' if row.get('status')=='Cancelled' else 'In progress'
    return dict(version=1,correlation_id=correlation,completion=completion,
        queue=dict(wait_seconds=number(local.get('queue_wait_seconds')),claim_request_seconds=number(local.get('claim_seconds'))),
        source={**fields(local,('psd_retrieval_seconds','source_bytes','source_transfer_bytes')),
                'verified_cache_hit':local.get('source_reused') if type(local.get('source_reused')) is bool else None},
        preparation=fields(local,('prepare_validate_seconds','source_checksums_seconds','source_staging_seconds',
            'inspection_seconds','native_preflight_seconds','photoshop_prepare_seconds','icc_preservation_seconds',
            'pixel_verification_seconds','package_build_seconds','package_checksum_seconds')),
        transfer=dict(payload_bytes=number(totals.get('payload_bytes')),bulk_requests=number(totals.get('bulk_requests')),
            server_confirmed_bytes=number(last.get('server_received_bytes')),resumed_bytes=number(last.get('resumed_bytes')),
            body_stream_seconds=number(totals.get('body_stream_seconds')),
            allowance_wait_seconds=number(totals.get('allowance_wait_seconds')),
            disk_read_seconds=number(totals.get('disk_read_seconds')),
            **fields(last,('slot_wait_seconds','pause_wait_seconds','calibration_wait_seconds','verification_seconds','client_confirmation_seconds'))),
        server=fields(server,('handler_total_seconds','body_receive_seconds','first_body_to_complete_seconds','authentication_context_seconds','validation_seconds','dropbox_upload_seconds',
            'prepared_upload_bytes','durable_package_download_seconds','complete_package_hash_seconds',
            'source_revalidation_seconds','database_save_seconds','database_checkpoint_seconds',
            'technical_verification_seconds','automatic_visual_seconds','final_status_seconds')),
        unknown=['Queue wait unless independently recorded','Proxy buffering and connection establishment',
                 'Unattributed transport time is not internet capacity'],
        accounting='Application payload bytes. Nested/overlapping stages must not be added; no cross-process clock subtraction.')
