"""Lazy, bounded background discount search inside the existing Settings tab."""
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore
from time import monotonic
import streamlit as st
from crm_discount_api import search,code_page

POOL=ThreadPoolExecutor(max_workers=2,thread_name_prefix='discount-search')
CAPACITY=BoundedSemaphore(4)


def change(editor,value):
    doc=editor['document']
    if doc.get('recovery_discount')==value:return
    if value:doc['recovery_discount']=value
    else:doc.pop('recovery_discount',None)
    from crm_email_editor_context import mark_content_edit
    from crm_campaign_recovery import flush_current
    from crm_campaign_library import COMPOSER_TARGET
    mark_content_edit(st.session_state,editor);flush_current()
    st.rerun(scope=COMPOSER_TARGET or 'fragment')


def launch(key,fn):
    if not CAPACITY.acquire(blocking=False):
        st.session_state[key+'error']='Discount search is busy. Try again shortly.'
        return
    def run():
        try:return fn()
        finally:CAPACITY.release()
    try:future=POOL.submit(run)
    except Exception:CAPACITY.release();raise
    st.session_state[key+'job']={'future':future,'started':monotonic()}


def repaint():
    from crm_campaign_library import COMPOSER_TARGET
    st.rerun(scope=COMPOSER_TARGET or 'fragment')


def control(shop,editor,key,trigger='abandoned'):
    key=key+'discount_'
    if trigger!='abandoned':
        st.markdown('**Recovery discount**')
        st.toggle('Apply Shopify discount automatically',False,disabled=True,key=key+'unavailable',help='Requires the original abandoned-checkout recovery link.')
        return
    # The composer already owns a fragment. Keep events in that fragment on
    # runtimes without keyed parent reruns; a nested timer would never start.
    _control(shop,editor,key)


def _control(shop,editor,key):
    saved=editor['document'].get('recovery_discount')
    st.markdown('**Recovery discount**')
    enabled=st.toggle('Apply Shopify discount automatically',value=bool(saved),key=key+'enabled')
    if not enabled:
        if saved:change(editor,None)
        return
    if saved:
        st.caption(saved['code']+' · '+saved['value'])
        if st.button('Clear discount',key=key+'clear'):change(editor,None)
    st.caption('Shopify checks eligibility at checkout. The best eligible standard offer applies; existing codes are never silently replaced.')
    st.html('''<style>
    [data-testid="stPopoverBody"]:has(input[aria-label="Search code or name"]){width:300px!important;min-width:0!important;max-width:calc(100vw - 24px)!important;box-sizing:border-box}
    </style>''')
    with st.popover('Select Shopify discount',width=280,key=key+'popover',on_change='rerun'):
        term=st.text_input('Search code or name',key=key+'search',max_chars=100)
        cols=st.columns(2)
        go=cols[0].button('Search',key=key+'go');refresh=cols[1].button('Refresh',key=key+'refresh')
        if go or refresh:
            launch(key,lambda:search(shop,term,refresh=refresh));repaint()
        job=st.session_state.get(key+'job')
        if job and not job['future'].done():
            if monotonic()-job['started']>=30:
                st.session_state[key+'error']='Shopify search timed out. Editing is available; retry Search.'
                st.session_state.pop(key+'job',None);repaint()
            st.caption('Loading Shopify discounts…')
        elif job:
            try:
                st.session_state[key+'results']=job['future'].result()
                st.session_state.pop(key+'error',None)
            except Exception as error:
                st.session_state[key+'error']=str(error) if isinstance(error,ValueError) else 'Shopify discounts unavailable. Check read_discounts permission or retry.'
            st.session_state.pop(key+'job',None)
            st.session_state.pop(key+'choice',None)
            repaint()
        if st.session_state.get(key+'error'):st.caption(st.session_state[key+'error'])
        results=st.session_state.get(key+'results') or {};rows=results.get('rows',[])
        if results:st.caption(str(len(rows))+' code'+('s' if len(rows)!=1 else '')+' loaded' if rows else 'No matching codes. Try the full code or discount name.')
        picked=st.selectbox('Shopify discount',range(len(rows)),index=None,placeholder='Search Shopify discounts',
            format_func=lambda i:rows[i]['code']+' — '+rows[i]['value']+' · '+rows[i]['status'].title(),key=key+'choice',disabled=bool(st.session_state.get(key+'job')) or not rows)
        if picked is not None and picked<len(rows):
            row=rows[picked];st.caption(row['label']+' · '+row['status'].title())
            if row['summary']:st.caption(row['summary'])
            if not row['supported']:st.caption('Shopify does not expose a supported value for this code; it cannot be applied automatically.')
            if st.button('Use discount',disabled=not row['supported'],key=key+'use'):
                change(editor,{k:row[k] for k in ('id','code','value','type')})
        if results.get('pageInfo',{}).get('hasNextPage') and st.button('Next results',key=key+'next'):
            after=results['pageInfo']['endCursor'];launch(key,lambda:search(shop,term,after));repaint()
        for index,bulk in enumerate(results.get('more_codes',[])):
            if st.button('More codes · '+bulk['title'],key=key+'bulk'+str(index)):
                launch(key,lambda b=bulk:code_page(shop,b['id'],b['after']));repaint()
        if not saved:st.caption('Choose a code to enable this email. Other emails remain unchanged.')
        if st.session_state.get(key+'job'):
            import json,uuid
            with st.container(key=key+'poll'):
                st.button('Check discount search',key=key+'check')
            selector=json.dumps('.st-key-'+key+'poll')
            st.html('<style>.st-key-'+key+'poll{display:none}</style><script>/*'+uuid.uuid4().hex+'*/'+'''
              clearTimeout(window.scDiscountSearchPoll);
              window.scDiscountSearchPoll=setTimeout(()=>{
                const input=document.querySelector('[data-testid="stPopoverBody"] input[aria-label="Search code or name"]');
                if(input?.getClientRects().length)document.querySelector('''+selector+'''+ ' button')?.click();
              },500);
            </script>''',unsafe_allow_javascript=True)
