"""Local Campaign UI with production-shaped UUID template metadata; no external I/O."""
from pathlib import Path
from unittest.mock import patch
from uuid import UUID
from crm_campaign_store import CampaignStore
from crm_campaign_library import save_template
from tests.crm_db_fixture import connect
from tests.test_crm import ADMIN
import streamlit as st

store = CampaignStore(connect)
if not st.session_state.get('uuid_fixture_seeded'):
    if not any(row['name'] == 'Trust Icons UUID fixture' for row in store.html_library(metadata=True)):
        save_template(store, ADMIN, 'Trust Icons UUID fixture', '<p>Trust Icons fixture</p>')
    st.session_state['uuid_fixture_seeded'] = True
original = CampaignStore.html_library


def uuid_rows(self, **kwargs):
    return [{**row, 'id': UUID(str(row['id']))} for row in original(self, **kwargs)]


with patch.object(CampaignStore, 'html_library', uuid_rows):
    exec((Path(__file__).parent / 'session_recovery_preview_app.py').read_text(encoding='utf-8'))
