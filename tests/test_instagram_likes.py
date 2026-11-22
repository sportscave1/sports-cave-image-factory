"""Official IG User /likes contract; synthetic credentials and provider responses."""
from unittest.mock import Mock, patch

import pytest
import requests
from streamlit.testing.v1 import AppTest

from meta_social import MetaCommunity, CommunityError
from tests import test_meta_social as contracts
from tests.community_fixtures import ADMIN, FakeCommunity, EVENTS

SCOPES = ["instagram_basic", "instagram_manage_engagement", "pages_read_user_content", "pages_show_list"]
VALID = {"is_valid": True, "type": "USER", "app_id": "app", "scopes": SCOPES}
PAGE = {"id": "page", "instagram_business_account": {"id": "ig"}}


def client(**overrides):
    http = Mock()
    settings = dict(contracts.ENV, META_SOCIAL_ACCESS_TOKEN="fixture-community", META_ACCESS_TOKEN="fixture-ads",
                    META_APP_ID="app", META_APP_SECRET="fixture")
    settings.update(overrides)
    api = MetaCommunity(dict(ADMIN), env=settings, session=http)
    api.comments = Mock(return_value={"data": [{"id": "comment"}], "after": ""})
    return api, http


@pytest.mark.parametrize("action,method", [("like", "POST"), ("unlike", "DELETE")])
def test_instagram_user_likes_endpoint_uses_dedicated_user_token_and_comment_id(action, method):
    api, http = client()
    http.request.side_effect = [contracts.response(PAGE), contracts.response({"success": True})]
    with patch("meta_ads_client.fetch_meta_token_debug", return_value=VALID):
        api.moderate("Instagram", "post", "comment", action, ad_id="ad", comment_edge="comments")
    call = http.request.call_args
    assert call.args[:2] == (method, "https://graph.facebook.com/v27.0/ig/likes")
    assert call.kwargs["json"] == {"comment_id": "comment"}
    assert call.kwargs["headers"]["Authorization"] == "Bearer fixture-community"
    assert api.comments.call_args.kwargs == {"after": "", "ad_id": "ad", "comment_edge": "comments"}
    assert sum(c.args[0] != "GET" for c in http.request.call_args_list) == 1
    assert api._token == "fixture-page-token"
    assert api.version == "v26.0"


def test_no_dedicated_token_does_not_fall_back_to_page_or_ads_token():
    api, http = client(META_SOCIAL_ACCESS_TOKEN="")
    with pytest.raises(CommunityError, match="Community User token"):
        api.moderate("Instagram", "post", "comment", "like")
    http.request.assert_not_called()
    api.comments.assert_not_called()


@pytest.mark.parametrize("metadata", [dict(VALID, type="PAGE"), dict(VALID, type="SYSTEM_USER"),
    dict(VALID, app_id="another-app"), dict(VALID, is_valid=False), dict(VALID, scopes=["instagram_basic"]), None])
def test_unverified_or_insufficient_user_tokens_cannot_like(metadata):
    api, http = client()
    with patch("meta_ads_client.fetch_meta_token_debug", return_value=metadata), pytest.raises(CommunityError):
        api.moderate("Instagram", "post", "comment", "like")
    http.request.assert_not_called()
    api.comments.assert_not_called()


def test_wrong_linked_instagram_account_is_rejected_before_membership_or_write():
    api, http = client()
    http.request.return_value = contracts.response(dict(PAGE, instagram_business_account={"id": "foreign"}))
    with patch("meta_ads_client.fetch_meta_token_debug", return_value=VALID), pytest.raises(CommunityError, match="does not match"):
        api.moderate("Instagram", "post", "comment", "like")
    assert http.request.call_count == 1
    api.comments.assert_not_called()


def test_foreign_comment_is_rejected_even_with_valid_like_permission():
    api, http = client()
    api.comments.return_value = {"data": [{"id": "another-comment"}], "after": ""}
    http.request.return_value = contracts.response(PAGE)
    with patch("meta_ads_client.fetch_meta_token_debug", return_value=VALID), pytest.raises(CommunityError, match="could not be verified"):
        api.moderate("Instagram", "post", "comment", "like")
    assert all(c.args[0] == "GET" for c in http.request.call_args_list)


def test_readonly_mode_never_inspects_or_writes_a_like():
    api, http = client(META_SOCIAL_WRITES_ENABLED="0")
    with patch("meta_ads_client.fetch_meta_token_debug") as inspect, pytest.raises(CommunityError, match="disabled"):
        api.moderate("Instagram", "post", "comment", "like")
    inspect.assert_not_called()
    http.request.assert_not_called()


def test_like_timeout_is_not_retried_or_claimed_successful():
    api, http = client()
    http.request.side_effect = [contracts.response(PAGE), requests.Timeout("private provider text")]
    with patch("meta_ads_client.fetch_meta_token_debug", return_value=VALID), pytest.raises(CommunityError, match="may have succeeded"):
        api.moderate("Instagram", "post", "comment", "like")
    assert http.request.call_count == 2


def test_burst_guard_is_shared_between_clients_and_stays_below_meta_limit():
    api, http = client()
    http.request.side_effect = lambda method, *a, **k: contracts.response(PAGE if method == "GET" else {"success": True})
    with patch("meta_social._like_windows", {}), patch("meta_social.time.monotonic", return_value=100), \
            patch("meta_ads_client.fetch_meta_token_debug", return_value=VALID):
        for _ in range(20):
            api.moderate("Instagram", "post", "comment", "like")
        another, transport = client()
        transport.request.return_value = contracts.response(PAGE)
        with pytest.raises(CommunityError, match="wait a few seconds"):
            another.moderate("Instagram", "post", "comment", "unlike")
        assert all(c.args[0] == "GET" for c in transport.request.call_args_list)


def test_facebook_likes_keep_original_page_token_and_version():
    api, http = client()
    http.request.return_value = contracts.response({"success": True})
    api.moderate("Facebook", "post", "comment", "like")
    call = http.request.call_args
    assert call.args[1] == "https://graph.facebook.com/v26.0/comment/likes"
    assert call.kwargs["headers"]["Authorization"] == "Bearer fixture-page-token"


def test_enabled_instagram_like_and_unlike_buttons_dispatch_directly_in_workspace():
    EVENTS.clear()
    with patch.object(FakeCommunity, "instagram_like_status", return_value={"available": True, "reason": "Authorized"}, create=True):
        app = AppTest.from_string(contracts.CommunityUiTests.SCRIPT).run()
        app.segmented_control[0].set_value("Comments").run()
        assert not app.button(key="like-Instagram-comment").disabled
        app.button(key="like-Instagram-comment").click().run()
        app.button(key="unlike-Instagram-comment").click().run()
    assert not app.exception
    assert ("like", "Instagram", "comment", "") in EVENTS
    assert ("unlike", "Instagram", "comment", "") in EVENTS
