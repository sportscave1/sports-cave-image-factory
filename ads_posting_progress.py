"""Shared New Ads / Creative Refresh posting view over the existing ledger."""
import uuid
import streamlit as st
from meta_posting_jobs import JOBS, TERMINAL, confirmed_ads

JOB_KEY = 'posting_tracked_job'
QUERY_KEY = 'meta_posting_job'

def track(identity):
    identity = str(uuid.UUID(str(identity)))
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


def cleanup_completed():
    """Run before widgets. Only clear inputs owned by this completed submission."""
    import ads_posting_page as posting
    receipt = st.session_state.get(RECEIPT_KEY)
    if not receipt or not verified_success(receipt):
        return
    identity = receipt['submission_id']
    if st.session_state.get(posting.SUBMISSION_ID_KEY) == identity:
        for key in list(st.session_state):
            if key.startswith(posting.STATE_PREFIX):
                st.session_state.pop(key, None)
        st.session_state.pop(posting.posting_handoff.LOADED_KEY, None)
        st.session_state.pop(posting.PRODUCT_SELECTOR_STATE_KEY, None)
    if st.session_state.get(JOB_KEY) == identity:
        clear()


def _close_success():
    st.session_state.pop(RECEIPT_KEY, None)
    st.rerun()


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
    polling_paused = st.session_state.get('posting_status_failures', 0) >= 5

    @st.dialog('Meta Ads', width='small', dismissible=False)
    def modal():
        st.markdown("""<style>
        div[role="dialog"] {width:min(500px,calc(100vw - 24px));border:1px solid #d6dce5;
          border-radius:12px;box-shadow:0 16px 48px #14223826;
          position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);
          margin:0;max-height:calc(100dvh - 24px);overflow:auto;}
        div[role="dialog"] [data-testid="stVerticalBlock"] {gap:.65rem;}
        div[role="dialog"] [data-testid="stHorizontalBlock"] {flex-wrap:nowrap;gap:.75rem;}
        div[role="dialog"] [data-testid="stColumn"] {min-width:0;flex:1;}
        div[role="dialog"] [role="progressbar"] > div > div {background:#0078d4;}
        div[role="dialog"]:has(.posting-success) [role="progressbar"] > div > div {background:#168342;}
        div[role="dialog"] [role="progressbar"] * {transition:none!important;animation:none!important;}
        div[role="dialog"] button[kind="primary"] {background:#0078d4;border-color:#0078d4;}
        .posting-success {color:#168342;font-weight:600;}
        </style>""", unsafe_allow_html=True)

        @st.fragment(run_every=None if receipt or polling_paused or st.session_state.get('posting_finished_job') == identity else 2)
        def panel():
            import ads_posting_page as posting
            if receipt:
                done, total = confirmed_ads(receipt)
                st.markdown('<div class="posting-success">✓ Ads created successfully.</div>', unsafe_allow_html=True)
                st.progress(1.0, text=f'{done} of {total} ads verified')
                st.write(receipt.get('campaign_name') or 'Meta campaign')
                st.caption('PAUSED — Ready for Review')
                left, right = st.columns(2)
                if left.button('New Campaign', type='primary', use_container_width=True):
                    _close_success()
                if right.button('Close', use_container_width=True):
                    _close_success()
                return
            # A late fragment callback must never restore an older run.
            if st.session_state.get(JOB_KEY) != identity:
                return
            try:
                row = JOBS.snapshot(identity)
            except Exception as error:
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
                if failures == 5:
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
                st.rerun()
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
                        st.rerun()
                if row.get('needs_original_inputs'):
                    st.caption('Restore the original images and copy in Posting to resume this same job safely.')
                elif not row.get('can_retry'):
                    st.caption('Reconcile the saved Meta IDs before retrying. No automatic reposting.')
                if st.button('Back to posting setup', key='posting_result_setup'):
                    clear()
                    st.rerun()
                if not row.get('running_here') and st.session_state.get('posting_finished_job') != identity:
                    st.session_state['posting_finished_job'] = identity
                    st.rerun()
            else:
                st.subheader('Creating Meta Ads…')
                st.progress(progress_value(row), text=f'{done} of {total} ads verified PAUSED · final verification pending')
                st.caption(row.get('operation') or 'Validating campaign settings…')
                if not row.get('running_here'):
                    st.warning('Outcome unknown. Reconcile the saved job before retrying; it will not be replayed automatically.')
        panel()
    modal()
    return True
