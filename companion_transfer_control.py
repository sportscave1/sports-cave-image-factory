"""Transfer settings on existing authenticated worker control/host channels."""
import json
import re
import uuid
from companion_transfer import settings


def identity(instance):
    if not isinstance(instance,str) or not re.fullmatch('[a-f0-9]{24}',instance):
        raise ValueError('Choose a registered companion instance.')
    return 'companion-transfer:'+instance


def requested(connect, instance):
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT detail FROM auto_edition_onboarding_audit
            WHERE product_gid=%s AND event='transfer_settings_requested' ORDER BY id DESC LIMIT 1""",(identity(instance),))
        row=cur.fetchone()
        return row['detail'] if row else None


def set_requested(connect, instance, value, actor):
    value=settings(value); key=identity(instance)
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT payload FROM auto_edition_worker_heartbeats WHERE component='Companion'
            AND instance_id=%s AND seen_at>now()-interval '150 seconds'""",(instance,))
        row=cur.fetchone()
        if not row or (row['payload'].get('transfer_control') or {}).get('capability') not in (1,2):
            raise ValueError('Companion transfer controls unavailable; update/reconnect the companion first.')
        command=dict(revision=uuid.uuid4().hex,settings=value)
        cur.execute("""INSERT INTO auto_edition_onboarding_audit(product_gid,actor_id,event,detail)
            VALUES(%s,%s,'transfer_settings_requested',%s::jsonb) RETURNING id""",(key,actor,json.dumps(command)))
        audit_id=cur.fetchone()['id']
        command['revision']='request_'+str(audit_id)
        cur.execute('UPDATE auto_edition_onboarding_audit SET detail=%s::jsonb WHERE id=%s',(json.dumps(command),audit_id))
    return command


def evidence(value):
    # No arbitrary dictionaries/messages, URLs or credentials in health payloads.
    if not isinstance(value,dict) or set(value)!={'capability','revision','settings','effective_mbps','protection','pause_state','transfer','active_upload','active_download'}:
        raise ValueError('Bounded transfer evidence required.')
    if any(type(value[k]) is not bool for k in ('active_upload','active_download')):raise ValueError('Invalid active transfer flags.')
    if value['capability'] not in (1,2) or not re.fullmatch('[a-zA-Z0-9_-]{1,64}',str(value['revision'])):
        raise ValueError('Unsupported transfer protocol.')
    settings(value['settings'])
    if value['protection'] not in ('Calibration needed','Limited','Maximum speed (uncapped)') or value['pause_state'] not in ('Running','Transfers paused','Pause after current transfer','Paused at chunk boundary','Pausing at chunk boundary'):
        raise ValueError('Invalid transfer state.')
    transfer=value['transfer']
    numbers={'confirmed_bytes','progress_bytes','transfer_seconds','verification_seconds','resumed_bytes','retries','pause_wait_seconds','calibration_wait_seconds','disk_read_seconds','unattributed_transport_response_seconds','total_bytes','disk_bytes','transport_bytes','server_received_bytes','slot_wait_seconds','allowance_wait_seconds','payload_bytes_per_second','eta_seconds','connection_seconds','body_first_handoff_seconds','body_last_handoff_seconds','request_preparation_seconds','request_seconds','response_after_last_handoff_seconds','client_confirmation_seconds'}
    booleans={'resumable'}
    strings={'request_id','correlation_id','state','connection_observability','failure_class'}
    if not isinstance(transfer,dict) or set(transfer)-numbers-strings-booleans or len(json.dumps(value))>4096:
        raise ValueError('Bounded transfer counters required.')
    import math
    for key,val in {**transfer,'effective_mbps':value['effective_mbps']}.items():
        if key in booleans:
            if type(val) is not bool:raise ValueError('Invalid resumable flag.')
        elif key in strings:
            if not isinstance(val,str) or not re.fullmatch(r'[A-Za-z0-9 _,/().-]{1,96}',val):raise ValueError('Invalid transfer label.')
        elif val is not None and (type(val) not in (int,float) or not math.isfinite(val) or not 0<=val<=10**12):
            raise ValueError('Invalid transfer counter.')
    return value
