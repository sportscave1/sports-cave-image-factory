"""Shared New Ads / Creative Refresh posting view over the existing ledger."""
import uuid
import streamlit as st
from meta_posting_jobs import JOBS, TERMINAL, confirmed_ads

JOB_KEY = 'posting_tracked_job'
QUERY_KEY = 'meta_posting_job'

def track(identity):
    identity = str(uuid.UUID(str(identity)))
    previous = st.session_state.get(JOB_KEY)
    receipt = st.session_state.get(RECEIPT_KEY) or {}
    if previous != identity:
        st.session_state.pop('posting_finished_job', None)
        st.session_state.pop('posting_status_failures', None)
    if receipt and receipt.get('submission_id') != identity:
        st.session_state[LAST_RESULT_KEY] = dict(receipt)
        st.session_state.pop(RECEIPT_KEY, None)
    st.session_state[JOB_KEY] = identity
    st.query_params[QUERY_KEY] = identity

def clear():
    st.session_state.pop(JOB_KEY, None)
    st.session_state.pop('posting_finished_job', None)
    st.session_state.pop('posting_status_failures', None)
    st.query_params.pop(QUERY_KEY, None)

def progress_value(row):
    """Object confirmation, never a fabricated time/operation percentage."""
    done, total = confirmed_ads(row)
    return done / total if total else 0


RECEIPT_KEY = 'posting_success_receipt'


def verified_success(row):
    done, total = confirmed_ads(row)
    return row.get('status') == 'COMPLETE' and total > 0 and done == total


NEW_CAMPAIGN_KEY = 'posting_new_campaign_after_success'
LAST_RESULT_KEY = 'posting_last_completed_result'


def cleanup_completed():
    """Apply an explicit New Campaign action before form widgets are created."""
    import ads_posting_page as posting
    identity = st.session_state.pop(NEW_CAMPAIGN_KEY, None)
    receipt = st.session_state.get(LAST_RESULT_KEY) or {}
    if (identity and receipt.get('submission_id') == identity and verified_success(receipt)
            and st.session_state.get(posting.SUBMISSION_ID_KEY) == identity):
        for key in list(st.session_state):
            if key.startswith(posting.STATE_PREFIX):
                st.session_state.pop(key, None)
        st.session_state.pop(posting.posting_handoff.LOADED_KEY, None)
        st.session_state.pop(posting.PRODUCT_SELECTOR_STATE_KEY, None)
        posting._start_new_posting_run()


def _close_success(identity, *, new_campaign=False):
    import ads_posting_page as posting
    receipt = st.session_state.get(RECEIPT_KEY) or {}
    if receipt.get('submission_id') != identity or not verified_success(receipt):
        return
    st.session_state[LAST_RESULT_KEY] = dict(receipt)
    if st.session_state.get(posting.SUBMISSION_ID_KEY) in (None, identity):
        st.session_state[posting.PROCESSING_KEY] = False
        st.session_state[posting.RESULT_KEY] = dict(receipt)
        st.session_state[posting.SUBMISSION_ID_KEY] = identity
        st.session_state[posting.RUN_STATE_KEY] = 'COMPLETE'
        if new_campaign:
            st.session_state[NEW_CAMPAIGN_KEY] = identity
    st.session_state.pop(RECEIPT_KEY, None)
    clear()
    st.rerun()


def _render_success(receipt):
    done, total = confirmed_ads(receipt)
    st.markdown('<div class="posting-success">✓ Ads created successfully.</div>', unsafe_allow_html=True)
    st.progress(1.0, text=f'{done} of {total} ads verified')
    st.write(receipt.get('campaign_name') or 'Meta campaign')
    st.caption('PAUSED — Ready for Review')
    left, right = st.columns(2)
    if left.button('New Campaign', key='posting_success_new', type='primary', use_container_width=True):
        _close_success(receipt['submission_id'], new_campaign=True)
    if right.button('Close', key='posting_success_close', use_container_width=True):
        _close_success(receipt['submission_id'])


def render_current(*, compact=False):
    receipt = st.session_state.get(RECEIPT_KEY)
    identity = st.query_params.get(QUERY_KEY) or st.session_state.get(JOB_KEY)
    if not identity and not receipt:
        return False
    if identity:
        try:
            identity = str(uuid.UUID(str(identity)))
        except ValueError:
            st.error('Invalid Posting job reference. Reconcile it before creating another campaign.')
            return True
        track(identity)
    receipt = st.session_state.get(RECEIPT_KEY)
    identity = identity or receipt.get("submission_id")
    polling_paused = st.session_state.get('posting_status_failures', 0) >= 5

    @st.dialog('Meta Ads', width='small', dismissible=False)
    def modal():
        st.markdown("""<style>
        [role="dialog"]:has(.posting-popup) {width:min(500px,calc(100vw - 24px));border:1px solid #d6dce5;
          border-radius:12px;box-shadow:0 16px 48px #14223826;
          margin:0;max-height:calc(100dvh - 24px);overflow:auto;}
        [role="dialog"]:has(.posting-popup) [data-testid="stVerticalBlock"] {gap:.65rem;}
        [role="dialog"]:has(.posting-popup) [data-testid="stHorizontalBlock"] {flex-wrap:nowrap;gap:.75rem;}
        [role="dialog"]:has(.posting-popup) [data-testid="stColumn"] {min-width:0;flex:1;}
        [role="dialog"]:has(.posting-popup) [role="progressbar"] > div {background:var(--sc-border,#E5E1D8);}
        [role="dialog"]:has(.posting-popup) [role="progressbar"] > div > div,
        [role="dialog"]:has(.posting-popup) [role="progressbar"] > div[style*="width"] {
          background:var(--sc-gold,#D4A54C);transition:width .25s ease,transform .25s ease;}
        [role="dialog"]:has(.posting-popup) button[kind="primary"] {
          background:var(--sc-gold,#D4A54C);border-color:var(--sc-gold,#D4A54C);color:var(--sc-text,#0B0B0D);}
        [role="dialog"]:has(.posting-popup) [data-stale="true"] {opacity:1;}
        @media(prefers-reduced-motion:reduce) {
          [role="dialog"]:has(.posting-popup) [role="progressbar"] * {transition:none;}}
        .posting-success {color:#168342;font-weight:600;}
        </style><span class="posting-popup"></span>""", unsafe_allow_html=True)

        polling_enabled = not (receipt or polling_paused or st.session_state.get('posting_finished_job') == identity)
        @st.fragment(run_every=2 if polling_enabled else None)
        def panel():
            import ads_posting_page as posting
            # This timer belongs only to the mounted dialog. After success it reads
            # the receipt without polling; dismissal's full rerun disposes the fragment.
            # Read live state, not a receipt captured when the dialog opened.
            current_receipt = st.session_state.get(RECEIPT_KEY)
            if current_receipt and current_receipt.get('submission_id') == identity:
                _render_success(current_receipt)
                return
            # A late fragment callback must never restore an older run.
            if st.session_state.get(JOB_KEY) != identity:
                return
            if st.session_state.get('posting_status_failures', 0) >= 5:
                st.caption('Automatic status checks paused. Retry status checks this same job without creating ads.')
                if st.button('Retry status', key='posting_retry_status'):
                    st.session_state.pop('posting_status_failures', None)
                    st.rerun()
                return
            try:
                row = JOBS.snapshot(identity)
            except Exception as error:
                if st.session_state.get(JOB_KEY) != identity:
                    return
                from meta_posting_recovery import diagnostic
                diagnostic(error, 'checkpoint_status_read', identity)
                failures = st.session_state.get('posting_status_failures', 0) + 1
                st.session_state['posting_status_failures'] = failures
                st.warning('Posting status is unavailable. The job may still be running. Do not submit again.')
                if failures >= 5:
                    st.caption('Automatic status checks paused. Retry status checks this same job without creating ads.')
                if st.button('Retry status', key='posting_retry_status'):
                    st.session_state.pop('posting_status_failures', None)
                    st.rerun()
                return
            if st.session_state.get(JOB_KEY) != identity:
                return
            st.session_state.pop('posting_status_failures', None)
            if not row.get('submission_id'):
                st.error('Posting job not found. Reconcile the saved reference before creating another campaign.')
                return
            if verified_success(row):
                st.session_state[RECEIPT_KEY] = dict(row)
                # Remove the durable browser restoration pointer immediately.
                st.query_params.pop(QUERY_KEY, None)
                posting._load_recent_posts.clear()
                if st.session_state.get(posting.SUBMISSION_ID_KEY) in (None, identity):
                    st.session_state[posting.RESULT_KEY] = dict(row)
                    st.session_state[posting.SUBMISSION_ID_KEY] = identity
                    st.session_state[posting.RUN_STATE_KEY] = 'COMPLETE'
                    st.session_state[posting.PROCESSING_KEY] = False
                _render_success(row)
                return
            status = row.get('status')
            done, total = confirmed_ads(row)
            # History inspection must not overwrite a newer draft's identity.
            owner = st.session_state.get(posting.SUBMISSION_ID_KEY)
            if owner in (None, identity):
                st.session_state[posting.RESULT_KEY] = dict(row)
                st.session_state[posting.SUBMISSION_ID_KEY] = identity
                st.session_state[posting.RUN_STATE_KEY] = status
                st.session_state[posting.PROCESSING_KEY] = status not in TERMINAL
            if status in TERMINAL:
                st.error(row.get('safe_error') or 'Posting is incomplete or unverified. Saved progress has been preserved.')
                st.caption(f'{done} of {total} ads confirmed PAUSED')
                if row.get('can_retry') and st.button('Retry incomplete steps', key='posting_retry_job'):
                    try:
                        JOBS.retry(identity)
                    except Exception:
                        st.error('Retry could not start. Check status before trying again.')
                    else:
                        st.session_state.pop('posting_finished_job', None)
                        if not polling_enabled:
                            st.rerun()
                        st.info('Retry started for the same saved job. Checking status…')
                if row.get('needs_original_inputs'):
                    st.caption('Restore the original images and copy in Posting to resume this same job safely.')
                elif not row.get('can_retry'):
                    st.caption('Reconcile the saved Meta IDs before retrying. No automatic reposting.')
                if st.button('Back to posting setup', key='posting_result_setup'):
                    clear()
                    st.rerun()
                if not row.get('running_here') and st.session_state.get('posting_finished_job') != identity:
                    st.session_state['posting_finished_job'] = identity
            else:
                st.subheader('Creating Meta Ads…')
                st.progress(progress_value(row), text=f'{done} of {total} ads verified PAUSED · final verification pending')
                st.caption(row.get('operation') or 'Validating campaign settings…')
                if not row.get('running_here'):
                    st.warning('Outcome unknown. Reconcile the saved job before retrying; it will not be replayed automatically.')
        panel()
    modal()
    return True
