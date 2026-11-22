import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import requests
from streamlit.testing.v1 import AppTest

from meta_social import CommunityError, MetaCommunity, assess_creator, reply_open
import social_collaborations as collabs
import os_accounts
import social_media
from tests.community_fixtures import ADMIN, EVENTS, FakeCommunity, FakeStore

ENV = {"META_FACEBOOK_PAGE_ID": "page", "META_INSTAGRAM_ACTOR_ID": "ig",
       "META_PAGE_ACCESS_TOKEN": "fixture-page-token", "META_SOCIAL_DISCOVERY_TOKEN": "fixture-discovery-token",
       "META_SOCIAL_WRITES_ENABLED": "1"}


def response(data, status=200):
    return Mock(status_code=status, json=Mock(return_value=data))


class MetaContractTests(unittest.TestCase):
    def setUp(self):
        self.http = Mock()
        self.api = MetaCommunity(dict(ADMIN), env=ENV, session=self.http)

    def test_denied_or_inactive_user_cannot_construct_client(self):
        for user in (None, {"role": "worker", "is_active": True}, dict(ADMIN, is_active=False)):
            with self.assertRaises(PermissionError):
                MetaCommunity(user, env=ENV, session=self.http)
        self.http.request.assert_not_called()

    def test_permission_is_rechecked_on_every_request(self):
        self.api.user["is_active"] = False
        with self.assertRaises(PermissionError):
            self.api.posts("Facebook")
        self.http.request.assert_not_called()

    def test_tokens_stay_in_headers_and_pagination_does_not_follow_remote_url(self):
        self.http.request.return_value = response({"data": [], "paging": {
            "next": "https://evil.test/?access_token=unsafe", "cursors": {"after": "cursor"}}})
        page = self.api.conversations("Instagram")
        self.assertEqual(page["after"], "cursor")
        args, kwargs = self.http.request.call_args
        self.assertEqual(args[1], "https://graph.facebook.com/v26.0/page/conversations")
        self.assertNotIn("access_token", kwargs["params"])
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer fixture-page-token")
        self.assertFalse(kwargs["allow_redirects"])

    def test_provider_errors_never_return_raw_error_or_secret(self):
        self.http.request.return_value = response({"error": {"code": 190, "message": "fixture-page-token"}}, 400)
        with self.assertRaises(CommunityError) as caught:
            self.api.posts("Facebook")
        self.assertNotIn("fixture-page-token", str(caught.exception))
        self.assertIn("Reconnect", str(caught.exception))

    def test_network_timeout_is_ambiguous_and_is_not_retried(self):
        self.http.request.side_effect = requests.Timeout("secret")
        with self.assertRaisesRegex(CommunityError, "may have succeeded"):
            self.api._request("POST", "page/messages", data={})
        self.assertEqual(self.http.request.call_count, 1)

    def test_disabled_writes_never_reach_transport(self):
        api = MetaCommunity(ADMIN, env=dict(ENV, META_SOCIAL_WRITES_ENABLED="0"), session=self.http)
        with self.assertRaisesRegex(CommunityError, "disabled"):
            api._request("DELETE", "comment")
        self.http.request.assert_not_called()

    def test_negative_provider_acknowledgement_is_not_reported_as_success(self):
        for payload in (False, {"success": False}):
            self.http.request.return_value = response(payload)
            with self.assertRaisesRegex(CommunityError, "did not confirm"):
                self.api._request("DELETE", "comment")

    def test_another_app_owning_thread_prevents_send(self):
        self.api._thread = Mock(return_value={"is_owner": False})
        with self.assertRaisesRegex(CommunityError, "Another app"):
            self.api.send("Instagram", "thread", "Hello")
        self.http.request.assert_not_called()

    def test_invalid_ids_or_discovery_expression_cannot_enter_graph_path(self):
        for value in ("../other", "x?fields=secret", "x){id}"):
            with self.assertRaises(CommunityError):
                self.api.discover(value)
            with self.assertRaises(CommunityError):
                self.api.comments("Facebook", value)
        self.http.request.assert_not_called()

    def test_wrong_page_or_linked_instagram_fails_connection(self):
        for payload in ({"id": "other"}, {"id": "page", "instagram_business_account": {"id": "wrong"}}):
            self.http.request.return_value = response(payload)
            with self.assertRaises(CommunityError):
                self.api.connection()

    def test_forged_thread_cannot_read_messages(self):
        self.http.request.return_value = response({"data": []})
        with self.assertRaisesRegex(CommunityError, "not in"):
            self.api.messages("Facebook", "foreign-thread")
        self.assertTrue(all("/messages" not in call.args[1] for call in self.http.request.call_args_list))

    def test_send_uses_verified_recipient_and_recent_inbound_only(self):
        self.api._thread = Mock(return_value={"participants": {"data": [{"id": "page"}, {"id": "customer"}]}})
        self.api.messages = Mock(return_value={"data": [{
            "from": {"id": "customer"}, "created_time": datetime.now(timezone.utc).isoformat()}]})
        self.http.request.return_value = response({"message_id": "sent"})
        self.api.send("Facebook", "thread", "Thank you")
        body = self.http.request.call_args.kwargs["json"]
        self.assertEqual(body["recipient"], {"id": "customer"})
        self.assertEqual(body["messaging_type"], "RESPONSE")
        self.api.messages.return_value = {"data": [{"from": {"id": "page"}, "created_time": datetime.now(timezone.utc).isoformat()}]}
        self.http.reset_mock()
        with self.assertRaisesRegex(CommunityError, "24 hours"):
            self.api.send("Facebook", "thread", "Hello")
        self.http.request.assert_not_called()

    def test_reply_window_boundary_future_and_malformed_times(self):
        now = datetime(2026, 11, 22, tzinfo=timezone.utc)
        def inbound(at):
            return [{"from": {"id": "person"}, "created_time": at}]
        self.assertTrue(reply_open(inbound((now-timedelta(hours=23)).isoformat()), "page", now=now))
        for at in ((now-timedelta(hours=24)).isoformat(), (now+timedelta(seconds=1)).isoformat(), "bad", "2026-11-22"):
            self.assertFalse(reply_open(inbound(at), "page", now=now))

    def test_foreign_post_blocks_comment_reads_and_actions(self):
        self.http.request.return_value = response({"id": "post", "from": {"id": "other"}})
        with self.assertRaisesRegex(CommunityError, "does not belong"):
            self.api.moderate("Facebook", "post", "comment", "delete")
        self.assertEqual(self.http.request.call_count, 1)

    def test_foreign_comment_never_moderated_even_if_post_owned(self):
        self.http.request.side_effect = [response({"from": {"id": "page"}}), response({"data": [{"id": "real"}]})]
        with self.assertRaisesRegex(CommunityError, "could not be verified"):
            self.api.moderate("Facebook", "post", "foreign", "delete")
        self.assertTrue(all(call.args[0] == "GET" for call in self.http.request.call_args_list))

    def test_comment_actions_use_platform_specific_edges(self):
        for platform, action, method, path, body in (
            ("Facebook", "like", "POST", "comment/likes", None),
            ("Facebook", "unlike", "DELETE", "comment/likes", None),
            ("Facebook", "reply", "POST", "comment/comments", {"message": "Thanks"}),
            ("Instagram", "reply", "POST", "comment/replies", {"message": "Thanks"}),
            ("Instagram", "hide", "POST", "comment", {"hide": True}),
            ("Facebook", "delete", "DELETE", "comment", None),
        ):
            with self.subTest(platform=platform, action=action):
                self.api.comments = Mock(return_value={"data": [{"id": "comment"}], "after": ""})
                self.http.request.return_value = response({"success": True})
                self.api.moderate(platform, "post", "comment", action, "Thanks")
                call = self.http.request.call_args
                self.assertEqual(call.args[:2], (method, "https://graph.facebook.com/v26.0/" + path))
                self.assertEqual(call.kwargs["json"], body)
        self.http.reset_mock()
        with self.assertRaises(CommunityError):
            self.api.moderate("Instagram", "post", "comment", "like")
        self.http.request.assert_not_called()

    def test_discovery_uses_separate_user_token_and_restricts_professional_profile(self):
        self.http.request.return_value = response({"business_discovery": {"username": "fixture"}})
        self.assertEqual(self.api.discover("@Fixture")["username"], "fixture")
        self.assertEqual(self.http.request.call_args.kwargs["headers"]["Authorization"], "Bearer fixture-discovery-token")

    def test_assessment_does_not_invent_engagement_or_assume_sports_fit(self):
        assessed = assess_creator({"username": "fixture", "followers_count": 5000})
        self.assertFalse(assessed["fit"])
        self.assertIsNone(assessed["engagement"])
        assessed = assess_creator(FakeCommunity(ADMIN).discover("fixture"))
        self.assertTrue(assessed["fit"])
        self.assertEqual(assessed["engagement"], 4.4)


class CommunityNavigationTests(unittest.TestCase):
    def test_reels_routes_are_retired_and_bookmarks_resolve_to_social_media(self):
        routes = os_accounts.allowed_navigation_routes(ADMIN)
        self.assertIn("Social Media", routes)
        self.assertNotIn("AI Reels", routes)
        self.assertNotIn("Social Media Reels Studio", routes)
        self.assertEqual(os_accounts.normalise_route("AI Reels"), "Social Media")
        self.assertEqual(os_accounts.normalise_route("Social Media Reels Studio"), "Social Media")

    def test_legacy_staff_permissions_grant_replacement_access_only(self):
        for key in (social_media.AI_REELS_PAGE_KEY, social_media.LEGACY_REELS_PAGE_KEY):
            worker = {"id": "fixture-worker", "role": "worker", "is_active": True, "page_permissions": [key]}
            self.assertTrue(os_accounts.can_access_page(worker, "Social Media"))
            self.assertFalse(os_accounts.can_access_page(worker, "Orders"))

    def test_old_schema_is_never_recreated_and_reporting_adapter_does_not_query_it(self):
        import run_migrations
        import social_media_store
        self.assertNotIn("20260728_social_media_hub.sql", [path.name for path in run_migrations.migration_files()])
        self.assertEqual(social_media_store.collect_reporting_social_summaries([ADMIN], "2026-11-22"), {})


class CollaborationTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeCommunity(ADMIN)
        self.store = Mock()
        self.creator = dict(assess_creator(self.api.discover("fixture")), state="discovered")
        self.store.claim_invitation.return_value = dict(self.creator)

    def test_no_inbound_no_send_and_no_claim(self):
        with patch.object(collabs, "eligible_thread", return_value=None):
            self.assertEqual(collabs.invite(self.api, self.creator, store=self.store), "waiting_for_inbound")
        self.store.claim_invitation.assert_not_called()

    def test_duplicate_claim_is_never_sent(self):
        self.store.claim_invitation.return_value = False
        with patch.object(collabs, "eligible_thread", return_value="thread"), patch.object(self.api, "send") as send:
            self.assertEqual(collabs.invite(self.api, self.creator, store=self.store), "already_processed")
            send.assert_not_called()

    def test_timeout_marks_unknown_and_prevents_automatic_retries(self):
        self.store.claim_invitation.return_value = dict(self.creator)
        with patch.object(collabs, "eligible_thread", return_value="thread"), patch.object(self.api, "send", side_effect=CommunityError("timeout")):
            with self.assertRaises(CommunityError):
                collabs.invite(self.api, self.creator, store=self.store)
        self.store.finish_invitation.assert_called_once_with(ADMIN, "fixture", state="unknown")

    def test_success_is_recorded_only_after_send(self):
        with patch.object(collabs, "eligible_thread", return_value="thread"):
            self.assertEqual(collabs.invite(self.api, self.creator, store=self.store), "sent")
        self.store.finish_invitation.assert_called_once_with(ADMIN, "fixture", state="sent", message_id="sent")

    def test_automation_requires_both_runtime_and_saved_opt_in(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(CommunityError, "disabled"):
                collabs.run_automation(self.api, store=self.store)
        self.store.list_creators.assert_not_called()


class CommunityUiTests(unittest.TestCase):
    SCRIPT = """import social_media_page
from tests.community_fixtures import ADMIN, FakeCommunity, FakeStore
social_media_page.render_page(ADMIN, api_factory=FakeCommunity, store=FakeStore)
"""

    def setUp(self):
        FakeStore.rows = []
        FakeStore.enabled = False
        EVENTS.clear()

    def app(self):
        return AppTest.from_string(self.SCRIPT).run()

    def button(self, app, text):
        return next(b for b in app.button if b.label == text)

    def test_replacement_tabs_and_instagram_only_shortcut(self):
        app = self.app()
        self.assertFalse(app.exception)
        self.assertEqual(app.segmented_control[0].options, ["Inbox", "Comments", "Collaborations", "Connection"])
        rendered = "\n".join(m.value for m in app.markdown)
        self.assertIn("instagram.com/sportscaveshop/", rendered)
        for old in ("Playbook", "Post Tracker", "AI Reels", "Tracking view"):
            self.assertNotIn(old, rendered)

    def test_reply_sent_to_selected_conversation(self):
        app = self.app()
        app.text_area[0].set_value("Yes, we deliver to Sydney.")
        self.button(app, "Send reply").click().run()
        self.assertFalse(app.exception)
        self.assertIn(("send", "Facebook", "thread", "Yes, we deliver to Sydney."), EVENTS)
        self.assertTrue(any("Reply sent" in s.value for s in app.success))

    def test_comment_delete_requires_explicit_checkbox(self):
        app = self.app()
        app.segmented_control[0].set_value("Comments").run()
        self.assertFalse(app.exception)
        self.assertTrue(self.button(app, "Delete comment").disabled)
        app.checkbox[0].check().run()
        self.button(app, "Delete comment").click().run()
        self.assertFalse(app.exception)
        self.assertIn(("delete", "Facebook", "comment", ""), EVENTS)

    def test_instagram_hides_unavailable_like_actions(self):
        app = self.app()
        app.segmented_control[0].set_value("Comments").run()
        app.radio[0].set_value("Instagram").run()
        self.assertFalse(app.exception)
        self.assertNotIn("Like", [b.label for b in app.button])
        self.assertIn("Hide", [b.label for b in app.button])

    def test_discovery_saves_ranked_prospect_and_draft(self):
        app = self.app()
        app.segmented_control[0].set_value("Collaborations").run()
        self.button(app, "Discover and assess creators").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(FakeStore.rows[0]["username"], "fixture")
        self.assertTrue(FakeStore.rows[0]["fit"])
        self.assertIn("Sports Cave Edition", FakeStore.rows[0]["draft"])

    def test_denied_ui_never_constructs_api(self):
        script = """import social_media_page
def forbidden(user):
    raise AssertionError('Unauthorized API constructed')
social_media_page.render_page({'role':'worker','is_active':True}, api_factory=forbidden)
"""
        app = AppTest.from_string(script).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "Access not approved")


if __name__ == "__main__":
    unittest.main()
