"""Administrator view for the local Edge Upload Companion."""
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def extension_package():
    source = Path(__file__).parent / 'windows-upload-companion'
    archive = BytesIO()
    with ZipFile(archive, 'w', compression=ZIP_DEFLATED) as bundle:
        for filename in ('manifest.json', 'os-bridge.js', 'worker.js', 'composer.js'):
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
    with st.expander('Set up in Microsoft Edge'):
        st.download_button('Download Upload Companion', extension_package(),
                           file_name='SportsCaveUploadCompanion.zip', mime='application/zip')
        st.write('Extract the download. In the Edge profile you use for Sports Cave OS and ChatGPT, '
                 'open Extensions → Manage extensions, turn on Developer mode, and choose Load unpacked. '
                 'Select the extracted folder containing manifest.json, then reload Sports Cave OS.')
