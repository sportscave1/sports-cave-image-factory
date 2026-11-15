"""Generate offline browser inputs from the real local preview/render code."""
import json
from pathlib import Path
from unittest.mock import patch
from crm_local_preview import model
from crm_middle_sections import middle_sections
from crm_flow_preview import hydrate,verify
from crm_collector_images import configurations,marker,render
from tests.test_crm_flow_customer_preview import document,preview_wire,AT,CFG
from tests.test_crm_collector_personalisation import product,P,Q


def build():
    store,shop,row,candidate,operational=preview_wire();state={}
    with patch('crm_lifecycle_shopify.order_facts',return_value=operational),patch('crm_flow_preview.now',return_value=AT):
        data=verify(store,shop,row,candidate)
    store.preview_document=lambda doc:hydrate(state,store,doc)
    pin={'selected':data,'options':[candidate]}
    results=[]
    with patch('streamlit.session_state',state),patch('crm_flow_preview.context',return_value=pin),patch('crm_personalisation_data.allocation',return_value=None):
        for key in ('purchased','collections'):
            doc=document(key);cfg=configurations(doc)[0]
            products=[dict(id=P,title='Fixture purchased Motorsport artwork',image='https://cdn.shopify.com/fixture-artwork.jpg',url=product(P)['onlineStoreUrl'],quantity=2)] if key=='purchased' else [dict(id='gid://shopify/Product/'+str(i),title='Fixture Motorsport recommendation '+str(i),image='https://cdn.shopify.com/fixture-artwork.jpg',url=product('gid://shopify/Product/'+str(i))['onlineStoreUrl']) for i in range(2,8)]
            facts={'recipient':data['_customer']['id'],'blocks':{marker(cfg):products}}
            with patch('crm_collector_resolver.resolve',return_value=facts):
                results.append(dict(key=key,model=model(doc,CFG,store),sections=middle_sections(doc),html=render(doc,facts['blocks'])['custom_html']))
    return results


if __name__=='__main__':
    target=Path('.tmp-flow-preview');target.mkdir(exist_ok=True)
    (target/'browser-input.json').write_text(json.dumps(build(),default=str),encoding='utf-8')
