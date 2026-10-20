"""Named wrapper around the actual existing Product Uploads UI fixture."""
from pathlib import Path
import runpy
import streamlit as st
from product_upload_mockups_preview import STATE

st.set_page_config(page_title="Recorder Product Uploads acceptance",layout="wide")
runpy.run_path(str(Path(__file__).with_name("product_upload_mockups.py")))
st.link_button("Open synthetic clipboard check",STATE["recorder_trial_origin"]+"/__test/copy-check")
