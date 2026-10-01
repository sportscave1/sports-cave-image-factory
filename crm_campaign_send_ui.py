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


def safe_error(exc):
    if isinstance(exc,(ValueError,PermissionError,DeliveryError,MarketingDisabled)):return str(exc).replace('Market legal review','Segment legal review').replace('market audience mode','segment audience mode')
    if isinstance(exc,StoreUnavailable):return 'Campaign storage is unavailable. Your edits are retained.'
    logging.getLogger(__name__).warning('crm_campaign_action_failed type=%s',type(exc).__name__)
    return 'The service is temporarily unavailable. Check the receipt before retrying.'


@st.fragment
def test_control(store,user,editor,key,available=True,cfg=None):
    with st.popover('Send test',disabled=not available or not os_accounts.can_access_page(user,'CRM Campaigns') or bool(editor.get('archived_at')),key=key+'test_popover',on_change='rerun'):
        from crm_campaign_test_ui import test_styles, readiness
        from crm_campaign_issues import CampaignValidationError
        from crm_campaign_content import preflight
        test_styles()
        st.caption('SEND TEST')
        checks=None
        current=st.session_state.get('campaign_editor',editor)
        if str(current.get('id'))==str(editor.get('id')):editor=current
        try:
            review_doc=deepcopy(editor['document']);review_doc['copy_reviewed']=True
            checks=preflight(review_doc,cfg=cfg if cfg is not None else store.render_settings())
        except Exception as exc:
            st.caption('Readiness unavailable · '+safe_error(exc))
        from pathlib import Path
        scripts=Path(__file__).with_name('components')/'campaign_recovery'
        controls_js='\n'.join(scripts.joinpath(name).read_text(encoding='utf-8') for name in ('test_flush.js','test_sections.js'))
        # Native popovers do not focus Streamlit inputs automatically. This small
        # observer is scoped to this labelled popover; no data leaves the browser.
        st.html("""<script>(()=>{
          if(window.scCampaignTestFocus)return;
          const seen=new WeakSet();
          const focus=()=>{const input=document.querySelector('[data-testid="stPopoverBody"] input[aria-label="Send test email"]');
            if(input&&input.getClientRects().length&&!seen.has(input)){seen.add(input);requestAnimationFrame(()=>input.focus({preventScroll:true}));}};
          const observer=new MutationObserver(focus);observer.observe(document.documentElement,{childList:true,subtree:true});
          window.scCampaignTestFocus=observer;focus();
        })();
        """+controls_js+'</script>',unsafe_allow_javascript=True)
        with st.form(key+'single_test',clear_on_submit=False,border=False):
            cols=st.columns([6,1],vertical_alignment='bottom',gap='small')
            recipient=cols[0].text_input('Send test email',placeholder='email@example.com',key=key+'test_recipient',help='Send test uses the real Shopify unsubscribe link for this customer.')
            submit=cols[1].form_submit_button('→',help='Send this test email',disabled=bool(st.session_state.get(key+'test_busy')))
        if submit:
            if st.session_state.get(key+'test_busy'):return
            # A fragment can retain an older argument after a component rerun.
            current=st.session_state.get('campaign_editor',editor)
            if current is not editor and str(current.get('id'))!=str(editor.get('id')):
                st.error('Campaign changed. Reopen Send test.');return
            editor=current
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
            except CampaignValidationError as exc:checks=exc.checks
            except Exception as exc:st.error('Test email could not be sent — '+safe_error(exc))
            finally:st.session_state[key+'test_busy']=False
        if checks is not None:readiness(checks)


@st.fragment
def send_control(shop,store,user,editor,key,cfg,available=True):
    if st.button('Send now',key=key+'open_review',type='primary',disabled=not available or bool(editor.get('archived_at')) or bool(editor.get('recovery_readonly'))):
        review_dialog(shop,store,user,editor,key,cfg)


@st.dialog('Review campaign',width='large',on_dismiss='ignore')
def review_dialog(shop,store,user,editor,key,cfg=None):
    # This shell performs no draft/history/audience/provider reads.
    import time
    started=time.monotonic()
    delivery=get_resend_marketing_config_status()
    doc=editor['document']
    st.html("""<style>
    [role="dialog"]:has(.st-key-crm-send-review-summary){max-height:92vh;overflow:auto}
    .st-key-crm-send-review-summary{min-height:255px}
    </style>""")
    with st.container(key='crm-send-review-summary'):
        summary,preview=st.columns(2)
        summary.write('**Campaign**  '+editor['name'])
        summary.write('**Subject**  '+(doc['content']['subject'] or 'Missing'))
        summary.caption('Preheader: '+doc['content']['preheader'])
        summary.caption('From: '+(delivery['sender'] or 'Not configured'))
        summary.caption('Reply-to: '+(delivery['reply_to'] or 'Not configured'))
        from crm_campaign_markets import MARKET_LABELS
        summary.caption('Segment: '+MARKET_LABELS[doc['market']])
        if (doc.get('counts') or {}).get('eligible') is not None:
            summary.caption('Last known eligible audience: '+str(doc['counts']['eligible'])+' · final check pending')
        from crm_tracking import send_identity
        if editor.get('id'):summary.caption('Tracking ID: '+send_identity(editor['id']))
        with preview:
            from crm_preview_cache import preview as render_preview
            if cfg is not None:st.iframe(render_preview(st.session_state,doc,st.session_state.get(key+'review_preview_settings',cfg))['html'],height=240)
        timing=doc.get('send_timing',{'mode':'now'})
        st.caption('Delivery: '+('Scheduled · '+timing['date']+' · '+timing['time']+' recipient local time' if timing['mode']=='schedule' else 'Send now'))
    logging.getLogger(__name__).info('campaign_review stage=modal_shell duration_ms=%.1f',(time.monotonic()-started)*1000)
    from crm_campaign_review import start_review
    token=key+'review_job'
    job=start_review(st.session_state.get(token),shop,store,user,editor,st.session_state.get('campaign_saved'))
    st.session_state[token]=job
    review_finalization(shop,store,user,editor,key,job,delivery)


@st.fragment
def review_finalization(shop,store,user,editor,key,job,delivery):
    job=st.session_state.get(key+'review_job',job)
    if job.closed:return
    from crm_campaign_review import identity
    result=None;error=None
    pending=not job.future.done()
    if not pending:
        try:
            result=job.future.result()
            if not job.applied:
                if identity(editor)!=job.identity:raise ValueError('Draft changed during review. Close and review the current draft.')
                editor.update(deepcopy(job.editor))
                st.session_state['campaign_saved']=deepcopy(editor)
                job.identity=identity(editor);job.applied=True
            elif identity(editor)!=job.identity:
                raise ValueError('Draft changed during review. Close and review the current draft.')
        except Exception as exc:error=safe_error(exc);result=None
    with st.container(key='crm-send-review-final',height=240,border=False):
        if error:
            st.error('Unable to finalize audience. '+error)
            if st.button('Retry',key=key+'review_retry'):
                from crm_campaign_review import start_review
                replacement=start_review(None,shop,store,user,editor,st.session_state.get('campaign_saved'))
                st.session_state[key+'review_job']=replacement
                st.rerun(scope='fragment')
        elif result:
            counts=result['counts']
            st.write(str(counts['eligible'])+' recipients · '+str(sum(counts['excluded'].values()))+' excluded')
            st.caption('✓ Final audience ready')
            if result.get('email_size'):
                from crm_email_size import size_line
                st.caption(size_line(result['email_size']))
            st.caption('Tracking · ✓ Sports Cave OS tracking attached' if result.get('tracking_ok') else 'Tracking · validation required')
            if counts['excluded']:
                with st.expander('Excluded'):
                    for reason,total in counts['excluded'].items():st.caption(reason.replace('_',' ').capitalize()+': '+str(total))
            if result['blockers']:st.warning('Production delivery issue: '+ '; '.join(result['blockers']))
            else:st.caption('Production delivery ready ✓')
        else:
            st.write('Finalizing audience…')
            st.caption('Checking current consent, suppressions, exclusions and production readiness.')
        if not delivery['marketing_enabled']:st.info(OFF)
        st.caption('Confirming Send now confirms review of this campaign’s copy and subject.')
    a,b=st.columns(2)
    with a,st.container(key='crm-review-dismiss'):
        st.button('Cancel',key=key+'cancel_send')
    # Cancel is the same native, client-only dismissal as X/Escape. Intercept only
    # this button, before its React click bubbles, so no server/page rerun occurs.
    st.html('''<script>(()=>{
    const cancel=document.querySelector('[role="dialog"] .st-key-crm-review-dismiss button');
    if(cancel&&!cancel.dataset.reviewDismiss){
      cancel.dataset.reviewDismiss='true';
      cancel.addEventListener('click',event=>{
        event.preventDefault();event.stopImmediatePropagation();
        cancel.closest('[role="dialog"]').querySelector('button[aria-label="Close"]')?.click();
      },true);
    }
    })();</script>'''.replace('<script>','<script>/* '+uuid.uuid4().hex+' */'),unsafe_allow_javascript=True)
    ready=bool(result and not result['blockers'] and result.get('snapshot_id') and editor.get('id') and delivery['marketing_enabled'])
    if b.button('Send now',key=key+'confirm_send',disabled=not ready) and ready:
        operation=st.session_state.setdefault(key+'production_operation',str(uuid.uuid4()))
        try:
            with st.spinner('Preparing send…'):
                sent=queue_campaign(shop,store,user,editor,operation,snapshot_id=result['snapshot_id'])
            job.closed=True
            st.success('Campaign already queued.' if sent['already_started'] else 'Campaign queued for '+str(sent['recipients'])+' recipients.')
            if sent.get('skipped_after_review'):st.caption(str(sent['skipped_after_review'])+' recipients became ineligible after review and were skipped.')
            st.rerun()  # Only a successful durable queue transaction changes the page lifecycle.
        except Exception as exc:st.error(safe_error(exc))
    if pending:
        # A one-shot native fragment event stops naturally on ready/error/dismiss.
        # Unlike run_every it cannot keep polling a closed review indefinitely.
        with st.container(key='crm-review-poll'):
            st.button('Check review status',key=key+'review_poll')
        st.html('''<style>.st-key-crm-review-poll{display:none}</style><script>
        clearTimeout(window.scCampaignReviewPoll);
        window.scCampaignReviewPoll=setTimeout(()=>{
          document.querySelector('[role="dialog"] .st-key-crm-review-poll button')?.click();
        },200);
        </script>'''.replace('<script>','<script>/* '+uuid.uuid4().hex+' */'),unsafe_allow_javascript=True)
