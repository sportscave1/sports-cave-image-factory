"""Offline wall-palette contracts through the real Ads prompt builders."""
import csv
import io
import re

import pytest

import ads_page as ads
import ads_ie_scenes as scenes
import ads_ie_usa as usa
import ads_ie_visual_systems as visuals
import ads_refresh_plan as refresh


COLOURED_WALL = re.compile(r"\b(blue|navy|green|olive|red|burgundy|sage|moss|teal|terracotta)\b", re.I)
ARTWORK = {"artwork_colours": "blue, green and red", "edition_limit": 100}


def neutral(value):
    assert not COLOURED_WALL.search(value), value


def test_every_wall_choice_is_neutral_and_existing_finishes_remain_available():
    for wall in (*scenes.WALLS, *usa.WALLS):
        neutral(" ".join(wall[:4]))
    for wall in (*ads.carousel_winner.LIGHT_WALLS, *ads.carousel_winner.DARK_WALLS,
                 *ads.IE_ADVANCED_VISUAL_OPTION_SETS["wall_colour_family"]):
        neutral(wall)
    for tone, _ in ads.CAROUSEL_NOSTALGIC_WALL_TONES.values():
        neutral(tone)
    for _, _, _, palettes in visuals.FAN_STYLES.values():
        for palette in palettes:
            neutral(palette)
    for palettes in ads.INSTANT_EXPERIENCE_WALL_PALETTES_V4.values():
        for _, colour in palettes:
            neutral(colour)
    assert {wall[4] for wall in scenes.WALLS} == {
        "matte painted brick", "textured plaster", "concrete", "natural stone", "aged timber"}
    assert {"Limewash", "Mineral Plaster", "Pale Stone"} <= set(ads.IE_ADVANCED_VISUAL_OPTION_SETS["wall_material"])
    assert "warm sandstone plaster" in visuals.FAN_STYLES["cricket"][3]
    assert any("limewash" in wall for style in visuals.FAN_STYLES.values() for wall in style[3])


@pytest.mark.parametrize("country", ["Australia", "USA", "UK"])
def test_fresh_ie_packs_keep_neutral_variety_camera_roles_and_standalone_rules(country):
    observed = set()
    for seed in range(6):
        rows = ads.resolve_standard_instant_experience_visuals(
            product_name="Synthetic Collector Edition", category="NBA", country=country,
            product_metadata=ARTWORK, variation_token=f"neutral-walls-{seed}")
        assert len(rows) == 3
        assert rows[1]["camera_role"] == "FRONT"
        assert {rows[0]["camera_role"], rows[2]["camera_role"]} == {"RIGHT", "LEFT"}
        if country != "USA":
            assert [row["camera_role"] for row in rows] == ["RIGHT", "FRONT", "LEFT"]
        assert len({row["home_setting"] for row in rows}) == 3
        assert len({row["wall_finish"] for row in rows}) == 3
        assert len({row["wall_colour_family"] for row in rows}) == 3
        for index, row in enumerate(rows, 1):
            neutral(row["wall_colour"])
            observed.add(row["wall_colour"])
            brief = ads.build_standard_instant_experience_image_prompt(index, row,
                product_name="Synthetic Collector Edition", category="NBA", country=country)
            assert scenes.NEUTRAL_WALL_RULES in brief
            assert row["camera_side"] in brief
            assert "PRODUCT LOCK — ABSOLUTE" in brief
            assert "exactly two centred text baselines" in brief
    assert len(observed) >= 4


@pytest.mark.parametrize("campaign", ["Instant Experience", "Carousel", "Single Image / Video"])
@pytest.mark.parametrize("country", ["Australia", "USA", "UK"])
def test_public_new_ads_prompts_apply_wall_rule_without_recolouring_product(campaign, country):
    prompt = ads.build_ads_prompt("Synthetic Collector Edition", "NBA", country, campaign,
        product_metadata=ARTWORK, variation_token="neutral-wall-public")
    assert scenes.NEUTRAL_WALL_RULES in prompt
    assert "Keep the original artwork, frame and printed colours exact." in prompt
    assert "CSV" in prompt
    assert "Claim Your Edition" in prompt


def test_carousel_keeps_five_roles_and_room_variety_with_neutral_walls():
    observed = set()
    for category in ("Cricket", "Motorsport", "NBA", "Football"):
        for seed in range(8):
            rows = ads.resolve_carousel_visual_scenes("Synthetic Edition", category, "Australia",
                product_metadata=ARTWORK, variation_token=f"neutral-carousel-{seed}")
            assert [row["card"] for row in rows] == [1, 2, 3, 4, 5]
            assert rows[0]["room_family"] == "close_up_wall_hero"
            assert rows[3]["room_family"] == "sports_cave"
            assert len({row["room_family"] for row in rows[1:]}) == 4
            assert len({row["camera_family"] for row in rows[1:]}) == 4
            for row in rows:
                neutral(row["wall_family"])
                observed.add(row["wall_family"])
                assert scenes.NEUTRAL_WALL_RULES in ads.carousel_winner.scene_block(row, "test")
    assert len(observed) >= 10


def test_refresh_style_selection_retains_light_mid_dark_and_material_variety():
    for style in refresh.STYLES:
        neutral(style["wall_hue"])
    for seed in range(20):
        selected = refresh.select_styles(str(seed), category="NBA")
        assert {style["wall_value"] for style in selected} == {"light", "mid", "dark"}
        assert len({style["wall_material"] for style in selected}) == 3
        assert len({style["architecture"] for style in selected}) == 3


def test_new_refresh_keeps_room_type_and_three_csv_rows_with_neutral_wall_precedence():
    result = ads.build_ads_result_record("Synthetic Edition", "NBA", "USA", "Instant Experience",
        variation_token="neutral-refresh", product_metadata=ARTWORK,
        creative_refresh_context={"winning_primary_text": "A collector memory worth keeping.",
                                  "winning_headline": "Make It Yours"})
    prompt = result["master_prompt"]
    assert prompt.startswith(ads.ads_refresh_generation.plan.distinct.VERSION)
    assert scenes.NEUTRAL_WALL_RULES in prompt
    assert "source/reference wall colours in new images" in prompt
    assert "Keep the same observed room TYPE" in prompt
    assert "For EACH refresh change BOTH camera position" in prompt
    rows = list(csv.DictReader(io.StringIO(prompt.split("DO NOT RETURN A BLANK TEMPLATE\n", 1)[1])))
    assert len(rows) == 3
    assert tuple(rows[0]) == ads.INSTANT_EXPERIENCE_COPY_CSV_HEADERS
