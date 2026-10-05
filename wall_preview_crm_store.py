"""Server-only Wall Preview CRM. All mutations use parameterized SQL and durable jobs."""
import hashlib
import hmac
import json
import secrets
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import wall_preview_store as legacy

PUBLIC_EVENTS = frozenset({'WallPreviewStarted', 'WallPreviewConfirmed', 'WallPreviewDownloaded',
                          'WallPreviewShared', 'WallPreviewEmailCaptured', 'WallPreviewAddedToCart'})
FLOW_NAME = 'See It On Your Wall Follow Up'


def identifier(value):
    result = uuid.UUID(str(value))
    if result.version != 4:
        raise ValueError('A random UUID v4 is required.')
    return str(result)


@contextmanager
def transaction():
    with legacy._backend().connect() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout='5000ms'")
                yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def event(cur, row, name, key, metadata=None):
    cur.execute('''INSERT INTO public.wall_preview_events
        (preview_id,event_name,event_key,session_id,metadata) VALUES (%s,%s,%s,%s,%s::jsonb)
        ON CONFLICT(preview_id,event_key) DO NOTHING''',
        (str(row['id']), name, key, row.get('session_id'), json.dumps(metadata or {})))


def authorize(cur, preview_id, token):
    cur.execute('SELECT * FROM public.wall_previews WHERE id=%s FOR UPDATE', (str(uuid.UUID(str(preview_id))),))
    row = dict(cur.fetchone() or {})
    # A canonical preview ID or claimed Shopify ID alone never authorizes a mutation.
    if not row or not token or not row.get('session_id') or not hmac.compare_digest(str(row['session_id']), str(token)):
        raise PermissionError('Preview authorization required.')
    return row


def confirm(payload, upload):
    client_id, session = identifier(payload['client_preview_id']), identifier(payload['session_id'])
    with transaction() as cur:
        # Cross-process retry/reconfirm serialization; no unbounded thread registry.
        cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('wall-preview:'+client_id,))
        cur.execute('SELECT * FROM public.wall_previews WHERE client_preview_id=%s FOR UPDATE', (client_id,))
        previous = dict(cur.fetchone() or {})
        if previous and not hmac.compare_digest(str(previous['session_id']), session):
            raise PermissionError('Preview authorization required.')
        if payload.get('preview_id') and (not previous or str(previous['id']) != str(payload['preview_id'])):
            raise PermissionError('Preview identity does not match.')
        # Retry of identical image AND metadata is a no-op. Never erase captured identity.
        fields = ('product_id','variant_id','product_handle','product_title','product_url','frame_label','size_label','measurement_unit')
        unchanged = previous and previous['archive_sha256'] == payload['image_sha256'] and all(
            str(previous.get(k) or '') == str(payload.get(k) or '') for k in fields)
        if unchanged:
            return _market(cur,previous,payload), True
        preview_id = str(previous.get('id') or uuid.uuid4())
        storage = upload(previous, preview_id)
        version = int(previous.get('version') or 0) + 1
        identity = payload['identity']
        if previous.get('customer_email'):
            identity = {k: previous.get(k) for k in identity}
        token = previous.get('share_token') or secrets.token_urlsafe(32)
        columns = ['id','client_preview_id','session_id','image_sha256',*fields,
                   'customer_email','customer_name','shopify_customer_id','identity_source','email_marketing_state',
                   'dropbox_file_id','dropbox_path','customer_folder','content_type','image_width','image_height','image_bytes',
                  'version','share_token','archive_sha256','started_at','attribution']
        fingerprint=hashlib.sha256((client_id+'\0'+payload['image_sha256']).encode()).hexdigest()
        values = [preview_id,client_id,session,fingerprint,*[payload.get(k,'') for k in fields],
                  *[identity.get(k,'') for k in columns[12:17]],
                  storage['file_id'],storage['path'],storage['folder'],'image/jpeg',payload['width'],payload['height'],payload['bytes'],
                  version,token,payload['image_sha256'],payload.get('started_at'),json.dumps(payload.get('attribution') or {})]
        updates = ','.join(f'{c}=EXCLUDED.{c}' for c in columns if c not in ('id','client_preview_id','session_id','share_token','started_at'))
        cur.execute(f'''INSERT INTO public.wall_previews ({','.join(columns)},confirmed_at,share_expires_at)
            VALUES ({','.join(['%s']*(len(values)-1))},%s::jsonb,now(),now()+interval '90 days')
            ON CONFLICT(client_preview_id) DO UPDATE SET {updates},updated_at=now(),last_saved_at=now(),
            save_count=wall_previews.save_count+1,marketing_permission=FALSE,
            image_reuse_consent_at=NULL,image_reuse_consent_source=NULL RETURNING *''', tuple(values))
        row = dict(cur.fetchone())
        row = _market(cur,row,payload)
        if storage.get('pending_archive'):
            image=payload.get('archive_image')
            if not isinstance(image,bytes) or not image:raise ValueError('Confirmed composite unavailable.')
            cur.execute('''INSERT INTO public.wall_preview_archive_jobs(preview_id,version,image)
                VALUES (%s,%s,decode(%s,'hex')) ON CONFLICT(preview_id) DO UPDATE SET
                version=EXCLUDED.version,image=EXCLUDED.image,state='queued',attempts=0,
                due_at=now(),last_attempt_at=NULL,finished_at=NULL,reason='' ''',(preview_id,version,image.hex()))
        else:
            cur.execute("UPDATE public.wall_preview_archive_jobs SET state='done',image=NULL,finished_at=now() WHERE preview_id=%s",(preview_id,))
        if not previous:
            event(cur,row,'WallPreviewStarted','started')
        event(cur,row,'WallPreviewConfirmed','confirmed:'+str(version),{'version':version})
        return row, False


def _market(cur,row,payload):
    cur.execute('''UPDATE public.wall_previews SET
        market_country_code=COALESCE(market_country_code,%s),
        market_country_name=COALESCE(market_country_name,%s) WHERE id=%s RETURNING *''',
        (payload.get('market_country_code'),payload.get('market_country_name'),str(row['id'])))
    return dict(cur.fetchone())


def pending_archive_image(preview_id):
    with transaction() as cur:
        cur.execute('''SELECT encode(j.image,'hex') AS image FROM public.wall_preview_archive_jobs j
            JOIN public.wall_previews p ON p.id=j.preview_id AND p.version=j.version
            WHERE j.preview_id=%s AND j.image IS NOT NULL''',(str(preview_id),))
        row=cur.fetchone()
        return bytes.fromhex(row['image']) if row else None


def add_event(preview_id, token, name, event_id):
    if name not in PUBLIC_EVENTS or name in {'WallPreviewEmailCaptured','WallPreviewConfirmed','WallPreviewStarted'}:
        raise ValueError('This event is recorded only by its authoritative server action.')
    key = identifier(event_id)
    with transaction() as cur:
        row = authorize(cur,preview_id,token)
        event(cur,row,name,name+':'+key)


def request_email(preview_id, token, address, options=None):
    options = options or {}
    with transaction() as cur:
        row = authorize(cur,preview_id,token)
        if not row.get('confirmed_at') or row.get('share_revoked_at') or not row.get('share_token'):
            raise ValueError('A confirmed available preview is required.')
        # One recipient and one immediate request per preview, including network retries.
        if row.get('email_requested_at') and row.get('customer_email') != address:
            raise ValueError('This preview email has already been requested.')
        if row.get('email_requested_at'):
            cur.execute("SELECT state FROM public.wall_preview_email_jobs WHERE preview_id=%s AND kind='requested'", (preview_id,))
            return (cur.fetchone() or {}).get('state','queued')
        cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',('wall-preview-email:'+address,))
        cur.execute('''SELECT count(*) AS n FROM public.wall_previews WHERE customer_email=%s
            AND email_requested_at>now()-interval '1 day' ''',(address,))
        if (cur.fetchone() or {}).get('n',0)>=3:
            raise ValueError('Preview email request limit reached.')
        cur.execute('''UPDATE public.wall_previews SET customer_email=%s,
            identity_source=CASE WHEN identity_source='logged_in' AND customer_email=%s THEN identity_source ELSE 'email_capture' END,
            shopify_customer_id=CASE WHEN customer_email=%s THEN shopify_customer_id ELSE '' END,
            email_marketing_state=CASE WHEN customer_email=%s THEN email_marketing_state ELSE 'UNKNOWN' END,
            email_requested_at=COALESCE(email_requested_at,now()),updated_at=now() WHERE id=%s RETURNING *''',
            (address,address,address,address,preview_id))
        row = dict(cur.fetchone())
        reuse = options.get('image_reuse_allowed')
        optin = options.get('marketing_opt_in')
        cur.execute('''UPDATE public.wall_previews SET customer_name=CASE WHEN %s<>'' THEN %s ELSE customer_name END,
            marketing_permission=%s, image_reuse_consent_at=CASE WHEN %s::boolean IS NOT NULL THEN now() ELSE NULL END,
            image_reuse_consent_source=%s, submitted_marketing_opt_in=%s,
            marketing_consent_at=CASE WHEN %s::boolean IS NOT NULL THEN now() ELSE NULL END,
            marketing_consent_source=%s,marketing_consent_text=%s,marketing_consent_version=%s,
            market_country_code=COALESCE(%s,market_country_code),
            market_country_name=COALESCE(%s,market_country_name) WHERE id=%s RETURNING *''',
            (options.get('name',''),options.get('name',''),reuse is True,reuse,
             options.get('reuse_consent_source') if reuse is not None else None,optin,optin,
             options.get('marketing_consent_source') if optin is not None else None,
             options.get('marketing_consent_text') if optin is not None else None,
             options.get('marketing_consent_version') if optin is not None else None,
             options.get('market_country_code'),options.get('market_country_name'),preview_id))
        row = dict(cur.fetchone())
        event(cur,row,'WallPreviewEmailCaptured','email-requested',
              {'image_reuse_allowed':reuse,'marketing_opt_in':optin,'email':address,
               'marketing_consent_source':row.get('marketing_consent_source'),
               'marketing_consent_text':row.get('marketing_consent_text'),
               'marketing_consent_version':row.get('marketing_consent_version'),
               'marketing_consent_at':str(row.get('marketing_consent_at') or ''),
               'shopify_customer_id':row.get('shopify_customer_id') or None,
               'market_country_code':row.get('market_country_code'),
               'market_country_name':row.get('market_country_name')})
        cur.execute('''INSERT INTO public.wall_preview_customer_jobs(preview_id) VALUES (%s)
            ON CONFLICT(preview_id) DO NOTHING''',(preview_id,))
        for kind, hours in (('requested',0),('4h',4),('24h',24)):
            cur.execute('''INSERT INTO public.wall_preview_email_jobs(preview_id,kind,due_at)
                VALUES (%s,%s,now()+%s*interval '1 hour') ON CONFLICT(preview_id,kind) DO NOTHING''',
                (preview_id,kind,hours))
        cur.execute("SELECT state FROM public.wall_preview_email_jobs WHERE preview_id=%s AND kind='requested'", (preview_id,))
        return (cur.fetchone() or {}).get('state','queued')


def public_preview(token):
    if not isinstance(token,str) or len(token) != 43:
        return None
    with transaction() as cur:
        cur.execute('''SELECT id,product_title,product_url,variant_id,frame_label,size_label,
            dropbox_path,dropbox_file_id,content_type FROM public.wall_previews
            WHERE share_token=%s AND share_revoked_at IS NULL AND share_expires_at>now()''',(token,))
        row = cur.fetchone()
        return dict(row) if row else None


def revoke_share(preview_id):
    # Internal admin action; no unauthenticated revocation/list endpoint.
    with transaction() as cur:
        cur.execute('UPDATE public.wall_previews SET share_revoked_at=now() WHERE id=%s',(preview_id,))


def timeline(preview_id):
    with transaction() as cur:
        cur.execute('SELECT event_name,occurred_at,metadata FROM public.wall_preview_events WHERE preview_id=%s ORDER BY occurred_at LIMIT 100',(preview_id,))
        return [dict(r) for r in cur.fetchall()]


def correlate_order(payload):
    """Called ONLY after verified Shopify ingestion. Properties must match the purchased variant."""
    order_id = str(payload.get('id') or '')[:100]
    if not order_id:
        return 0
    matched = 0
    with transaction() as cur:
        for line in payload.get('line_items') or []:
            props = {str(p.get('name') or ''):str(p.get('value') or '') for p in line.get('properties') or [] if isinstance(p,dict)}
            value = props.get('_wall_preview_id') or props.get('_wall_preview_client_id')
            if not value:
                continue
            try:
                value = str(uuid.UUID(value))
            except (ValueError,TypeError):
                continue
            column = 'id' if props.get('_wall_preview_id') else 'client_preview_id'
            cur.execute(f'SELECT * FROM public.wall_previews WHERE {column}=%s FOR UPDATE',(value,))
            row = dict(cur.fetchone() or {})
            if not row or not row.get('variant_id') or str(row['variant_id']).rsplit('/',1)[-1] != str(line.get('variant_id')):
                continue
            cur.execute('''UPDATE public.wall_previews SET purchased_at=COALESCE(purchased_at,now()),
                order_id=COALESCE(order_id,%s),order_number=COALESCE(order_number,%s),updated_at=now() WHERE id=%s''',
                (order_id,str(payload.get('name') or payload.get('order_number') or '')[:100],str(row['id'])))
            event(cur,row,'WallPreviewPurchased','order:'+order_id,{'order_id':order_id})
            cur.execute("UPDATE public.wall_preview_email_jobs SET state='suppressed',reason='purchased',finished_at=now() WHERE preview_id=%s AND kind<>'requested' AND state='queued'",(str(row['id']),))
            matched += 1
    return matched
