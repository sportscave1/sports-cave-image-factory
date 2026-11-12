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
    """Clear only the verified completed draft before form widgets are created."""
    identity = st.session_state.pop(NEW_CAMPAIGN_KEY, None)
    if not identity:
        return
    import ads_posting_page as posting
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
    if st.button('Dismiss', key='posting_success_close', use_container_width=True):
        _close_success(receipt['submission_id'])


def preserve_draft_on_navigation():
    """Detach saved form values from widget cleanup while another page is mounted.

    Upload widgets themselves are ephemeral; their captured bytes already live in
    IMAGE_STATE_KEYS / CSV_IMPORT_STATE_KEY. Never restore button/upload values.
    """
    if not any(key.startswith('ads_posting_v2_') for key in st.session_state):
        return
    import ads_posting_page as posting
    uploads = {*posting.IMAGE_KEYS, *posting.CAROUSEL_IMAGE_KEYS, posting.CSV_IMPORT_KEY}
    for name, value in vars(posting).items():
        keys = (value,) if name.endswith('_KEY') else value if name.endswith('_KEYS') and isinstance(value, tuple) else ()
        for key in keys:
            if isinstance(key, str) and key.startswith(posting.STATE_PREFIX) and key not in uploads and key in st.session_state:
                st.session_state[key] = st.session_state[key]



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

    from ads_posting_status_style import install
    install(st)

    def notification():
        polling_enabled = not (receipt or polling_paused or st.session_state.get('posting_finished_job') == identity)
        def panel_contents():
            import ads_posting_page as posting
            # The app mounts this monitor on every route; navigation never cancels the job.
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
                st.session_state[LAST_RESULT_KEY] = dict(row)
                st.session_state[NEW_CAMPAIGN_KEY] = identity
                clear()
                st.rerun()
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
                st.caption(row.get('operation') or ('Posting worker lease is active. Checking saved progress…'
                           if row.get('lease_active') else 'Checking saved posting progress…'))
                if not row.get('running_here') and not row.get('lease_active'):
                    st.warning('The posting worker is no longer confirmed active. Your draft and saved progress are retained. Reconcile the saved job before retrying; no ads will be replayed automatically.')
        @st.fragment(run_every=2 if polling_enabled else None)
        def panel():
            import ads_posting_page as posting
            latest = st.session_state.get(RECEIPT_KEY) or st.session_state.get(posting.RESULT_KEY) or {}
            done, total = confirmed_ads(latest)
            if st.session_state.get('posting_status_failures'):
                label = 'Meta Ads · Status unavailable'
            elif verified_success(latest):
                label = '✓ Ads created · PAUSED for review'
            elif latest.get('status') in TERMINAL or (latest and not latest.get('running_here') and not latest.get('lease_active')):
                label = 'Meta Ads · Needs review'
            else:
                label = f'Meta Ads · Posting {done}/{total}' if total else 'Meta Ads · Posting…'
            with st.container(key='posting_notification'):
                with st.expander(label, expanded=False):
                    state_class = 'posting-state-success' if verified_success(latest) else 'posting-state-working'
                    st.markdown(f'<span class="{state_class}" data-posting-job="{identity}" hidden></span>', unsafe_allow_html=True)
                    panel_contents()
        panel()
    notification()
    return True
