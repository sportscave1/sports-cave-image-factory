"""Campaign-specific market counts and timing; no infrastructure controls."""
from datetime import date, time as local_time, timedelta
import logging
import time
import streamlit as st
from crm_campaign_markets import MARKET_LABELS, audience, calculate

def market_control(shop,store,doc,key):
    # Session-local aggregate cache: no addresses/profile data retained by this UI.
    cache_key='campaign_market_counts_'+str(doc.get('smart_hours',16))
    cached=st.session_state.get(cache_key)
    if not cached or time.monotonic()-cached['at']>120:
        try:
            with st.spinner('Loading subscribers…'):
                results=calculate(shop,store,doc.get('smart_hours',16))
            cached={'at':time.monotonic(),'counts':{m:r['eligible'] for m,r in results.items()}}
        except Exception as exc:
            logging.getLogger(__name__).warning('crm_market_counts_unavailable type=%s',type(exc).__name__)
            cached={'at':time.monotonic(),'counts':{}}
        st.session_state[cache_key]=cached
    counts=cached['counts']
    doc['market']=st.selectbox('Market',list(MARKET_LABELS),index=list(MARKET_LABELS).index(doc['market']),
        format_func=lambda m:MARKET_LABELS[m]+' · '+(format(counts[m],',') if m in counts else '—'),key=key+'market')
    selected=audience(doc['market'])
    if doc.get('audience')!=selected:doc['counts']={}
    doc['audience']=selected;doc['market_audience']=True
    if counts:st.caption(format(counts[doc['market']],',')+' eligible subscribers')
    else:st.caption('Subscriber counts unavailable. Editing is available; send review will recheck.')

def timing_control(doc,key):
    value=doc.get('send_timing',{'mode':'now'})
    selected=st.radio('Send timing',('Send now','Schedule'),index=int(value['mode']=='schedule'),key=key+'timing')
    if selected=='Send now':doc['send_timing']={'mode':'now'};return
    a,b=st.columns(2)
    day=a.date_input('Date',date.fromisoformat(value['date']) if value.get('date') else date.today()+timedelta(days=1),key=key+'date')
    hour=b.time_input('Local send time',local_time.fromisoformat(value.get('time','07:00')),key=key+'time')
    doc['send_timing']={'mode':'schedule','date':day.isoformat(),'time':hour.strftime('%H:%M')}
    st.caption('Recipients receive this at approximately '+hour.strftime('%I:%M %p').lstrip('0')+' in their local timezone.')
