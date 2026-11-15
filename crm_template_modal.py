"""Reuse template editors inside the existing automation dialog without nesting."""
from functools import wraps
import streamlit as st


def template_modal(title,**options):
    def decorate(fn):
        dialog=st.dialog(title,**options)(fn)
        @wraps(fn)
        def open_editor(*args,**kwargs):
            if st.session_state.get('email_editor_mode')=='automation':
                st.session_state['automation_template_view']=(fn,args,kwargs)
                st.rerun(scope='app')
            return dialog(*args,**kwargs)
        return open_editor
    return decorate
