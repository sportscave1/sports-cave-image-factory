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
        from crm_tracking import public_https
        for row in rows:
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

FORM_STYLE='<style>body{font:16px system-ui;color:#191919;background:#faf8f3;margin:0;padding:24px}main{max-width:560px;margin:24px auto;background:white;padding:24px;border:1px solid #e8e2d7;border-radius:12px;box-sizing:border-box}input,textarea,select,button{font:inherit;max-width:100%;box-sizing:border-box;width:100%;padding:10px;margin:6px 0 16px;border:1px solid #d4cfc5;border-radius:5px}button{background:#c7a13f;color:#181818}label{display:block}.trap{display:none}input[type=checkbox]{width:auto}h1{font-size:24px}</style>'

@router.get('/reviews/request/{token}',response_class=HTMLResponse)
async def review_form(token:str,request:Request):
    if not allow_rate('review-form:'+str(request.client.host if request.client else 'unknown')):return Response(status_code=429)
    try:
        store=ReviewsStore();row=await run_in_threadpool(token_row,store,token)
        if row['review_id']:return HTMLResponse(FORM_STYLE+'<main><h1>Thank you</h1><p>Your review has been received.</p></main>',headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
        product=await run_in_threadpool(store.match_product,{'product_id':row['product_id']})
        if not product:raise ValueError()
        html=FORM_STYLE+'<main><h1>Share your review</h1><p>'+escape(product['title'])+'</p><form method="post"><label>Rating<select name="rating" required>'+''.join('<option value="'+str(n)+'">'+str(n)+' stars</option>' for n in (5,4,3,2,1))+'</select></label><label>Display name<input name="reviewer_name" maxlength="120" required></label><label>Title<input name="title" maxlength="200"></label><label>Review<textarea name="body" maxlength="5000" required rows="5"></textarea></label><label class="trap" aria-hidden="true">Website<input name="website" tabindex="-1" autocomplete="off"></label><label><input type="checkbox" name="display_consent" value="yes" required>Display my review and chosen name publicly</label><button type="submit">Submit review</button></form></main>'
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
        if request.headers.get('content-type','').split(';')[0]!='application/x-www-form-urlencoded':return Response(status_code=415)
        fields=parse_qs((await bounded_body(request,24000)).decode('utf-8'),keep_blank_values=True)
        if any(len(v)!=1 for v in fields.values()):return Response(status_code=400)
        payload={k:v[0] for k,v in fields.items()};payload['display_consent']=payload.get('display_consent')=='yes'
        await run_in_threadpool(submit,ReviewsStore(),token,payload)
        return HTMLResponse(FORM_STYLE+'<main><h1>Thank you</h1><p>Your review has been received.</p></main>',headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
    except (ValueError,TypeError):return HTMLResponse(FORM_STYLE+'<main><h1>Review not submitted</h1><p>Check your review and link, then try again.</p></main>',status_code=400)
    except Exception:return Response(status_code=503)
