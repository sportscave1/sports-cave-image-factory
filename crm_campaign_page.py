"""Compact Campaigns V1 workspace. Explicit buttons are the only external-I/O triggers."""
from copy import deepcopy
import json
import uuid
import streamlit as st
import streamlit.components.v1 as components
import os_accounts
from crm_campaign_content import (TYPES,MARKETS,OBJECTIVES,FIELDS,new_document,settings,
                                  preflight,render_campaign,prompt_for,parse_copy)
from crm_campaign_store import CampaignStore
from crm_audience import count_page
from crm_logic import rule,SPORTS
from crm_store import StoreUnavailable


def copy_prompt(value):
    payload=json.dumps(value).replace('<','\\u003c').replace('>','\\u003e')
    components.html('''<button id="copy" style="background:#d6a548;border:0;border-radius:8px;padding:12px 20px;cursor:pointer">Copy Prompt</button>
<script>document.getElementById('copy').onclick=async function(){const s='''+payload+''';
try { await navigator.clipboard.writeText(s); this.textContent='Prompt copied'; }
catch(e){this.textContent='Use the copy icon below';}}</script>''',height=50)


def campaign_workspace(shop,store,actions):
    drafts=CampaignStore(store.connect)
    st.warning('LIVE MARKETING DELIVERY: DISABLED')
    st.caption('Create → review audience → write → preview → one admin test. No production send or scheduling actions.')
    try: rows=drafts.list_drafts()
    except StoreUnavailable:
        st.info('Campaign workspace storage is not installed yet. Apply the reviewed local V1 migration after approval. No live data was changed.')
        return
    top=st.columns([2,5,2])
    if top[0].button('+ New Campaign',type='primary'):
        st.session_state['campaign_editor']={'id':None,'version':None,'name':'','document':new_document()}
        st.session_state['campaign_edit_key']=str(uuid.uuid4())
    archived=top[2].checkbox('Show archived')
    if archived: rows=drafts.list_drafts(True)
    if rows:
        with st.expander('Campaign list', expanded=not bool(st.session_state.get('campaign_editor'))):
            st.dataframe([{'Name':r['name'],'Type':r['document']['type'],'Market':r['document']['market'],
                           'Audience':r['document']['audience'].get('name',''),
                           'Eligible':str(r['document']['counts'].get('eligible','—')), 'Status':r['status'],
                           'Last edited':str(r['updated_at'])[:19],
                           'Test status':'Current version accepted' if r['tested_version']==r['version'] else 'Needs test',
                           'Created by':r['created_by']} for r in rows],hide_index=True,height=185,use_container_width=True)
            controls=st.columns([5,1,1,1])
            selected=controls[0].selectbox('Campaign',rows,format_func=lambda r:r['name'],label_visibility='collapsed')
            if controls[1].button('Edit',disabled=archived):
                st.session_state['campaign_editor']=deepcopy(selected);st.session_state['campaign_edit_key']=str(uuid.uuid4())
            if controls[2].button('Duplicate'):
                row=drafts.duplicate(actions.user,selected['id'])
                st.session_state['campaign_editor']=row;st.session_state['campaign_edit_key']=str(uuid.uuid4());st.rerun()
            if controls[3].button('Archive',disabled=archived):
                drafts.archive(actions.user,selected['id'],selected['version'])
                st.session_state.pop('campaign_editor',None);st.rerun()
    editor=st.session_state.get('campaign_editor')
    if not editor:
        st.info('Choose New Campaign or edit a saved draft. Shopify remains the customer and consent source of truth.')
        return
    doc=editor['document']; key=st.session_state.setdefault('campaign_edit_key',str(uuid.uuid4()))
    step=st.radio('Campaign editor',('1 · Basics','2 · Audience','3 · Email creator','4 · Preview + test'),horizontal=True,key='campaign_step')
    if step.startswith('1'):
        a,b,c=st.columns(3)
        editor['name']=a.text_input('Campaign name',editor['name'],key=key+'name')
        doc['type']=b.selectbox('Campaign type',TYPES,index=TYPES.index(doc['type']),key=key+'type')
        doc['market']=c.selectbox('Market',MARKETS,index=MARKETS.index(doc['market']),key=key+'market')
        doc['objective']=a.selectbox('Objective',OBJECTIVES,index=OBJECTIVES.index(doc['objective']),key=key+'objective')
        doc['offer']=b.text_input('Offer — None or a real reviewed offer',doc['offer'],key=key+'offer')
        doc['offer_reviewed']=c.checkbox('I verified this offer',doc['offer_reviewed'],key=key+'offercheck')
        with st.expander('Product facts + notes'):
            product_id=st.text_input('Shopify product ID (optional)',key=key+'productid')
            if st.button('Load canonical product facts'):
                from crm_shopify import gid
                found=shop.products([gid(product_id,'Product')],fresh=True)
                if found:
                    p=found[0];doc['product']={k:p.get(k) for k in ('id','title','onlineStoreUrl','productType','tags')}
                    st.success('Canonical product facts loaded.')
                else: st.warning('Product not found; no facts added.')
            if doc['product']: st.json(doc['product'],expanded=False)
            st.caption('Price and edition availability are omitted when not supplied by the existing product reader. Never infer scarcity.')
            doc['notes']=st.text_area('Notes for the copy brief',doc['notes'],height=80,key=key+'notes')
    elif step.startswith('2'):
        audience_editor(shop,store,doc,key)
    elif step.startswith('3'):
        c=doc['content'];before_copy=dict(c);left,right=st.columns([3,2])
        with left:
            c['subject']=st.text_input('Subject',c['subject'],key=key+'subject')
            c['preheader']=st.text_input('Preheader',c['preheader'],key=key+'preheader')
            c['headline']=st.text_input('Headline',c['headline'],key=key+'headline')
            c['body']=st.text_area('Body copy',c['body'],height=120,key=key+'body')
            cols=st.columns(2)
            c['cta_label']=cols[0].text_input('CTA label',c['cta_label'],key=key+'cta_label')
            c['cta_url']=cols[1].text_input('CTA URL',c['cta_url'],key=key+'cta_url')
            with st.expander('Hero image + supporting copy'):
                for f,label in (('hero_url','Hero image HTTPS URL'),('hero_alt','Hero image alt text'),('eyebrow','Eyebrow / collection'),('intro','Intro'),('product_block','Product / collector block'),('secondary','Secondary block'),('ps','Closing / PS')):
                    c[f]=st.text_input(label,c[f],key=key+f)
                st.caption('Source 600–1000px wide; aim ≤1MB. Hero 16:9 or 5:3; product 4:3 or 1:1. Avoid very tall heroes. Images scale proportionally: no destructive crop. Keep headline, price and CTA as text.')
            if c!=before_copy:
                doc['copy_reviewed']=False
                st.session_state[key+'review']=False
            doc['copy_reviewed']=st.checkbox('I reviewed facts, subject, offer and urgency for accuracy.',doc['copy_reviewed'],key=key+'review')
        with right:
            if st.button('Generate Sports Cave Prompt'): st.session_state[key+'prompt']=prompt_for(doc)
            if st.session_state.get(key+'prompt'):
                copy_prompt(st.session_state[key+'prompt'])
                with st.expander('Generated prompt'): st.code(st.session_state[key+'prompt'],language=None)
            with st.expander('Paste Generated Copy'):
                pasted=st.text_area('Paste COPY JSON',height=160,key=key+'paste')
                if st.button('Apply copy'):
                    c.update(parse_copy(pasted));doc['copy_reviewed']=False
                    st.session_state['campaign_edit_key']=str(uuid.uuid4());st.rerun()
            st.caption('Footer is generated by the system and cannot be edited or supplied by AI.')
    else:
        preview_and_test(drafts,actions.user,editor,key)
    controls=st.columns([3,2,5])
    status=controls[0].selectbox('Save as',('DRAFT','NEEDS REVIEW','TEST READY','CANCELED'),key=key+'status')
    if controls[1].button('Save campaign',type='primary'):
        row=drafts.save(actions.user,editor['name'],doc,editor.get('id'),editor.get('version'),requested_status=status)
        st.session_state['campaign_editor']=row
        st.success('Campaign saved. Changes invalidate the previous test approval.')
    controls[2].caption('Drafts only. Ready for Future Live Send, Scheduled and Sent are unavailable in V1.')
    if editor.get('id'):
        with st.expander('Campaign history'):
            st.dataframe(drafts.history(editor['id']),hide_index=True,use_container_width=True)


def audience_editor(shop,store,doc,key):
    current=json.dumps(doc['audience'],sort_keys=True)
    mode=st.radio('Audience source',('All subscribed / filters','Saved segment'),horizontal=True,key=key+'source')
    if mode.startswith('All'):
        cols=st.columns(4)
        country=cols[0].selectbox('Country',('Any','AU','US','GB'),key=key+'country')
        sport=cols[1].selectbox('Interest / sport',('Any',*SPORTS),key=key+'sport')
        orders=cols[2].number_input('Minimum orders (2 = repeat buyers)',min_value=0,max_value=10000,key=key+'orders')
        days=cols[3].selectbox('Last purchase',('Any','Last 30 days','Last 180 days','Over 180 days'),key=key+'days')
        if st.button('Use these filters'):
            rules=[rule('consent','SUBSCRIBED')]
            if country!='Any':rules.append(rule('country',country))
            if sport!='Any':rules.append(rule('interest',sport,'contains'))
            if orders:rules.append(rule('orders',orders,'gte'))
            if days!='Any':rules.append(rule('last_order_days',30 if days=='Last 30 days' else 180,'gte' if days.startswith('Over') else 'lte'))
            doc['audience']={'kind':'Rules','name':'Subscribed · '+country+' · '+sport+' · '+str(orders)+'+ orders · '+days,'rules':{'all':rules}}
    else:
        if st.button('Load saved segments'):
            page=shop.segments()
            st.session_state[key+'segments']=[{'kind':'Shopify',**s} for s in page['nodes']]+[{'kind':'Rules','name':s['name'],'rules':s['rules']} for s in store.list('segments')]
            st.session_state[key+'segment_cursor']=page['pageInfo'].get('endCursor') if page['pageInfo'].get('hasNextPage') else None
        if st.session_state.get(key+'segment_cursor') and st.button('Load more Shopify segments'):
            page=shop.segments(st.session_state[key+'segment_cursor'])
            st.session_state[key+'segments'] += [{'kind':'Shopify',**s} for s in page['nodes']]
            st.session_state[key+'segment_cursor']=page['pageInfo'].get('endCursor') if page['pageInfo'].get('hasNextPage') else None
        options=st.session_state.get(key+'segments',[])
        if options:
            selected=st.selectbox('Saved segment',options,format_func=lambda s:s['name'])
            if st.button('Use selected segment'):
                doc['audience']={k:selected[k] for k in (('kind','name','id') if selected['kind']=='Shopify' else ('kind','name','rules'))}
    if current!=json.dumps(doc['audience'],sort_keys=True):doc['counts']={};st.session_state.pop(key+'count',None)
    st.caption('Selected: '+doc['audience']['name']+' · All members still pass explicit consent and suppression checks.')
    a,b=st.columns(2)
    restart=a.button('Recalculate eligibility')
    previous=st.session_state.get(key+'count')
    more=b.button('Continue calculation',disabled=not previous or previous.get('complete',False))
    if restart or more:
        source=('Shopify' if doc['audience']['kind']=='Shopify' else 'Sports Cave',doc['audience'])
        state=count_page(shop,store,source,previous if more else None)
        st.session_state[key+'count']=state
        doc['counts']={k:state[k] for k in ('members','eligible','excluded','complete','checked_at')}
        st.rerun()
    counts=doc['counts']; cols=st.columns(3)
    for col,label,value in zip(cols,('Raw segment count','Eligible','Excluded'),(counts.get('members','—'),counts.get('eligible','—'),sum(counts.get('excluded',{}).values()) if counts else '—')):col.metric(label,value)
    if counts:
        st.caption(('Complete' if counts.get('complete') else 'Partial — continue calculation')+' · '+counts.get('checked_at','')+' · Must be recalculated before future production sending.')
        with st.expander('Excluded reasons'):st.json(counts.get('excluded',{}))


def preview_and_test(store,user,editor,key):
    doc=editor['document'];checks=preflight(doc); rendered=render_campaign(doc)
    left,right=st.columns([3,2])
    with left:
        width=st.select_slider('Layout preview width',options=[320,375,390,430,600],value=375,key=key+'width')
        st.caption('Layout preview only — not a Gmail or Outlook rendering engine. Images are shown without cropping.')
        components.html(rendered['html'],width=width,height=360,scrolling=True)
        with st.expander('Plain text'):st.text(rendered['text'])
    with right:
        st.caption(checks['policy'])
        with st.container(height=200):
            for label,passed in {**checks['test'],**checks['live']}.items(): st.caption(('✓ ' if passed else '○ ')+label)
        st.caption('One-click unsubscribe production path not activated. Postal address and footer gaps are visible in test previews.')
        with st.expander('Domain verification evidence'):
            st.caption('Domain sportscaveshop.com reported verified by Nathan. Record SPF/DKIM evidence before bulk activation; DMARC and webhooks remain unproven.')
        if os_accounts.is_admin(user):
            with st.form(key+'test',clear_on_submit=True):
                recipient=st.text_input('Manual test recipient',value='')
                confirmed=st.checkbox('CAMPAIGN TEST ONLY — I confirm one mailbox and understand the inactive unsubscribe / live-compliance warnings.')
                clicked=st.form_submit_button('Send Test',disabled=not editor.get('id') or not checks['test_ready'])
            if clicked:
                saved=store.draft(editor['id'])
                if saved['document']!=doc:st.warning('Save your current edits before sending a test.')
                else:
                    result=store.test_campaign(user,editor['id'],editor['version'],recipient=recipient,confirmed=confirmed,operation_id=str(uuid.uuid4()))
                    st.success('Test accepted by Resend');st.text(result['message_id']+'\n'+result['accepted_at'])
                    if not result['audit_saved']:st.warning('Accepted, but final history could not be saved. Do not resend; check the message ID.')
        else:st.caption('Only an active administrator can send a test.')
        with st.expander('Future reputation + delivery'):
            st.caption('Prioritize delivered, clicks, purchases/revenue, unsubscribes, hard bounces and complaints. Opens are secondary. Complaint target <0.10%; critical ≥0.30%. No data yet.')
            st.caption('Future engaged-audience warm-up requires explicit review. Broadcasts and audience management are not activated.')
