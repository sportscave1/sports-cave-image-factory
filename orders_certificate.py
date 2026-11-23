"""Resolve a completed unit's current Shopify certificate only when opened."""
from urllib.parse import urlparse
from starlette.concurrency import run_in_threadpool
from starlette.responses import RedirectResponse


def url(allocation):
    import prodigi_preparation as prep,certificate_engine
    import certificate_frame_fulfilment as frames
    if frames.is_unit(allocation):
        import collector_vault as vault
        _,certificate,_,request=frames._read(allocation,prep.connect)
        certificate.update(order_customer_id=request['shopify_customer_id'])
        link=vault._certificate_public_row(certificate).get('pdf_url')
        if not link:raise ValueError('The original certificate PDF is unavailable.')
        return link
    with prep.connect() as c,c.cursor() as q:
        q.execute('SELECT * FROM edition_orders WHERE id=%s',(allocation,))
        unit=q.fetchone()
    if not unit or unit.get('allocation_valid') is not True or unit.get('invalidated_at'):
        raise ValueError('This edition allocation is unavailable.')
    state=certificate_engine.read_order_certificate_state(unit['shopify_order_id'])
    def line(value):return str(value or '').rsplit('/',1)[-1]
    matches=[r for r in state.get('certificates',[]) if
        line(r.get('line_item_id') or r.get('shopify_line_item_id'))==line(unit['shopify_line_item_id'])
        and int(r.get('edition_number') or 0)==unit['edition_number']
        and int(r.get('line_item_unit_index') or 1)==int(unit.get('allocation_index') or unit.get('unit_ordinal') or 1)]
    if len(matches)!=1:raise ValueError('The exact uploaded certificate is missing or ambiguous. Open the certificate controls for review.')
    record=matches[0]
    link=record.get('pdf_url') or record.get('certificate_pdf_url') or record.get('certificate_url') or record.get('shopify_file_url')
    parsed=urlparse(str(link or ''))
    if parsed.scheme!='https' or parsed.hostname!='cdn.shopify.com' or parsed.username or parsed.password:
        raise ValueError('No verified Shopify-hosted certificate PDF is available.')
    return link


async def open_certificate(request):
    from files_upload_api import _request_user
    from product_upload_api import HEADERS,failure
    try:
        await run_in_threadpool(_request_user,request,required_page='Orders')
        allocation=request.query_params.get('allocation_id','')
        if not allocation.isdigit() or int(allocation)<=0:raise ValueError('Select an allocated edition in Orders.')
        link=await run_in_threadpool(url,int(allocation))
        return RedirectResponse(link,headers=HEADERS)
    except Exception as error:return failure(error)
