"""Named wrapper around the actual existing Product Uploads UI fixture."""
from pathlib import Path
import runpy
import streamlit as st
from product_upload_mockups_preview import STATE

st.set_page_config(page_title="Recorder Product Uploads acceptance",layout="wide")
with st.sidebar:
    if st.button("Reset synthetic generation",key="recorder-reset-generation"):
        from product_upload_jobs import JOBS
        from tests.test_product_upload_intake import ADMIN
        key=st.session_state.get('_product_upload_active')
        identity=(str(ADMIN['id']),str(key),'generate')
        with JOBS.lock:
            active=JOBS.jobs.get(identity)
            if active and active['state'] in ('Queued','Running'):
                st.error('Wait for the synthetic generation to finish before resetting.')
            else:
                JOBS.jobs.pop(identity,None)
                app=st.session_state.get('fixture-app')
                if app:app._set_mockups_result(None)
                for prefix in ('product-upload-generation-ack-','product-upload-job-applied-',
                               'product-upload-generation-seen-','product-upload-job-error-'):
                    st.session_state.pop(prefix+str(key),None)
runpy.run_path(str(Path(__file__).with_name("product_upload_mockups.py")))
st.link_button("Open synthetic clipboard check",STATE["recorder_trial_origin"]+"/__test/copy-check")
