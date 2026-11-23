"""Offline scope and workflow preservation for the prompt-only language update."""
import copy
import pytest
from unittest.mock import patch
import ads_page as ads
import ads_prompt_language as language
import ads_ie_copy as writing
from tests.test_ads_copy_optimisation import completed_ad, payload


@pytest.mark.parametrize("market,format,expected", [
    ("Australia", "Instant Experience", True), ("AU", "Instant Experience", True),
    ("USA", "Instant Experience", False), ("UK", "Instant Experience", False),
    ("Australia", "Carousel", False), ("Australia", "Single Image / Video", False)])
def test_market_and_format_scope(market, format, expected):
    prompt = ads.build_ads_prompt("Synthetic Sporting Edition", "NBA", market, format,
                                  variation_token="language-scope")
    assert (language.AU_COPY in prompt) is expected
    assert prompt.count(language.CONTINUITY) == 1


def test_australian_templates_remove_explicit_name_slots_and_conflicting_instruction():
    au = writing.instructions("Synthetic Athlete — Golden Era Edition", "NBA", "Australia", "s", {})
    us = writing.instructions("Synthetic Athlete — Golden Era Edition", "NBA", "USA", "s", {})
    assert "[SUBJECT / ATHLETE / TEAM]" not in au
    assert "[ATHLETE / TEAM / MOMENT]" not in au
    assert "[PRODUCT / SUBJECT / MOMENT]" not in au
    assert "Empty ATHLETE_NAMES does not erase a name" not in au
    assert "[SUBJECT / ATHLETE / TEAM]" in us
    assert language.AU_COPY not in us
    assert "never automatic labels" in au
    assert "If uncertain, omit the nickname" in au


@pytest.mark.parametrize("market", ["Australia", "USA"])
def test_refresh_keeps_header_and_exact_csv_at_end(market):
    kwargs = dict(product_name="Synthetic Sporting Edition", category="NBA", country=market,
        campaign_type="Instant Experience", variation_token="language-refresh",
        creative_refresh_context={"winning_primary_text":"Synthetic winning collector text",
                                  "winning_headline":"Synthetic winning headline"})
    result = ads.build_ads_result_record(**kwargs)
    prompt = result["master_prompt"]
    assert (language.AU_COPY in prompt) is (market == "Australia")
    assert prompt.startswith(ads.ads_refresh_generation.plan.distinct.VERSION)
    import csv, io
    rows = list(csv.DictReader(io.StringIO(prompt.split("DO NOT RETURN A BLANK TEMPLATE\n")[1])))
    assert len(rows) == 3
    assert tuple(rows[0]) == ads.INSTANT_EXPERIENCE_COPY_CSV_HEADERS


def test_copy_optimisation_is_scoped_and_keeps_saved_data_and_csv():
    for market in ("Australia", "USA"):
        result, workflow = completed_ad("Instant Experience")
        result["country"] = market
        before = copy.deepcopy((result, workflow))
        with patch.object(ads.st, "session_state", {}):
            prompt = ads.build_final_ad_review_copy_prompt(result, workflow)
            _, data = payload(prompt)
            assert data == ads.build_instant_experience_copy_csv(result, copy.deepcopy(workflow))
        assert (language.AU_COPY in prompt) is (market == "Australia")
        assert (result, workflow) == before


def test_google_gets_continuity_without_australian_ie_copy_rule():
    prompt = ads.google_ads.build_google_prompt("Synthetic Edition", "NBA", "Australia", "https://example.com/products/test")
    assert language.CONTINUITY in prompt
    assert language.AU_COPY not in prompt


def test_rules_leave_prompt_body_and_csv_untouched_and_are_idempotent():
    original = "VERSION\noriginal image workflow\nCSV\na,b\n1,2\n"
    updated = language.apply(original, "Australia", "Instant Experience")
    assert updated.startswith("VERSION\n")
    assert updated.endswith(original.split("\n", 1)[1])
    assert language.apply(updated, "Australia", "Instant Experience") == updated
