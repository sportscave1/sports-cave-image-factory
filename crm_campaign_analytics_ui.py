"""Compact Sent rows and on-demand details using existing Streamlit dialogs."""
import streamlit as st
from crm_campaign_analytics import sent_page,details,money
from crm_campaign_markets import MARKET_LABELS
from crm_store import StoreUnavailable

def _close_analytics():
    from crm_campaign_home_data import invalidate
    invalidate(st.session_state)
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
    email_orders(store,detail.get('orders',[]))
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
        from crm_campaign_recovery import flush_current
        if flush_current():
            _close_analytics()
            open_editor(store.duplicate(user,row['id']));st.rerun()
    if b.button('Restore' if row.get('archived_at') else 'Archive',key='sent_archive_'+str(row['id'])):
        draft=store.draft(row['id'])
        (store.restore if row.get('archived_at') else store.archive)(user,row['id'],draft['version'])
        _close_analytics()
        st.rerun()


def email_orders(store,orders):
    from crm_logic import date
    import os
    from shopify_sync import normalize_store_domain
    def stamp(value):return date(value).strftime('%d %b %H:%M %Z') if value else '—'
    def elapsed(value):
        if value is None:return '—'
        seconds=int(value)
        return str(seconds//86400)+'d '+str(seconds%86400//3600)+'h' if seconds>=86400 else str(seconds//3600)+'h '+str(seconds%3600//60)+'m' if seconds>=3600 else str(seconds//60)+'m'
    def link(row):
        host=normalize_store_domain(os.getenv('SHOPIFY_STORE_DOMAIN',''))
        identity=row['shopify_order_id'].rsplit('/',1)[-1]
        return 'https://'+host+'/admin/orders/'+identity if host.endswith('.myshopify.com') and identity.isdigit() else ''
    st.caption('EMAIL ORDERS')
    if not orders:
        st.caption('No attributed orders yet.');return
    selection=st.dataframe([{'Order':r['order_name'],'Ordered':stamp(r['order_created_at']),
      'Products':', '.join(p['title']+' ×'+str(p.get('purchased_quantity',p['quantity'])) for p in r['products']),
      'Revenue':money({r['currency']:r['amount']}),'Email click':stamp(r['click_at']),
      'Time to purchase':elapsed((r.get('evidence') or {}).get('time_to_purchase_seconds')),
      'Attribution':'Shopify UTM' if r['method'] in ('SHOPIFY_UTM','SHOPIFY_UTM_EXACT') else 'Resend click',
      'Shopify':{'UPDATED':'✓ Mirrored','FAILED':'Failed','PENDING':'Pending'}.get(r['mirror_status'],r['mirror_status']),
      'Open':link(r)} for r in orders],hide_index=True,height='content',on_select='rerun',selection_mode='single-row',key='email_orders_'+str(orders[0]['campaign_id']),
      column_config={'Open':st.column_config.LinkColumn('Open',display_text='Open Shopify ↗')})
    picked=selection.selection.rows
    index=picked[0] if picked and 0<=picked[0]<len(orders) else None
    with st.expander('Order evidence',expanded=index is not None):
        selected=st.selectbox('Order',options=[r['shopify_order_id'] for r in orders],index=None,
          format_func=lambda identity:next(r['order_name'] for r in orders if r['shopify_order_id']==identity),key='email_order_evidence') if index is None else orders[index]['shopify_order_id']
        if not selected:return
        row=next(r for r in orders if r['shopify_order_id']==selected);proof=row.get('evidence') or {}
        from crm_campaign_analytics import order_delivery
        st.caption('Campaign · '+str(proof.get('campaign_name') or '—'))
        st.caption('Campaign send ID · '+str(row['campaign_send_id']))
        resend,shopify,attribution,purchase=st.tabs(['Resend','Shopify','Attribution','Purchase'])
        def facts(items):
            from html import escape
            st.html('<div style="display:grid;grid-template-columns:minmax(8rem,12rem) minmax(0,1fr);gap:5px 12px;font-size:13px;line-height:1.6;overflow-wrap:anywhere">'+
              ''.join('<strong>'+escape(label)+'</strong><span>'+escape(str(value if value is not None else 'Unavailable'))+'</span>' for label,value in items)+'</div>')
        with resend:
            delivery=order_delivery(store,row)
            if not delivery:st.caption('No matching recipient delivery record.')
            for item in delivery:
                facts([(k.replace('_',' ').title(),stamp(item[k])) for k in ('sent','delivered','opened','first_click','last_click')])
                st.caption('Recipient send · '+str(item['recipient_send_id']))
                st.caption('Resend message · '+str(item['provider_email_id'] or 'Unavailable'))
        with shopify:
            facts([('Order',row['order_name']),('Ordered',stamp(row['order_created_at'])),('Journey ready',proof.get('journey_ready')),
              ('Matching visit',stamp(proof.get('shopify_visit_occurred_at'))),
              *[(k.replace('_',' ').upper(),proof.get(k)) for k in ('utm_source','utm_medium','utm_campaign','utm_content')]])
            st.caption('Landing page (tracking parameters only)');st.text(proof.get('landing_page') or 'Unavailable')
        with attribution:
            facts([('Method',row['method']),('Confidence',proof.get('confidence')),('Click → purchase',elapsed(proof.get('time_to_purchase_seconds'))),
              ('Window',str(proof.get('attribution_window_days','—'))+' days'),('Shopify mirror',row['mirror_status'])])
            if row.get('mirror_error'):st.caption(row['mirror_error'].replace('_',' '))
        with purchase:
            st.dataframe(row['products'],hide_index=True,height='content')
            facts([('Gross received',money({row['currency']:row.get('gross_revenue')})),
                   ('Refunded',money({row['currency']:row.get('refund_amount')})),('Net attributed revenue',money({row['currency']:row['amount']}))])

@st.fragment(run_every='30s')
def _live_sent_table(store,user):
    try:_sent_table(store,user)
    except StoreUnavailable:st.caption('Campaign list temporarily unavailable.')

def sent_table(store,user):
    # A timer rerun must not unregister an open dialog's lazy widgets.
    if st.session_state.get('sent_analytics_id'):
        _sent_table(store,user)
    else:
        _live_sent_table(store,user)

def _sent_table(store,user):
    from crm_composer_style import history_cell,history_date,history_header
    with st.popover('View all campaigns / archived'):
        archived=st.checkbox('Archived sent campaigns',key='sent_archived')
    if st.session_state.get('sent_archived_filter')!=archived:
        st.session_state.update(sent_archived_filter=archived,sent_offset=0)
    offset=st.session_state.get('sent_offset',0);rows=sent_page(store,offset,26,archived=archived)
    if store.state('email_attribution_scan').get('error'):st.caption('Shopify attribution refresh delayed. Stored metrics remain available.')
    if not rows:
        with st.container(key='crm-history-empty'):
            st.html(history_cell('No sent campaigns yet.','Sent campaign performance will appear here after your first send.'))
        return
    widths=[2.9,.9,1,1,1,.7,1.2,1.25,.8,1.3]
    with st.container(key='crm-sent-rows'):
        history_header(('Campaign','Recipients','Delivered','Opened','Clicked','Orders','Revenue','Rev/recipient','B / C','Actions'),widths)
        for row in rows[:25]:
            identity=str(row['id'])
            with st.container(key='crm-history-row-sent-'+identity):
                cells=st.columns(widths,vertical_alignment='center',gap='small')
                cells[0].html(history_cell(row['name'],MARKET_LABELS.get(row['market'],row['market'])+' · '+history_date(row['sent_at'] or row['updated_at'])))
                cells[1].html(history_cell(format(row['recipients'],',')))
                for column,count,rate in ((2,'delivered','delivery_rate'),(3,'opens','open_rate'),(4,'clicks','click_rate')):
                    cells[column].html(history_cell(format(row[count],','),'—' if row[rate] is None else str(row[rate])+'%'))
                cells[5].html(history_cell(format(row['orders'],',')))
                cells[6].html(history_cell(money(row['revenue'])))
                cells[7].html(history_cell(money(row['revenue_per_recipient'])))
                cells[8].html(history_cell(str(row['bounces'])+' / '+str(row['complaints']),label='Bounces / Complaints'))
                with cells[9].popover('Actions'):
                    if st.button('View analytics',key='sent_analytics_'+identity):
                        st.session_state['sent_analytics_id']=row['id'];st.rerun()
                    if st.button('Duplicate',key='sent_row_duplicate_'+identity):
                        from crm_campaign_page import open_editor
                        from crm_campaign_recovery import flush_current
                        if flush_current():open_editor(store.duplicate(user,row['id']));st.rerun()
                    if st.button('Restore' if row.get('archived_at') else 'Archive',key='sent_row_archive_'+identity):
                        draft=store.draft(row['id'])
                        (store.restore if row.get('archived_at') else store.archive)(user,row['id'],draft['version']);st.rerun()
    active=next((r for r in rows if str(r['id'])==str(st.session_state.get('sent_analytics_id'))),None)
    if active:analytics(store,user,active)
    elif st.session_state.get('sent_analytics_id'):_close_analytics()
    if offset or len(rows)>25:
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
