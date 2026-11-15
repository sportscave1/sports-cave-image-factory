"""Opt-in reusable copies in the existing versioned Templates screen."""
import streamlit as st
from crm_collector_templates import library_rows,document,source


def starters(store,user):
    with st.expander('Collector email templates · V1'):
        st.caption('Welcome, Post Purchase and Win Back starters. Saving a reusable copy does not change an automation draft.')
        for row in library_rows():
            label,action=st.columns([3,2],vertical_alignment='center')
            label.write(row['name'])
            with action.container(horizontal=True):
                if st.button('Save reusable copy',key='collector_save_'+row['id']):
                    store.save_design(user,row['name'],document(row['id']))
                    st.success('Reusable template saved. Select it in the automation composer when ready.')
                st.download_button('Source .txt',source(row['id']),file_name=row['name'].lower().replace(' ','-')+'.txt',mime='text/plain',key='collector_export_'+row['id'])
