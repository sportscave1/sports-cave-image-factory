"""Compact middle composer + lazy product picker using the existing component bridge."""
from copy import deepcopy
from pathlib import Path
import logging
import uuid
import streamlit as st
import streamlit.components.v1 as components
from crm_campaign_recovery import autosaving, flush_current
from crm_component_json import render_component
from crm_middle_sections import middle_sections, apply_event, commit_middle
from crm_catalogue import Catalogue, product_issues, price_label, refresh_catalogues


def rerun_editor():
    from crm_email_editor_context import current,mark_content_edit
    editor=current(st.session_state)
    if editor:mark_content_edit(st.session_state,editor)
    flush_current()
    from streamlit.errors import StreamlitAPIException
    try: st.rerun(scope='fragment')
    except StreamlitAPIException: st.rerun()


@st.dialog('Select products', width='medium', on_dismiss='rerun')
@autosaving
def product_picker(doc, section_id, catalogue, key, editor_key=None):
    section = next(s for s in middle_sections(doc) if s['id']==section_id)
    basket = st.session_state.setdefault(key+'basket', {p['id']:deepcopy(p) for p in section['products']})
    query = st.text_input('Search products…', max_chars=150, key=key+'search_text')
    try:
        choices = catalogue.collections()
        if choices.get('stale'): st.caption('Showing cached collections. Refresh will retry shortly.')
        st.session_state[key+'collections'] = choices['rows']
    except Exception:
        st.caption('Collections temporarily unavailable. Existing selection retained.')
    options = {r['id']:r['title'] for r in st.session_state.get(key+'collections',[])}
    old = st.session_state.get(key+'collection','')
    if old and old not in options: options[old] = 'Selected collection (unavailable)'
    collection = st.selectbox('Collection', ['',*options], format_func=lambda i:options.get(i,'All collections'), key=key+'collection')
    active = st.checkbox('Active only', True, key=key+'active_control')
    submitted = st.button('Search', key=key+'search_button')
    # Text inputs submit on Enter/blur, not every keystroke. Dialog reruns stay local.
    filters = (query.strip(),active,collection)
    if filters != st.session_state.get(key+'filters'):
        st.session_state[key+'filters'] = filters
        st.session_state[key+'offset'] = 0; st.session_state.pop(key+'page', None)
        st.session_state[key+'generation'] = uuid.uuid4().hex
    try:
        if key+'page' not in st.session_state:
            with st.spinner('Loading products…'):
                page = catalogue.search(query,st.session_state.get(key+'offset',0),active,collection)
                st.session_state[key+'page'] = page
        page = st.session_state[key+'page']
        facts = page['rows']
        if page.get('stale'):st.caption('Showing cached products. Refresh will retry shortly.')
        if not facts:st.caption('No products found in this collection.' if collection else 'No matching products.')
        for p in facts:
            a,b,c = st.columns([1,7,2], vertical_alignment='center')
            selected = a.checkbox('Select '+p['title'],p['id'] in basket,label_visibility='collapsed',key=key+st.session_state[key+'generation']+p['id'])
            if selected: basket[p['id']] = p
            else: basket.pop(p['id'], None)
            with b.container(horizontal=True,vertical_alignment='center'):
                from crm_campaign_html import email_image_url
                if email_image_url(p['image']): st.image(email_image_url(p['image']),width=38)
                st.text(p['title'])
            c.caption(p['status'])
        left,right=st.columns(2)
        if left.button('Previous',disabled=st.session_state.get(key+'offset',0)==0,key=key+'prev'):
            st.session_state[key+'offset']-=12;st.session_state.pop(key+'page');st.session_state[key+'generation']=uuid.uuid4().hex;st.rerun(scope='fragment')
        if right.button('Next',disabled=not page['more'],key=key+'next'):
            st.session_state[key+'offset']=st.session_state.get(key+'offset',0)+12;st.session_state.pop(key+'page');st.session_state[key+'generation']=uuid.uuid4().hex;st.rerun(scope='fragment')
        st.caption('Selected: '+str(len(basket))+' / 12')
        cancel,add=st.columns(2)
        if cancel.button('Cancel',key=key+'cancel'):
            st.session_state.pop(key+'basket',None);st.rerun()
        if add.button('Add selected',type='primary',disabled=len(basket)>12,key=key+'add'):
            with st.spinner('Checking current product facts…'):
                selected = catalogue.resolve(list(basket),doc['market'],fresh=True)
            sections=middle_sections(doc)
            next(s for s in sections if s['id']==section_id)['products']=selected
            commit_middle(doc,sections);doc['copy_reviewed']=False
            if editor_key:
                previous=st.session_state.get(editor_key+'catalogue_loaded',(doc['market'],()))
                known=set(previous[1]) if previous[0]==doc['market'] else set()
                known.update(p['id'] for p in selected)
                visible=tuple(sorted({p['id'] for s in sections if s['type']=='catalogue' and s['visible'] for p in s['products']}))
                if set(visible)<=known:
                    st.session_state[editor_key+'catalogue_loaded']=(doc['market'],visible)
            st.session_state.pop(key+'basket',None);st.rerun()
    except Exception as exc:
        logging.getLogger(__name__).warning('crm_catalogue_picker_failed type=%s',type(exc).__name__)
        st.warning('Product catalogue is temporarily unavailable. Your selections are retained.')
        if st.button('Retry product loading',key=key+'retry'):
            st.session_state.pop(key+'page',None);st.rerun(scope='fragment')


def middle_editor(doc, key, shop, store=None):
    # Opening a saved snapshot is read-only. The existing Refresh action and
    # final test/send validation own fresh product facts, never tab activation.
    sections = middle_sections(doc)
    warnings = {s['id']:[issue for p in s['products'] for issue in product_issues(p,s['settings'])]
                for s in sections if s['type']=='catalogue'}
    component = components.declare_component('crm_middle_sections_v2',path=str(Path(__file__).parent/'components'/'crm_sections'))
    templates=[]
    if store is not None:
        from crm_campaign_library import library_rows
        from crm_store import StoreUnavailable
        try:templates=[{k:r[k] for k in ('id','name','version')} for r in library_rows(store)]
        except StoreUnavailable:st.caption('Templates temporarily unavailable. Add HTML and Add Catalogue remain available.')
    from crm_image_prompt import image_prompt
    from crm_email_editor_context import current
    editor = current(st.session_state,{})
    campaign_name = editor.get('name', '') if editor.get('document') is doc else ''
    from crm_email_prompt import handoff
    from crm_prompt_copy import clipboard_script
    verified=handoff(st.session_state,editor) if campaign_name else None
    event = render_component(component,preview_debounce=350 if getattr(store,'email_mode',None)=='automation' else 750,clipboard_script=clipboard_script(),history_scope=doc.get('campaign_key',key),image_prompt=image_prompt(doc,campaign_name,verified),sections=sections,templates=templates,warnings=warnings,ack=st.session_state.get(key+'section_event'),key=key+'middle',default=None)
    if st.session_state.get(key+'section_error'):st.warning(st.session_state.pop(key+'section_error'))
    if event and event.get('event') != st.session_state.get(key+'section_event'):
        st.session_state[key+'section_event'] = event.get('event')
        try:
            if event.get('type')=='add' and event.get('kind')=='checkout':
                if store is None:raise ValueError('Template storage is unavailable.')
                from crm_checkout_section import insert
                insert(store,doc,event);rerun_editor()
            elif event.get('type')=='add' and event.get('kind')=='template':
                if store is None:raise ValueError('Template storage is unavailable.')
                from crm_campaign_library import insert_saved_template
                from crm_store import StoreUnavailable
                try:
                    with st.spinner('Loading template...'):
                        insert_saved_template(store,doc,event.get('template_id'),event.get('version'))
                except (ValueError,StoreUnavailable):raise ValueError('Template could not be loaded.') from None
                rerun_editor()
            elif event.get('type')=='picker':
                if not any(s['id']==event.get('id') and s['type']=='catalogue' for s in sections): raise ValueError('Catalogue not found.')
                picker_key=key+'picker_'+event['id']
                for suffix in ('basket','page'):st.session_state.pop(picker_key+suffix,None)
                st.session_state[picker_key+'generation']=uuid.uuid4().hex
                product_picker(doc,event['id'],Catalogue(shop),picker_key,editor_key=key)
            elif event.get('type')=='refresh':
                with st.spinner('Refreshing catalogue facts…'):
                    refreshed=refresh_catalogues(doc,Catalogue(shop))
                doc.update(refreshed);doc['copy_reviewed']=False
                rerun_editor()
            else:
                apply_event(doc,event);doc['copy_reviewed']=False
                rerun_editor()
        except ValueError as exc:
            st.session_state[key+'section_error']=str(exc);rerun_editor()
        except Exception as exc:
            logging.getLogger(__name__).warning('crm_catalogue_editor_failed type=%s',type(exc).__name__)
            st.session_state[key+'section_error']='Catalogue facts could not be refreshed. Saved content is retained; retry before testing.'
            rerun_editor()
