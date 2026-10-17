"""R2 atomic public pointers. Assets keep working independently of the OS process."""
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from copy import deepcopy
from product_quiz import DEFAULT, digest, validate, classify, public_product, verified_collections

ROOT=Path(__file__).parent


def now(): return datetime.now(timezone.utc).isoformat()


def asset_base():
    from crm_tracking import public_https
    value=os.getenv('PRODUCT_QUIZ_ASSET_BASE','').rstrip('/')
    if not public_https(value) or '?' in value or '#' in value: raise ValueError('Configure the public HTTPS quiz asset base on the existing Render service before publishing.')
    return value


class Assets:
    def __init__(self,client=None,bucket=None):
        from services.r2_storage import get_r2_client,get_bucket_name
        self.client=client or get_r2_client(); self.bucket=bucket or get_bucket_name('assets')
        if not self.bucket: raise ValueError('R2 assets bucket is not configured.')

    def put(self,path,body,content_type='application/json',immutable=False):
        if not isinstance(body,(str,bytes)): body=json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=False)
        if isinstance(body,str): body=body.encode()
        if len(body)>250_000: raise ValueError('Quiz asset exceeds 250 KB; split the catalogue before publishing.')
        self.client.put_object(Bucket=self.bucket,Key='product-quiz/'+path,Body=body,ContentType=content_type+'; charset=utf-8',
            CacheControl='public,max-age=31536000,immutable' if immutable else 'public,max-age=60,must-revalidate')
        return path

    def get(self,path):
        try:
            return json.loads(self.client.get_object(Bucket=self.bucket,Key='product-quiz/'+path)['Body'].read())
        except Exception as exc:
            if getattr(exc,'response',{}).get('Error',{}).get('Code') in ('NoSuchKey','404'): return None
            raise


def compile_catalogue(rows,overrides,aliases):
    review=[]; eligible={}
    for row in rows:
        pid=str(row.get('shopify_product_id') or row.get('id') or '')
        override=overrides.get(pid) or overrides.get('gid://shopify/Product/'+pid.rsplit('/',1)[-1])
        p=classify(row,override,aliases)
        review.append(p)
        if p['status']=='Eligible': eligible[p['id']]=public_product(p)
    return list(eligible.values()),review


def sync(store,assets,*,rows=None):
    with store.lock():
        config=store.get_state('classification',{'aliases':{},'overrides':{}})
        published=assets.get('manifest.json') or {}
        live_config=assets.get(published['config']) if published.get('config') else DEFAULT
        products,review=compile_catalogue(store.catalogue_rows() if rows is None else rows,config['overrides'],live_config['aliases'])
        revision=digest(products)
        previous=assets.get('catalogue.json') or {}
        if previous.get('revision') != revision:
            shards={}
            for sport in sorted({s for p in products for s in p['sports']}):
                subset=[p for p in products if sport in p['sports']]
                data={'products':subset}
                path='catalogue/'+digest(data)+'.json'
                assets.put(path,data,immutable=True)
                shards[sport]=path
            previous={'revision':revision,'sports':shards}
        assets.put('catalogue.json',{**previous,'generated_at':now()})
        store.put_state('catalogue_status',{'last_success':now(),'error':'','revision':revision,'products':review})
        return review


def publish(store,assets,config,*,expected_revision=None):
    config=validate(config)
    base=asset_base()
    with store.lock():
        if expected_revision is not None and store.draft()['revision'] != expected_revision: raise ValueError('Draft changed. Reload before publishing.')
        verified=verified_collections(store.catalogue_rows())
        if any(verified.get(handle)!=sport for handle,sport in config['collections'].items()):
            raise ValueError('Collection context must match a verified collection/sport mapping in the existing catalogue.')
        if not assets.get('catalogue.json'): raise ValueError('Reconcile the catalogue before publishing.')
        old=assets.get('manifest.json')
        version=digest(config)
        config_path='config/'+version+'.json'
        assets.put(config_path,config,immutable=True)
        source=(ROOT/'static/product-quiz/runtime.js').read_bytes()
        runtime_path='runtime/'+digest(source.decode())+'.js'
        assets.put(runtime_path,source,'text/javascript',True)
        assets.put('loader.js',(ROOT/'static/product-quiz/loader.js').read_bytes(),'text/javascript')
        pointer={'version':version,'config':config_path,'runtime':runtime_path,'published_at':now(),
                 'previous':({k:v for k,v in old.items() if k!='previous'} if old else None)}
        endpoint=os.getenv('PRODUCT_QUIZ_ANALYTICS_URL','')
        if endpoint:
            from crm_tracking import public_https
            from urllib.parse import urlsplit
            parsed=urlsplit(endpoint)
            if not public_https(endpoint) or parsed.query or parsed.fragment or parsed.path!='/api/product-quiz/events': raise ValueError('Analytics endpoint must be the public HTTPS quiz ingest route without query parameters.')
            pointer['analytics_endpoint']=endpoint
        # Durable history is written BEFORE the one public visibility switch.
        store.put_state('version/'+version,{'config':config,'published_at':pointer['published_at']})
        assets.put('manifest.json',pointer)
        return {**pointer,'loader_url':base+'/product-quiz/loader.js'}


def revert(store,assets):
    with store.lock():
        current=assets.get('manifest.json') or {}
        previous=current.get('previous')
        if not previous: raise ValueError('There is no previous published version.')
        # Verify dependencies still exist before changing the pointer.
        if not assets.get(previous['config']): raise ValueError('Previous configuration is unavailable.')
        assets.put('manifest.json',{**previous,'previous':{k:v for k,v in current.items() if k!='previous'}})


def snippets(base,collection=''):
    from html import escape
    loader=escape(base.rstrip('/')+'/product-quiz/loader.js',quote=True)
    context=' data-collection="'+escape(collection,quote=True)+'"' if collection else ''
    return {
        'Collection button':f'<div data-sports-cave-quiz="button"{context}><a href="/collections/all">Find your edition</a></div>\n<script src="{loader}" defer></script>',
        'Inline page':f'<div data-sports-cave-quiz="inline"><a href="/collections/all">Browse editions</a></div>\n<script src="{loader}" defer></script>'}


def verify_public(assets):
    """Read public delivery without credentials before offering installation code."""
    import requests
    base=asset_base()+'/product-quiz/'
    expected=assets.get('manifest.json')
    if not expected: raise ValueError('Quiz is not published.')
    for path in ('manifest.json',expected['config'],expected['runtime'],'loader.js','catalogue.json'):
        response=requests.get(base+path,timeout=10,headers={'Origin':'https://sportscaveshop.com'})
        response.raise_for_status()
        expected_type='json' if path.endswith('.json') else 'javascript'
        if expected_type not in response.headers.get('Content-Type','').lower(): raise ValueError('Unexpected public asset content type.')
        if path.endswith('.json') and response.headers.get('Access-Control-Allow-Origin') not in {'*','https://sportscaveshop.com'}:
            raise ValueError('Public quiz CORS is not ready.')
        if path=='manifest.json' and response.json()!=expected: raise ValueError('Public quiz pointer has not reached the asset cache yet.')
    return expected
