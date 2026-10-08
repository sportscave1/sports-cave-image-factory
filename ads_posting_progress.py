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
    # Include final verification as a separate unit, even if every ID is saved.
    verified = row.get('status') == 'COMPLETE' and done == total
    return (done + int(verified)) / (total + 1)


def render_current(*, compact=False):
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
    polling_paused = st.session_state.get('posting_status_failures', 0) >= 5
    @st.fragment(run_every=None if polling_paused or st.session_state.get('posting_finished_job') == identity else 2)
    def panel():
        import ads_posting_page as posting
        try:
            row = JOBS.snapshot(identity)
        except Exception:
            failures = st.session_state.get('posting_status_failures', 0) + 1
            st.session_state['posting_status_failures'] = failures
            st.warning('Posting status is temporarily unavailable. The job may still be running. Do not submit again.')
            if failures >= 5:
                st.caption('Automatic status checks paused after five failures. Retry status to check the same job; this does not create ads.')
            if st.button('Retry status', key='posting_retry_status'):
                st.session_state.pop('posting_status_failures', None)
                st.rerun()
            if failures == 5:
                st.rerun()
            return
        st.session_state.pop('posting_status_failures', None)
        if not row.get('submission_id'):
            st.error('This Posting job could not be found. Reconcile the saved job reference before creating another.')
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
        if compact and status not in TERMINAL:
            st.button('Create Ad', disabled=True, key='posting_create_in_progress')
        st.progress(progress_value(row), text=f'{done} of {total} ads confirmed · Paused · final verification required'
                    if status != 'COMPLETE' else f'{done} of {total} ads verified · PAUSED')
        if (status in TERMINAL and not row.get('running_here')
                and st.session_state.get('posting_finished_job') != identity):
            st.session_state['posting_finished_job'] = identity
            posting._load_recent_posts.clear()
            st.rerun()
        if status == 'COMPLETE':
            posting._render_success(row, compact=compact)
        elif status in TERMINAL:
            st.error(row.get('safe_error') or 'Posting stopped. Review the saved result.')
            if row.get('last_operation'):
                st.caption('Stopped during: ' + row['last_operation'])
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
            if row.get('elapsed_seconds') is not None:
                st.caption(f"Elapsed: {row['elapsed_seconds']} seconds · current operation: {row['operation_seconds']} seconds")
            completed = [label for key, label in (
                ('campaign_id', 'Campaign selected or created'),
                ('adset_id', 'Ad set selected or created'),
            ) if row.get(key)]
            if done:
                completed.append(f'{done} paused ads confirmed')
            if completed:
                st.caption('✓ ' + ' · ✓ '.join(completed[-4:]))
            if (row.get('operation_seconds') or 0) >= 90:
                st.warning('Meta is taking longer than expected. The outcome is not yet confirmed; do not submit again. Status checks continue using this saved job.')
            st.caption('Job '+identity+' · You can leave this page; posting continues on the server.')
            if not row.get('running_here'):
                st.warning('Outcome unknown: this server has no running worker for the saved checkpoint. Another worker may still be posting. Reconcile the saved IDs in Meta before retrying; this job will not be replayed automatically.')
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
    if not compact:
        posting._render_recent_posts()
    return True
