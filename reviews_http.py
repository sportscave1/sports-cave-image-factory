"""Public projection and token-only review form, mounted on the existing server."""
from html import escape
import json
from fastapi import APIRouter,Request,Response
from fastapi.responses import HTMLResponse,JSONResponse
from fastapi.encoders import jsonable_encoder
from starlette.concurrency import run_in_threadpool
from reviews_store import ReviewsStore
from reviews_submission import token_row,submit
from crm_onsite import allow_rate
from crm_http import bounded_body

router=APIRouter()

@router.get('/reviews/widget')
async def storefront_widget(request:Request):
    if not allow_rate('review-widget:'+str(request.client.host if request.client else 'unknown')):return Response(status_code=429)
    try:
        from reviews_public_cache import load
        from reviews_widget import projection
        store=ReviewsStore()
        settings=await run_in_threadpool(load,store,('settings',),store.settings)
        if not settings['enabled']:return Response(status_code=404)
        country='US' if request.query_params.get('country')=='US' else 'AU'
        offset=int(request.query_params.get('offset','0'))
        if not 0<=offset<=50000:return Response(status_code=400)
        origin=str(request.base_url).rstrip('/')
        data=await run_in_threadpool(load,store,('widget-v1',origin,country,offset),lambda:projection(store,origin,country,offset,settings))
        return JSONResponse(jsonable_encoder(data),headers={'Access-Control-Allow-Origin':'*','Cache-Control':'public,max-age=30','X-Content-Type-Options':'nosniff'})
    except (ValueError,TypeError):return Response(status_code=400)
    except Exception:return Response(status_code=503)

@router.get('/reviews/public')
async def published_reviews(request:Request):
    store=ReviewsStore()
    if not allow_rate('reviews:'+str(request.client.host if request.client else 'unknown')):return Response(status_code=429)
    try:
        from reviews_public_cache import load
        settings=await run_in_threadpool(load,store,('settings',),store.settings)
        if not settings['enabled']:return Response(status_code=404)
        product=request.query_params.get('product','')
        from reviews_model import product_gid
        if product and not product_gid(product):return Response(status_code=400)
        if product:product=product_gid(product)
        offset=int(request.query_params.get('offset','0'));rating=int(request.query_params.get('rating','0'))
        if not 0<=offset<=50000 or not 0<=rating<=5:return Response(status_code=400)
        sort=request.query_params.get('sort',settings['sort']);search=request.query_params.get('search','')[:150]
        rows=[] if request.query_params.get('summary')=='1' else await run_in_threadpool(load,store,('table',product,offset,sort,rating,search,settings['per_page']),lambda:store.rows(product=product,offset=offset,limit=settings['per_page'],sort=sort,rating=rating,search=search,public=True))
        aggregate=await run_in_threadpool(load,store,('aggregate',product),lambda:store.aggregate(product or None))
        more=len(rows)>settings['per_page'];rows=rows[:settings['per_page']]
        media=[] if not rows else await run_in_threadpool(store.q,
            "SELECT id,review_id,kind,storage FROM sc_review_media WHERE review_id=ANY(%s::uuid[]) AND status='COPIED' AND approved=true AND storage->>'provider'='dropbox' ORDER BY created_at,id",([str(r['id']) for r in rows],))
        by_review={}
        for m in media:
            url=str(request.base_url).rstrip('/')+'/reviews/media/'+str(m['id'])
            variants=m['storage'].get('posters' if m['kind']=='video' else 'variants') or {}
            if not variants.get('320') or not variants.get('1280'):continue
            by_review.setdefault(str(m['review_id']),[]).append({'kind':m['kind'],
              'url':url+('?size=original' if m['kind']=='video' else '?size=1280'),
              'thumbnail_url':url+'?size=320','poster_url':url+'?size=1280',
              'width':variants['1280'].get('width',1280),'height':variants['1280'].get('height',1280)})
        from crm_tracking import public_https
        for row in rows:
            row['media']=by_review.get(str(row['id']),[])
            row.pop('status',None)
            row['created_at']=str(row['created_at']) if settings['date'] and row.pop('date_known',True) else None
            row.pop('date_known',None)
            row['verified_purchase']=bool(row['verified_purchase'] and settings['verified'])
            if not settings['reply']:row['merchant_reply']=''
            if not settings['thumbnail'] or not public_https(row['product_image']):row['product_image']=''
            if not public_https(row['product_url']):row['product_url']=''
        products=[] if product or request.query_params.get('summary')=='1' else await run_in_threadpool(load,store,('products',),lambda:store.q("SELECT p.shopify_product_id AS product_id,p.title AS product_title FROM sc_review_totals t JOIN shopify_products p ON t.scope=p.shopify_product_id OR t.scope='gid://shopify/Product/'||p.shopify_product_id WHERE t.published>0 ORDER BY p.title LIMIT 25"))
        return JSONResponse(jsonable_encoder({'summary':aggregate,'reviews':rows,'products':products,'next_offset':offset+len(rows) if more else None,'appearance':{'accent':settings['accent'],'density':settings['density'],'sort':settings['sort']}}),headers={'Access-Control-Allow-Origin':'*','Cache-Control':'public,max-age=30','X-Content-Type-Options':'nosniff'})
    except (ValueError,TypeError):return Response(status_code=400)
    except Exception:return Response(status_code=503)

@router.api_route('/reviews/media/{identity}',methods=['GET','HEAD'])
async def review_media(identity:str,request:Request):
    from fastapi.responses import StreamingResponse
    from starlette.background import BackgroundTask
    import uuid
    if not allow_rate('review-media:'+str(request.client.host if request.client else 'unknown')):return Response(status_code=429)
    try:
        identity=str(uuid.UUID(identity));store=ReviewsStore()
        from reviews_public_cache import load
        settings=await run_in_threadpool(load,store,('settings',),store.settings)
        if not settings['enabled']:return Response(status_code=404)
        from reviews_display_media import public_media
        media=await run_in_threadpool(load,store,('media',identity),lambda:public_media(store,identity))
        if not media:return Response(status_code=404)
        from reviews_dropbox import asset,ReviewDropboxStorage
        size=request.query_params.get('size','original' if media['kind']=='video' else '1280')
        if size=='640' and not (media['storage'].get('posters' if media['kind']=='video' else 'variants') or {}).get('640'):
            from reviews_display_media import ensure_carousel
            media={**media,'storage':await run_in_threadpool(ensure_carousel,store,identity,media)}
        ref,mime=asset(media['storage'],size,media['kind'])
        total=ref['size'];start=0;end=total-1;partial=False
        headers={'Cache-Control':'public,max-age=300','Referrer-Policy':'no-referrer','Accept-Ranges':'bytes',
          'ETag':'"'+ref['sha256']+'"','X-Content-Type-Options':'nosniff','Access-Control-Allow-Origin':'*',
          'Access-Control-Expose-Headers':'Content-Length,Content-Range,Accept-Ranges,ETag'}
        if request.headers.get('if-none-match')==headers['ETag'] and not request.headers.get('range'):return Response(status_code=304,headers=headers)
        if request.headers.get('range'):
            import re
            match=re.fullmatch(r'bytes=(\d*)-(\d*)',request.headers['range'])
            if not match or not any(match.groups()):return Response(status_code=416,headers={'Content-Range':f'bytes */{total}'})
            a,b=match.groups()
            if a:start=int(a);end=min(int(b),end) if b else end
            else:start=max(0,total-int(b))
            if not 0<=start<=end<total:return Response(status_code=416,headers={'Content-Range':f'bytes */{total}'})
            partial=True;headers['Content-Range']=f'bytes {start}-{end}/{total}'
        headers['Content-Length']=str(end-start+1)
        if request.method=='HEAD':return Response(status_code=206 if partial else 200,media_type=mime,headers=headers)
        if mime=='image/webp' and not partial:
            from reviews_display_cache import display_bytes
            body=await run_in_threadpool(display_bytes,ref,ReviewDropboxStorage())
            return Response(body,media_type=mime,headers=headers)
        stream=await run_in_threadpool(ReviewDropboxStorage().open,ref,start,end)
        return StreamingResponse(stream.iter_chunks(),status_code=206 if partial else 200,media_type=mime,headers=headers,background=BackgroundTask(stream.close))
    except ValueError:return Response(status_code=404)
    except Exception:return Response(status_code=503)

FORM_STYLE='<style>body{font:16px system-ui;color:#191919;background:#faf8f3;margin:0;padding:24px}main{max-width:560px;margin:24px auto;background:white;padding:24px;border:1px solid #e8e2d7;border-radius:12px;box-sizing:border-box}input,textarea,select,button{font:inherit;max-width:100%;box-sizing:border-box;width:100%;padding:10px;margin:6px 0 16px;border:1px solid #d4cfc5;border-radius:5px}button{background:#c7a13f;color:#181818}label{display:block}.trap{display:none}input[type=checkbox]{width:auto}h1{font-size:24px}</style>'

@router.get('/reviews/request/{token}',response_class=HTMLResponse)
async def review_form(token:str,request:Request):
    if not allow_rate('review-form:'+str(request.client.host if request.client else 'unknown')):return Response(status_code=429)
    try:
        store=ReviewsStore();row=await run_in_threadpool(token_row,store,token)
        if row['review_id']:return HTMLResponse(FORM_STYLE+'<main><h1>Thank you</h1><p>Your review has been received.</p></main>',headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
        product=await run_in_threadpool(store.match_product,{'product_id':row['product_id']})
        if not product:raise ValueError()
        html=form_html(product['title'],reward=store.collection_settings())
        return HTMLResponse(html,headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'"})
    except ValueError:return HTMLResponse(FORM_STYLE+'<main><h1>Review link unavailable</h1><p>This link is invalid or expired.</p></main>',status_code=400)
    except Exception:return Response(status_code=503)

@router.post('/reviews/request/{token}')
async def review_submit(token:str,request:Request):
    if not allow_rate('review-submit:'+str(request.client.host if request.client else 'unknown')):return Response(status_code=429)
    try:
        from urllib.parse import parse_qs,urlsplit
        # Same-origin form only. No third-party scripts, credentials or token logs.
        origin=request.headers.get('origin')
        expected=urlsplit(str(request.url));expected_origin=expected.scheme+'://'+expected.netloc
        if origin and origin!=expected_origin:return Response(status_code=403)
        store=ReviewsStore()
        known=await run_in_threadpool(token_row,store,token)
        if known['review_id']:return HTMLResponse(FORM_STYLE+'<main><h1>Thank you</h1><p>Your review has been received.</p></main>',headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
        payload,uploads=await read_submission(request)
        await run_in_threadpool(submit,store,token,payload,uploads)
        return HTMLResponse(FORM_STYLE+'<main><h1>Thank you</h1><p>Your review has been received.</p></main>',headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
    except (ValueError,TypeError):return HTMLResponse(FORM_STYLE+'<main><h1>Review not submitted</h1><p>Check your review and link, then try again.</p></main>',status_code=400)
    except Exception:return Response(status_code=503)

async def read_submission(request):
    from urllib.parse import parse_qs
    content_type=request.headers.get('content-type','').split(';')[0]
    uploads=[]
    if content_type=='multipart/form-data':
        from starlette.formparsers import MultiPartParser,MultiPartException
        from starlette.datastructures import UploadFile
        # Bound total bytes before multipart parsing, including chunked requests.
        async def limited_stream():
            total=0
            async for part in request.stream():
                total+=len(part)
                if total>65*1024*1024:raise MultiPartException('Upload exceeds 65 MB.')
                yield part
        try:form=await MultiPartParser(request.headers,limited_stream(),max_files=5,max_fields=10).parse()
        except MultiPartException:raise ValueError('Invalid or oversized upload.') from None
        try:
            fields={}
            for key,value in form.multi_items():
                if isinstance(value,UploadFile):
                    if key!='media':raise ValueError('Invalid file field.')
                    if not value.filename:continue
                    kind='video' if (value.content_type or '').startswith('video/') else 'image'
                    limit=50*1024*1024 if kind=='video' else 10*1024*1024
                    data=await value.read(limit+1)
                    if len(data)>limit:raise ValueError('Media exceeds file size limit.')
                    uploads.append({'data':data,'kind':kind})
                else:fields.setdefault(key,[]).append(value)
        finally:await form.close()
    elif content_type=='application/x-www-form-urlencoded':
        fields=parse_qs((await bounded_body(request,24000)).decode('utf-8'),keep_blank_values=True)
    else:raise ValueError('Unsupported form format.')
    if any(len(v)!=1 for v in fields.values()):raise ValueError('Duplicate form field.')
    payload={k:v[0] for k,v in fields.items()};payload['display_consent']=payload.get('display_consent')=='yes'
    return payload,uploads

def form_html(title,token=None,reward=None):
    html=FORM_STYLE+'<main><h1>Share your review</h1><p>'+escape(title)+'</p><form method="post" enctype="multipart/form-data"><label>Rating<select name="rating" required>'+''.join('<option value="'+str(n)+'">'+str(n)+' stars</option>' for n in (5,4,3,2,1))+'</select></label><label>Display name<input name="reviewer_name" maxlength="120" required></label><label>Title<input name="title" maxlength="200"></label><label>Review<textarea name="body" maxlength="5000" required rows="5"></textarea></label><label>Photos or video (optional)<input type="file" name="media" accept="image/jpeg,image/png,image/webp,video/mp4,video/webm" multiple></label><p>Up to 5 files: images up to 10 MB each, one video up to 50 MB, 65 MB total. Files are reviewed before display.</p><label class="trap" aria-hidden="true">Website<input name="website" tabindex="-1" autocomplete="off"></label><label><input type="checkbox" name="display_consent" value="yes" required>Display my review, attached media and chosen name publicly</label><button type="submit">Submit review</button></form></main>'
    if token:html=html.replace('<label>Rating','<input type="hidden" name="form_token" value="'+escape(token,quote=True)+'">'+'<label>Rating')
    html=html.replace('<h1>Share your review</h1>','<p>SPORTS CAVE Â· COLLECT. CELEBRATE. KEEP FOREVER.</p><h1>Share your review</h1>')
    if reward and reward.get('rewards_enabled'):
        text=f"<p>Once approved, eligible verified buyers receive {int(reward['image_percent'])}% for a photo or {int(reward['video_percent'])}% for a video. One reward per order, valid for 30 days. Your rating never affects the reward.</p>"
        html=html.replace('<label>Photos or video',text+'<label>Photos or video')
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Share your review | Sports Cave</title>'+html+'</html>'

PUBLIC_FORM_HEADERS={'Cache-Control':'no-store','Referrer-Policy':'no-referrer',
 'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors https://www.sportscaveshop.com https://sportscaveshop.com https://sportscave-nb.myshopify.com https://admin.shopify.com https://online-store-web.shopifyapps.com"}

@router.get('/reviews/write',response_class=HTMLResponse)
async def storefront_form(request:Request):
    if not allow_rate('review-write:'+str(request.client.host if request.client else 'unknown')):return Response(status_code=429)
    try:
        from reviews_public_submission import issue
        product=request.query_params.get('product','');store=ReviewsStore()
        if not await run_in_threadpool(lambda:store.settings()['enabled']):return Response(status_code=404)
        token=issue(product)
        mapped=await run_in_threadpool(store.match_product,{'product_id':product}) if product else None
        if product and not mapped:raise ValueError('Product unavailable.')
        from reviews_storefront_form import storefront_html,form_headers
        return HTMLResponse(storefront_html(mapped,token),headers=form_headers(PUBLIC_FORM_HEADERS))
    except ValueError:return HTMLResponse(FORM_STYLE+'<main><h1>Review form unavailable</h1><p>Please reload and try again.</p></main>',status_code=400,headers=PUBLIC_FORM_HEADERS)
    except Exception:return Response(status_code=503)

@router.post('/reviews/write',response_class=HTMLResponse)
async def storefront_submit(request:Request):
    if not allow_rate('review-write-submit:'+str(request.client.host if request.client else 'unknown')):return Response(status_code=429)
    try:
        from urllib.parse import urlsplit
        origin=request.headers.get('origin');url=urlsplit(str(request.url))
        if origin and origin!=url.scheme+'://'+url.netloc:return Response(status_code=403)
        payload,uploads=await read_submission(request)
        token=payload.pop('form_token','')
        from reviews_public_submission import submit as public_submit
        store=ReviewsStore()
        if not await run_in_threadpool(lambda:store.settings()['enabled']):return Response(status_code=404)
        await run_in_threadpool(public_submit,store,token,payload,uploads)
        return HTMLResponse(FORM_STYLE+'<main><h1>Thank you</h1><p>Your review has been received by Sports Cave and is awaiting review.</p></main>',headers=PUBLIC_FORM_HEADERS)
    except (ValueError,TypeError):return HTMLResponse(FORM_STYLE+'<main><h1>Review not submitted</h1><p>Check the fields, display permission and file sizes, then try again.</p></main>',status_code=400,headers=PUBLIC_FORM_HEADERS)
    except Exception:return Response(status_code=503)
