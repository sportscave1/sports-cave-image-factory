"""Async picker inside the existing section editor. No imperative reruns."""
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore
from time import monotonic
from copy import deepcopy
import logging
import streamlit as st
from crm_discount_api import search, code_page, selectable

POOL=ThreadPoolExecutor(max_workers=2,thread_name_prefix='discount-search')
CAPACITY=BoundedSemaphore(4)
TIMEOUT=30


def state(key):
    return st.session_state.setdefault(key+'discount_picker',{'open':False,'term':'','rows':[],
        'pageInfo':{},'more_codes':[],'error':'','generation':0,'loaded':False,'group':None,'loaded_at':0})


def launch(value,fn,*,append=False,bulk_id=None):
    value['generation']+=1
    previous=value.pop('job',None)
    if previous:previous['future'].cancel()
    if not CAPACITY.acquire(blocking=False):
        value['error']='Discount search is busy. Retry shortly.'
        return
    def run():
        try:return fn()
        finally:CAPACITY.release()
    try:future=POOL.submit(run)
    except Exception:CAPACITY.release();raise
    future.add_done_callback(lambda f:CAPACITY.release() if f.cancelled() else None)
    value['job']={'future':future,'started':monotonic(),'generation':value['generation'],
                  'append':append,'bulk_id':bulk_id}
    value['error']=''


def collect(value):
    job=value.get('job')
    if not job:return
    if monotonic()-job['started']>=TIMEOUT:
        job['future'].cancel();value.pop('job',None)
        value['error']='Shopify search timed out. Your email and previous results are retained. Use Refresh to retry.'
        return
    if not job['future'].done():return
    value.pop('job',None)
    if job['generation']!=value['generation']:return
    try:
        result=job['future'].result()
        rows=([*value['rows'],*result['rows']] if job['append'] else result['rows'])
        value['rows']=list({(r['id'],r['code'].casefold()):r for r in rows}.values())
        value['pageInfo']=result['pageInfo']
        value['more_codes']=([b for b in value['more_codes'] if b['id']!=job['bulk_id']]
            if job['append'] else [])+result.get('more_codes',[])
        if value.get('group'):value['more_codes']=[]
        value['loaded']=True;value['loaded_at']=monotonic();value['error']=''
    except Exception as exc:
        logging.getLogger(__name__).warning('discount_picker_failed type=%s',type(exc).__name__)
        value['error']=str(exc) if isinstance(exc,ValueError) else 'Shopify discount search failed. Check the app’s read_discounts access and retry. Previous results are retained.'


def view(key,*,trigger):
    value=state(key);collect(value)
    return {k:deepcopy(value[k]) for k in ('open','term','pageInfo','more_codes','error','loaded','group')}|{
        'pending':bool(value.get('job')),
        'rows':[{k:r[k] for k in ('id','code','value','label','status','title')}|
                 {'unavailable':selectable(r) or ('' if trigger=='abandoned' else 'Requires an abandoned-checkout recovery email.')}
                 for r in value['rows']],
        'notice':'' if trigger=='abandoned' else 'Recovery discounts require an abandoned-checkout email. Other email types remain unchanged.'}


def is_event(event):
    return isinstance(event,dict) and (str(event.get('type','')).startswith('discount_') or
        (event.get('type')=='add' and event.get('kind')=='discount'))


def handle(shop,doc,key,event,*,trigger):
    """Component widget callback, before fragment rendering."""
    value=state(key);collect(value)
    kind=event.get('type')
    from crm_middle_sections import apply_event,middle_sections
    if event.get('base')!=[s['id'] for s in middle_sections(doc)]:raise ValueError('Sections changed. Reopen Add Discount.')
    before=deepcopy(doc)
    existing={s['id']:s.get('html') for s in middle_sections(doc)}
    if any(existing.get(k)!=v for k,v in (event.get('edits') or {}).items()):
        apply_event(doc,{**event,'type':'order','ids':event['base']})
    if kind in ('add','discount_open'):
        value['open']=True;value['section_id']=event.get('id')
        if trigger!='abandoned':return before!=doc
        if (not value['loaded'] or monotonic()-value['loaded_at']>=60) and not value.get('job'):
            term=value['term'];group=value['group']
            launch(value,lambda:code_page(shop,group['id'],None,term=term) if group else search(shop,term))
    elif kind=='discount_close':value['open']=False
    elif kind in ('discount_search','discount_refresh'):
        if trigger!='abandoned':return before!=doc
        term=str(event.get('term',value['term'])).strip()[:100];value['term']=term
        value['pageInfo']={};value['more_codes']=[]
        group=value['group']
        launch(value,lambda:code_page(shop,group['id'],None,term=term,refresh=kind=='discount_refresh') if group else search(shop,term,refresh=kind=='discount_refresh'))
    elif kind=='discount_next' and not value.get('job'):
        page=value['pageInfo']
        if page.get('hasNextPage'):
            term=value['term'];after=page['endCursor'];group=value['group']
            launch(value,lambda:code_page(shop,group['id'],after,term=term) if group else search(shop,term,after),append=True)
    elif kind=='discount_codes' and not value.get('job'):
        bulk=next((b for b in value['more_codes'] if b['id']==event.get('id')),None)
        if bulk:
            value['group']={'id':bulk['id'],'title':bulk['title']};value['term']=''
            value['pageInfo']={};value['more_codes']=[]
            # A group's cursor belongs to its query. Restart before applying a
            # prefix; never reuse an unfiltered cursor with a different search.
            launch(value,lambda:code_page(shop,bulk['id'],None))
    elif kind=='discount_browse':
        value['group']=None;value['term']='';value['pageInfo']={};value['more_codes']=[]
        launch(value,lambda:search(shop))
    elif kind=='discount_select':
        if value.get('job') or value['error']:raise ValueError('Wait for a successful discount search before selecting.')
        row=next((r for r in value['rows'] if r['id']==event.get('id') and r['code']==event.get('code')),None)
        if not row:raise ValueError('Discount results changed. Search again.')
        from crm_discount_section import insert
        insert(doc,row,{**event,'section_id':value.get('section_id')},trigger=trigger)
        value['open']=False
    elif kind!='discount_poll':raise ValueError('Unknown discount action.')
    return before!=doc


def callback(shop,doc,key,*,trigger):
    event=st.session_state.get(key+'middle')
    if not is_event(event) or event.get('event')==st.session_state.get(key+'section_event'):return
    st.session_state[key+'section_event']=event.get('event')
    try:
        if handle(shop,doc,key,event,trigger=trigger):
            from crm_email_editor_context import current,mark_content_edit
            from crm_campaign_recovery import flush_current
            editor=current(st.session_state)
            if editor:mark_content_edit(st.session_state,editor)
            flush_current()
    except ValueError as exc:state(key)['error']=str(exc)
