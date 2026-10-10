"""Campaign-specific market counts and timing; no infrastructure controls."""
from datetime import date, time as local_time, timedelta
import streamlit as st
from crm_campaign_markets import MARKET_LABELS, audience

@st.fragment
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
    # This dropdown needs only aggregate counts. Exact recipient preparation is
    # owned by Review & send, including fresh eligibility and identity checks.
    st.caption('Shopify subscribed segment size. Eligible recipients and exclusions are checked before sending.')
    if state['error']:st.caption('Audience refresh delayed. Last available counts are shown; sending still requires current eligibility.')
    if doc['market']!=previous:
        doc['copy_reviewed']=False
        from crm_campaign_recovery import flush_current
        flush_current()
        st.rerun() # User selection can affect catalogue prices; hydration cannot.
    # Reuse the visible-control timer. Streamlit's periodic fragment event can
    # outlive this lazy tab and keep targeting its removed fragment identifier.
    poll=key+'market-poll'
    st.html('<style>.st-key-'+poll+'{display:none}</style>')
    with st.container(key=poll):st.button('Refresh segment counts',key=poll+'-tick')
    from crm_campaign_home import arm_home_poll
    arm_home_poll(key=poll,seconds=2 if state.get('pending') else 10)


def timing_control(doc,key,*,schedule_only=False):
    from crm_campaign_schedule import ZONES,DEFAULTS,summary
    value=doc.get('send_timing',{'mode':'now'})
    selected='Schedule'
    if not schedule_only:
        with st.container(key='crm-send-timing'):
            selected=st.radio('Send timing',('Send now','Schedule'),index=int(value['mode']=='schedule'),key=key+'timing',horizontal=True)
    if selected=='Send now':doc['send_timing']={'mode':'now'};return
    a,b=st.columns(2)
    day=a.date_input('Date',date.fromisoformat(value['date']) if value.get('date') else date.today()+timedelta(days=1),key=key+'date')
    hour=b.time_input('Send time',local_time.fromisoformat(value.get('time','07:00')),key=key+'time')
    # Existing recipient-local drafts remain explicitly labelled until edited.
    old_local=value.get('mode')=='schedule' and value.get('time_basis','recipient_local')=='recipient_local'
    basis=st.selectbox('Time basis',('Campaign timezone','Each recipient’s own timezone'),index=int(old_local),key=key+'basis')
    timing={'mode':'schedule','policy_version':2,'time_basis':'campaign_timezone' if basis=='Campaign timezone' else 'recipient_local',
            'date':day.isoformat(),'time':hour.strftime('%H:%M')}
    if basis=='Campaign timezone':
        market=doc.get('market','AU');zones=ZONES.get(market)
        if zones:
            choices=['Choose timezone']+list(zones);preferred=value.get('timezone')
            if preferred not in zones:preferred=DEFAULTS.get(market,'')
            zone=st.selectbox('Timezone',choices,index=choices.index(preferred) if preferred in choices else 0,key=key+'zone-'+market)
            timing['timezone']=zone if zone!='Choose timezone' else ''
        else:timing['timezone']=st.text_input('IANA timezone',value=value.get('timezone',''),placeholder='Choose an explicit timezone, e.g. Europe/London',key=key+'zone-global').strip()
    else:st.caption('Send at this time in each recipient’s own timezone. Delivery can span many hours; review the UTC window before confirming.')
    policy=st.selectbox('Daylight-saving repeated time',('Reject ambiguous time','Earlier occurrence','Later occurrence'),
        index={'reject':0,'earlier':1,'later':2}[value.get('ambiguity','reject')],key=key+'ambiguity')
    timing['ambiguity']={'Reject ambiguous time':'reject','Earlier occurrence':'earlier','Later occurrence':'later'}[policy]
    doc['send_timing']=timing
    try:st.caption('Scheduled · '+summary(timing))
    except ValueError as exc:st.caption(str(exc))
