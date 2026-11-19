"""Isolated Home refresh reproduction, with no external connections."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import streamlit as st
from datetime import date
import home_fast, os_accounts
from home_morning_brief_actions import brief_html
st.set_page_config(layout='wide')
os_accounts.is_reporting_owner=lambda _:True
os_accounts.can_access_reporting=lambda _:True
os_accounts.can_access_page=lambda *args:True
home_fast.SNAPSHOTS.ttl=.5
original=st.fragment
st.fragment=lambda **kwargs:original(run_every=.3)
@st.cache_resource
def count():return {'n':0}
def sports(today):
    count()['n']+=1
    return dict(saved={'date':str(today),'recommendations':[dict(title='Synthetic story '+str(count()['n']),recommendation='Test',links=[]) ]},editions=[],statuses={})
def meta(today):
    return dict(saved=dict(date=str(today),report_date=str(today),summary='Synthetic Meta',recommendations=['Saved recommendation']),refresh='')
home_fast.sports_data=sports
home_fast.meta_data=meta
home_fast.render_briefs(st,{'id':'fixture'},date(2026,11,18))
st.button('Full rerun')
