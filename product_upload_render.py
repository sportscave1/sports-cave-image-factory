"""Pre-Shopify artwork rendering on the existing exclusive Photoshop host.

Intake-owned JSON checkpoints; no product, mapping, allocation or queue reset.
Only a requested render is claimable. Expired native ownership is never stolen.
"""
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from product_upload_intake import Intakes


def identity(row):
    m = row['data']['source']
    return dict(template_id='product-upload:' + str(row['id']), file_id=m['id'],
                revision=m['rev'], content_hash=m['content_hash'])


class Renders:
    def __init__(self, connect):
        self.store = Intakes(connect)

    def request(self, key, actor, *, retry=False):
        with self.store.locked(key, actor) as (row, cur):
            if not row['data'].get('basic_validated'):
                raise ValueError('Finish saving and validating the PSD first.')
            previous = row['data'].get('mockup_render') or {}
            if previous.get('state') in ('Queued', 'Rendering', 'Ready'):
                return previous
            if previous.get('state') == 'Failed':
                if not retry or not previous.get('retryable'):
                    raise ValueError(previous.get('reason') or 'Review the retained render failure before retrying.')
                if previous.get('attempt',1)>=3:raise ValueError('Three native attempts retained. Review this PSD before further processing.')
            value = dict(state='Queued', source=identity(row), version=1,attempt=previous.get('attempt',0)+1,history=previous.get('history',[])+([previous] if previous else []))
            row['data']['mockup_render'] = value
            return value

    def claim(self, actor, host_id=None):
        from product_upload_services import enabled
        if not enabled():return None
        with self.store.connect() as conn, conn.cursor() as cur:
            cur.execute('LOCK TABLE auto_edition_onboarding IN SHARE ROW EXCLUSIVE MODE')
            from worker_health import control
            if control(cur)['paused']: return None
            cur.execute("SELECT 1 FROM auto_edition_onboarding WHERE lease_until>now() AND (status='Preparing' OR to_jsonb(auto_edition_onboarding)->'replacement'->>'stage'='Preparing') LIMIT 1")
            if cur.fetchone():return None
            # One in-flight render per authenticated host account. A reconnect
            # gets the same operation/token, not a second native operation.
            cur.execute("""SELECT * FROM product_upload_intakes WHERE actor_id=%s
                AND data->'mockup_render'->>'state' IN ('Queued','Rendering')
                ORDER BY CASE WHEN data->'mockup_render'->>'state'='Rendering' THEN 0 ELSE 1 END, created_at
                LIMIT 1 FOR UPDATE SKIP LOCKED""", (str(actor),))
            row = cur.fetchone()
            if not row: return None
            value = row['data']['mockup_render']
            if value.get('host_id') and value['host_id'] != host_id: return None
            if value['source'] != identity(row): raise ValueError('Render source changed.')
            if value['state'] == 'Queued':
                value.update(state='Rendering', host_id=host_id, token=secrets.token_urlsafe(32),
                             claimed_at=datetime.now(timezone.utc).isoformat())
                cur.execute('UPDATE product_upload_intakes SET data=%s::jsonb,updated_at=now() WHERE id=%s',
                            (json.dumps(row['data']), row['id']))
            return dict(id=str(row['id']), source=value['source'], metadata=row['data']['source'], token=value['token'], attempt=value.get('attempt',1))

    def finish(self, key, actor, token, receipt, path, provider):
        from PIL import Image
        from auto_editions_colour_source import profile_info
        with self.store.locked(key, actor) as (row, cur):
            value = row['data'].get('mockup_render') or {}
            if not secrets.compare_digest(str(value.get('token', '')), str(token)):
                raise PermissionError('The exact render lease is required.')
            if value.get('state') == 'Ready': return value
            if value.get('state') != 'Rendering' or value.get('source') != identity(row) or receipt.get('source') != identity(row):
                raise ValueError('Render no longer belongs to this source.')
            if receipt.get('source_unchanged') is not True or receipt.get('owned_document_closed') is not True:
                raise ValueError('Native source preservation and document cleanup must be verified.')
            if not receipt.get('colour') or not receipt.get('native_render'):
                raise ValueError('Native colour evidence is required; embedded PSD previews are not accepted.')
            if Path(path).stat().st_size > 20*1024**2: raise ValueError('Rendered artwork exceeds Mockups limits.')
            import auto_editions as ae
            if ae.file_hash(path) != receipt.get('render_sha256'):
                raise ValueError('Rendered bytes differ from the native receipt.')
            with Image.open(path) as image:
                if image.format != 'PNG' or max(image.size) > 2000 or min(image.size) < 1:
                    raise ValueError('A bounded native PNG render is required.')
                info = profile_info(image.info.get('icc_profile', b''))
                if 'srgb' not in info['description'].lower(): raise ValueError('The web render must have a verified sRGB profile.')
                image.verify()
            source = provider.metadata_if_present(row['data']['source']['id'])
            if not source or any(source.get(k) != row['data']['source'].get(k) for k in ('id','rev','content_hash')):
                raise ValueError('Original PSD identity changed during rendering.')
            output = provider.save_render(str(row['id']), path)
            value.update(state='Ready', output=output, receipt=receipt)
            return value

    def fail(self, key, actor, token, reason, retryable=False):
        with self.store.locked(key, actor) as (row, cur):
            value = row['data'].get('mockup_render') or {}
            if not secrets.compare_digest(str(value.get('token', '')), str(token)):
                raise PermissionError('The exact render lease is required.')
            if value.get('state') != 'Ready':
                value.update(state='Failed', reason=str(reason)[:500],retryable=retryable is True)


async def host(request):
    """Existing preparation host authentication and transfer manager protections."""
    from auto_editions_onboarding_api import preparation_actor,host_health
    import files_upload_api as files
    from product_upload_api import connect, Dropbox, failure, HEADERS
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse
    import tempfile
    try:
        if not request.headers.get('x-sports-cave-preparation-host'):
            raise PermissionError('The existing scoped preparation host is required.')
        user = await preparation_actor(request)
        op = request.path_params['render_action']
        renders = Renders(connect)
        if op == 'claim':
            body=await files._json_body(request)
            await run_in_threadpool(host_health,request,body.pop('health',None))
            if body != {}: raise ValueError('Render claims use authoritative intake identities.')
            job = await run_in_threadpool(renders.claim, user['id'], __import__('hashlib').sha256(request.headers['x-sports-cave-preparation-host'].encode()).hexdigest())
            if job:
                auth = await run_in_threadpool(files._dropbox_context)
                meta = await run_in_threadpool(files.dropbox_integration.psd_open_metadata, auth['access_token'], job['source']['file_id'], include_preview=False)
                if any(meta.get(k) != job['metadata'].get(k) for k in ('id','rev','content_hash')):
                    await run_in_threadpool(renders.fail,job['id'],user['id'],job['token'],'The requested PSD revision changed. Select the current original PSD again.')
                    raise ValueError('The requested PSD revision changed.')
                grant = files.NATIVE_TRANSFER_MANAGER.create_psd(access_token=auth['access_token'], root_path=auth['root_path'], user=user, metadata=meta)
                job['grant'] = dict(base_url=str(request.base_url).rstrip('/'), ticket=grant.ticket, secret=grant.secret)
            return JSONResponse(dict(job=job), headers=HEADERS)
        if op == 'fail':
            body = await files._json_body(request)
            await run_in_threadpool(renders.fail, body['id'], user['id'], body['token'], body['reason'], body.get('retryable',False))
            return JSONResponse(dict(ok=True), headers=HEADERS)
        if op != 'complete': raise ValueError('Unknown render action.')
        receipt = json.loads(request.headers.get('x-render-receipt', '{}'))
        with tempfile.TemporaryDirectory(prefix='product-render-') as folder:
            path = Path(folder)/'render.png'
            length = 0
            with path.open('xb') as output:
                async for block in request.stream():
                    length += len(block)
                    if length > 20*1024**2: raise ValueError('Render exceeds the bounded transfer limit.')
                    output.write(block)
            provider = await run_in_threadpool(Dropbox)
            await run_in_threadpool(renders.finish, request.query_params['id'], user['id'],
                                    request.headers.get('x-render-token'), receipt, path, provider)
        return JSONResponse(dict(ok=True), headers=HEADERS)
    except Exception as error: return failure(error)


ROUTES = (('/api/product-uploads/render/{render_action}', host, ('POST',)),)
