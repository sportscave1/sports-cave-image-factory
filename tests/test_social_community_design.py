"""Synthetic interaction and network budgets for the compact community workspace."""
from datetime import datetime, timezone
from unittest.mock import Mock, patch
import unittest

import pytest

from meta_social import CommunityError, MetaCommunity
from social_community_feed import CommunityFeed
from tests.community_fixtures import ADMIN, FakeCommunity, FakeStore, READS
from tests import test_meta_social as contracts
from tests.test_meta_social import ENV, response


def test_history_does_not_reload_when_the_latest_page_refreshes():
    clock = [0.0]
    api = FakeCommunity(dict(ADMIN))
    api.conversations = Mock(return_value={"data": [], "after": ""})
    feed = CommunityFeed(api, {}, now=lambda: clock[0])
    feed.read("conversations", "Instagram")
    feed.read("conversations", "Instagram", after="older")
    clock[0] = 61
    feed.read("conversations", "Instagram")
    feed.read("conversations", "Instagram", after="older")
    assert api.conversations.call_count == 3
    clock[0] = 301
    feed.read("conversations", "Instagram", after="older")
    assert api.conversations.call_count == 4


def test_transient_errors_recover_without_waiting_for_history_cache_expiry():
    clock = [0.0]
    api = FakeCommunity(dict(ADMIN))
    api.messages = Mock(side_effect=[CommunityError("Temporarily unavailable"), {"data": []}])
    feed = CommunityFeed(api, {}, now=lambda: clock[0])
    for at in (0, 5, 14):
        clock[0] = at
        with pytest.raises(CommunityError):
            feed.read("messages", "Instagram", "thread", after="older")
    assert api.messages.call_count == 1
    clock[0] = 16
    assert feed.read("messages", "Instagram", "thread", after="older") == {"data": []}
    assert api.messages.call_count == 2


def test_reply_checks_ownership_once_then_reads_window_and_sends_once():
    http = Mock()
    http.request.side_effect = [response({"data": [{"id": "thread", "participants": {"data": [
        {"id": "page"}, {"id": "customer"}]}}]}),
        response({"data": [{"id": "inbound", "from": {"id": "customer"},
                           "created_time": datetime.now(timezone.utc).isoformat()}]}),
        response({"message_id": "sent"})]
    api = MetaCommunity(dict(ADMIN), env=ENV, session=http)
    api.send("Facebook", "thread", "Thanks")
    assert [call.args[0] for call in http.request.call_args_list] == ["GET", "GET", "POST"]
    assert http.request.call_args.kwargs["json"]["recipient"]["id"] == "customer"


@pytest.mark.parametrize("payload", [True, {}, {"data": None}, {"data": {}}, {"data": ["invalid"]}])
def test_malformed_provider_page_has_a_recoverable_error(payload):
    http = Mock()
    http.request.return_value = response(payload)
    api = MetaCommunity(dict(ADMIN), env=ENV, session=http)
    with pytest.raises(CommunityError, match="unexpected page"):
        api.comment_feed("Facebook")


class DesignInteractions(unittest.TestCase):
    SCRIPT = contracts.CommunityUiTests.SCRIPT
    setUp = contracts.CommunityUiTests.setUp
    app = contracts.CommunityUiTests.app
    button = contracts.CommunityUiTests.button
    open_comment = contracts.CommunityUiTests.open_comment
    def test_collaboration_filters_do_not_repeat_database_reads(self):
        FakeStore.rows = [{"username": "fixture", "followers": 5000, "engagement": 4.4,
            "score": 80, "reason": "Sports collector", "fit": True, "draft": "Hello", "state": "shortlisted"}]
        with patch.object(FakeStore, "list_creators", wraps=FakeStore.list_creators) as read:
            app = self.app()
            app.segmented_control[0].set_value("Collaborations").run()
            app.text_input(key="community-creator-search").set_value("fixture").run()
            app.selectbox(key="community-creator-stage").set_value("shortlisted").run()
            assert not app.exception
            assert read.call_count == 1
            assert [tab.label for tab in app.tabs] == ["Overview", "Invitation", "History"]

    def test_only_one_comment_reply_form_is_built_when_two_rows_are_open(self):
        app = self.app()
        app.segmented_control[0].set_value("Comments").run()
        self.open_comment(app, "Facebook")
        self.open_comment(app, "Instagram")
        assert not app.exception
        assert len(app.text_area) == 1
        assert app.session_state["community-selected-comment"] == ("Instagram", "comment")

    def test_switching_to_connection_does_not_poll_meta_or_reveal_stale_account(self):
        app = self.app()
        before = len(READS)
        app.segmented_control[0].set_value("Connection").run()
        assert not app.exception
        assert len(READS) == before
        assert not app.success

    def test_unread_filter_does_not_reload_inbox(self):
        app = self.app()
        before = len(READS)
        app.selectbox(key="community-inbox-filter").set_value("Unread").run()
        assert not app.exception
        assert len(READS) == before

    def test_unexpected_fragment_failure_is_contained(self):
        with patch.object(FakeCommunity, "messages", side_effect=TypeError("synthetic bad data")):
            app = self.app()
        assert not app.exception
        assert any("draft is kept" in item.value for item in app.warning)

    def test_changing_users_clears_the_previous_users_draft(self):
        from streamlit.testing.v1 import AppTest
        script = '''import streamlit as st
import social_media_page
from tests.community_fixtures import ADMIN, FakeCommunity, FakeStore
social_media_page.render_page(dict(ADMIN, id=st.session_state.get("test-user", "one")),
    api_factory=FakeCommunity, store=FakeStore)
'''
        app = AppTest.from_string(script).run()
        app.text_area[0].set_value("Private draft for user one").run()
        app.session_state["test-user"] = "two"
        app.run()
        assert not app.exception
        assert app.text_area[0].value == ""
