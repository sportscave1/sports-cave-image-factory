"""Compact middle composer + lazy product picker using the existing component bridge."""
from copy import deepcopy
from pathlib import Path
import logging
import uuid
import streamlit as st
import streamlit.components.v1 as components
from crm_middle_sections import middle_sections, apply_event, commit_middle
from crm_catalogue import Catalogue, product_issues, price_label, refresh_catalogues


def rerun_editor():
    from streamlit.errors import StreamlitAPIException
    try: st.rerun(scope='fragment')
    except StreamlitAPIException: st.rerun()


@st.dialog('Select products', width='medium', on_dismiss='rerun')
def product_picker(doc, section_id, catalogue, key):
    section = next(s for s in middle_sections(doc) if s['id']==section_id)
    basket = st.session_state.setdefault(key+'basket', {p['id']:deepcopy(p) for p in section['products']})
    with st.form(key+'search'):
        query = st.text_input('Search products…', max_chars=150)
        active = st.checkbox('Active only', True)
        submitted = st.form_submit_button('Search')
    if submitted:
        st.session_state[key+'query'] = query; st.session_state[key+'active'] = active
        st.session_state[key+'offset'] = 0; st.session_state.pop(key+'page', None)
        st.session_state[key+'generation'] = uuid.uuid4().hex
    try:
        if key+'page' not in st.session_state:
            with st.spinner('Loading products…'):
                page = catalogue.search(st.session_state.get(key+'query',''),st.session_state.get(key+'offset',0),st.session_state.get(key+'active',True))
                ids = [r['id'] for r in page['rows'] if r['id']]
                page['facts'] = catalogue.resolve(ids,doc['market'])
                st.session_state[key+'page'] = page
        page = st.session_state[key+'page']
        facts = page['facts']
        if not facts:st.caption('No synced products match this search.')
        for p in facts:
            a,b,c = st.columns([1,7,2], vertical_alignment='center')
            selected = a.checkbox('Select '+p['title'],p['id'] in basket,label_visibility='collapsed',key=key+st.session_state[key+'generation']+p['id'])
            if selected: basket[p['id']] = p
            else: basket.pop(p['id'], None)
            with b.container(horizontal=True,vertical_alignment='center'):
                from crm_campaign_html import email_image_url
                if email_image_url(p['image']): st.image(email_image_url(p['image']),width=38)
                st.text(p['title'])
            ed=p['edition']; c.caption(price_label(p)+' · '+p['status']+(' · #'+format(ed['next'],'03d')+'/'+str(ed['limit']) if ed and ed['remaining'] else ''))
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
            st.session_state.pop(key+'basket',None);st.rerun()
    except Exception as exc:
        logging.getLogger(__name__).warning('crm_catalogue_picker_failed type=%s',type(exc).__name__)
        st.warning('Product catalogue is temporarily unavailable. Your selections are retained.')
        if st.button('Retry product loading',key=key+'retry'):
            st.session_state.pop(key+'page',None);st.rerun(scope='fragment')


def middle_editor(doc, key, shop, store=None):
    # Resolve only selected, visible products once per opened draft/market/selection.
    # Preview size and text edits never trigger product/edition reads.
    selection=(doc['market'],tuple(sorted({p['id'] for s in middle_sections(doc)
        if s['type']=='catalogue' and s['visible'] for p in s['products']})))
    if selection[1] and st.session_state.get(key+'catalogue_loaded')!=selection:
        st.session_state[key+'catalogue_loaded']=selection
        try:
            with st.spinner('Loading selected product facts…'):
                current=refresh_catalogues(doc,Catalogue(shop),fresh=False)
            if current!=doc:doc.update(current);doc['copy_reviewed']=False
        except Exception as exc:
            logging.getLogger(__name__).warning('crm_catalogue_load_failed type=%s',type(exc).__name__)
            st.warning('Current product facts are unavailable. Saved preview retained; refresh catalogue facts before testing.')
    sections = middle_sections(doc)
    warnings = {s['id']:[issue for p in s['products'] for issue in product_issues(p,s['settings'])]
                for s in sections if s['type']=='catalogue'}
    component = components.declare_component('crm_middle_sections_v2',path=str(Path(__file__).parent/'components'/'crm_sections'))
    event = component(sections=sections,warnings=warnings,ack=st.session_state.get(key+'section_event'),key=key+'middle',default=None)
    if st.session_state.get(key+'section_error'):st.warning(st.session_state.pop(key+'section_error'))
    if event and event.get('event') != st.session_state.get(key+'section_event'):
        st.session_state[key+'section_event'] = event.get('event')
        try:
            if event.get('type')=='add' and event.get('kind')=='template':
                if store is None:raise ValueError('Template storage is unavailable.')
                from crm_campaign_library import picker
                picker(store,doc)
            elif event.get('type')=='picker':
                if not any(s['id']==event.get('id') and s['type']=='catalogue' for s in sections): raise ValueError('Catalogue not found.')
                picker_key=key+'picker_'+event['id']
                for suffix in ('basket','page'):st.session_state.pop(picker_key+suffix,None)
                st.session_state[picker_key+'generation']=uuid.uuid4().hex
                product_picker(doc,event['id'],Catalogue(shop),picker_key)
            elif event.get('type')=='refresh':
                with st.spinner('Refreshing catalogue facts…'):
                    refreshed=refresh_catalogues(doc,Catalogue(shop))
                doc.update(refreshed);doc['copy_reviewed']=False;rerun_editor()
            else:
                apply_event(doc,event);doc['copy_reviewed']=False;rerun_editor()
        except ValueError as exc:
            st.session_state[key+'section_error']=str(exc);rerun_editor()
        except Exception as exc:
            logging.getLogger(__name__).warning('crm_catalogue_editor_failed type=%s',type(exc).__name__)
            st.session_state[key+'section_error']='Catalogue facts could not be refreshed. Saved content is retained; retry before testing.'
            rerun_editor()
