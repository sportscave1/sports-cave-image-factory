"""Small queue composer using the same catalog, metadata and prompt builder as Ads."""
from uuid import UUID, uuid4
import design_publish_ad as queue


def catalog():
    import ads_page as ads
    from ads_product_catalog import recommend_new_ads_category
    records=ads.build_ads_product_selector_records(ads.load_edition_ops_product_rows())
    products=[]
    for row in records:
        sport=recommend_new_ads_category(row['row'],row['label'])
        country=queue.country_name(row['row'].get('primary_market')) or {
            'NFL':'USA','Baseball':'USA','Basketball':'USA','NASCAR':'USA','AFL':'Australia','NRL':'Australia',
        }.get(sport,'Australia')
        if row.get('product_url'):
            products.append(dict(id=row['identity'],name=row['label'],sport=sport,country=country))
    return dict(products=products,countries=list(queue.COUNTRIES),
                sports=[s for s in ads.CATEGORY_OPTIONS if s!='Select category'],types=['Instant Experience'])


def enqueue(user, body):
    import ads_page as ads
    from ads_companion_queue import enqueue as submit
    from product_upload_staff_queue import can_control_queues
    if not can_control_queues(user): raise PermissionError('A companion administrator must add queued ads.')
    request_id=str(UUID(body.get('request_id','')))
    kind=body.get('type','Instant Experience')
    if kind!='Instant Experience': raise ValueError('Automatic ads currently support Instant Experience.')
    rows=ads.load_edition_ops_product_rows()
    records=ads.build_ads_product_selector_records(rows)
    record=next((r for r in records if r['identity']==body.get('product')),None)
    if not record: raise ValueError('Select a current Edition Ops product.')
    selection=ads.resolve_ads_product_selector_value(record['identity'],records=records)
    sport,country=queue.check_request(user,body.get('sport'),body.get('country'))
    result=ads.build_ads_result_record(ads._product_name_from_edition_ops_row(record['row']),sport,country,kind,product_id=record['product_id'],
        product_url=record['product_url'],variation_token=request_id,
        product_metadata=ads.instant_experience_product_metadata_from_selection(selection,category=sport))
    return submit(user,result,selection,request_key=request_id)


def render():
    import streamlit as st
    from ads_page import current_ads_user
    with st.expander('Add to queue',expanded=False):
        try: data=catalog()
        except Exception:
            st.warning('Could not load products. Try again shortly.');return
        products={row['id']:row for row in data['products']}
        if not products: st.info('No eligible Edition Ops products found.');return
        product=st.selectbox('Product',list(products),index=None,format_func=lambda key:products[key]['name'],key='cq-ad-product')
        if not product:return
        row=products[product]
        if st.session_state.get('cq-ad-selected')!=product:
            st.session_state.update({'cq-ad-selected':product,'cq-ad-country':row['country'],
                'cq-ad-sport':row['sport'] or data['sports'][0],'cq-ad-request':str(uuid4())})
        with st.form('cq-ad-add'):
            a,b,c=st.columns(3)
            sport=a.selectbox('Sport',data['sports'],key='cq-ad-sport')
            country=b.selectbox('Country',data['countries'],key='cq-ad-country')
            kind=c.selectbox('Type',data['types'])
            if st.form_submit_button('Add to queue'):
                try:
                    selection=(product,sport,country,kind)
                    if st.session_state.get('cq-ad-last-input')!=selection:
                        st.session_state['cq-ad-request']=str(uuid4())
                        st.session_state['cq-ad-last-input']=selection
                    enqueue(current_ads_user(),dict(product=product,sport=sport,country=country,type=kind,request_id=st.session_state['cq-ad-request']))
                    st.success('Added to Ads queue.')
                except (ValueError,PermissionError) as error:st.error(str(error))


async def route(request):
    from files_upload_api import _request_user,_same_origin
    from product_upload_staff_queue import can_control_queues
    from product_upload_api import HEADERS,failure
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse
    try:
        user=await run_in_threadpool(_request_user,request,required_page='Upload Companion')
        if not can_control_queues(user):raise PermissionError('Administrator required.')
        if request.method=='GET':result=await run_in_threadpool(catalog)
        else:
            if not request.headers.get('origin') or not _same_origin(request):raise PermissionError('Request origin rejected.')
            body=await request.json()
            if not isinstance(body,dict):raise ValueError('Invalid ad request.')
            result=await run_in_threadpool(enqueue,user,body)
        return JSONResponse(result,headers=HEADERS)
    except Exception as error:return failure(error)
