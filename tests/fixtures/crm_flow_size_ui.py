"""Real five-flow preview surfaces and original action-area meter; offline facts."""
from pathlib import Path
source=Path('tests/fixtures/crm_ultimate_preview.py').read_text()
source=source.replace("automation_canvas(doc,CFG,'fixture',store)","automation_canvas(doc,CFG,'fixture',store)")
source=source.replace("with preview:automation_canvas", "with preview:automation_canvas")
source=source.replace("store,doc,metrics=st.session_state[slot]",'''store,doc,metrics=st.session_state[slot]
if st.query_params.get('smart')=='1':
    import crm_smart_catalogue
    from tests.test_crm_smart_catalogue import fixture
    from tests.test_crm_modular_catalogue import catalogue_doc
    from crm_lifecycle_shopify import PRODUCT_AVAILABILITY
    cat,authority,_=fixture()
    crm_smart_catalogue.Catalogue=lambda *a,**k:cat
    if not store.preview_shop.__dict__.get('_smart_fixture_configured'):
        original=store.preview_shop.query.side_effect
        store.preview_shop.query.side_effect=lambda q,v,*a,_source=original,_authority=authority:_authority.query(q,v,*a) if q==PRODUCT_AVAILABILITY else _source(q,v,*a)
        store.preview_shop._smart_fixture_configured=True
    store.preview_shop.storefront_query.side_effect=authority.storefront_query.side_effect
    if not any(s.get('type')=='catalogue' for s in doc['middle_sections']):
        section=catalogue_doc()['middle_sections'][-1];section['products']=[];section['settings']['smart']=True
        parts=deepcopy(doc['middle_sections']);parts.append(section);commit_middle(doc,parts)
    if kind=='abandoned':
        cid=st.session_state['_automation_checkout_pin']['last_good']['customer_id']
        c={'id':cid,'defaultAddress':{'countryCodeV2':'AU'}}
        st.session_state.setdefault('_smart_preview_contexts',{})[cid]=(time.monotonic()+120,c,[])
''')
# Mount the same action-area fragment used by crm_automation_toolbar, after the
# existing editor owns its session context. The original preview stays unchanged.
source+='''
from crm_email_size_ui import size_meter
st.session_state['automation_editor_context']=(store,{})
with st.container(horizontal=True,key='fixture-actions'):
    size_meter(st.session_state['automation_editor'],'fixture-size-'+kind,CFG)
'''
exec(compile(source,'ultimate-preview-fixture','exec'))
