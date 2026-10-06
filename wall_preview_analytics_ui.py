"""Compact analytics above the unchanged operational inbox."""
from datetime import datetime,timedelta
import streamlit as st
import social_media
import wall_preview_analytics as store

@st.cache_data(ttl=60,show_spinner=False)
def snapshot(start,end,product='',device='',capture=''):
    return store.report(dict(start_date=start,end_date=end,product_id=product,device_type=device,capture_source=capture))

def cash(rows):
    return ' · '.join(f"{r['currency']} {float(r['revenue']):,.2f}" for r in rows if r.get('revenue') is not None) or '—'

def pct(value):return '—' if value is None else f'{value:.1f}%'

def bounds(days):
    today=datetime.now(social_media.SYDNEY_TZ).date()
    start=datetime.combine(today-timedelta(days=days-1),datetime.min.time(),social_media.SYDNEY_TZ)
    end=datetime.combine(today+timedelta(days=1),datetime.min.time(),social_media.SYDNEY_TZ)
    return start.isoformat(),end.isoformat()

def overview():
    st.subheader('Wall Preview — Last 7 Days')
    try:
        data=snapshot(*bounds(7))['summary']
        for col,label,value in zip(st.columns(4),('Opens','ATCs','Purchases','Revenue'),(data['opens'],data['atc'],data['purchased'],cash(data['revenue']))):col.metric(label,value)
    except Exception:st.caption('Wall Preview analytics temporarily unavailable.')
    def open_inbox():st.session_state['social-media-workspace-view']='Wall Preview Inbox'
    st.button('View Wall Preview Analytics →',key='wall-preview-overview-open',on_click=open_inbox)

def render():
    with st.container(border=True):
        st.markdown('**Wall Preview performance**')
        cols=st.columns([2,2,1,1])
        period=cols[0].selectbox('Date range',('Today','7 Days','30 Days','90 Days','Custom'),index=2,key='wp-analytics-period')
        product=cols[1].text_input('Product ID',key='wp-analytics-product')
        device=cols[2].selectbox('Device',('All','mobile','desktop','tablet'),key='wp-analytics-device')
        capture=cols[3].selectbox('Photo source',('All','camera','upload'),key='wp-analytics-capture')
        start,end=bounds({'Today':1,'7 Days':7,'30 Days':30,'90 Days':90,'Custom':30}[period])
        if period=='Custom':
            dates=st.date_input('Date range (Sydney)',value=(datetime.fromisoformat(start).date(),datetime.now(social_media.SYDNEY_TZ).date()),key='wp-analytics-custom')
            if len(dates)!=2:return
            start=datetime.combine(dates[0],datetime.min.time(),social_media.SYDNEY_TZ).isoformat()
            end=datetime.combine(dates[1]+timedelta(days=1),datetime.min.time(),social_media.SYDNEY_TZ).isoformat()
        try:data=snapshot(start,end,product,'' if device=='All' else device,'' if capture=='All' else capture)
        except Exception:st.caption('Analytics temporarily unavailable. Inbox controls remain available below.');return
        summary=data['summary']
        metrics=[('Preview Opens',summary['opens']),('Unique Sessions',summary['sessions']),('Photos Loaded',summary['photo_ready']),('Placement Confirmed',summary['confirmed']),('Added To Cart',summary['atc']),('Purchased',summary['purchased']),('Preview → ATC %',pct(summary['atc_percent'])),('Preview → Purchase %',pct(summary['purchase_percent'])),('Revenue',cash(summary['revenue']))]
        for offset in (0,5):
            for col,(label,value) in zip(st.columns(5 if offset==0 else 4),metrics[offset:offset+5]):col.metric(label,value)
        st.caption('Unique preview journeys per stage. Revenue is attributed line revenue, separated by currency. Tracking starts at rollout; missing events are not inferred.')
        with st.expander('Funnel and product performance',expanded=True):
            st.dataframe([{'Stage':r['stage'],'Event count':r['events'],'Journeys':r['journeys'],'Next stage':pct(r['next_stage_percent']),'Drop-off':pct(r['drop_off_percent'])} for r in data['funnel']],hide_index=True,use_container_width=True)
            st.dataframe([{'Product':r['product'] or r['product_id'],'Preview Opens':r['opens'],'Photo Ready':r['photo_ready'],'Confirmed':r['confirmed'],'ATC':r['atc'],'Purchased':r['purchased'],'Revenue':cash(r['revenue']),'Preview → Purchase %':pct(r['purchase_percent'])} for r in data['products']],hide_index=True,use_container_width=True)
        with st.expander('Interaction insights'):
            st.dataframe(data['insights'],hide_index=True,use_container_width=True)
