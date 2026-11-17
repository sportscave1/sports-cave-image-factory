"""Administrator view for the local Edge Upload Companion."""
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def extension_package():
    source = Path(__file__).parent / 'windows-upload-companion'
    archive = BytesIO()
    with ZipFile(archive, 'w', compression=ZIP_DEFLATED) as bundle:
        for filename in ('manifest.json', 'os-bridge.js', 'worker.js', 'composer.js', 'staff-queue.js', 'design-queue.js'):
            bundle.write(source / filename, filename)
    return archive.getvalue()


def render_page(user):
    import os_accounts
    import streamlit as st

    if not os_accounts.can_access_page(user, 'Upload Companion'):
        st.error('Upload Companion requires an authorised administrator.')
        return
    st.subheader('Companion Queues')
    st.caption('One design and one product upload can run at the same time. Both queues continue automatically after success or failure.')
    designs, uploads = st.tabs(['Design queue', 'Upload queue'])
    with designs:
        render_design_queue()
    with uploads:
        render_queue()


def render_queue():
    import streamlit as st
    from product_upload_staff_queue import list_jobs

    @st.fragment(run_every=10)
    def history():
        try:
            status = list_jobs()
        except Exception:
            st.warning('Could not load the desktop queue. It will retry automatically.')
            return
        st.caption('Paired desktop online' if status['online'] else 'Waiting for the paired desktop')
        st.subheader('Upload queue and history')
        if not status['jobs']:
            st.caption('Press Publish now on any number of artworks in Design Studio. They will queue here and upload one at a time.')
        active = sum(job['stage'] < 6 for job in status['jobs'])
        done = sum(job['stage'] == 6 for job in status['jobs'])
        attention = sum(job['stage'] == 7 for job in status['jobs'])
        st.caption(f'{active} in progress · {done} completed · {attention} need attention · latest 20 jobs')
        for job in status['jobs']:
            with st.expander(f"{job['title']} · {job['label']}", expanded=job['stage'] < 6 or job['stage'] == 7):
                st.caption('Job ' + job['id'][:8])
                if job['stage'] < 6:
                    st.progress(job['percent'] / 100, text=job['label'])
                st.caption(job['updated_at'])
                if job['detail']:
                    st.error(job['detail'])
                if job['storefront']:
                    st.link_button('Open live listing', job['storefront'])
    history()


def render_design_queue():
    import streamlit as st
    from morning_design_queue import settings, list_jobs, current_suggestions, enqueue_selected

    @st.fragment(run_every=10)
    def history():
        st.subheader('Morning design queue')
        try:
            control = settings()
            enabled = st.toggle('Automatically create morning designs', value=control['enabled'])
            if enabled != control['enabled']:
                settings(enabled)
            st.caption('One design chat at a time. Edge must stay open and signed in. '
                       'New suggestions published after first enabling are included. '
                       'Pausing stops new claims; existing jobs continue to be checked.')
            suggestions = current_suggestions()
            with st.expander('Queue a current suggestion now'):
                if suggestions:
                    selected = st.selectbox('Morning suggestion', suggestions, format_func=lambda entry: entry['item']['title'])
                    if st.button('Add design to queue'):
                        enqueue_selected(selected['id'])
                        st.success('Design queued. Previously queued suggestions are not duplicated.')
            for job in list_jobs():
                with st.expander(job['title'] + ' · ' + job['label']):
                    if job['chat_url']:
                        st.link_button('Open design chat', job['chat_url'])
                    if job['file_path']:
                        st.caption(job['file_path'])
                    if job['detail']:
                        st.caption(job['detail'])
        except Exception:
            st.warning('The design queue is unavailable. Check the database migration and desktop connection.')
    history()
