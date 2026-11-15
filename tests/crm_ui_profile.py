"""Opt-in fixture instrumentation of actual Streamlit fragment execution."""
from functools import wraps
from time import perf_counter
import streamlit as st


def instrument(module,name):
    function=getattr(module,name)
    if getattr(function,'fixture_profile',False):return
    @st.fragment
    @wraps(function.__wrapped__)
    def measured(*args,**kwargs):
        started=perf_counter()
        try:return function.__wrapped__(*args,**kwargs)
        finally:
            samples=st.session_state.setdefault('fixture-fragment-ms',[])
            samples.append(round((perf_counter()-started)*1000,2))
            del samples[:-100]
    measured.fixture_profile=True
    setattr(module,name,measured)
