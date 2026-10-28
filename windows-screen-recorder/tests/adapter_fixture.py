"""Local-only acceptance surface for the unpacked Edge adapter."""
import streamlit as st

st.set_page_config(page_title="Recorder adapter acceptance")
st.title("Recorder adapter acceptance")
choice = st.selectbox("Local test choice", ["First", "Second", "Third"])
st.write("Selected:", choice)
