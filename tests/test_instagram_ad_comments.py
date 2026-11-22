"""Offline contracts for ad comments whose ordinary media node is unavailable."""
from unittest.mock import Mock, patch

import pytest

from meta_social import CommunityError, MetaCommunity
from tests.community_fixtures import ADMIN
from tests.test_meta_social import ENV, response
from tests.community_fixtures import FakeCommunity
from social_community_feed import CommunityFeed


def client():
    http = Mock()
    return MetaCommunity(dict(ADMIN), env=dict(ENV, META_AD_ACCOUNT_ID="123",
                         META_ACCESS_TOKEN="fixture-ads-token"), session=http), http


def ad(media="media", actor="ig", account="123"):
    return {"id": "ad1", "account_id": account, "creative": {
        "effective_object_story_id": "page_1", "instagram_user_id": actor,
        "effective_instagram_media_id": media}}


def test_three_ad_media_read_comments_without_requiring_unavailable_metadata():
    api, http = client()
    ads = [dict(ad("media" + str(i)), id="ad" + str(i)) for i in range(3)]
    http.request.side_effect = [response({"data": ads}),
        response({"id": "page_1", "from": {"id": "page"}}),
        *[response({"data": [{"id": "comment" + str(i), "text": "Question"}]}) for i in range(3)]]
    result = api.ad_comment_feed()
    instagram = [p for p in result["data"] if p["platform"] == "Instagram"]
    assert len(instagram) == 3
    assert not result["errors"]
    assert {p["ad_id"] for p in instagram} == {"ad0", "ad1", "ad2"}
    for call in http.request.call_args_list[2:]:
        assert call.args[1].endswith("/ordered_comments")
        assert call.kwargs["headers"]["Authorization"] == "Bearer fixture-ads-token"


def test_reply_to_other_placement_comment_verifies_ad_account_and_membership():
    api, http = client()
    http.request.side_effect = [response(ad()), response({"data": [{"id": "placement-comment"}]}),
                                 response({"id": "reply"})]
    api.moderate("Instagram", "media", "placement-comment", "reply", "Thanks", ad_id="ad1")
    calls = http.request.call_args_list
    assert calls[0].args[1].endswith("/ad1")
    assert calls[1].args[1].endswith("/media/ordered_comments")
    assert calls[-1].args[1].endswith("/placement-comment/replies")
    assert calls[-1].kwargs["json"] == {"message": "Thanks"}
    assert calls[-1].kwargs["headers"]["Authorization"] == "Bearer fixture-ads-token"
    assert sum(c.args[0] == "POST" for c in calls) == 1


@pytest.mark.parametrize("foreign", [ad(actor="foreign"), ad(account="456"), ad(media="other-media")])
def test_untrusted_ad_context_cannot_authorize_foreign_media(foreign):
    api, http = client()
    http.request.return_value = response(foreign)
    with pytest.raises(CommunityError, match="does not belong"):
        api.moderate("Instagram", "media", "comment", "reply", "Thanks", ad_id="ad1")
    assert http.request.call_count == 1
    assert http.request.call_args.args[0] == "GET"


def test_non_member_comment_cannot_be_replied_to():
    api, http = client()
    http.request.side_effect = [response(ad()), response({"data": [{"id": "other"}]})]
    with pytest.raises(CommunityError, match="could not be verified"):
        api.moderate("Instagram", "media", "comment", "reply", "Thanks", ad_id="ad1")
    assert all(c.args[0] == "GET" for c in http.request.call_args_list)


def test_story_fallback_retains_its_own_edge_for_pagination_and_reply():
    api, http = client()
    cursor = "opaque" * 240
    http.request.side_effect = [response(ad()), response({"error": {"code": 100}}, 400),
        response({"data": [{"id": "c"}], "paging": {"next": "unused", "cursors": {"after": cursor}}}),
        response(ad()), response({"data": [{"id": "next"}]})]
    first = api.comments("Instagram", "media", ad_id="ad1")
    assert first["comment_edge"] == "comments"
    api.comments("Instagram", "media", ad_id="ad1", after=first["after"], comment_edge=first["comment_edge"])
    assert http.request.call_args.args[1].endswith("/media/comments")
    assert http.request.call_args.kwargs["params"]["after"] == cursor


def test_ordered_pagination_failure_never_reuses_cursor_on_another_edge():
    api, http = client()
    http.request.side_effect = [response(ad()), response({"error": {"code": 100}}, 400)]
    with pytest.raises(CommunityError):
        api.comments("Instagram", "media", ad_id="ad1", after="ordered-cursor")
    assert http.request.call_count == 2


def test_failed_reply_is_not_retried():
    api, http = client()
    http.request.side_effect = [response(ad()), response({"data": [{"id": "c"}]}),
                                 response({"error": {"code": 200}}, 400)]
    with pytest.raises(CommunityError):
        api.moderate("Instagram", "media", "c", "reply", "Thanks", ad_id="ad1")
    assert sum(c.args[0] == "POST" for c in http.request.call_args_list) == 1


def test_boosted_post_retains_ad_comments_and_context_when_organic_post_is_loaded():
    api = FakeCommunity(dict(ADMIN))
    post = {"id": "post", "platform": "Instagram", "advertising": True, "ad_id": "ad1",
            "comments": {"data": [{"id": "ad-comment", "text": "Ad question"}], "after": "ad-cursor"}}
    feed = CommunityFeed(api, {})
    with patch.object(api, "ad_comment_feed", create=True, return_value={"data": [post], "after": ""}), \
            patch.object(api, "comments", wraps=api.comments) as read:
        first = feed.comments()
        row = next(r for r in first["items"] if r["id"] == "ad-comment")
        assert row["post"]["ad_id"] == "ad1"
        feed.more_comments(first)
        feed.comments()
        read.assert_called_with("Instagram", "post", after="ad-cursor", ad_id="ad1", comment_edge="")


def test_page_token_recovers_ad_comments_and_reply_uses_that_same_token():
    api, http = client()
    unavailable = response({"error": {"code": 100, "error_subcode": 33}}, 400)
    http.request.side_effect = [response(ad()), unavailable, unavailable,
        response({"data": [{"id": "c"}]}), response({"id": "reply"})]
    api.moderate("Instagram", "media", "c", "reply", "Thanks", ad_id="ad1")
    calls = http.request.call_args_list
    assert calls[-2].kwargs["headers"]["Authorization"] == "Bearer fixture-page-token"
    assert calls[-1].kwargs["headers"]["Authorization"] == "Bearer fixture-page-token"
    assert calls[-1].args[1].endswith("/c/replies")
    assert sum(c.args[0] == "POST" for c in calls) == 1


def test_boosted_original_media_recovers_when_effective_ad_media_is_unavailable():
    api, http = client()
    creative = ad()["creative"]
    creative["source_instagram_media_id"] = "source-media"
    unavailable = response({"error": {"code": 100, "error_subcode": 33}}, 400)
    http.request.side_effect = [response({"data": [{"id": "ad1", "creative": creative}]}),
        response({"id": "page_1", "from": {"id": "page"}}), unavailable, unavailable, unavailable,
        response({"data": [{"id": "boosted-comment"}]})]
    result = api.ad_comment_feed()
    recovered = next(p for p in result["data"] if p["platform"] == "Instagram")
    assert recovered["id"] == "source-media"
    assert recovered["ad_id"] == "ad1"
    assert not result["errors"]
    assert recovered["comments"]["data"][0]["id"] == "boosted-comment"


def test_original_media_reply_requires_the_source_id_to_be_on_the_verified_ad():
    api, http = client()
    verified = ad()
    verified["creative"]["source_instagram_media_id"] = "source-media"
    http.request.side_effect = [response(verified), response({"data": [{"id": "c"}]}), response({"id": "reply"})]
    api.moderate("Instagram", "source-media", "c", "reply", "Thanks", ad_id="ad1")
    assert http.request.call_args_list[1].args[1].endswith("/source-media/ordered_comments")
    assert http.request.call_args.args[1].endswith("/c/replies")
