"""Admin job controls; independent tombstones cannot be overwritten by a worker."""
import json
from uuid import UUID, uuid4
import design_publish_ad as ads

PREFIX = 'ads_job_control:'


def stopped(job):
    with ads.connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT value FROM app_settings WHERE key=%s', (PREFIX+str(UUID(job)),))
        row=cur.fetchone()
    return bool(row and row['value'].get('action') in ('cancel','delete'))


def action(user, job, operation):
    from product_upload_staff_queue import can_control_queues
    if not can_control_queues(user):
        raise PermissionError('A companion administrator must control Ads jobs.')
    if operation not in ('play','cancel','delete'):
        raise ValueError('Choose Play, Cancel or Delete.')
    job=str(UUID(job))
    with ads.connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT 1 FROM product_upload_desktop WHERE singleton FOR UPDATE')
        cur.execute('SELECT value FROM app_settings WHERE key=%s FOR UPDATE', (ads.PREFIX+job,))
        row=cur.fetchone()
        if not row: raise ValueError('Ad job not found.')
        value=row['value']
        if operation=='play':
            cur.execute("SELECT 1 FROM app_settings WHERE key=%s AND updated_at > now()-interval '10 minutes'", (ads.PREFIX+'lease',))
            if cur.fetchone(): raise ValueError('The companion is finishing a step. Press Play again shortly.')
            value.pop('catalog_retry', None)
            if value.get('attachment_repair'):
                value.setdefault('attachment_repair_history', []).append(value.pop('attachment_repair'))
            if value['stage']=='complete': raise ValueError('This job already completed. Open its Posting receipt.')
            if value.get('posting_id'):
                value['stage']='posting' # Observe the same durable posting job, never submit another.
            elif value.get('folder') and ads.CHAT.fullmatch(value.get('chat_url','')):
                value.update(stage='generating',collect_only=True,resume_token=str(uuid4()),detail='Resuming saved chat and collected files')
            elif value['stage']=='opening' or value.get('folder'):
                raise ValueError('The original chat has not been confirmed. Reopen it in Edge so the companion can report its saved conversation; do not generate again.')
            else:
                value.update(stage='waiting',detail='Queued for preparation')
            # Play may resume a saved checkpoint, but cannot take another ad's slot.
            cur.execute('''SELECT 1 FROM app_settings a WHERE a.key LIKE %s AND a.key<>%s
                AND a.value->>'stage' IN ('preparing','opening','generating','posting')
                AND NOT EXISTS (SELECT 1 FROM app_settings c
                    WHERE c.key='ads_job_control:' || (a.value->>'upload')
                      AND c.value->>'action' IN ('cancel','delete')) LIMIT 1''',
                        (ads.PREFIX+'%', ads.PREFIX+job))
            if cur.fetchone() and value['stage'] != 'waiting':
                value.update(resume_stage=value['stage'], stage='waiting',
                             detail='Queued to resume after the active ad finishes or stops')
            cur.execute('UPDATE app_settings SET value=%s::jsonb,updated_at=now() WHERE key=%s',(json.dumps(value),ads.PREFIX+job))
            cur.execute('DELETE FROM app_settings WHERE key=%s',(PREFIX+job,))
            cur.execute("INSERT INTO app_settings(key,value) VALUES(%s,'true') ON CONFLICT(key) DO UPDATE SET value='true',updated_at=now()",(ads.CONTROL_KEY,))
        else:
            # A cancel cannot undo a Meta operation already accepted. Retain its receipt.
            cur.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=now()',
                        (PREFIX+job,json.dumps(dict(action=operation,actor=str(user['id'])))))
    # Invalidate only after commit, including the separate Streamlit queue view.
    from product_upload_staff_queue import _HEADER_DISPLAYS
    from companion_display import invalidate
    _HEADER_DISPLAYS.invalidate_matching(lambda _: True)
    invalidate()
    return {'id':job,'action':operation}


async def route(request):
    from files_upload_api import _request_user,_same_origin
    from product_upload_api import HEADERS,failure
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse
    try:
        if not request.headers.get('origin') or not _same_origin(request): raise PermissionError('Request origin rejected.')
        user=await run_in_threadpool(_request_user,request,required_page='Upload Companion')
        body=await request.json()
        if not isinstance(body,dict): raise ValueError('Invalid Ads action.')
        return JSONResponse(await run_in_threadpool(action,user,body.get('id',''),body.get('action')),headers=HEADERS)
    except Exception as error: return failure(error)
