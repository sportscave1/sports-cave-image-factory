import unittest
import json
from unittest.mock import Mock, patch

from meta_social import CommunityError, MetaCommunity
from social_community_feed import CommunityFeed, timestamp
from social_community_views import dated
from tests.community_fixtures import ADMIN, FakeCommunity, READS
from tests import test_meta_social as contracts


class MergedFeedTests(unittest.TestCase):
    def setUp(self):
        READS.clear()
        self.api = FakeCommunity(dict(ADMIN))
        self.state = {}
        self.clock = [100.0]
        self.feed = CommunityFeed(self.api, self.state, now=lambda: self.clock[0])

    def test_inbox_combines_channels_without_collapsing_same_scoped_id(self):
        rows = self.feed.threads()["items"]
        self.assertEqual([(r["platform"], r["id"]) for r in rows], [("Facebook", "thread"), ("Instagram", "thread")])
        self.assertEqual(sum(r["unread_count"] for r in rows), 2)

    def test_comment_feed_is_two_calls_and_keeps_both_channel_rows(self):
        first = self.feed.comments()
        second = self.feed.comments()
        self.assertEqual(len(first["items"]), 2)
        self.assertEqual(first["items"], second["items"])
        self.assertEqual(READS, [("comment_feed", "Facebook"), ("comment_feed", "Instagram")])

    def test_cache_refresh_expiry_and_account_identity(self):
        self.feed.threads()
        self.feed.threads()
        self.assertEqual(len(READS), 2)
        self.clock[0] += 61
        self.feed.threads()
        self.assertEqual(len(READS), 4)
        self.feed.invalidate()
        self.feed.threads()
        self.assertEqual(len(READS), 6)
        other = FakeCommunity(dict(ADMIN, id="another-user"))
        CommunityFeed(other, self.state).threads()
        self.assertEqual(len(READS), 8)
        self.assertNotIn("token", repr(self.state))

    def test_revoked_permission_never_reads_cached_data(self):
        self.feed.threads()
        self.api.user["is_active"] = False
        with self.assertRaises(PermissionError):
            self.feed.threads()
        self.assertEqual(len(READS), 2)

    def test_one_channel_failure_does_not_hide_other_channel_or_retry_on_every_click(self):
        original = self.api.comment_feed
        def load(platform, **kwargs):
            if platform == "Instagram":
                raise CommunityError("Permission unavailable.")
            return original(platform, **kwargs)
        with patch.object(self.api, "comment_feed", side_effect=load) as read:
            for _ in range(2):
                result = self.feed.comments()
                self.assertEqual(len(result["items"]), 1)
                self.assertIn("Instagram", result["errors"][0])
            self.assertEqual(read.call_count, 2)

    def test_post_and_comment_pagination_appends_without_loss_or_repeat_requests(self):
        def posts(platform, after=""):
            if platform == "Instagram":
                return {"data": [], "after": ""}
            if after == "older-posts":
                return {"data": [{"id": "post2", "comments": {"data": [{"id": "third", "created_time": "2026-11-19T00:00:00Z"}]}}], "after": ""}
            return {"data": [{"id": "post", "comments": {"data": [{"id": "first", "created_time": "2026-11-22T00:00:00Z"}],
                     "paging": {"next": "https://graph.facebook.com/ignored", "cursors": {"after": "older-comments"}}}}], "after": "older-posts"}
        with patch.object(self.api, "comment_feed", side_effect=posts) as post_read, patch.object(
            self.api, "comments", return_value={"data": [{"id": "second", "created_time": "2026-11-20T00:00:00Z"}], "after": ""}) as comment_read:
            snapshot = self.feed.comments()
            self.feed.more_comments(snapshot)
            snapshot = self.feed.comments()
            self.assertEqual([r["id"] for r in snapshot["items"]], ["first", "second"])
            self.feed.more_comments(snapshot)
            snapshot = self.feed.comments()
            self.assertEqual([r["id"] for r in snapshot["items"]], ["first", "second", "third"])
            self.feed.comments()
            self.assertEqual(comment_read.call_count, 1)
            self.assertEqual(post_read.call_count, 3)
            self.assertFalse(snapshot["more_comments"])
            self.assertFalse(any(snapshot["more_posts"].values()))

    def test_inbox_pagination_deduplicates_overlapping_results(self):
        def threads(platform, after=""):
            return {"data": [{"id": "same"}, *([{"id": "older"}] if after else [])], "after": "" if after else "next"}
        with patch.object(self.api, "conversations", side_effect=threads) as read:
            self.feed.more_threads(self.feed.threads())
            self.assertEqual(len(self.feed.threads()["items"]), 4)
            self.feed.threads()
            self.assertEqual(read.call_count, 4)

    def test_dates_sort_by_instant_and_display_sydney_timezone(self):
        self.assertGreater(timestamp("2026-11-22T00:00:00Z"), timestamp("2026-11-22T08:00:00+11:00"))
        self.assertEqual(dated("2026-11-22T00:00:00Z"), "22 Nov 2026 · 11:00 AM AEDT")
        self.assertEqual(dated("not a date"), "Date unavailable")

    def test_graph_field_expansion_returns_summary_without_per_post_queries(self):
        http = Mock()
        api = MetaCommunity(ADMIN, env=contracts.ENV, session=http)
        http.request.return_value = contracts.response({"data": [], "paging": {}})
        api.comment_feed("Facebook")
        api.comment_feed("Instagram")
        self.assertEqual(http.request.call_count, 2)
        for call in http.request.call_args_list:
            self.assertIn("comments", call.kwargs["params"]["fields"])
            self.assertEqual(call.kwargs["params"]["limit"], 8)
            self.assertNotIn("access_token", call.kwargs["params"])


class CompactWorkspaceTests(unittest.TestCase):
    SCRIPT = contracts.CommunityUiTests.SCRIPT
    setUp = contracts.CommunityUiTests.setUp
    app = contracts.CommunityUiTests.app
    button = contracts.CommunityUiTests.button
    open_comment = contracts.CommunityUiTests.open_comment

    def test_merged_inbox_has_channel_column_and_no_account_switch(self):
        app = self.app()
        self.assertEqual(app.dataframe[0].value["Channel"].tolist(), ["Facebook", "Instagram"])
        self.assertEqual(len(app.radio), 0)
        self.assertFalse(app.exception)

    def test_selecting_instagram_row_sends_reply_to_instagram(self):
        app = self.app()
        states = app._tree.get_widget_states()
        selected = states.widgets.add()
        selected.id = app.dataframe[0].proto.id
        selected.string_value = json.dumps({"selection": {"rows": [1], "columns": [], "cells": []}})
        app._run(widget_state=states)
        self.assertEqual(app.session_state["community-selected-thread"], ("Instagram", "thread"))
        app.text_area[0].set_value("Reply from the merged inbox")
        self.button(app, "Send reply").click().run()
        from tests.community_fixtures import EVENTS
        self.assertIn(("send", "Instagram", "thread", "Reply from the merged inbox"), EVENTS)

    def test_closed_comment_rows_have_dates_and_no_forms(self):
        app = self.app()
        app.segmented_control[0].set_value("Comments").run()
        self.assertEqual(len(app.expander), 0)
        self.assertEqual(len(app.text_area), 0)
        self.assertEqual(len(app.selectbox), 0)
        rendered = "\n".join(item.value for item in app.markdown)
        self.assertIn("22 Nov 2026", rendered)
        self.assertIn("AEDT", rendered)
        self.assertEqual(len([b for b in app.button if str(b.key).startswith("comment-select-")]), 2)
        self.assertFalse(app.exception)

    def test_opening_and_typing_does_not_fetch_comment_feed_again(self):
        app = self.app()
        app.segmented_control[0].set_value("Comments").run()
        initial = len(READS)
        self.open_comment(app, "Facebook")
        app.text_area[0].set_value("Thanks for your support")
        self.open_comment(app, "Facebook")
        self.assertEqual(len(READS), initial)
        self.button(app, "Reply").click()
        self.open_comment(app, "Facebook")
        from tests.community_fixtures import EVENTS
        self.assertIn(("reply", "Facebook", "comment", "Thanks for your support"), EVENTS)

    def test_instagram_reply_uses_its_channel_even_when_comment_ids_match(self):
        app = self.app()
        app.segmented_control[0].set_value("Comments").run()
        self.open_comment(app, "Instagram")
        app.text_area[0].set_value("Thank you!")
        self.button(app, "Reply").click()
        self.open_comment(app, "Instagram")
        from tests.community_fixtures import EVENTS
        self.assertIn(("reply", "Instagram", "comment", "Thank you!"), EVENTS)

    def test_refresh_invalidates_reads_but_search_is_cached(self):
        app = self.app()
        initial = len(READS)
        app.text_input[0].set_value("fixture").run()
        self.assertEqual(len(READS), initial)
        self.button(app, "Refresh").click().run()
        self.assertGreater(len(READS), initial)

    def test_failed_send_keeps_the_draft(self):
        app = self.app()
        app.text_area[0].set_value("Please keep this draft")
        with patch.object(FakeCommunity, "send", side_effect=CommunityError("Sending unavailable.")):
            self.button(app, "Send reply").click().run()
        self.assertEqual(app.text_area[0].value, "Please keep this draft")
        self.assertTrue(any("Sending unavailable" in w.value for w in app.warning))

    def test_all_loaded_comments_are_reachable_beyond_first_forty(self):
        def many(api, platform, **kwargs):
            return {"data": [{"id": "post", "comments": {"data": [
                {"id": str(i), "text": "Fixture comment " + str(i), "timestamp": "2026-11-22T00:00:00Z"}
                for i in range(45)]}}], "after": ""}
        with patch.object(FakeCommunity, "comment_feed", many):
            app = self.app()
            app.segmented_control[0].set_value("Comments").run()
            self.assertEqual(len([b for b in app.button if str(b.key).startswith("comment-select-")]), 40)
            self.button(app, "Show more comments").click().run()
            self.assertEqual(len([b for b in app.button if str(b.key).startswith("comment-select-")]), 80)
            self.button(app, "Show more comments").click().run()
            self.assertEqual(len([b for b in app.button if str(b.key).startswith("comment-select-")]), 90)
            self.assertFalse(app.exception)


if __name__ == "__main__":
    unittest.main()
