"""Offline browser acceptance fixture using the real Research and Ideas controls."""
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import streamlit as st
import design_schedule
import design_studio_page
import design_studio_intelligence_store as store
import design_studio_sales_intelligence as intel
from tests.test_design_studio_sales_intelligence import fixture_sources

st.set_page_config(layout='wide', initial_sidebar_state='collapsed')
outage = st.checkbox('Simulate analytics outage')
if st.session_state.get('fixture-outage') != outage:
    intel._CACHE.clear()
    st.session_state['fixture-outage'] = outage
st.session_state.setdefault('fixture-source-reads', 0)

def load(*args):
    st.session_state['fixture-source-reads'] += 1
    if outage:
        raise RuntimeError('Fixture outage: diagnostic must not leak')
    return fixture_sources()

task = {'id': 'v3-fixture', 'title': 'Joe Montana — The Catch', 'text': 'Joe Montana — The Catch',
        'design_style': 'ultimate_moment', 'metadata': {'design_style': 'ultimate_moment', 'design_details': {
            'sport': 'NFL', 'principal_subject_one': 'Joe Montana', 'event_moment': 'The Catch'}}}
with patch.object(store, 'load_sources', side_effect=load), \
     patch.object(design_schedule, 'render_design_schedule', return_value=task):
    design_studio_page.render_design_studio_v2(can_edit_prompts=True)
    st.session_state[design_schedule.SCHEDULE_GENERATOR_OPEN_KEY] = True
    design_schedule._render_idea_generator()
st.caption(f"Fixture source reads: {st.session_state['fixture-source-reads']}")
