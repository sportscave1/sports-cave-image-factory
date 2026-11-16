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
    from product_upload_gallery import render

    if not os_accounts.can_access_page(user, 'Upload Companion'):
        st.error('Upload Companion requires an authorised administrator.')
        return
    st.subheader('Upload Companion')
    render(key='upload-companion-health', mode='companion-health')
    render_queue()
    with st.expander('Set up in Microsoft Edge'):
        st.download_button('Download Upload Companion', extension_package(),
                           file_name='SportsCaveUploadCompanion.zip', mime='application/zip')
        st.write('Extract the download. In the Edge profile you use for Sports Cave OS and ChatGPT, '
                 'open Extensions → Manage extensions, turn on Developer mode, and choose Load unpacked. '
                 'Select the extracted folder containing manifest.json, then reload Sports Cave OS. '
                 'Choose Pair this Edge profile here once. Keep that Edge profile signed in to both apps.')


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
            st.caption('No staff uploads queued.')
        for job in status['jobs']:
            with st.expander(f"{job['title']} · {job['label']}"):
                st.caption(job['updated_at'])
                if job['detail']:
                    st.error(job['detail'])
                if job['storefront']:
                    st.link_button('Open live listing', job['storefront'])
    history()
