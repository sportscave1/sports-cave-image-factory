"""Compact analytics above the unchanged operational inbox."""
from table_design import TABLE_ROW_HEIGHT
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

def render():
    with st.container():
        kpis=st.container()
        with st.container(key='wp-analytics-filters'):
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
        except Exception:
            st.caption('Analytics temporarily unavailable. Inbox remains available.')
            return dict(start_date=start,end_date=end,product_id=product,device_type='' if device=='All' else device,capture_source='' if capture=='All' else capture)
        summary=data['summary']
        engagement=data.get('engagement',{})
        def number(key):return engagement.get(key,0)
        def duration(key):
            value=engagement.get(key)
            return '—' if value is None else f'{float(value):.1f}s'
        metrics=[('CTA Clicks',number('cta_clicks')),('Unique Clickers',number('unique_clickers')),
                 ('Preview Opens',number('opens')),('Click → Open %',pct(engagement.get('click_open_percent'))),
                 ('Avg Active Time',duration('avg_active_seconds')),('Median Active Time',duration('median_active_seconds')),
                 ('Photos Loaded',number('photo_ready')),('Placement Confirmed',number('confirmed')),
                 ('Placement Rate',pct(engagement.get('placement_percent'))),('Added to Cart',number('atc')),
                 ('Preview → Cart %',pct(engagement.get('cart_percent')))]
        import html
        kpis.markdown('<div class="sc-social-kpis">'+''.join('<div class="sc-social-kpi"><span>'+html.escape(label)+'</span><strong>'+html.escape(str(value))+'</strong></div>' for label,value in metrics)+'</div>',unsafe_allow_html=True)
        return dict(start_date=start,end_date=end,product_id=product,device_type='' if device=='All' else device,capture_source='' if capture=='All' else capture)


def details(filters):
    with st.popover('Analytics details'):
        try:data=snapshot(filters['start_date'],filters['end_date'],filters['product_id'],filters['device_type'],filters['capture_source'])
        except Exception:
            st.caption('Analytics temporarily unavailable.');return
        summary=data['summary']
        st.caption('Performance uses instrumented viewer visits: one count per stage per visit; unique clickers are anonymous browser-session visitors. Rates match subsequent stages to the same visit. Active time excludes hidden, unfocused and 60-second idle periods; averages use recorded cumulative samples, never open-to-close elapsed time. Historical events without visit IDs remain below, not inferred into the new funnel.')
        st.caption('Unique journeys per stage; sessions span all recorded events. Historical captures may lack opening events. Missing events are not inferred.')
        st.caption('Purchased: '+str(summary['purchased'])+' · Revenue: '+cash(summary['revenue'])+' · Preview → ATC: '+pct(summary['atc_percent'])+' · Preview → Purchase: '+pct(summary['purchase_percent']))
        st.dataframe(data['funnel'],hide_index=True,use_container_width=True, row_height=TABLE_ROW_HEIGHT)
        st.dataframe(data['products'],hide_index=True,use_container_width=True, row_height=TABLE_ROW_HEIGHT)
        st.dataframe(data['insights'],hide_index=True,use_container_width=True, row_height=TABLE_ROW_HEIGHT)
