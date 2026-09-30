"""Compact Sent rows and on-demand details using existing Streamlit dialogs."""
import streamlit as st
from crm_campaign_analytics import sent_page,details,money
from crm_campaign_markets import MARKET_LABELS

def _close_analytics():
    st.session_state.pop('sent_analytics_id',None)
    st.session_state.pop('sent_preview_id',None)

@st.dialog('Campaign analytics',width='large',on_dismiss=_close_analytics)
def analytics(store,user,row):
    st.text(row['name'])
    detail=details(store,row['id'])
    conversion='—' if row['conversion_rate'] is None else str(row['conversion_rate'])+'%'
    st.caption('Suppressed: '+str(row['suppressed'])+' · Conversion: '+conversion+' · Revenue/click: '+money(row['revenue_per_click']))
    seconds=detail['timing']['seconds']
    if seconds is not None:st.caption('Average click → purchase: '+format(float(seconds)/3600,'.1f')+' hours')
    if detail['timing']['mirror_unavailable']:st.caption('Shopify attribution marker unavailable for some orders; recorded attribution is retained.')
    if detail['products']:
        st.dataframe([{'Product':p['product'],'Orders':p['orders'],'Units':p['units'],'Revenue':money({p['currency']:p['revenue']})} for p in detail['products']],hide_index=True,height='content')
    if st.button('Email preview',key='sent_preview_'+str(row['id'])):
        st.session_state['sent_preview_id']=row['id']
    if st.session_state.get('sent_preview_id')==row['id']:
        snapshot=store.template(row['template_id'],row['template_version'])
        if snapshot.get('document'):
            from crm_html_workspace import composer_canvas
            composer_canvas(snapshot['document'],snapshot['render_settings'],'sent_preview',None)
    with st.expander('Recipient delivery history (first 100)'):st.dataframe(detail['recipients'],hide_index=True,height='content')
    a,b=st.columns(2)
    if a.button('Duplicate',key='sent_duplicate_'+str(row['id'])):
        from crm_campaign_page import open_editor
        _close_analytics()
        open_editor(store.duplicate(user,row['id']));st.rerun()
    if b.button('Restore' if row.get('archived_at') else 'Archive',key='sent_archive_'+str(row['id'])):
        draft=store.draft(row['id'])
        (store.restore if row.get('archived_at') else store.archive)(user,row['id'],draft['version'])
        _close_analytics()
        st.rerun()

@st.fragment(run_every='30s')
def _live_sent_table(store,user):
    _sent_table(store,user)

def sent_table(store,user):
    # A timer rerun must not unregister an open dialog's lazy widgets.
    if st.session_state.get('sent_analytics_id'):
        _sent_table(store,user)
    else:
        _live_sent_table(store,user)

def _sent_table(store,user):
    with st.popover('View'):
        archived=st.checkbox('Archived sent campaigns',key='sent_archived')
    if st.session_state.get('sent_archived_filter')!=archived:
        st.session_state.update(sent_archived_filter=archived,sent_offset=0)
    offset=st.session_state.get('sent_offset',0);rows=sent_page(store,offset,26,archived=archived)
    if store.state('email_attribution_scan').get('error'):st.caption('Shopify attribution refresh delayed. Stored metrics remain available.')
    if not rows:st.caption('No sent campaigns yet.');return
    def pair(n,r):return str(n)+' · '+(str(r)+'%' if r is not None else '—')
    cells=[{'Campaign':r['name'],'Market':MARKET_LABELS.get(r['market'],r['market']),
      'Sent':str(r['sent_at'] or r['updated_at'])[:16],'Recipients':r['recipients'],
      'Delivered':pair(r['delivered'],r['delivery_rate']),'Opens':pair(r['opens'],r['open_rate']),
      'Clicks':pair(r['clicks'],r['click_rate']),'Bounces':r['bounces'],'Complaints':r['complaints'],
      'Orders':r['orders'],'Revenue':money(r['revenue']),'Revenue / recipient':money(r['revenue_per_recipient']),
      'Actions':'View analytics'} for r in rows[:25]]
    generation=st.session_state.get('sent_table_generation',0)
    selected=st.dataframe(cells,hide_index=True,height=58+35*len(cells),row_height=35,on_select='rerun',selection_mode='single-row',key='sent_table_'+str(generation))
    if selected.selection.rows:
        st.session_state['sent_table_generation']=generation+1
        st.session_state['sent_analytics_id']=rows[selected.selection.rows[0]]['id']
        st.rerun()
    active=next((r for r in rows if str(r['id'])==str(st.session_state.get('sent_analytics_id'))),None)
    if active:analytics(store,user,active)
    elif st.session_state.get('sent_analytics_id'):_close_analytics()
    with st.container(horizontal=True):
        if st.button('Previous',disabled=not offset,key='sent_previous'):st.session_state['sent_offset']=max(0,offset-25);st.rerun()
        if st.button('Next',disabled=len(rows)<26,key='sent_next'):st.session_state['sent_offset']=offset+25;st.rerun()

def locked_campaign(store,user,delivery):
    snapshot=store.template(delivery['template_id'],delivery['template_version'])
    from crm_campaign_page import html_escape_name
    st.markdown('### '+html_escape_name(delivery['name'])+' · '+delivery['status'])
    st.caption('This campaign is locked. Duplicate it to create a new draft.')
    if st.button('Duplicate campaign',key='locked_duplicate'):
        from crm_campaign_page import open_editor
        open_editor(store.duplicate(user,delivery['id']));st.rerun()
    from crm_html_workspace import composer_canvas
    if snapshot.get('document'):composer_canvas(snapshot['document'],snapshot['render_settings'],'locked_campaign',None)
