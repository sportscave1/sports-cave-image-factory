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


def picker_collection_labels(rows):
    """Streamlit serializes labels, so identical titles must remain distinct."""
    from collections import Counter
    titles = {r['id']:r['title'] for r in rows}
    counts = Counter(titles.values())
    labels = {identity:(title+' · '+identity.rsplit('/',1)[-1]
                        if counts[title]>1 or title=='All collections' else title)
              for identity,title in titles.items()}
    # Also protect against a real title matching another collection's suffix.
    duplicates = Counter(labels.values())
    return {identity:(label+' ['+identity+']' if duplicates[label]>1 else label)
            for identity,label in labels.items()}


def picker_selection_changed(key, widget_key, product):
    """Capture the old result's checkbox before a filter/page rerun replaces it."""
    basket = st.session_state.setdefault(key+'basket', {})
    if st.session_state.get(widget_key, False):
        basket[product['id']] = deepcopy(product)
    else:
        basket.pop(product['id'], None)


def picker_dismissed():
    target = st.session_state.pop('_crm_picker_focus_target', None)
    if target:
        editor_key, section_id = target
        st.session_state[editor_key+'picker_focus'] = {'section':section_id,'event':uuid.uuid4().hex}


@st.dialog('Select products', width='medium', on_dismiss=picker_dismissed)
@autosaving
def product_picker(doc, section_id, catalogue, key, editor_key=None):
    if editor_key: st.session_state['_crm_picker_focus_target'] = (editor_key,section_id)
    section = next(s for s in middle_sections(doc) if s['id']==section_id)
    basket = st.session_state.setdefault(key+'basket', {p['id']:deepcopy(p) for p in section['products']})
    query = st.text_input('Search products…', max_chars=150, key=key+'search_text')
    try:
        choices = catalogue.collections()
        if choices.get('stale'): st.caption('Showing cached collections. Refresh will retry shortly.')
        st.session_state[key+'collections'] = choices['rows']
    except Exception:
        st.caption('Collections temporarily unavailable. Existing selection retained.')
    options = picker_collection_labels(st.session_state.get(key+'collections',[]))
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
            widget_key = key+st.session_state[key+'generation']+p['id']
            if widget_key in st.session_state and st.session_state[widget_key] != (p['id'] in basket):
                st.session_state[widget_key] = p['id'] in basket
            a.checkbox('Select '+p['title'],False if widget_key in st.session_state else p['id'] in basket,label_visibility='collapsed',
                                  key=widget_key,on_change=picker_selection_changed,args=(key,widget_key,p))
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
    except Exception as exc:
        logging.getLogger(__name__).warning('crm_catalogue_picker_failed type=%s',type(exc).__name__)
        st.warning('Product catalogue is temporarily unavailable. Your selections are retained.')
        if st.button('Retry product loading',key=key+'retry'):
            st.session_state.pop(key+'page',None);st.rerun(scope='fragment')

    st.caption('Selected: '+str(len(basket))+' / 12')
    cancel,add=st.columns(2)
    if cancel.button('Cancel',key=key+'cancel'):
        picker_dismissed()
        st.session_state.pop(key+'basket',None);st.rerun()
    if add.button('Add selected',type='primary',disabled=len(basket)>12,key=key+'add'):
        try:
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
            picker_dismissed()
            st.session_state.pop(key+'basket',None);st.rerun()
        except Exception as exc:
            logging.getLogger(__name__).warning('crm_catalogue_verification_failed type=%s',type(exc).__name__)
            st.warning('Selected products could not be verified with Shopify. Your selections are retained. Retry Add selected.')


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
        try:
            from crm_campaign_library import template_html,template_sections
            for row in library_rows(store):
                item={k:row[k] for k in ('id','name','version')}
                try:item.update(html=template_html(store,row),sections=template_sections(store,row),builtin=bool(row.get('builtin')))
                except (ValueError,StoreUnavailable):pass
                templates.append(item)
        except StoreUnavailable:st.caption('Templates temporarily unavailable. Add HTML and Add Catalogue remain available.')
    from crm_image_prompt import image_prompt
    from crm_email_editor_context import current
    editor = current(st.session_state,{})
    campaign_name = editor.get('name', '') if editor.get('document') is doc else ''
    from crm_email_prompt import handoff
    from crm_prompt_copy import clipboard_script
    verified=handoff(st.session_state,editor) if campaign_name else None
    from crm_discount_ui import view as discount_view,callback as discount_callback
    from crm_local_preview import scope
    from crm_checkout_elements import element,starter
    from crm_checkout_template import load as load_checkout
    from crm_discount_section import default_html as discount_html
    from crm_template_cache import cached
    checkout=cached(store,('local-checkout-master',),lambda:load_checkout(store)) if store else None
    def resolve_insert(action):
        if action['kind']=='checkout':
            from crm_checkout_template import validate
            return {'html':validate(checkout['html']),'name':'Abandoned Checkout'}
        row=next((r for r in library_rows(store) if str(r['id'])==str(action.get('template_id')) and r['version']==action.get('version')),None)
        if row is None:raise ValueError('Template changed. Reload the template list.')
        return {'html':template_html(store,row),'sections':template_sections(store,row),'name':row['name'] if row.get('builtin') else '',
                'template_ref':{k:str(row[k]) if k=='id' else row[k] for k in ('id','name','version')}}
    trigger=getattr(store,'preview_trigger',None) if getattr(store,'email_mode',None)=='automation' else None
    component_args={'discount_offer':doc.get('recovery_discount'),'discount_html':discount_html()}
    event = render_component(component,**component_args,picker_focus=st.session_state.pop(key+'picker_focus',None),on_change=lambda:discount_callback(shop,doc,key,trigger=trigger),discount=discount_view(key,trigger=trigger),automation=getattr(store,'email_mode',None)=='automation',preview_debounce=180,clipboard_script=clipboard_script(),history_scope=scope(key),preview_scope=scope(key),element_defaults=element()['settings'],starter_sections=starter(),checkout_template=checkout,draft_version=editor.get('version'),save_status=st.session_state.get('campaign_save_status','Saved'),save_error=st.session_state.get('campaign_save_error',''),edit_error=st.session_state.get(key+'edit_error',''),image_prompt=image_prompt(doc,campaign_name,verified),sections=sections,templates=templates,warnings=warnings,ack=st.session_state.get(key+'section_event'),key=key+'middle',default=None)
    if st.session_state.get(key+'section_error'):st.warning(st.session_state.pop(key+'section_error'))
    if event and event.get('event') != st.session_state.get(key+'section_event'):
        st.session_state[key+'section_event'] = event.get('event')
        st.session_state.pop(key+'edit_error',None)
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
                apply_event(doc,event,resolve_insert=resolve_insert);doc['copy_reviewed']=False
                rerun_editor()
        except ValueError as exc:
            st.session_state[key+'edit_error']=str(exc)
            st.session_state[key+'section_error']=str(exc);rerun_editor()
        except Exception as exc:
            logging.getLogger(__name__).warning('crm_catalogue_editor_failed type=%s',type(exc).__name__)
            st.session_state[key+'section_error']='Catalogue facts could not be refreshed. Saved content is retained; retry before testing.'
            rerun_editor()
