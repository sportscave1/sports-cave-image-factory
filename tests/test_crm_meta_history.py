"""Synthetic tests for direct, read-only Meta reporting."""
from datetime import date
from unittest.mock import Mock, patch

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

import chatgpt_crm_mcp as mcp
import crm_meta_history as history

DAY = date(2026, 11, 5)
CONFIG = {"configured": True, "ad_account_id": "act_123", "api_version": "v26.0", "access_token": "fixture"}
ACCOUNT = {"account_id": "123", "currency": "AUD", "timezone_name": "Australia/Sydney"}


def raw(ad_id):
    return {
        "account_id": "123", "ad_id": str(ad_id), "date_start": DAY.isoformat(), "date_stop": DAY.isoformat(),
        "spend": "20", "impressions": "100", "clicks": "4", "inline_link_clicks": "2",
        "actions": [{"action_type": "add_to_cart", "value": "2"},
                    {"action_type": "omni_add_to_cart", "value": "2"},
                    {"action_type": "post_engagement", "value": "10"},
                    {"action_type": "post_reaction", "value": "0"},
                    {"action_type": "like", "value": "3"}],
        "_review_creative": {"private": "excluded"},
    }


def test_live_reads_paginate_reuse_cache_and_force_refresh(monkeypatch):
    monkeypatch.setattr(history, "_cache", {})
    reader = Mock()
    reader.get.return_value = ACCOUNT
    reader.pages.return_value = [raw(n) for n in range(100, 123)]
    with patch.object(history.meta, "get_meta_config", return_value=CONFIG), \
            patch.object(history.live, "Reader", return_value=reader):
        args = {"since": DAY.isoformat(), "until": DAY.isoformat()}
        first = history.meta_ad_history(*history.meta_history_args(args))
        second = history.meta_ad_history(*history.meta_history_args({**args, "cursor": first["next_cursor"]}))
        reader.pages.assert_called_once()
        assert len(first["rows"]) == 20
        assert len(second["rows"]) == 3
        assert second["next_cursor"] is None
        assert first["captured_at"] == second["captured_at"]
        item = first["rows"][0]
        assert "_review_creative" not in item["meta_fields"]
        assert item["metrics"]["add_to_cart"] == 2
        assert item["metrics"]["engagement"] == 10
        assert item["metrics"]["reactions"] == 0
        assert item["metrics"]["likes"] == 3
        assert item["metrics"]["checkout"] is None
        assert item["metrics"]["click_ctr"] == 4
        assert item["metrics"]["cpc"] == 5
        history.meta_ad_history(*history.meta_history_args({**args, "refresh": True}))
        assert reader.pages.call_count == 2


def test_provider_field_fallback_and_wrong_account_rejection():
    reader = Mock()
    reader.get.return_value = ACCOUNT
    bad_field = "instagram_profile_follow"
    video = "video_play_actions"
    assert "unique_inline_link_click_ctr" in history.EXTRA_FIELDS
    assert "unique_inline_link_ctr" not in history.EXTRA_FIELDS
    error = history.meta.MetaAdsApiError(f"Tried accessing nonexisting field ({bad_field})", error_code=100)
    reader.pages.side_effect = [error, [raw(1)], [{**raw(1), video: [{"value": "25"}]}]]
    _, rows, _, coverage = history._fetch(CONFIG, DAY, DAY, reader)
    assert coverage["rejected"] == [bad_field]
    assert coverage["returned"] == [video]
    assert coverage["unverified"] == []
    assert history._report_row(rows[0][1])["metrics"][video] == 25
    assert reader.pages.call_args_list[1].args[1]["fields"] == history.CORE_FIELDS
    assert bad_field not in reader.pages.call_args.args[1]["fields"].split(",")
    reader.pages.side_effect = None
    reader.pages.return_value = [{**raw(1), "account_id": "999"}]
    with pytest.raises(ValueError, match="outside the requested account"):
        history._fetch(CONFIG, DAY, DAY, reader)


def test_generic_extra_error_keeps_video_and_bounds_probes(monkeypatch):
    reader = Mock()
    reader.get.return_value = ACCOUNT
    bad = history.meta.MetaAdsApiError("Invalid parameter", error_code=100)
    monkeypatch.setattr(history, "OPTIONAL_REQUEST_LIMIT", 2)
    reader.pages.side_effect = [bad, [raw(1)], [{**raw(1), "video_play_actions": [{"value": "9"}]}], bad]
    _, _, _, coverage = history._fetch(CONFIG, DAY, DAY, reader)
    assert coverage["returned"] == ["video_play_actions"]
    assert coverage["rejected"] == []
    assert "unique_clicks" in coverage["unverified"]
    assert reader.pages.call_count == 4


def test_paid_post_likes_use_reaction_breakdown_without_overwriting_page_likes():
    reader = Mock()
    reader.get.return_value = ACCOUNT
    row = raw(1)
    row["actions"] = [{"action_type": "post_reaction", "value": "5"},
                      {"action_type": "like", "value": "1"}]
    reader.pages.side_effect = [[row], [{**row, "actions": [
        {"action_type": "post_reaction", "action_reaction": "LIKE", "value": "3"},
        {"action_type": "post_reaction", "action_reaction": "LOVE", "value": "2"},
    ]}]]
    _, rows, _, coverage = history._fetch(CONFIG, DAY, DAY, reader)
    metrics = history._report_row(rows[0][1])["metrics"]
    assert coverage["paid_post_likes_breakdown"] == "accepted"
    assert metrics["reactions"] == 5
    assert metrics["page_likes"] == 1
    assert metrics["paid_post_likes"] == 3
    assert reader.pages.call_args.args[1]["action_breakdowns"] == "action_type,action_reaction"


def test_mcp_history_requires_its_own_scope_and_current_owner(monkeypatch):
    monkeypatch.setenv("SPORTS_CAVE_CHATGPT_CRM_MCP_SECRET", "s" * 45)
    client = TestClient(Starlette(routes=[Route(mcp.MCP_PATH, mcp.mcp, methods=["POST"])]))
    arguments = {"since": DAY.isoformat(), "until": DAY.isoformat()}

    def call(scope, args=arguments):
        bearer = mcp._seal(mcp._key(), "access", {
            "sub": "fixture", "version": "1", "scope": scope, "iss": mcp.ISSUER, "aud": mcp.RESOURCE,
        })
        return client.post(mcp.MCP_PATH, headers={"Authorization": f"Bearer {bearer}"}, json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": mcp.META_HISTORY_TOOL, "arguments": args},
        })

    with patch.object(mcp, "_active_owner", return_value=False) as owner, \
            patch.object(mcp, "meta_ad_history", return_value={"rows": []}) as read:
        assert call(mcp.META_SCOPE).json()["result"]["isError"]
        assert call(mcp.META_HISTORY_SCOPE).status_code == 401
        read.assert_not_called()
        owner.return_value = True
        assert call(mcp.META_HISTORY_SCOPE, {**arguments, "cursor": "malformed"}).json()["error"]["code"] == -32602
        assert call(mcp.META_HISTORY_SCOPE, {**arguments, "refresh": True}).json()["result"]["structuredContent"] == {"rows": []}
        assert owner.call_args.args[1] == "ads_meta_review"
        read.assert_called_once_with(DAY, DAY, None, True)
