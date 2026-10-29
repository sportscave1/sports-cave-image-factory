"""Synthetic popup browser fixture; no credentials, database or Meta access."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import dotenv
dotenv.load_dotenv = lambda *a, **k: False
import requests
from unittest.mock import Mock
requests.sessions.Session.request = Mock(side_effect=AssertionError("Offline fixture"))
import time
import streamlit as st
import ads_posting_progress as progress
import ads_posting_page as posting
from ui_styles import inject_global_ui_styles

ID = "11111111-1111-4111-8111-111111111111"
def snapshot(identity):
    st.session_state["reads"] = st.session_state.get("reads", 0) + 1
    elapsed = time.monotonic() - st.session_state.get("started", time.monotonic())
    status = "UPLOADING" if elapsed < 4 else "AD_CREATED" if elapsed < 8 else "COMPLETE"
    if st.query_params.get("scenario") == "failure" and elapsed >= 4 and not st.session_state.get("retried"):
        status = "FAILED"
    return dict(can_retry=status == "FAILED", safe_error="Mock upload failed" if status == "FAILED" else "",
                submission_id=identity, campaign_id="fixture-campaign", adset_id="fixture-adset",
                campaign_name="Fixture campaign", status=status, running_here=status != "COMPLETE",
                ad_results=[dict(index=i, meta_ad_id=str(i), meta_ad_configured_status="PAUSED")
                            for i in range(1, 1 if elapsed < 4 else 4)])
def retry(identity):
    assert identity == ID
    st.session_state["retried"] = True
    st.session_state["retries"] = st.session_state.get("retries", 0) + 1
progress.JOBS = Mock(snapshot=snapshot, retry=retry)
progress.JOBS.submit.side_effect = AssertionError("No submission from popup")
posting._load_recent_posts = Mock(return_value=[])
inject_global_ui_styles()
progress.cleanup_completed()
posting._ensure_posting_run()
st.title("Offline posting fixture")
st.text_input("Campaign form", key="fixture_form")
if st.button("Start mocked upload"):
    st.session_state["started"] = time.monotonic()
    st.session_state[posting.SUBMISSION_ID_KEY] = ID
    st.session_state["starts"] = st.session_state.get("starts", 0) + 1
    progress.track(ID)
st.caption("Starts: " + str(st.session_state.get("starts", 0)))
st.caption("Reads: " + str(st.session_state.get("reads", 0)))
st.caption("Retries: " + str(st.session_state.get("retries", 0)))
progress.render_current()
