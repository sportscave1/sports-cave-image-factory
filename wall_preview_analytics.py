"""First-party wall-preview analytics. No photos, customer PII or public reads."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit, urlunsplit
from wall_preview_crm_store import transaction, identifier

EVENTS = tuple('WallPreview'+name for name in (
    'Started','CameraOpened','GalleryOpened','PhotoCaptured','PhotoUploaded','PhotoReady',
    'ArtworkDragged','FrameChanged','SizeChanged','ScaleStarted','ScaleCompleted',
    'QuickPreviewUsed','Confirmed','Downloaded','Shared','AddedToCart','CheckoutStarted','Purchased','Closed'))
TEXT_FIELDS = {'product_id':80,'variant_id':80,'product_handle':255,'product_title':500,
    'frame':120,'size':160,'unit':2,'device_type':16,'capture_source':16,
    'utm_source':160,'utm_medium':160,'utm_campaign':160,'utm_content':160,'utm_term':160,'furthest_stage':40}
STAGES = [('Opened','Started'),('Photo Ready','PhotoReady'),('Interacted / Dragged','ArtworkDragged'),
          ('Confirmed','Confirmed'),('Added to Cart','AddedToCart'),('Checkout','CheckoutStarted'),('Purchased','Purchased')]


def clean(payload):
    if not isinstance(payload,dict):raise ValueError('Invalid event')
    name=payload.get('event') or payload.get('event_name')
    if name not in EVENTS or name=='WallPreviewPurchased':raise ValueError('Unsupported client event')
    result={'event_name':name,'event_key':'analytics:'+identifier(payload.get('event_id')),
            'session_id':identifier(payload.get('session_id')),'client_preview_id':identifier(payload.get('client_preview_id'))}
    result['preview_id']=identifier(payload['preview_id']) if payload.get('preview_id') else None
    at=datetime.fromisoformat(str(payload.get('occurred_at') or datetime.now(timezone.utc).isoformat()).replace('Z','+00:00'))
    if not at.tzinfo or not datetime.now(timezone.utc)-timedelta(days=7)<=at<=datetime.now(timezone.utc)+timedelta(minutes=5):raise ValueError('Invalid timestamp')
    result['occurred_at']=at
    for key,limit in TEXT_FIELDS.items():
        value=payload.get(key,payload.get('camera_or_upload','') if key=='capture_source' else '')
        if not isinstance(value,(str,int)):raise ValueError('Invalid field')
        result[key]=' '.join(str(value).split())[:limit]
    for key,allowed in [('device_type',('','mobile','desktop','tablet')),('capture_source',('','camera','upload')),('unit',('','cm','in'))]:
        if result[key] not in allowed:raise ValueError('Invalid category')
    for key in ('page_url','referrer'):
        parts=urlsplit(str(payload.get(key) or ''))
        result[key]=urlunsplit((parts.scheme,parts.netloc,parts.path,'',''))[:1200] if parts.scheme in ('https','http') and parts.hostname and not parts.username else ''
    elapsed=payload.get('elapsed_ms',0)
    if type(elapsed) is not int or not 0<=elapsed<=86400000:raise ValueError('Invalid duration')
    for key in ('product_id','variant_id'):
        result[key]=result[key].rsplit('/',1)[-1]
    result['elapsed_ms']=elapsed
    result['source']='storefront'
    return result


def insert(cur,data):
    columns=list(data)
    cur.execute(f"INSERT INTO public.wall_preview_events ({','.join(columns)}) VALUES ({','.join(['%s']*len(columns))}) ON CONFLICT DO NOTHING RETURNING id",tuple(data.values()))
    return bool(cur.fetchone())


def ingest(payload):
    data=clean(payload)
    with transaction() as cur:
        # The existing session is also a private write capability, never a public analytics ID.
        cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',('wall-preview:'+data['client_preview_id'],))
        cur.execute('SELECT id,session_id,client_preview_id FROM public.wall_previews WHERE client_preview_id=%s',(data['client_preview_id'],))
        row=cur.fetchone()
        if row and str(row['session_id'])!=data['session_id']:raise PermissionError('Journey mismatch')
        if data['preview_id'] and (not row or str(row['id'])!=data['preview_id']):raise PermissionError('Preview mismatch')
        if row:data['preview_id']=str(row['id'])
        cur.execute('SELECT session_id FROM public.wall_preview_events WHERE client_preview_id=%s LIMIT 1',(data['client_preview_id'],))
        previous=cur.fetchone()
        if previous and previous['session_id'] and str(previous['session_id'])!=data['session_id']:raise PermissionError('Journey mismatch')
        return insert(cur,data)


def purchase(cur,payload,line,row=None):
    """Only called by the HMAC-verified paid-order path. Never trusts client revenue."""
    props={str(p.get('name')):p.get('value') for p in line.get('properties') or [] if isinstance(p,dict)}
    client=(row or {}).get('client_preview_id') or props.get('_wall_preview_client_id')
    try:client=identifier(client)
    except (ValueError,TypeError,AttributeError):return False
    product=str(line.get('product_id') or '');variant=str(line.get('variant_id') or '')
    if not row:
        if props.get('_wall_preview_id'):return False
        cur.execute("SELECT * FROM public.wall_preview_events WHERE client_preview_id=%s AND product_id=%s AND variant_id=%s ORDER BY occurred_at DESC LIMIT 1",(client,product,variant))
        row=dict(cur.fetchone() or {})
    if not row or str(row.get('variant_id') or '').rsplit('/',1)[-1]!=variant:return False
    if row.get('product_id') and str(row['product_id']).rsplit('/',1)[-1]!=product:return False
    if not line.get('id') or not payload.get('id'):return False
    def money(value):
        number=Decimal(str(value))
        if not number.is_finite() or number<0:raise ValueError('Invalid money')
        return number
    try:
        quantity=int(line.get('quantity') or 0)
        if quantity<=0:return False
        revenue=max(Decimal(0),money(line['price'])*quantity-sum((money(d['amount']) for d in line.get('discount_allocations') or []),Decimal(0)))
        total=money(payload['total_price'])
    except (ValueError,InvalidOperation,KeyError,TypeError):revenue=total=None
    cur.execute("SELECT device_type,capture_source FROM public.wall_preview_events WHERE client_preview_id=%s AND source='storefront' ORDER BY occurred_at DESC LIMIT 1",(client,))
    dimensions=dict(cur.fetchone() or {})
    at=payload.get('processed_at') or payload.get('created_at') or datetime.now(timezone.utc)
    data={'event_name':'WallPreviewPurchased','event_key':f"purchase:{payload['id']}:{line['id']}",
          'source':'shopify','occurred_at':at,'client_preview_id':client,
          'preview_id':str(row['id']) if 'archive_sha256' in row else row.get('preview_id'),
          'session_id':row.get('session_id'),'product_id':product,'variant_id':variant,
          'product_title':str(row.get('product_title') or line.get('title') or '')[:500],
          'product_handle':str(row.get('product_handle') or '')[:255],
          'frame':row.get('frame_label',row.get('frame','')),'size':row.get('size_label',row.get('size','')),
          'device_type':dimensions.get('device_type',row.get('device_type','')),'capture_source':dimensions.get('capture_source',row.get('capture_source','')),
          'order_id':str(payload['id']),'order_number':str(payload.get('name') or payload.get('order_number') or '')[:100],
          'quantity':int(line.get('quantity') or 0),'line_revenue':revenue,'order_revenue':total,
          'currency':str(payload.get('currency') or '')[:3]}
    return insert(cur,data)


def filters(params):
    end=datetime.now(timezone.utc)+timedelta(seconds=1)
    start=end-timedelta(days=30)
    if params.get('start_date'):start=datetime.fromisoformat(str(params['start_date']).replace('Z','+00:00'))
    if params.get('end_date'):
        raw=str(params['end_date']);end=datetime.fromisoformat(raw.replace('Z','+00:00'))
        if len(raw)==10:end+=timedelta(days=1)
    start=start.replace(tzinfo=start.tzinfo or timezone.utc);end=end.replace(tzinfo=end.tzinfo or timezone.utc)
    if end<=start or end-start>timedelta(days=366):raise ValueError('Choose a date range up to 366 days')
    clauses=['occurred_at >= %s','occurred_at < %s'];args=[start,end]
    for field in ('product_id','device_type','capture_source','preview_id'):
        if params.get(field):clauses.append(field+'=%s');args.append(str(params[field])[:80])
    return ' AND '.join(clauses),args

# Prefer true browser observations over old server confirmation proxies, preserving old history.
BASE="""WITH resolved AS (SELECT e.*,
 COALESCE(e.client_preview_id,p.client_preview_id) AS journey,
 COALESCE(NULLIF(e.product_id,''),p.product_id,'') AS resolved_product,
 COALESCE(NULLIF(e.product_title,''),p.product_title,'') AS resolved_title,
 COALESCE(NULLIF(e.capture_source,''),d.capture_source,'') AS resolved_capture,
 COALESCE(NULLIF(e.device_type,''),d.device_type,'') AS resolved_device
 FROM public.wall_preview_events e LEFT JOIN public.wall_previews p ON p.id=e.preview_id
 LEFT JOIN LATERAL (SELECT capture_source,device_type FROM public.wall_preview_events x
 WHERE x.client_preview_id=COALESCE(e.client_preview_id,p.client_preview_id) AND x.capture_source<>''
 ORDER BY x.occurred_at DESC LIMIT 1) d ON TRUE),
 normalized AS (SELECT r.* FROM resolved r WHERE NOT (source='legacy' AND event_name='WallPreviewStarted')
 AND NOT (source='legacy' AND EXISTS (SELECT 1 FROM resolved n WHERE n.journey=r.journey AND n.event_name=r.event_name AND n.source<>'legacy'))),
 filtered AS (SELECT * FROM normalized WHERE {where}) """


def report(params=None):
    where,args=filters(params or {})
    # product filters also resolve legacy preview metadata, without fabricating events.
    where=where.replace('product_id=%s','resolved_product=%s').replace('capture_source=%s','resolved_capture=%s').replace('device_type=%s','resolved_device=%s')
    base=BASE.format(where=where)
    def rows(cur,sql):cur.execute(base+sql,tuple(args));return [dict(r) for r in cur.fetchall()]
    with transaction() as cur:
        counts=rows(cur,"SELECT event_name,count(*) AS events,count(DISTINCT COALESCE(journey::text,preview_id::text)) AS journeys FROM filtered GROUP BY event_name")
        sessions=rows(cur,'SELECT count(DISTINCT session_id) AS n FROM filtered')[0]['n']
        revenue=rows(cur,"SELECT currency,sum(line_revenue) AS revenue FROM filtered WHERE source='shopify' AND event_name='WallPreviewPurchased' AND line_revenue IS NOT NULL AND currency<>'' GROUP BY currency")
        products=rows(cur,"""SELECT resolved_product AS product_id,max(resolved_title) AS product,
         count(DISTINCT journey) FILTER(WHERE event_name='WallPreviewStarted') AS opens,
         count(DISTINCT journey) FILTER(WHERE event_name='WallPreviewPhotoReady') AS photo_ready,
         count(DISTINCT journey) FILTER(WHERE event_name='WallPreviewConfirmed') AS confirmed,
         count(DISTINCT journey) FILTER(WHERE event_name='WallPreviewAddedToCart') AS atc,
         count(DISTINCT journey) FILTER(WHERE event_name='WallPreviewPurchased') AS purchased,
         count(DISTINCT journey) FILTER(WHERE event_name='WallPreviewPurchased' AND EXISTS(SELECT 1 FROM filtered o WHERE o.journey=filtered.journey AND o.resolved_product=filtered.resolved_product AND o.event_name='WallPreviewStarted' AND o.occurred_at<=filtered.occurred_at)) AS converted,
         sum(line_revenue) FILTER(WHERE source='shopify') AS sort_revenue
         FROM filtered GROUP BY resolved_product ORDER BY purchased DESC,sort_revenue DESC NULLS LAST LIMIT 100""")
        insight=rows(cur,"""SELECT insight,value,count(DISTINCT journey) AS journeys FROM filtered f
         CROSS JOIN LATERAL (VALUES
          ('Camera vs Upload',NULLIF(resolved_capture,'')),('Mobile vs Desktop',NULLIF(resolved_device,'')),
          ('Frame popularity',CASE WHEN event_name IN ('WallPreviewConfirmed','WallPreviewFrameChanged') THEN NULLIF(frame,'') END),
          ('Size popularity',CASE WHEN event_name IN ('WallPreviewConfirmed','WallPreviewSizeChanged') THEN NULLIF(size,'') END),
          ('Quick Preview vs True Scale',CASE WHEN event_name='WallPreviewQuickPreviewUsed' THEN 'Quick Preview' WHEN event_name='WallPreviewScaleCompleted' THEN 'True Scale' END),
          ('Downloads',CASE WHEN event_name='WallPreviewDownloaded' THEN 'Downloaded' END),
          ('Shares',CASE WHEN event_name='WallPreviewShared' THEN 'Shared' END)) AS d(insight,value)
         WHERE value IS NOT NULL GROUP BY insight,value ORDER BY insight,journeys DESC""")
        product_revenue=rows(cur,"SELECT resolved_product AS product_id,currency,sum(line_revenue) AS revenue FROM filtered WHERE source='shopify' AND line_revenue IS NOT NULL AND currency<>'' GROUP BY resolved_product,currency")
        transitions=rows(cur,"""SELECT a.event_name,b.event_name AS next_event,count(DISTINCT a.journey) AS n
          FROM (SELECT journey,event_name,min(occurred_at) AS occurred_at FROM filtered GROUP BY journey,event_name) a
          JOIN (SELECT journey,event_name,min(occurred_at) AS occurred_at FROM filtered GROUP BY journey,event_name) b
          ON b.journey=a.journey AND b.occurred_at>=a.occurred_at
          GROUP BY a.event_name,b.event_name""")
    by={r['event_name']:r for r in counts}
    def count(name):return int(by.get('WallPreview'+name,{}).get('journeys',0))
    def ratio(a,b):return round(a/b*100,1) if b else None
    funnel=[]
    for i,(label,suffix) in enumerate(STAGES):
        name='WallPreview'+suffix
        current=int(by.get(name,{}).get('journeys',0))
        reached=next((int(r['n']) for r in transitions if r['event_name']==name and r['next_event']=='WallPreview'+STAGES[i+1][1]),0) if i+1<len(STAGES) else None
        conversion=ratio(reached,current) if reached is not None else None
        funnel.append({'stage':label,'events':int(by.get(name,{}).get('events',0)),'journeys':current,'next_stage_percent':conversion,'drop_off_percent':round(100-conversion,1) if conversion is not None else None})
    for p in products:
        p['revenue']=[r for r in product_revenue if r['product_id']==p['product_id']]
        p['purchase_percent']=ratio(int(p.pop('converted')),int(p['opens']))
        p.pop('sort_revenue',None)
    return {'summary':{'opens':count('Started'),'sessions':int(sessions),'photo_ready':count('PhotoReady'),
            'confirmed':count('Confirmed'),'atc':count('AddedToCart'),'purchased':count('Purchased'),
            'atc_percent':ratio(next((int(r['n']) for r in transitions if r['event_name']=='WallPreviewStarted' and r['next_event']=='WallPreviewAddedToCart'),0),count('Started')),'purchase_percent':ratio(next((int(r['n']) for r in transitions if r['event_name']=='WallPreviewStarted' and r['next_event']=='WallPreviewPurchased'),0),count('Started')),'revenue':revenue},
            'funnel':funnel,'products':products,'insights':insight}


def events(params=None):
    params=params or {};where,args=filters(params)
    limit=min(200,max(1,int(params.get('limit',100))));offset=min(10000,max(0,int(params.get('offset',0))))
    if params.get('preview_id'):
        where=where.replace('preview_id=%s',"(preview_id=%s OR client_preview_id=(SELECT client_preview_id FROM public.wall_previews WHERE id=%s))")
        args.append(str(params['preview_id']))
    with transaction() as cur:
        cur.execute('SELECT event_name,occurred_at,product_title,frame,size,furthest_stage,source FROM public.wall_preview_events WHERE '+where+' ORDER BY occurred_at,id LIMIT %s OFFSET %s',tuple(args+[limit,offset]))
        return [dict(r) for r in cur.fetchall()]
