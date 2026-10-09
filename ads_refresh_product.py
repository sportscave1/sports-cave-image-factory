"""Explicit product corrections owned by one Creative Refresh workspace."""
from copy import deepcopy
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
import meta_review_products as products


def corrected_url(url,previous):
    if products.product_url_handle(previous)==products.product_url_handle(url):return previous
    target=urlsplit(url)
    query=parse_qsl(target.query,keep_blank_values=True)
    keys={k.casefold() for k,_ in query}
    for key,value in parse_qsl(urlsplit(previous).query,keep_blank_values=True):
        if (key.casefold().startswith('utm_') or key.casefold() in ('fbclid','gclid','msclkid')) and key.casefold() not in keys:
            query.append((key,value));keys.add(key.casefold())
    return urlunsplit((target.scheme,target.netloc,target.path,urlencode(query),target.fragment))


def correct(state,row,previous_url):
    """Never updates Meta Review's shared mapping or another saved result."""
    import ads_page as ads
    source=state.get('meta-review-refresh-source')
    product=products.canonical(row) if row else None
    if not source or not product:return False
    updated=deepcopy(source)
    original=deepcopy(source.get('product_mapping') or {})
    updated['product_mapping']=deepcopy(product)
    updated.update({k:v for k,v in product.items() if k!='canonical_row'})
    updated.setdefault('product_correction',{'ad_id':source.get('ad_id'),'decision_id':source.get('decision_id'),'original_mapping':original})
    updated['product_correction']['selected_mapping']=deepcopy(product)
    state['meta-review-refresh-source']=updated
    url=corrected_url(product['product_url'],previous_url)
    state[ads.ADS_PRODUCT_URL_KEY]=url
    state[ads.ADS_PRODUCT_URL_LAST_AUTO_VALUE_KEY]=url
    state[ads.ADS_PRODUCT_URL_MANUALLY_EDITED_KEY]=True
    state.pop('meta-review-product-error',None)
    return True


def select_from_url(rows):
    import ads_page as ads
    state=ads.st.session_state
    handle=products.product_url_handle(state.get(ads.ADS_PRODUCT_URL_KEY))
    matches={ads._edition_ops_product_selector_identity(row):row for row in rows
             if handle and ads._edition_ops_product_handle_from_row(row).casefold()==handle}
    if len(matches)!=1:
        state['meta-review-product-error']='URL could not be matched to one catalogue product. Search and select the correct product name.'
        return
    identity,row=next(iter(matches.items()))
    state[ads.ADS_PRODUCT_SELECTOR_KEY]=identity
    ads._on_ads_product_selector_changed(list(rows))
