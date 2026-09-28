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
from crm_email_blocks import PURPOSES, STARTERS, KINDS, block, starter, duplicate_block, legacy_blocks
from crm_campaign_content import html_budget
from crm_audience import selection_page
from crm_tracking import asset_url
from crm_resend_marketing import get_resend_marketing_config_status
from crm_logic import now


def open_editor(row):
    st.session_state['campaign_editor']=deepcopy(row)
    st.session_state['campaign_saved']=deepcopy(row)
    st.session_state['campaign_edit_key']=str(uuid.uuid4())
    st.session_state['campaign_step_v2']=0


@st.dialog('New campaign')
def create_dialog(store,user):
    with st.form('new_campaign_form'):
        name=st.text_input('Campaign name',max_chars=150)
        a,b=st.columns(2)
        purpose=a.selectbox('Purpose',PURPOSES)
        market=b.selectbox('Market',MARKETS)
        tags=st.text_input('Internal tags (comma separated)')
        clicked=st.form_submit_button('Create draft',type='primary')
    if clicked:
        doc=new_document();doc.update(type=purpose,market=market,tags=[v.strip() for v in tags.split(',') if v.strip()],smart_hours=store.setting('sending')['value']['smart_hours'])
        open_editor(store.save(user,name,doc));st.rerun()


def dirty(editor):
    saved=st.session_state.get('campaign_saved',{})
    return editor.get('document')!=saved.get('document') or editor.get('name')!=saved.get('name')


def campaign_workspace(shop,store,actions,navigate=lambda _:None):
    drafts=CampaignStore(store.connect)
    st.warning('Live marketing disabled — internal tests only. LIVE MARKETING DELIVERY: DISABLED')
    try:
        drafts.setting('sending')
    except StoreUnavailable as exc:
        st.error(str(exc))
        st.button('+ New Campaign', type='primary', disabled=True)
        st.caption('Campaigns · draft list and editing will return when persistence is restored. Refresh to retry. Existing saved drafts have not been erased.')
        if st.session_state.get('campaign_editor'):
            st.info('Your open draft remains in this session. Saving is disabled until storage is available.')
        return
    editor=st.session_state.get('campaign_editor')
    if not editor:
        top=st.columns([2,3,2,2])
        if top[0].button('+ New Campaign',type='primary'):create_dialog(drafts,actions.user)
        search=top[1].text_input('Search campaigns',placeholder='Search by name')
        status=top[2].selectbox('Status filter',('All','DRAFT','NEEDS_REVIEW','TEST_READY','TESTED','ARCHIVED'))
        market=top[3].selectbox('Market filter',('All',*MARKETS))
        filters=(search,status,market)
        if st.session_state.get('campaign_list_filters')!=filters:
            st.session_state['campaign_list_filters']=filters;st.session_state['campaign_list_offset']=0
        offset=st.session_state.get('campaign_list_offset',0)
        page=drafts.list_drafts(status=='ARCHIVED',search=search,status=status,market=market,offset=offset,limit=26)
        rows=page[:25]
        if st.button('Create first test campaign'):
            doc=new_document();doc['type']='New Editions';doc['blocks']=starter('New Editions')
            doc['content'].update(subject='New collector editions',preheader='Discover your next collector piece')
            doc['smart_hours']=drafts.setting('sending')['value']['smart_hours']
            open_editor(drafts.save(actions.user,'New Collector Editions — Test Draft',doc));st.rerun()
        st.caption('Email campaigns · newest edits first · production sending and scheduling are unavailable.')
        previous,following=st.columns(2)
        if previous.button('Previous campaigns',disabled=offset==0):st.session_state['campaign_list_offset']=max(0,offset-25);st.rerun()
        if following.button('Next campaigns',disabled=len(page)<=25):st.session_state['campaign_list_offset']=offset+25;st.rerun()
        if not rows:st.info('No matching campaigns. Create a draft to begin.');return
        st.dataframe([{'Campaign':r['name'],'Audience':r['document']['audience'].get('name',''),'Market':r['document']['market'],
                       'Eligible':r['document'].get('counts',{}).get('eligible','Not calculated'),'Status':r['status'],'Updated':str(r['updated_at'])[:19],'Last test':str(r['last_tested_at'] or 'Not tested')[:19],'Created by':r['created_by']} for r in rows],hide_index=True,height=280,use_container_width=True)
        selected=st.selectbox('Campaign actions',rows,format_func=lambda r:r['name'])
        cols=st.columns(5)
        if cols[0].button('Open',disabled=bool(selected['archived_at'])):open_editor(selected);st.rerun()
        if cols[1].button('Duplicate'):open_editor(drafts.duplicate(actions.user,selected['id']));st.rerun()
        if cols[2].button('Archive',disabled=bool(selected['archived_at'])):drafts.archive(actions.user,selected['id'],selected['version']);st.rerun()
        if cols[3].button('Restore',disabled=not bool(selected['archived_at'])):drafts.restore(actions.user,selected['id'],selected['version']);st.rerun()
        if cols[4].button('Report'):st.session_state['campaign_report']=selected['id']
        if st.session_state.get('campaign_report'):
            from crm_settings_page import campaign_report
            campaign_report(drafts,shop,actions.user,st.session_state['campaign_report'])
        return
    doc=editor['document'];key=st.session_state.setdefault('campaign_edit_key',str(uuid.uuid4()))
    target=st.session_state.get('crm_requested_route')
    if target:
        st.warning('Save or discard the pending campaign edits before opening '+target+'.')
        a,b,c=st.columns(3)
        if a.button('Save and continue'):
            updated=drafts.save(actions.user,editor['name'],doc,editor['id'],editor['version'])
            st.session_state['campaign_editor']=deepcopy(updated);st.session_state['campaign_saved']=deepcopy(updated);st.session_state.pop('crm_requested_route',None);navigate(target);return
        if b.button('Discard and continue'):
            st.session_state['campaign_editor']=deepcopy(st.session_state['campaign_saved']);st.session_state.pop('crm_requested_route',None);navigate(target);return
        if c.button('Keep editing'):st.session_state.pop('crm_requested_route',None);st.rerun()
    cfg=drafts.render_settings();step=st.session_state.setdefault('campaign_step_v2',0)
    st.html('<style>.st-key-campaign-sticky{position:sticky;top:2.8rem;z-index:50;background:#faf8f2;padding:.35rem 0;border-bottom:1px solid #e6e0d6}.st-key-campaign-sticky [data-testid="stVerticalBlock"]{gap:.3rem}.st-key-crm-workspace [data-testid="stVerticalBlock"]{gap:.6rem}</style>')
    with st.container(key='campaign-sticky'):
        st.markdown('**'+editor['name'].replace('*','')+'** · '+editor['status'])
        bar=st.columns([1,1,1,1,1,1])
        back=bar[0].button('← Back',disabled=step==0)
        next_step=bar[1].button('Next →',disabled=step==2)
        save=bar[2].button('Save draft',type='primary')
        preview=bar[3].button('Preview')
        test=bar[4].button('Test only')
        close=bar[5].button('Campaign list')
        save_indicator=st.empty()
    if step==0:audience_editor(shop,drafts,doc,key)
    elif step==1:message_editor(shop,drafts,actions.user,editor,key,cfg)
    else:review_editor(drafts,actions.user,editor,key,cfg)
    save_indicator.caption(('Unsaved changes · use Save draft' if dirty(editor) else 'Saved · revision '+str(editor['version']))+' · '+(' → '.join(('['+v+']') if i==step else v for i,v in enumerate(('Recipients','Message','Review')))))
    if save:
        with st.spinner('Saving draft…'):
            try:
                updated=drafts.save(actions.user,editor['name'],doc,editor['id'],editor['version'])
                st.session_state['campaign_editor']=deepcopy(updated);st.session_state['campaign_saved']=deepcopy(updated)
                st.session_state[key+'save_notice']='Saved';st.rerun()
            except (ValueError,StoreUnavailable) as exc:st.error('Save failed — your edits are retained. '+str(exc))
    if st.session_state.pop(key+'save_notice',None):st.success('Saved. Your draft is stored in the CRM database.')
    if back or next_step or preview or test:
        st.session_state['campaign_step_v2']=2 if preview or test else step+(-1 if back else 1);st.rerun()
    if close:st.session_state[key+'close_requested']=True
    if st.session_state.get(key+'close_requested'):
        if dirty(editor):
            st.warning('Unsaved changes. Save this draft or explicitly discard changes before returning to the list.')
            if st.button('Discard unsaved changes and close'):st.session_state.pop('campaign_editor',None);st.rerun()
        else:st.session_state.pop('campaign_editor',None);st.rerun()


def audience_editor(shop,store,doc,key):
    st.caption('RECIPIENTS · Existing Shopify customers and consent. No recipient list is stored with a draft.')
    a,b=st.columns([3,1]);a.write('Include segments as a union. Exclusions always win.')
    old_hours=doc.get('smart_hours',16)
    doc['smart_hours']=int(b.number_input('Smart Sending · hours',1,168,int(old_hours),key=key+'frequency'))
    if old_hours!=doc['smart_hours']:doc['counts']={};st.session_state.pop(key+'count',None)
    st.caption('Default 16 hours · based only on actual Sports Cave OS marketing sends, including future campaigns and flows. Excludes internal tests, support and transactional emails. External Klaviyo / Shopify Email history is not included.')
    mode=st.radio('Audience source',('All subscribed / filters','Saved segments'),horizontal=True,key=key+'source')
    current=json.dumps(doc['audience'],sort_keys=True)
    if mode.startswith('All'):
        cols=st.columns(4)
        country=cols[0].selectbox('Country',('Any','AU','US','GB'),key=key+'country')
        sport=cols[1].selectbox('Interest / sport',('Any',*SPORTS),key=key+'sport')
        orders=cols[2].number_input('Minimum orders',0,10000,key=key+'orders')
        days=cols[3].selectbox('Last purchase',('Any','Last 30 days','Last 180 days','Over 180 days'),key=key+'days')
        if st.button('Use these filters'):
            rules=[rule('consent','SUBSCRIBED')]
            if country!='Any':rules.append(rule('country',country))
            if sport!='Any':rules.append(rule('interest',sport,'contains'))
            if orders:rules.append(rule('orders',orders,'gte'))
            if days!='Any':rules.append(rule('last_order_days',30 if days=='Last 30 days' else 180,'gte' if days.startswith('Over') else 'lte'))
            doc['audience']={'kind':'Selection','name':'Subscribed · '+country+' · '+sport,'include':[{'kind':'Rules','name':'Selected filters','rules':{'all':rules}}],'exclude':[]}
    if st.button('Load saved segments'):
        page=shop.segments();st.session_state[key+'segments']=[{'kind':'Shopify','name':s['name'],'id':s['id']} for s in page['nodes']]+[{'kind':'Rules','name':s['name'],'rules':s['rules']} for s in store.list('segments')]
        st.session_state[key+'segment_cursor']=page['pageInfo'].get('endCursor') if page['pageInfo'].get('hasNextPage') else None
    if st.session_state.get(key+'segment_cursor') and st.button('Load more segments'):
        page=shop.segments(st.session_state[key+'segment_cursor']);st.session_state[key+'segments'] += [{'kind':'Shopify','name':s['name'],'id':s['id']} for s in page['nodes']]
        st.session_state[key+'segment_cursor']=page['pageInfo'].get('endCursor') if page['pageInfo'].get('hasNextPage') else None
    options=st.session_state.get(key+'segments',[])
    if options:
        cols=st.columns(2)
        included=cols[0].multiselect('Include segments',range(len(options)),format_func=lambda i:options[i]['name'],key=key+'include')
        excluded=cols[1].multiselect('Exclude segments',range(len(options)),format_func=lambda i:options[i]['name'],key=key+'exclude')
        if st.button('Apply segment selection'):
            if not included:st.warning('Choose at least one included segment.')
            else:doc['audience']={'kind':'Selection','name':' + '.join(options[i]['name'] for i in included)[:300],'include':[options[i] for i in included],'exclude':[options[i] for i in excluded]}
    if current!=json.dumps(doc['audience'],sort_keys=True):doc['counts']={};st.session_state.pop(key+'count',None)
    selection=doc['audience'] if doc['audience']['kind']=='Selection' else {'kind':'Selection','name':doc['audience']['name'],'include':[doc['audience']],'exclude':[]}
    st.caption('Selected: '+selection['name']+' · Only explicit SUBSCRIBED profiles are eligible. Purchase is not consent.')
    a,b=st.columns(2);restart=a.button('Recalculate eligibility');previous=st.session_state.get(key+'count')
    more=b.button('Continue calculation',disabled=not previous or previous.get('complete',False))
    if restart or more:
        doc['counts']={}
        st.session_state.pop(key+'count',None)
        state=selection_page(shop,store,selection,previous if more else None,smart_hours=doc.get('smart_hours',16));st.session_state[key+'count']=state
        if state['complete']:doc['counts']={k:state[k] for k in ('members','eligible','excluded','complete','checked_at')}
        st.rerun()
    state=st.session_state.get(key+'count',doc['counts']);complete=state.get('complete',False)
    cols=st.columns(3)
    for col,label,value in zip(cols,('Matched profiles','Eligible estimate','Excluded'),(state.get('members','—'),state.get('eligible','—') if complete else 'Unavailable',sum(state.get('excluded',{}).values()) if complete else 'Unavailable')):col.metric(label,value)
    st.caption(('Complete' if complete else 'Not calculated / partial — continue all pages, including consent verification')+' · '+state.get('checked_at','')+' · Always recheck consent, suppression and frequency before future dispatch.')
    with st.expander('Exclusion reasons + calculation detail'):
        st.json({'primary_reasons':state.get('excluded',{}),'diagnostics':state.get('diagnostics',{}),'pages_scanned':state.get('pages',0)})


def layout_preview(doc,cfg,key):
    controls=st.columns([2,2])
    width=controls[0].selectbox('Layout width',(600,375,320,430),key=key+'previewwidth')
    mode=controls[1].selectbox('Preview mode',('Images on','Images off','Plain text'),key=key+'previewmode')
    rendered=render_campaign(doc,cfg,images_off=mode=='Images off')
    st.caption('Layout preview · not a Gmail / Outlook certification')
    if mode=='Plain text':st.text_area('Plain-text alternative',rendered['text'],height=460,disabled=True,key=key+'plain')
    else:components.html(rendered['html'],width=width,height=490,scrolling=True)
    budget=html_budget(rendered['html']);st.caption(budget['label'])
    if budget['warning']:st.warning('HTML size needs review before testing.')


def message_editor(shop,store,user,editor,key,cfg):
    doc=editor['document'];c=doc['content'];before=json.dumps(doc,sort_keys=True)
    left,right=st.columns([4,7],gap='medium')
    with left:
        c['subject']=st.text_input('Subject',c['subject'],max_chars=250,key=key+'subject')
        c['preheader']=st.text_input('Preheader',c['preheader'],max_chars=250,key=key+'preheader')
        delivery=get_resend_marketing_config_status()
        with st.expander('Sender + campaign details'):
            import os
            st.text_input('Sender name',os.getenv('RESEND_FROM_NAME',''),disabled=True)
            st.text_input('Sender address',delivery['sender'],disabled=True)
            st.text_input('Reply-To',delivery['reply_to'],disabled=True)
            st.caption('Approved sender configuration only. Change verified identity through the reviewed deployment configuration.')
            editor['name']=st.text_input('Campaign name',editor['name'],key=key+'name')
            st.caption('Purpose: '+doc['type']+' · Market: '+doc['market'])
            doc['notes']=st.text_area('Notes for prompt',doc['notes'],height=90,key=key+'notes')
            doc['offer']=st.text_input('Reviewed offer or None',doc['offer'],key=key+'offer')
            doc['offer_reviewed']=st.checkbox('I verified this offer',doc['offer_reviewed'],key=key+'offer_reviewed')
        with st.expander('Choose template / starter'):
            selected=st.selectbox('Starter layout',STARTERS,key=key+'starter')
            replace=st.checkbox('Replace the current design with the selected snapshot',key=key+'replace')
            if st.button('Use starter',disabled=bool(doc.get('blocks')) and not replace):
                doc['blocks']=starter(selected);doc['template_ref']={'name':selected,'version':1};reset_widgets();st.rerun()
            templates=store.templates()
            if templates:
                t=st.selectbox('Saved template',templates,format_func=lambda t:t['name']+' · v'+str(t['version']),key=key+'template')
                if st.button('Use saved template',disabled=bool(doc.get('blocks')) and not replace):
                    snapshot=store.template_document(t);doc['blocks']=snapshot['blocks'];doc['content']=snapshot['content'];doc['template_ref']={'id':str(t['id']),'version':t['version'],'name':t['name']};reset_widgets();st.rerun()
            if os_accounts.can_access_page(user,'crm_templates_manage'):
                name=st.text_input('Save design as template',key=key+'designname')
                if st.button('Save as template'):store.save_design(user,name,doc);st.success('Versioned template saved. This campaign keeps its own snapshot.')
        if not doc.get('blocks'):
            if any(c.values()):
                if st.button('Edit existing content as blocks'):doc['blocks']=legacy_blocks(c);reset_widgets();st.rerun()
            else:st.info('Choose a starter or add a block. Brand header and compliance footer are locked.')
        block_editor(shop,doc,key)
        with st.expander('Prompt factory'):
            from crm_prompt_factory import generate,parse,proposals,apply
            if st.button('Generate Sports Cave Prompt'):st.session_state[key+'prompt']=generate(doc,store.setting('prompts')['value'])
            if st.session_state.get(key+'prompt'):
                copy_prompt(st.session_state[key+'prompt']);st.code(st.session_state[key+'prompt'],language=None)
            pasted=st.text_area('Paste generated JSON',height=120,key=key+'paste')
            if st.button('Validate proposed copy'):st.session_state[key+'proposal']=parse(pasted,doc)
            proposal=st.session_state.get(key+'proposal')
            if proposal:
                with st.expander('Generated copy brief + options'):
                    st.json({k:proposal[k] for k in ('subject_options','preheader_options','copy')})
                changes=proposals(proposal,doc);st.dataframe([{'Field':k,**v} for k,v in changes.items()],hide_index=True)
                selected_fields=st.multiselect('Apply selected fields',list(changes),key=key+'copyselection')
                if st.button('Apply selected copy',disabled=not selected_fields):editor['document']=apply(doc,proposal,selected_fields);reset_widgets();st.rerun()
        if before!=json.dumps(doc,sort_keys=True):doc['copy_reviewed']=False;st.session_state[key+'review']=False
        doc['copy_reviewed']=st.checkbox('I reviewed facts, offer and subject for accuracy',doc['copy_reviewed'],key=key+'review')
    with right:layout_preview(doc,cfg,key)


def reset_widgets():
    st.session_state['campaign_edit_key']=str(uuid.uuid4())
    if st.session_state.get('campaign_editor'):st.session_state['campaign_editor']['document']['copy_reviewed']=False


def block_editor(shop,doc,key):
    blocks=doc.setdefault('blocks',[])
    st.caption('DESIGN · Locked brand header above; locked compliance footer below.')
    cols=st.columns([3,1]);kind=cols[0].selectbox('Add block',KINDS,key=key+'newkind')
    if cols[1].button('Add'):blocks.append(block(kind));reset_widgets();st.rerun()
    if blocks:
        index=st.selectbox('Edit block',range(len(blocks)),format_func=lambda i:str(i+1)+' · '+blocks[i]['type']+' · '+str(blocks[i].get('text',blocks[i].get('label','')))[:35],key=key+'blockindex')
        b=blocks[index];bk=key+b['id'];kind=b['type'];cols=st.columns([1,1,1.5,1.7])
        if cols[0].button('↑',disabled=index==0):blocks[index-1],blocks[index]=blocks[index],blocks[index-1];reset_widgets();st.rerun()
        if cols[1].button('↓',disabled=index==len(blocks)-1):blocks[index+1],blocks[index]=blocks[index],blocks[index+1];reset_widgets();st.rerun()
        if cols[2].button('Copy',help='Duplicate this block'):blocks.insert(index+1,duplicate_block(b));reset_widgets();st.rerun()
        if cols[3].button('Remove block'):blocks.pop(index);reset_widgets();st.rerun()
        if kind in ('heading','text'):b['text']=st.text_area('Block copy',b['text'],height=110,key=bk+'text')
        elif kind=='image':
            b['url']=st.text_input('Image URL (public JPEG/PNG)',b['url'],key=bk+'url')
            b['alt']=st.text_input('Image alt text',b['alt'],key=bk+'alt');b['decorative']=st.checkbox('Decorative image',b['decorative'],key=bk+'decorative')
            image_picker(shop,b,bk)
        elif kind=='button':
            b['label']=st.text_input('Button label',b['label'],key=bk+'label');b['url']=st.text_input('Button HTTPS URL',b['url'],key=bk+'url')
        elif kind=='spacer':b['height']=int(st.number_input('Spacer height',8,64,b['height'],key=bk+'height'))
        elif 'products' in b:product_picker(shop,b,doc['market'],bk)
    st.caption('Images: public JPEG/PNG, 600–1000px wide; aim ≤1 MB. Shopify supplies a proportional JPEG derivative up to 1000px, without cropping. Other unsupported sources require conversion in the existing asset workflow. Asset byte size is not fetched automatically.')


def image_picker(shop,b,key):
    query=st.text_input('Find product images',key=key+'imagequery')
    if st.button('Search images',key=key+'imagesearch'):st.session_state[key+'imageproducts']=shop.campaign_products(query)['nodes']
    products=st.session_state.get(key+'imageproducts',[])
    images=[(p,i) for p in products for i in p.get('images',{}).get('nodes',[]) if asset_url(i.get('url',''))]
    if images:
        selected=st.selectbox('Existing Shopify image',images,format_func=lambda x:x[0]['title']+' · '+str(x[1].get('altText') or x[1].get('id')),key=key+'img')
        product=selected[0];page=product.get('images',{})
        if page.get('pageInfo',{}).get('hasNextPage') and st.button('More images for this product',key=key+'moreimg'):
            following=shop.campaign_images(product['id'],page['pageInfo']['endCursor'])
            product['images']={'nodes':page.get('nodes',[])+following['nodes'],'pageInfo':following['pageInfo']};st.rerun()
        if st.button('Use image',key=key+'useimg'):b['url']=selected[1]['url'];b['alt']=selected[1].get('altText') or selected[0]['title'];reset_widgets();st.rerun()


def product_picker(shop,b,market,key):
    query=st.text_input('Search Shopify products',key=key+'query')
    if st.button('Search products',key=key+'search'):
        page=shop.campaign_products(query);st.session_state[key+'products']=page['nodes'];st.session_state[key+'cursor']=page['pageInfo'].get('endCursor') if page['pageInfo'].get('hasNextPage') else None
    if st.session_state.get(key+'cursor') and st.button('More products',key=key+'more'):
        page=shop.campaign_products(query,st.session_state[key+'cursor']);st.session_state[key+'products']+=page['nodes'];st.session_state[key+'cursor']=page['pageInfo'].get('endCursor') if page['pageInfo'].get('hasNextPage') else None
    products=st.session_state.get(key+'products',[])
    if products:
        p=st.selectbox('Shopify product',products,format_func=lambda p:p['title'],key=key+'product')
        image_page=p.get('images',{})
        if image_page.get('pageInfo',{}).get('hasNextPage') and st.button('More product images',key=key+'moreimages'):
            page=shop.campaign_images(p['id'],image_page['pageInfo']['endCursor'])
            p['images']={'nodes':image_page.get('nodes',[])+page['nodes'],'pageInfo':page['pageInfo']};st.rerun()
        images=[i for i in p.get('images',{}).get('nodes',[]) if asset_url(i.get('url',''))]
        img=st.selectbox('Product image',images,format_func=lambda i:i.get('altText') or i['id'],key=key+p['id']+'image') if images else {}
        if img:st.image(img['url'],width=120)
        if st.button('Select product',key=key+'select',disabled=len(b['products'])>=(4 if b['type']=='product_grid' else 1)):
            b['products'].append({'id':p['id'],'title':p['title'],'url':p.get('onlineStoreUrl') or '', 'image':img.get('url',''),'alt':img.get('altText') or p['title'],'market':market,'facts_checked_at':now().isoformat()});reset_widgets();st.rerun()
    if b['products']:
        index=st.selectbox('Selected artwork',range(len(b['products'])),format_func=lambda i:b['products'][i]['title'],key=key+'selected')
        p=b['products'][index];p['alt']=st.text_input('Artwork alt text',p.get('alt',''),key=key+str(index)+'alt')
        variant_key=key+p['id']+'variants_data'
        st.caption(p['title']+' · '+(p.get('currency','')+' '+p.get('price','') if p.get('price') else 'Price omitted')+' · Edition availability omitted until verified by an approved source.')
        if st.button('Load variants / market price',key=key+'variants'):
            st.session_state[variant_key]=shop.campaign_variants(p['id'])
        variant_page=st.session_state.get(variant_key,{})
        variants=variant_page.get('nodes',[])
        if variant_page.get('pageInfo',{}).get('hasNextPage') and st.button('More variants',key=key+'morevariants'):
            page=shop.campaign_variants(p['id'],variant_page['pageInfo']['endCursor']);page['nodes']=variants+page['nodes'];st.session_state[variant_key]=page;st.rerun()
        if variants:
            v=st.selectbox('Variant for displayed price',variants,format_func=lambda v:v['title'],key=key+p['id']+'variant')
            if st.button('Use verified market price',key=key+'price'):
                money=shop.campaign_price(v['id'],market)
                if money:p.update(variant_id=v['id'],variant_title=v['title'],market=market,price=money['amount'],currency=money['currencyCode'],facts_checked_at=now().isoformat());st.rerun()
                else:st.warning('Market price unavailable. No price was added.')
        if st.button('Refresh canonical facts for comparison',key=key+'refreshproduct'):
            current=shop.products([p['id']],fresh=True)
            if current:
                diff={k:{'saved':p.get(k),'current':current[0].get(remote)} for k,remote in (('title','title'),('url','onlineStoreUrl')) if p.get(k)!=current[0].get(remote)}
                st.session_state[key+'factdiff']=diff
        if key+'factdiff' in st.session_state:st.json(st.session_state[key+'factdiff']);st.caption('Changed facts flagged; saved edits were not overwritten. Re-select the product to use current facts.')
        if st.button('Remove artwork',key=key+'removeproduct'):b['products'].pop(index);reset_widgets();st.rerun()


def review_editor(store,user,editor,key,cfg):
    doc=editor['document'];checks=preflight(doc,cfg=cfg)
    left,right=st.columns([4,7],gap='medium')
    with left:
        st.caption('REVIEW · '+checks['policy'])
        st.caption('Internal test checks: '+str(sum(checks['test'].values()))+' / '+str(len(checks['test']))+' passed')
        with st.expander('Internal test preflight',expanded=not checks['test_ready']):
            for label,ok in checks['test'].items():st.caption(('✓ ' if ok else '○ ')+label)
        with st.expander('Production readiness — blocked'):
            for label,ok in checks['live'].items():st.caption(('✓ ' if ok else '○ ')+label)
            st.caption('One-click unsubscribe production path not activated. Missing legal identity is shown as a test-only warning; no market is automatically legally cleared.')
        a,b=st.columns(2)
        needs=a.button('Needs review',disabled=dirty(editor))
        ready=b.button('Mark test ready',disabled=dirty(editor) or not checks['test_ready'])
        if needs or ready:
            updated=store.save(user,editor['name'],doc,editor['id'],editor['version'],requested_status='NEEDS_REVIEW' if needs else 'TEST_READY')
            st.session_state['campaign_editor']=deepcopy(updated);st.session_state['campaign_saved']=deepcopy(updated);st.rerun()
        if os_accounts.is_admin(user):
            allowlist=store.setting('sending')['value']['internal_recipients']
            if not allowlist:st.info('Configure internal-test recipients in Settings → Sending & Compliance before sending.')
            with st.form(key+'test',clear_on_submit=False):
                recipient=st.text_input('Manual internal test recipient',value='')
                confirmed=st.checkbox('I confirm one internal mailbox and the TEST ONLY footer / inactive unsubscribe warnings.')
                clicked=st.form_submit_button('Send internal test',disabled=not checks['test_ready'] or not allowlist or dirty(editor))
            if dirty(editor):st.caption('Save current changes before sending a test.')
            if clicked:
                saved=store.draft(editor['id'])
                if saved['document']!=doc:st.warning('Save the current revision before testing.')
                else:
                    operation=st.session_state.setdefault(key+'test_operation',str(uuid.uuid4()))
                    result=store.test_campaign(user,editor['id'],editor['version'],recipient=recipient,confirmed=confirmed,operation_id=operation)
                    editor['status']=store.draft(editor['id'])['status']
                    st.success('Test accepted by Resend');st.text(result['message_id']+'\n'+str(result['accepted_at']))
                    if not result['audit_saved']:st.warning('Receipt persistence needs review. Do not resend.')
            if st.button('Start a separate test attempt'):
                st.session_state[key+'test_operation']=str(uuid.uuid4());st.caption('New explicit test attempt prepared. Type and confirm the recipient before sending.')
        else:st.caption('Only an administrator can send an allowlisted internal test.')
        with st.expander('Test history'):
            st.dataframe([{k:r[k] for k in ('campaign_version','status','provider_id','created_at','delivered')} for r in store.test_history(editor['id'])],hide_index=True)
        with st.expander('Revision history'):st.dataframe(store.history(editor['id']),hide_index=True)
    with right:layout_preview(doc,cfg,key)


def copy_prompt(value):
    payload=json.dumps(value).replace('<','\\u003c').replace('>','\\u003e')
    components.html('''<button id="copy" style="background:#d6a548;border:0;border-radius:8px;padding:12px 20px;cursor:pointer">Copy Prompt</button>
<script>document.getElementById('copy').onclick=async function(){const s='''+payload+''';
try { await navigator.clipboard.writeText(s); this.textContent='Prompt copied'; }
catch(e){this.textContent='Use the copy icon below';}}</script>''',height=50)
