"""Versioned header-only representation; controls keep their authoritative reads."""
import hashlib
import json

JOB_FIELDS = frozenset(('id', 'title', 'label', 'stage', 'state', 'percent', 'detail',
    'chat_url', 'updated_at', 'estimated', 'cancelled', 'can_cancel', 'can_defer',
    'can_play', 'control_action', 'posting_id'))
UPLOAD_FIELDS = JOB_FIELDS | {'dispatch_id', 'storefront', 'restartable', 'cancellable', 'stalled'}


def pick(row, fields):
    return {key: value for key, value in row.items() if key in fields}


def payload(result):
    value = pick(result, {'online', 'display_state', 'checked_at'})
    value['schema_version'] = 1
    value['jobs'] = []
    for row in result.get('jobs', []):
        job = pick(row, UPLOAD_FIELDS)
        if row.get('ad') is not None:
            job['ad'] = pick(row['ad'], {'label', 'detail', 'posting_id'})
        value['jobs'].append(job)
    if 'queues' in result:
        value['queues'] = {}
        for name in ('upload', 'design', 'ads', 'editions'):
            if name not in result['queues']:
                continue
            control = result['queues'][name]
            queue = pick(control, {'online', 'enabled', 'waiting', 'display', 'unavailable'})
            if 'jobs' in control:
                queue['jobs'] = [pick(row, JOB_FIELDS) for row in control['jobs']]
            value['queues'][name] = queue
    return value


def response(result, user, request, headers):
    from starlette.responses import Response
    from workspace_display_cache import user_scope
    body = json.dumps(payload(result), ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
    # Account revision/permissions bind validators even when two bodies match.
    scope = json.dumps(user_scope(user), default=str, separators=(',', ':')).encode()
    tag = '"' + hashlib.sha256(scope + b'\0' + body).hexdigest() + '"'
    headers = {**headers, 'ETag': tag}
    # Only exact validators issued by this representation are accepted. Auth and
    # exact-receipt ownership have already been checked by the route.
    if request.headers.get('if-none-match') == tag:
        return Response(status_code=304, headers=headers)
    return Response(body, media_type='application/json', headers=headers)
