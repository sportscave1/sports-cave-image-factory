"""Cookie-authenticated admin endpoint; no storefront CORS or provider secrets."""
import json
from urllib.parse import urlsplit

from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from wall_preview_analytics_api import authorize
import wall_preview_deletion as deletion
import os_accounts


async def bulk_delete(request):
    headers = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'}
    try:
        # Cookie authentication requires same-origin intent, not storefront CORS.
        origin = urlsplit(request.headers.get('origin', ''))
        if (origin.scheme, origin.netloc) != (request.url.scheme, request.url.netloc):
            raise PermissionError()
        if request.headers.get('x-wall-preview-action') != 'delete':
            raise PermissionError()
        user = await run_in_threadpool(authorize, request)
        if not os_accounts.is_admin(user):
            raise PermissionError()
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 4096:
                return JSONResponse({'error': 'Request too large'}, status_code=413, headers=headers)
        payload = json.loads(body)
        if not isinstance(payload, dict) or payload.get('confirmed') is not True:
            raise ValueError()
        ids = deletion.validate_ids(payload.get('preview_ids'))
        results = await run_in_threadpool(deletion.bulk_delete, ids, user=user)
        return JSONResponse({'results': results}, status_code=207 if any(r['status']=='failed' for r in results) else 200, headers=headers)
    except PermissionError:
        return JSONResponse({'error': 'Administrator access and same-origin confirmation required.'}, status_code=403, headers=headers)
    except (ValueError, TypeError):
        return JSONResponse({'error': 'Confirm 1–24 valid preview IDs.'}, status_code=400, headers=headers)
    except deletion.WallPreviewStoreError as error:
        return JSONResponse({'error': str(error)}, status_code=409, headers=headers)
    except Exception:
        return JSONResponse({'error': 'Deletion unavailable. Retry safely.'}, status_code=503, headers=headers)


ROUTES = (('/api/wall-previews/inbox/bulk-delete', bulk_delete, ('POST',)),)
