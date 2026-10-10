"""Editor-only composition model. No queue, publication, or provider operations.

Server renderers resolve the pinned product facts and fixed brand sections. The
browser owns current section state and composes immediately from these facts.
"""
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
import json


@lru_cache(maxsize=1)
def javascript():
    return (Path(__file__).parent/'components/crm_sections/preview.js').read_text(encoding='utf-8')


def scope(key):
    return 'sc-local-email:'+str(key)


def preview_assets(data,store,state,doc):
    from crm_automation_preview_cache import digest
    from crm_lifestyle_images import gallery
    from crm_frame_banner_template import resolve
    from types import SimpleNamespace
    source=json.dumps(doc.get('middle_sections',[]))
    need_gallery='SC_LIFESTYLE_IMAGE_' in source or '"lifestyle"' in source
    need_banner='SC_FRAME_BANNER_' in source
    token=digest([data,need_gallery,need_banner])
    entries=state.setdefault('_local_preview_assets',{})
    if token not in entries:
        galleries={}
        for item in data.get('items',[]) if need_gallery else []:
            galleries[item.get('product_id')]=gallery({**data,'items':[item]},shop=getattr(store,'preview_shop',None))
        markers=('<!--SC_FRAME_BANNER_IMAGE-->','<!--SC_FRAME_BANNER_PRODUCT-->')
        try:
            # One immutable context asset set for the editor session. Editing
            # text, visibility or order never refreshes product media.
            fragments=resolve({'custom_html':markers[0]+'SC_SPLIT_MARKER'+markers[1]},data)['custom_html'].split('SC_SPLIT_MARKER') if need_banner else ['','']
            banner=dict(zip(markers,fragments))
        except Exception:banner=dict.fromkeys(markers,'')
        entries[token]=(galleries,banner)
        while len(entries)>4:entries.pop(next(iter(entries)))
    galleries,banner=entries[token]
    shop=SimpleNamespace(campaign_images=lambda identity,**_: {'nodes':galleries.get(identity,[]),'pageInfo':{'hasNextPage':False}})
    return galleries,banner,shop


def model(doc,cfg,store=None):
    from crm_middle_sections import middle_sections,commit_middle,render_middle
    from crm_campaign_content import render_campaign
    from crm_campaign_sections import with_email_defaults
    from crm_checkout_preview import sample,document
    from crm_campaign_html import TAGS,CSS
    import streamlit as st
    data=((st.session_state.get('_automation_checkout_pin') or {}).get('last_good') if getattr(store,'email_mode',None)=='automation' else None) or sample(doc)
    # Never expose recovery credentials to the reactive renderer. Preview links
    # are inert and all checkout data remains the already selected visual sample.
    data={**deepcopy(data),'recovery_url':''}
    galleries,banner_fragments,asset_shop=preview_assets(data,store,st.session_state,doc)
    sections=middle_sections(doc)
    base=deepcopy(doc);base.pop('recovery_discount',None)
    base['content']={**base['content'],'subject':'Email preview','preheader':''}
    base['blocks']=[]
    commit_middle(base,[dict(id='preview-slot',type='html',html_number=1,visible=True,html='<div>SC_LOCAL_PREVIEW_SLOT_7D26</div>')])
    shell=render_campaign(with_email_defaults(base,cfg),cfg)['html']
    shell=shell.replace('<div>SC_LOCAL_PREVIEW_SLOT_7D26</div>','<div id="sc-local-sections"></div>')
    resolved={};errors={};error_sections={}
    from crm_automation_preview_cache import digest
    entries=st.session_state.setdefault('_local_section_outputs',{})
    for s in sections:
        try:
            isolated=deepcopy({k:v for k,v in doc.items() if k not in ('middle_sections','custom_html','blocks')});isolated['content']=deepcopy(base['content']);isolated['blocks']=[]
            current={**deepcopy(s),'visible':True}
            if 'html' in current:
                for marker,value in banner_fragments.items():current['html']=current['html'].replace(marker,value)
                current['html']=current['html'].replace('SC_FRAME_BANNER_URL','')
            commit_middle(isolated,[current])
            # An isolated section keeps the authoritative email-level offer,
            # including tokens in ordinary HTML and hidden sibling creative.
            if doc.get('recovery_discount'):
                isolated['recovery_discount']=deepcopy(doc['recovery_discount'])
            token=digest([isolated,data])
            if token in entries:
                resolved[s['id']]={'section':s,'html':entries[token]}
                continue
            from crm_recovery_discount import substitute
            hydrated=document(substitute(isolated,preview=True),data,test=True,shop=asset_shop)[0]
            resolved[s['id']]={'section':s,'html':render_middle(hydrated)[0]}
            entries[token]=resolved[s['id']]['html']
            while len(entries)>128:entries.pop(next(iter(entries)))
        except ValueError as exc:
            errors[s['id']]=str(exc)
            error_sections[s['id']]=s
        except Exception:
            errors[s['id']]='Section preview unavailable. Edit this section or retry loading the preview.'
            error_sections[s['id']]=s
    from crm_checkout_styles import default_html,rules,MARKER
    from crm_abandoned_checkout import block_html,edition_label,variant_details
    from crm_catalogue import price_label
    from crm_lifestyle_images import gallery
    items=[]
    for item in data.get('items',[]):
        variant,dimensions=variant_details(item.get('variant'))
        images=galleries.get(item.get('product_id'),[])
        items.append({k:item.get(k,'') for k in ('title','image','quantity')}|
                     {'variant':variant,'dimensions':dimensions,'edition':edition_label(item.get('edition')),
                      'price':price_label({'currency':item.get('currency'),'price':item.get('amount')}) if item.get('amount') is not None else '',
                      'gallery':[v.get('url','') for v in images]})
    from crm_checkout_elements import element
    # Rich dynamic HTML uses the same server compiler on the pinned sample.
    replacements={MARKER:block_html(data,test=True)}
    for n in (2,3,4):
        replacements[f'SC_LIFESTYLE_IMAGE_{n}_URL']=items[0]['gallery'][n-1] if items and len(items[0]['gallery'])>=n else ''
    replacements['SC_WALL_PREVIEW_URL']=''
    replacements['SC_CHECKOUT_RECOVERY_URL']=''
    replacements.update(banner_fragments)
    replacements['SC_FRAME_BANNER_URL']=''
    return dict(context_token=digest([data,cfg]),shell=shell,resolved=resolved,errors=errors,error_sections=error_sections,items=items,replacements=replacements,offer=doc.get('recovery_discount'),association_independent=True,
                tags=sorted(TAGS),css=sorted(CSS),theme=rules(default_html()),element=element()['settings'])


def canvas(doc,cfg,key,store=None):
    import streamlit as st
    import streamlit.components.v1 as components
    from crm_automation_preview_cache import digest
    from crm_middle_sections import middle_sections
    identity=scope(key)
    from crm_email_editor_context import current
    version=current(st.session_state,{}).get('version',0)
    token=digest([doc,cfg,(st.session_state.get('_automation_checkout_pin') or {}).get('last_good')])
    cached=st.session_state.get(key+'local_preview_model')
    if not cached or cached[0]!=token:
        cached=(token,model(doc,cfg,store));st.session_state[key+'local_preview_model']=cached
    if any(s['type']=='discount' for s in middle_sections(doc)) and not doc.get('recovery_discount'):
        st.caption('Presentation preview · no checkout discount connected. Bracketed discount text is a preview placeholder.')
    try:
        from crm_discount_section import validate_presentation
        validate_presentation(doc)
    except ValueError as exc:st.caption('Before publishing: '+str(exc))
    source='\n'.join(s.get('html','') for s in middle_sections(doc))
    if '<style' in source.lower():
        st.caption('HTML source is retained. Edited sections support simple tag, class and ID style rules; media queries and complex selectors are not rendered. Inline email styles remain supported.')
    if __import__('re').search(r'<\s*(script|iframe|object|form)\b|\bon\w+\s*=|javascript\s*:',source,__import__('re').I):
        st.caption('Active HTML is excluded from preview and blocks delivery validation. Your source remains editable.')
    payload=json.dumps(dict(scope=identity,version=version,model=cached[1],sections=middle_sections(doc)),default=str).replace('<','\\u003c')
    # Refresh seed data without changing the iframe srcdoc. Existing image nodes,
    # scroll and local edits survive every save acknowledgement and app rerun.
    st.html('<script>(()=>{const p='+payload+';window.scEmailDrafts??=new Map();let s=window.scEmailDrafts.get(p.scope);if(!s){s={sections:p.sections,revision:0,listeners:new Set()};window.scEmailDrafts.set(p.scope,s);}if(p.version<(s.serverVersion||0))return;s.serverVersion=p.version;s.model=p.model;if(!s.dirty)s.sections=p.sections;for(const fn of s.listeners)fn(s.sections);})();</script>',unsafe_allow_javascript=True)
    boot='<!doctype html><meta charset="utf-8"><script>'+javascript()+'</script><script>SCPreview.mount('+json.dumps({'scope':identity})+');</script>'
    mode=st.session_state.get(key+'preview_device','Desktop')
    components.html(boot,width=600 if mode=='Desktop' else 390,height=520,scrolling=True)
