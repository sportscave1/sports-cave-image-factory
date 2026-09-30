"""Campaign-specific market counts and timing; no infrastructure controls."""
from datetime import date, time as local_time, timedelta
import streamlit as st
from crm_campaign_markets import MARKET_LABELS, audience

@st.fragment(run_every=2)
def market_control(shop,store,doc,key):
    # Polling reruns only this small fragment, never the editor or preview.
    from crm_segment_counts import COUNTS
    state=COUNTS.display(shop,store,doc.get('smart_hours',16))
    counts=state['counts'];previous=doc['market']
    doc['market']=st.selectbox('Segment',list(MARKET_LABELS),index=list(MARKET_LABELS).index(previous),
        format_func=lambda m:MARKET_LABELS[m]+' · '+(format(counts[m],',') if m in counts else '—' if state['error'] else '…'),key=key+'market')
    selected=audience(doc['market'])
    if doc.get('audience')!=selected:doc['counts']={}
    doc['audience']=selected;doc['market_audience']=True
    st.caption('Shopify subscribed segment size. Eligible recipients and exclusions are checked before sending.')
    if state['error']:st.caption('Audience refresh delayed. Last available counts are shown; sending still requires current eligibility.')
    if st.button('Refresh audiences',key=key+'refresh_audiences'):
        COUNTS.refresh(shop,store)
        doc['counts']={}
        st.rerun(scope='fragment')
    if doc['market']!=previous:
        doc['copy_reviewed']=False
        from crm_campaign_recovery import flush_current
        flush_current()
        st.rerun() # User selection can affect catalogue prices; hydration cannot.


def timing_control(doc,key):
    value=doc.get('send_timing',{'mode':'now'})
    with st.container(key='crm-send-timing'):
        selected=st.radio('Send timing',('Send now','Schedule'),index=int(value['mode']=='schedule'),key=key+'timing',horizontal=True)
    if selected=='Send now':doc['send_timing']={'mode':'now'};return
    a,b=st.columns(2)
    day=a.date_input('Date',date.fromisoformat(value['date']) if value.get('date') else date.today()+timedelta(days=1),key=key+'date')
    hour=b.time_input('Local send time',local_time.fromisoformat(value.get('time','07:00')),key=key+'time')
    doc['send_timing']={'mode':'schedule','date':day.isoformat(),'time':hour.strftime('%H:%M')}
    st.caption('Recipients receive this at approximately '+hour.strftime('%I:%M %p').lstrip('0')+' in their local timezone.')
