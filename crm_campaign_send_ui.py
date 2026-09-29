"""Compact explicit send controls. No provider call occurs during rendering."""
from copy import deepcopy
import hashlib
import json
import logging
import uuid
import streamlit as st
import os_accounts
from crm_campaign_send import send_test, review, queue_campaign, OFF
from crm_resend_marketing import DeliveryError, get_resend_marketing_config_status
from crm_store import StoreUnavailable
from crm_resend import MarketingDisabled
ATTESTED_LABELS={
 'Marketing delivery enabled','Business postal address configured and verified',
 'Contact identity configured and confirmed','Visible unsubscribe footer / functional production link',
 'One-click unsubscribe production path activated','SPF/DKIM verification documented',
 'DMARC confirmed before bulk activation','Resend webhooks proven before bulk activation',
 'Market legal review complete','Broadcast provider activated',
 'Sender configured','Reply-To configured','Resend marketing API configured',
}


def safe_error(exc):
    if isinstance(exc,(ValueError,PermissionError,DeliveryError,MarketingDisabled)):return str(exc)
    if isinstance(exc,StoreUnavailable):return 'Campaign storage is unavailable. Your edits are retained.'
    logging.getLogger(__name__).warning('crm_campaign_action_failed type=%s',type(exc).__name__)
    return 'The service is temporarily unavailable. Check the receipt before retrying.'


@st.fragment
def test_control(store,user,editor,key,available=True):
    with st.popover('Send test',disabled=not available or not os_accounts.is_admin(user) or bool(editor.get('archived_at')),key=key+'test_popover'):
        # Native popovers do not focus Streamlit inputs automatically. This small
        # observer is scoped to this labelled popover; no data leaves the browser.
        st.html("""<script>(()=>{
          if(window.scCampaignTestFocus)return;
          const seen=new WeakSet();
          const focus=()=>{const input=document.querySelector('[role="dialog"] input[aria-label="Send test email"]');
            if(input&&input.getClientRects().length&&!seen.has(input)){seen.add(input);requestAnimationFrame(()=>input.focus({preventScroll:true}));}};
          const observer=new MutationObserver(focus);observer.observe(document.body,{childList:true,subtree:true});
          window.scCampaignTestFocus=observer;focus();
        })();</script>""",unsafe_allow_javascript=True)
        with st.form(key+'single_test',clear_on_submit=False,border=False):
            cols=st.columns([6,1],vertical_alignment='bottom',gap='small')
            recipient=cols[0].text_input('Send test email',placeholder='email@example.com',key=key+'test_recipient',help='Enter confirms you reviewed this copy and chose one approved internal mailbox.')
            submit=cols[1].form_submit_button('→',help='Send this reviewed internal test',disabled=bool(st.session_state.get(key+'test_busy')))
        if submit:
            if st.session_state.get(key+'test_busy'):return
            # Identical content/recipient retries retain their durable operation ID.
            doc={k:v for k,v in editor['document'].items() if k!='copy_reviewed'}
            digest=hashlib.sha256(json.dumps([doc,recipient.strip().casefold()],sort_keys=True).encode()).hexdigest()
            operations=st.session_state.setdefault(key+'test_operations',{})
            operation=operations.setdefault(digest,str(uuid.uuid4()))
            st.session_state[key+'test_busy']=True
            try:
                with st.spinner('Sending…'):
                    result=send_test(store,user,editor,recipient,operation)
                st.session_state['campaign_saved']=deepcopy(editor)
                st.success('Test email sent to '+recipient.strip())
                if not result['audit_saved']:st.warning('Provider accepted the test; receipt storage needs review. Do not resend.')
            except Exception as exc:st.error('Test email could not be sent — '+safe_error(exc))
            finally:st.session_state[key+'test_busy']=False


@st.dialog('Review campaign',width='small')
def review_dialog(shop,store,user,editor,key):
    delivery=get_resend_marketing_config_status()
    token=key+'send_review'
    if token not in st.session_state:
        try:
            with st.spinner('Checking audience…'):
                st.session_state[token]=review(shop,store,editor)
        except Exception as exc:
            st.error('Campaign review unavailable — '+safe_error(exc))
            if st.button('Cancel'):st.rerun()
            return
    result=st.session_state[token];doc=result['document'];counts=result['counts']
    st.write('**Campaign**  '+editor['name'])
    st.write('**Subject**  '+(doc['content']['subject'] or 'Missing'))
    from crm_campaign_markets import MARKET_LABELS
    st.caption('Market: '+MARKET_LABELS[doc['market']]+' · Audience: '+doc['audience']['name'])
    st.write(str(counts['eligible'])+' recipients · '+str(sum(counts['excluded'].values()))+' excluded')
    if counts['excluded']:
        with st.expander('Excluded'):
            for reason,total in counts['excluded'].items():st.caption(reason.replace('_',' ').capitalize()+': '+str(total))
    timing=doc.get('send_timing',{'mode':'now'})
    st.caption('Delivery: '+('Scheduled · '+timing['date']+' · '+timing['time']+' recipient local time' if timing['mode']=='schedule' else 'Send now'))
    st.caption('From: '+(delivery['sender'] or 'Not configured')+' · Marketing delivery '+('ON' if delivery['marketing_enabled'] else 'OFF'))
    blockers=result['blockers']
    content_blockers=[b for b in blockers if b not in ATTESTED_LABELS]
    if not editor.get('id'):content_blockers.insert(0,'Save draft before sending')
    if content_blockers:st.warning('Complete before sending: '+ '; '.join(content_blockers))
    if delivery['marketing_enabled'] and any(b in ATTESTED_LABELS for b in blockers):
        st.warning('Production delivery setup is not yet verified. Production configuration requires administrator verification before activation.')
    if not delivery['marketing_enabled']:st.info(OFF)
    st.caption('Confirming Send now confirms review of this campaign’s copy and subject.')
    a,b=st.columns(2)
    if a.button('Cancel',key=key+'cancel_send'):st.rerun()
    if b.button('Send now',key=key+'confirm_send',disabled=(bool(blockers) or not editor.get('id')) and delivery['marketing_enabled']):
        operation=st.session_state.setdefault(key+'production_operation',str(uuid.uuid4()))
        try:
            with st.spinner('Preparing delivery…'):
                sent=queue_campaign(shop,store,user,editor,operation)
            st.success('Campaign already queued.' if sent['already_started'] else 'Campaign queued for '+str(sent['recipients'])+' recipients.')
        except Exception as exc:st.error(safe_error(exc))
