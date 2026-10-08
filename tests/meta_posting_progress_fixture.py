"""Loopback UI fixture: all Meta and database operations are synthetic."""
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from threading import Event
from unittest.mock import patch, Mock
import streamlit as st
from tests.test_meta_posting_jobs import Ledger
from tests.test_meta_posting import FakePostingClient, request_for
from meta_posting_service import MetaPostingService
from meta_posting_jobs import PostingJobs
import ads_posting_progress as progress


@st.cache_resource
def fixture():
    gate = Event()
    store = Ledger()
    client = FakePostingClient(fail_at='ad_2')
    class Service(MetaPostingService):
        def create_paused_campaign(self, request):
            gate.wait(60)
            return super().create_paused_campaign(request)
    jobs = PostingJobs(lambda: store, lambda **kw: Service(client=client, **kw))
    return gate, store, client, jobs


gate, store, client, jobs = fixture()
if os.environ.get('META_POSTING_UI_FIXTURE') == '1':
    # Fragment timer callbacks execute after the script's patch contexts exit.
    import ads_posting_page as posting
    import requests
    progress.JOBS = jobs
    posting.MetaPostingClient = lambda: Mock(ad_account_id='act_123')
    posting._load_recent_posts = Mock(side_effect=store.recent)
    requests.sessions.Session.request = Mock(side_effect=AssertionError('No external network allowed'))
st.title('Creative Refresh / New Ads — mocked posting')
if st.button('Create 3 Paused Meta Ads'):
    progress.track(jobs.submit(request_for()))
if st.button('Continue mocked Meta job'):
    gate.set()
if store.record.get('status') == 'FAILED':
    client.fail_at = ''
with patch.object(progress, 'JOBS', jobs), \
     patch('ads_posting_page.MetaPostingClient', return_value=Mock(ad_account_id='act_123')), \
     patch('ads_posting_page._load_recent_posts', return_value=store.recent()), \
     patch('requests.sessions.Session.request', side_effect=AssertionError('No external network allowed')):
    progress.render_current()
