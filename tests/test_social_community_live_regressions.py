"""Offline reproductions of the live pagination and partial-connection failures."""
import unittest
from unittest.mock import Mock, patch

from meta_social import CommunityError, MetaCommunity
from social_community_feed import CommunityFeed
from tests.community_fixtures import ADMIN, FakeCommunity
from tests.test_meta_social import ENV, response
from tests import test_meta_social as contracts


class LiveApiRegressionTests(unittest.TestCase):
    def test_opaque_long_cursors_survive_every_paginated_edge(self):
        http = Mock()
        http.request.return_value = response({"data": []})
        api = MetaCommunity(dict(ADMIN), env=ENV, session=http)
        cursor = "opaque" * 240 + "=="
        for platform in ("Facebook", "Instagram"):
            api.comment_feed(platform, after=cursor)
            self.assertEqual(http.request.call_args.kwargs["params"]["after"], cursor)
        self.assertEqual(http.request.call_count, 2)

    def test_permission_diagnostic_keeps_codes_and_scope_names_but_no_provider_secrets(self):
        http = Mock()
        http.request.return_value = response({"error": {"code": 200, "error_subcode": 123,
            "message": "Requires instagram_manage_messages; fixture-page-token https://private.invalid"}}, 400)
        api = MetaCommunity(dict(ADMIN), env=ENV, session=http)
        with self.assertRaises(CommunityError) as caught:
            api.conversations("Instagram")
        message = str(caught.exception)
        self.assertIn("200/123", message)
        self.assertIn("instagram_manage_messages", message)
        self.assertNotIn("fixture-page-token", message)
        self.assertNotIn("private.invalid", message)

    def test_connection_checks_preserve_available_features_when_instagram_messages_fail(self):
        api = MetaCommunity(dict(ADMIN), env=ENV, session=Mock())
        def conversations(platform):
            if platform == "Instagram":
                raise CommunityError("Meta rejected the request (Meta 200).")
            return {"data": []}
        with patch.object(api, "conversations", side_effect=conversations), patch.object(api, "comment_feed", return_value={"data": []}):
            checks = api.connection_checks()
        self.assertEqual(len(checks), 4)
        self.assertEqual(sum(row["Status"] == "Available" for row in checks), 3)
        self.assertEqual(checks[2]["Status"], "Needs attention")
        api._session.request.assert_not_called()


class HistoryRegressionTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeCommunity(dict(ADMIN))
        self.feed = CommunityFeed(self.api, {})

    @staticmethod
    def history(platform, after="", found_at=3):
        if platform == "Instagram":
            return {"data": [], "after": ""}
        index = int(after or 0)
        comments = [{"id": "older-comment", "message": "An older customer comment"}] if index == found_at else []
        return {"data": [{"id": "post" + str(index), "comments": {"data": comments}}],
                "after": str(index + 1) if index < 20 else ""}

    def test_initial_search_passes_recent_empty_posts_and_finds_older_comments(self):
        with patch.object(self.api, "comment_feed", side_effect=self.history) as read:
            result = self.feed.comments()
            self.assertEqual([row["id"] for row in result["items"]], ["older-comment"])
            self.assertEqual(result["posts_scanned"], 4)
            self.feed.comments()
            self.assertEqual(read.call_count, 5)

    def test_empty_history_search_is_bounded_and_only_advances_on_request(self):
        with patch.object(self.api, "comment_feed", side_effect=lambda p, after="": self.history(p, after, found_at=7)) as read:
            first = self.feed.comments()
            self.assertFalse(first["items"])
            self.assertTrue(first["more_posts"]["Facebook"])
            self.feed.comments()
            self.assertEqual(read.call_count, 5)
            self.feed.more_comments(first)
            second = self.feed.comments()
            self.assertEqual(second["items"][0]["id"], "older-comment")
            self.assertEqual(read.call_count, 9)

    def test_failed_older_page_keeps_comments_already_loaded(self):
        def load(platform, after=""):
            if after:
                raise CommunityError("Meta error 100")
            return self.history(platform, found_at=0)
        with patch.object(self.api, "comment_feed", side_effect=load):
            first = self.feed.comments()
            self.feed.more_comments(first)
            second = self.feed.comments()
            self.assertEqual(second["items"][0]["id"], "older-comment")
            self.assertTrue(second["errors"])


class LiveUiRegressionTests(unittest.TestCase):
    SCRIPT = contracts.CommunityUiTests.SCRIPT
    setUp = contracts.CommunityUiTests.setUp
    app = contracts.CommunityUiTests.app
    button = contracts.CommunityUiTests.button

    def test_pending_history_never_claims_no_comments_and_offers_search(self):
        with patch.object(FakeCommunity, "comment_feed", side_effect=lambda p, after="": HistoryRegressionTests.history(p, after, found_at=7)):
            app = self.app()
            app.segmented_control[0].set_value("Comments").run()
            self.assertFalse(app.exception)
            self.assertTrue(any("so far" in item.value for item in app.info))
            self.button(app, "Search older posts").click().run()
            self.assertTrue(app.expander)
            self.assertFalse(app.exception)

    def test_message_content_is_escaped_in_bubbles(self):
        with patch.object(FakeCommunity, "messages", return_value={"data": [{"id": "m", "from": {"id": "person"},
                "message": '<img src=x onerror="alert(1)">'}], "after": ""}):
            app = self.app()
        self.assertFalse(app.exception)
        rendered = "\n".join(item.value for item in app.markdown)
        self.assertIn("&lt;img", rendered)
        self.assertNotIn('<img src=x', rendered)
        self.assertEqual(len(app.chat_message), 0)

    def test_connection_panel_displays_feature_results_without_a_false_success(self):
        checks = [{"Channel": "Instagram", "Feature": "Messages", "Status": "Needs attention", "Details": "Meta 200"}]
        with patch.object(FakeCommunity, "connection_checks", return_value=checks, create=True), patch.object(
                FakeCommunity, "connection", side_effect=CommunityError("Wrong linked account")):
            app = self.app()
            app.segmented_control[0].set_value("Connection").run()
            self.button(app, "Check Meta connection").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.warning)
        self.assertFalse(app.success)
        self.assertEqual(app.dataframe[0].value["Status"].tolist(), ["Needs attention"])


if __name__ == "__main__":
    unittest.main()
