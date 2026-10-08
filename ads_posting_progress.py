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
    st.query_params.pop(QUERY_KEY, None)

def render_current():
    identity = st.query_params.get(QUERY_KEY) or st.session_state.get(JOB_KEY)
    if not identity:
        return False
    try:
        identity = str(uuid.UUID(str(identity)))
    except ValueError:
        st.error('Invalid Posting job reference.')
        if st.button('Return to Posting', key='posting_invalid_return'):
            clear()
            st.rerun()
        return True
    track(identity)
    @st.fragment(run_every=None if st.session_state.get('posting_finished_job') == identity else 2)
    def panel():
        import ads_posting_page as posting
        try:
            row = JOBS.snapshot(identity)
        except Exception:
            st.warning('Posting status is temporarily unavailable. The job may still be running. Do not submit again.')
            st.button('Retry status', key='posting_retry_status')
            return
        if not row.get('submission_id'):
            st.error('This Posting job could not be found. Check Recent Posting jobs before creating another.')
            if st.button('Return to Posting', key='posting_missing_return'):
                clear()
                st.rerun()
            return
        status = row.get('status')
        done, total = confirmed_ads(row)
        st.session_state[posting.RESULT_KEY] = dict(row)
        st.session_state[posting.SUBMISSION_ID_KEY] = identity
        st.session_state[posting.RUN_STATE_KEY] = status
        st.session_state[posting.PROCESSING_KEY] = status not in TERMINAL
        st.subheader('Creating your Meta ads' if status not in TERMINAL else 'Meta posting result')
        st.progress(done / total, text=f'{done} of {total} ads confirmed · Paused')
        if (status in TERMINAL and not row.get('running_here')
                and st.session_state.get('posting_finished_job') != identity):
            st.session_state['posting_finished_job'] = identity
            posting._load_recent_posts.clear()
            st.rerun()
        if status == 'COMPLETE':
            posting._render_success(row)
        elif status in TERMINAL:
            st.error(row.get('safe_error') or 'Posting stopped. Review the saved result.')
            posting._render_object_result(row, title=f'{done} of {total} ads confirmed · partial result')
            if row.get('can_retry') and st.button('Retry incomplete steps', key='posting_retry_job'):
                try:
                    JOBS.retry(identity)
                except Exception:
                    st.error('Retry could not start. Refresh status before trying again.')
                else:
                    st.session_state.pop('posting_finished_job', None)
                    st.rerun()
            if status in {'AMBIGUOUS', 'ABANDONED_EXTERNALLY'} or not row.get('can_retry'):
                st.caption('No automatic retry. Reconcile the saved IDs in Meta before any new submission.')
            if st.button('Back to posting setup', key='posting_result_setup'):
                clear()
                st.rerun()
        else:
            stage = row.get('operation') or str(status or 'VALIDATING').replace('_', ' ').title()
            st.info(stage)
            st.caption('Job '+identity+' · You can leave this page; posting continues on the server.')
            if not row.get('running_here'):
                st.caption('Tracking the saved checkpoint. If the server restarted, reconcile this run before retrying; it will not be replayed automatically.')
        with st.expander('View Posting Details', expanded=False):
            st.write('Posting job: '+identity)
            posting._render_object_result(row, title='Saved posting result')
        if st.button('Close', key='posting_progress_close'):
            from ads_navigation import (
                ADS_PAGE_KEY, CREATIVE_REFRESH_PAGE_KEY, ADS_CREATE_ROUTE, CREATIVE_REFRESH_ROUTE,
            )
            loaded = st.session_state.get(posting.posting_handoff.LOADED_KEY) or {}
            refresh = bool(loaded.get('creative_refresh'))
            st.session_state['current_page'] = CREATIVE_REFRESH_ROUTE if refresh else ADS_CREATE_ROUTE
            st.session_state['selected_page'] = st.session_state['current_page']
            st.query_params['page'] = CREATIVE_REFRESH_PAGE_KEY if refresh else ADS_PAGE_KEY
            st.rerun()
    panel()
    import ads_posting_page as posting
    posting._render_recent_posts()
    return True
