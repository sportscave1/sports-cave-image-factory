"""A server-acknowledged responsiveness probe around the real UI fixture."""
from pathlib import Path
import runpy
import sys
import streamlit as st

root=str(Path(__file__).resolve().parents[2])
if root in sys.path:sys.path.remove(root)
sys.path.insert(0,root)

with st.sidebar:
    if st.button('Responsiveness probe'):
        st.session_state['responsive-probe']=st.session_state.get('responsive-probe',0)+1
    st.caption('Probe receipt: '+str(st.session_state.get('responsive-probe',0)))
runpy.run_path(str(Path(__file__).with_name('product_upload_mockups.py')))
