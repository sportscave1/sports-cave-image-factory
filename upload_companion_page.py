"""Administrator view for the local Edge Upload Companion."""
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def extension_package():
    source = Path(__file__).parent / 'windows-upload-companion'
    archive = BytesIO()
    with ZipFile(archive, 'w', compression=ZIP_DEFLATED) as bundle:
        for filename in ('manifest.json', 'os-bridge.js', 'worker.js', 'composer.js', 'staff-queue.js'):
            bundle.write(source / filename, filename)
    return archive.getvalue()


def render_page(user):
    import os_accounts
    import streamlit as st

    if not os_accounts.can_access_page(user, 'Upload Companion'):
        st.error('Upload Companion requires an authorised administrator.')
        return
    st.subheader('Upload Companion')
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
            st.caption('No uploads yet. Publish a design from Design Studio to start.')
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
