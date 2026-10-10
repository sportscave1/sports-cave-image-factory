"""Compact explicit send controls. No provider call occurs during rendering."""
from copy import deepcopy
import hashlib
import json
import logging
import uuid
import streamlit as st
import os_accounts
from crm_campaign_send import send_test, review, OFF
from crm_resend_marketing import DeliveryError, get_resend_marketing_config_status
from crm_store import StoreUnavailable
from crm_resend import MarketingDisabled
from crm_campaign_progress_ui import dismiss as dismiss_send_status


def safe_error(exc):
    if isinstance(exc,(ValueError,PermissionError,DeliveryError,MarketingDisabled)):return str(exc).replace('Market legal review','Segment legal review').replace('market audience mode','segment audience mode')
    if isinstance(exc,StoreUnavailable):return 'Campaign storage is unavailable. Your edits are retained.'
    logging.getLogger(__name__).warning('crm_campaign_action_failed type=%s',type(exc).__name__)
    return 'The service is temporarily unavailable. Check the receipt before retrying.'


@st.fragment
def test_control(store,user,editor,key,available=True,cfg=None):
    automation=getattr(store,'email_mode',None)=='automation'
    from crm_email_editor_context import current,saved_key
    with st.popover('Send test',disabled=not available or not os_accounts.can_access_page(user,'CRM Automations' if automation else 'CRM Campaigns') or bool(editor.get('archived_at')),key=key+'test_popover',on_change='rerun') as popover:
        mounted_key=key+'test_mounted'
        if popover.open:st.session_state[mounted_key]=True
        # A form's unsent text may exist only in the browser. Once opened, keep
        # its widgets mounted across close/reopen instead of discarding that text.
        if not st.session_state.get(mounted_key):return
        from crm_campaign_test_ui import test_styles, readiness
        from crm_campaign_issues import CampaignValidationError
        from crm_campaign_content import preflight
        test_styles()
        st.caption('SEND TEST')
        checks=None
        active=current(st.session_state,editor)
        if str(active.get('id'))==str(editor.get('id')):editor=active
        if popover.open:
            try:
                review_doc=deepcopy(editor['document']);review_doc['copy_reviewed']=True
                if automation:
                    review_doc,_=store.preview_document(review_doc)
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
            if automation:
                from crm_checkout_preview import needs_checkout
                if needs_checkout(editor['document']):st.caption('Uses your authorized test address’s own verified checkout. No automation journey is started.')
            cols=st.columns([6,1],vertical_alignment='bottom',gap='small')
            recipient=cols[0].text_input('Send test email',placeholder='email@example.com',key=key+'test_recipient',help='Send test uses the real Shopify unsubscribe link for this customer.')
            submit=cols[1].form_submit_button('→',help='Send this test email',disabled=bool(st.session_state.get(key+'test_busy')))
        if submit:
            if st.session_state.get(key+'test_busy'):return
            # A fragment can retain an older argument after a component rerun.
            active=current(st.session_state,editor)
            if active is not editor and str(active.get('id'))!=str(editor.get('id')):
                st.error('Campaign changed. Reopen Send test.');return
            editor=active
            # Identical content/recipient retries retain their durable operation ID.
            doc={k:v for k,v in editor['document'].items() if k!='copy_reviewed'}
            digest=hashlib.sha256(json.dumps([doc,recipient.strip().casefold()],sort_keys=True).encode()).hexdigest()
            operations=st.session_state.setdefault(key+'test_operations',{})
            operation=operations.setdefault(digest,str(uuid.uuid4()))
            st.session_state[key+'test_busy']=True
            try:
                with st.spinner('Sending…'):
                    result=send_test(store,user,editor,recipient,operation)
                st.session_state[saved_key(st.session_state)]=deepcopy(editor)
                st.success('Test email sent to '+recipient.strip())
                if not result['audit_saved']:st.warning('Provider accepted the test; receipt storage needs review. Do not resend.')
            except CampaignValidationError as exc:checks=exc.checks
            except Exception as exc:st.error('Test email could not be sent — '+safe_error(exc))
            finally:st.session_state[key+'test_busy']=False
        if checks is not None:readiness(checks)


@st.fragment
def send_control(shop,store,user,editor,key,cfg,available=True):
    if st.button('Send now',key=key+'open_review',type='primary',help='Review recipients, delivery timing and required checks before explicitly confirming. Opening review sends nothing.',disabled=not available or bool(editor.get('archived_at')) or bool(editor.get('recovery_readonly'))):
        review_dialog(shop,store,user,editor,key,cfg)


@st.dialog('Review & send',width='small',on_dismiss=dismiss_send_status)
def review_dialog(shop,store,user,editor,key,cfg=None):
    # This shell performs no draft/history/audience/provider reads.
    delivery=get_resend_marketing_config_status()
    st.html("""<style>
    [role="dialog"]:has(.st-key-crm-send-review-summary){max-height:90vh;max-width:560px;width:calc(100vw - 32px);overflow:auto}
    .st-key-crm-send-review-summary [data-testid="stVerticalBlock"],
    .st-key-crm-send-review-final [data-testid="stVerticalBlock"]{gap:6px}
    .st-key-crm-send-review-summary p,.st-key-crm-send-review-final p{margin-bottom:2px}
    .st-key-crm-review-actions{position:sticky;bottom:0;background:#fffdf8;padding-top:8px;border-top:1px solid #e5e1d8;z-index:2}
    .st-key-crm-review-actions [data-testid="stHorizontalBlock"]{flex-wrap:nowrap}
    .st-key-crm-review-actions [data-testid="stColumn"]{min-width:0;flex:1 1 0}
    .st-key-crm-review-actions [data-testid="stColumn"]:last-child > [data-testid="stVerticalBlock"]{align-items:flex-end}
    .st-key-crm-review-actions button[kind="primary"]{background:#171714;color:#fffdf8;border-color:#b59b65}
    @media(max-width:640px){.st-key-crm-send-review-summary [data-testid="stHorizontalBlock"]{flex-wrap:wrap}
    .st-key-crm-send-review-summary [data-testid="stColumn"]{flex:1 1 100%;width:100%;min-width:0}}
    </style>""")
    review_finalization(shop,store,user,editor,key,None,delivery,cfg=cfg)


def _review_summary(editor,key,delivery,cfg):
    doc=editor['document']
    with st.container(key='crm-send-review-summary'):
        show_preview=st.checkbox('Email preview',key=key+'review_show_preview')
        if show_preview:summary,preview=st.columns([42,58],gap='small')
        else:summary=st.container();preview=None
        summary.write('**Campaign**  '+editor['name'])
        summary.write('**Subject**  '+(doc['content']['subject'] or 'Missing'))
        summary.caption('From: '+(delivery['sender'] or 'Not configured'))
        summary.caption('Reply-to: '+(delivery['reply_to'] or 'Not configured'))
        from crm_campaign_markets import MARKET_LABELS
        summary.caption('Segment: '+MARKET_LABELS[doc['market']])
        cached=st.session_state.get(key+'size_cache')
        if cached:
            from crm_email_size import analyze_rendered_email,size_line
            import hashlib
            token=hashlib.sha256(json.dumps([editor.get('id'),doc,st.session_state.get(key+'review_preview_settings',cfg)],sort_keys=True,default=str).encode()).hexdigest()
            if cached.get('token')==token:
                message=cached['message']
                summary.caption(size_line(analyze_rendered_email(message['html'],message['text'])))
        if preview is not None:
            with preview:
                from crm_preview_cache import preview as render_preview
                if cfg is not None:st.iframe(render_preview(st.session_state,doc,st.session_state.get(key+'review_preview_settings',cfg))['html'],height=240)



@st.fragment
def review_finalization(shop,store,user,editor,key,job,delivery,cfg=None):
    # Both slots belong to this fragment, including the initial summary.
    # Never mutate a placeholder supplied by the surrounding dialog.
    summary_slot=st.empty()
    if not st.session_state.get(key+'queued_receipt'):
        if job is None:
            import time
            started=time.monotonic()
            with summary_slot.container():
                _review_summary(editor,key,delivery,cfg)
            logging.getLogger(__name__).info('campaign_review stage=modal_shell duration_ms=%.1f',(time.monotonic()-started)*1000)
            from crm_campaign_review import start_review
            token=key+'review_job'
            audience_job=None
            if shop is not None and store is not None:
                from crm_campaign_audience_prepare import prepare_session
                audience_job=prepare_session(st.session_state,shop,store,editor,key,cfg)
            job=start_review(st.session_state.get(token),shop,store,user,editor,st.session_state.get('campaign_saved'),cfg,audience_job)
            st.session_state[token]=job
    body=st.empty()
    with body.container():
        _review_finalization(shop,store,user,editor,key,job,delivery,summary_slot,cfg,body)



def _accepted_navigation(receipt,editor):
    from crm_campaign_home_progress import accepted_home
    from crm_campaign_home import return_home
    accepted_home(st.session_state,receipt,editor)
    return_home()
    # A single full-app navigation closes the review dialog. Delivery already
    # belongs to the worker; retain the original composer and durable receipt.
    st.rerun()


def _review_finalization(shop,store,user,editor,key,job,delivery,summary_slot,cfg,body):
    retry_requested=st.session_state.pop(key+'acceptance_retry',False)
    if st.session_state.get(key+'acceptance_uncertain'):
        from crm_campaign_preparation import lookup
        try:known=lookup(store,user,editor['id'])
        except Exception:
            st.warning('Acceptance status unavailable. No replacement operation will be created.')
            if st.button('Check acceptance',key=key+'check_acceptance'):st.rerun(scope='fragment')
            return
        st.session_state.pop(key+'acceptance_uncertain',None)
        if known:_accepted_navigation(known,editor);return
    receipt=st.session_state.get(key+'queued_receipt')
    if receipt:
        _accepted_navigation(receipt,editor)
        return
    job=st.session_state.get(key+'review_job',job)
    if job.closed:return
    from crm_campaign_review import identity
    result=None;error=None
    pending=not job.future.done()
    current=st.session_state.get('campaign_editor',editor)
    if identity(current)!=identity(editor):
        error='Draft changed during review. Close and review the current draft.'
        pending=False
    if not pending and not error:
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
    with st.container(key='crm-send-review-final',border=False):
        if error:
            st.caption('⚠ Audience verification failed · '+error)
            if st.button('Retry',key=key+'review_retry'):
                from crm_campaign_review import start_review
                audience_job=None
                if shop is not None and store is not None:
                    from crm_campaign_audience_prepare import prepare_session
                    st.session_state.pop(key+'audience_job',None)
                    audience_job=prepare_session(st.session_state,shop,store,editor,key,cfg)
                replacement=start_review(None,shop,store,user,editor,st.session_state.get('campaign_saved'),getattr(job,'requested_settings',None),audience_job)
                st.session_state[key+'review_job']=replacement
                st.rerun(scope='fragment')
        elif result:
            counts=result['counts']
            from crm_campaign_schedule import summary as timing_summary
            st.caption('Delivery: '+timing_summary(result.get('document',editor['document']).get('send_timing',{'mode':'now'}),result.get('schedule')))
            st.write(str(counts['eligible'])+' recipients · '+str(sum(counts['excluded'].values()))+' excluded')
            if counts['excluded']:
                st.caption('Exclusions',help=' · '.join(str(n)+' '+reason.replace('_',' ') for reason,n in sorted(counts['excluded'].items())))
            if result.get('email_size'):
                from crm_email_size import size_line
                st.caption(size_line(result['email_size']))
            st.caption('Tracking ✓ · Delivery ✓' if result.get('tracking_ok') and not result['blockers'] else 'Tracking · '+('✓' if result.get('tracking_ok') else 'validation required'))
            if result['blockers']:st.caption('⚠ '+ '; '.join(result['blockers']))
            else:st.caption(':green[✓ Ready to send]')
        else:
            prepared=st.session_state.get(key+'audience_job')
            known=prepared.display() if prepared else None
            if known:
                st.write(str(known['eligible'])+' eligible · '+str(sum(known['excluded'].values()))+' excluded')
                st.caption('Checking for recent changes…' if not prepared.valid() else '✓ Audience verified · Checking delivery…')
            else:
                count=(editor['document'].get('counts') or {}).get('eligible')
                if count is not None:st.write(str(count)+' recipients · last known')
                st.write('Verifying recipients…')
        if not delivery['marketing_enabled']:st.caption(OFF)
    with st.container(key='crm-review-actions'):
        a,b=st.columns([1,2])
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
    final_count=result['counts']['eligible'] if result else None
    scheduled=editor['document'].get('send_timing',{}).get('mode')=='schedule'
    action=('Schedule for ' if scheduled else 'Send to ')+str(final_count)+' recipients' if final_count is not None else ('Schedule' if scheduled else 'Send now')
    with b,st.container(key='crm-review-submit'):action_slot=st.empty()
    clicked=action_slot.button(action,key=key+'confirm_send',disabled=not ready or bool(st.session_state.get(key+'queue_busy')),type='primary')
    # Immediate native feedback; durable uniqueness remains exclusively server
    # owned. Preserve the real label and accessibility rather than disguising it.
    st.html('''<script>/* '''+uuid.uuid4().hex+''' */(()=>{
      const b=document.querySelector('[role="dialog"] .st-key-crm-review-submit button');
      if(!b)return;
      b.disabled='''+('false' if ready and not st.session_state.get(key+'queue_busy') else 'true')+''';
      b.removeAttribute('aria-busy');b.style.opacity='';
      if(b.dataset.acceptFeedback)return;b.dataset.acceptFeedback='true';
      b.addEventListener('click',()=>queueMicrotask(()=>{
        b.disabled=true;b.setAttribute('aria-busy','true');b.style.opacity='.65';
      }));
    })();</script>''',unsafe_allow_javascript=True)
    if (clicked or retry_requested) and ready:
        operation=st.session_state.setdefault(key+'production_operation',str(uuid.uuid4()))
        st.session_state[key+'queue_busy']=True
        action_slot.button('Accepting campaign…',disabled=True,key=key+'preparing_send')
        try:
            from crm_campaign_preparation import accept,lookup
            sent=accept(store,user,editor,operation,snapshot_id=result['snapshot_id'],confirmed=True)
        except Exception as exc:
            # A lost commit response must resolve against durable identity first.
            try:sent=lookup(store,user,editor['id'])
            except Exception:
                st.session_state[key+'acceptance_uncertain']=True
                st.warning('Acceptance status unavailable. Open Campaigns Home to check this campaign before retrying.')
                return
            if not sent:
                st.error('Campaign was not accepted. '+safe_error(exc))
                if not isinstance(exc,(ValueError,PermissionError)) and st.button('Retry acceptance',key=key+'retry_acceptance'):
                    st.session_state[key+'acceptance_retry']=True
                    st.rerun(scope='fragment')
                return
        finally:st.session_state[key+'queue_busy']=False
        # Nothing below owns delivery; the receipt exists only after commit.
        job.closed=True
        st.session_state[key+'queued_receipt']=sent
        _accepted_navigation(sent,editor)
        return
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
