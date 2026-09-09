import copy
import csv
import io
from decimal import Decimal
import unittest
from unittest.mock import patch, MagicMock

from streamlit.testing.v1 import AppTest
import ads_page as ads
import ads_posting_page as posting
import ads_posting_handoff as handoff
import ads_refresh_winners as winners
import ads_target_relevance as relevance
import supabase_backend as backend
from posting_import_csv import parse_posting_import_csv
from tests.test_ads_posting_handoff import completed_ad, save_locally
from tests.test_posting_import_csv import product_records


class WinnerRefinementTests(unittest.TestCase):
    def test_prompt_single_pair_and_winner_style_contract(self):
        prompt = ads.build_ads_prompt(
            "Michael Jordan", "NBA", "USA", "Instant Experience",
            product_url="https://sportscave.com.au/products/jordan",
            creative_refresh_context={"winning_primary_text": "The night Chicago believed.", "winning_headline": "Own the memory"},
        )
        for value in ("The night Chicago believed.", "Own the memory", "controlled sibling evolutions", "exactly ONE Primary Text", "ONE Headline", "winner_refinement", "Michael Jordan", "NBA", "1024 x 1024"):
            self.assertIn(value, prompt)
        for value in ("Scene Expansion", "Pattern Interrupt", "Description 2", "Description 3", "genuinely different customer's home"):
            self.assertNotIn(value, prompt)

    def test_legacy_normalization_does_not_rewrite_saved_source(self):
        result, workflow = completed_ad("Instant Experience", "creative_refresh")
        original = copy.deepcopy(workflow)
        legacy_result = {**result, "workflow_mode": "new_ads"}
        with patch.object(ads.st, "session_state", {}):
            old_csv = ads.build_instant_experience_copy_csv(legacy_result, copy.deepcopy(workflow))
            state = {ads._instant_experience_copy_widget_key(result["context_key"], ads.INSTANT_EXPERIENCE_CONCEPTS[0]["id"], "primary_text", 2): "stale option"}
            with patch.object(ads.st, "session_state", state):
                ads.apply_instant_experience_copy_csv(result, workflow, old_csv)
                self.assertFalse(any(key.endswith("::2") for key in state))
                new_csv = ads.build_instant_experience_copy_csv(result, workflow)
        self.assertEqual(len(list(csv.DictReader(io.StringIO(old_csv.decode("utf-8-sig"))))), 9)
        self.assertEqual(len(list(csv.DictReader(io.StringIO(new_csv.decode("utf-8-sig"))))), 3)
        for concept in ads.INSTANT_EXPERIENCE_CONCEPTS:
            pair = workflow["ad_notes"]["instant_experience_concepts"][concept["id"]]
            self.assertEqual(len(pair), 1)
            self.assertEqual(pair[0]["primary_text"], original["ad_notes"]["instant_experience_concepts"][concept["id"]][0]["primary_text"])

    def test_saved_refresh_pairs_hydrate_once_with_exact_assets_and_context(self):
        result, workflow = completed_ad("Instant Experience", "creative_refresh")
        self.assertNotIn(handoff.SAVED_PACKAGE_KEY, workflow)
        uploaded = save_locally(result, workflow)
        package = workflow[handoff.SAVED_PACKAGE_KEY]
        self.assertEqual(package["source"], "Creative Refresh")
        state = {posting.PRIMARY_TEXT_KEYS[0]: "stale", posting.HEADLINE_KEYS[1]: "stale", posting.CAROUSEL_PRIMARY_TEXT_KEYS[0]: "stale carousel"}
        with patch.object(posting.MetaPostingService, "create_paused_campaign", side_effect=AssertionError("No Meta writes")):
            handoff.queue_saved_package(package, state=state)
            self.assertTrue(posting.consume_saved_posting_package(product_records(), state=state))
            for index, (ad, asset) in enumerate(zip(package["batch"]["ads"], package["assets"])):
                self.assertEqual(len(ad["variations"]), 1)
                self.assertEqual(state[posting.PRIMARY_TEXT_KEYS[index]], ad["primary_text"])
                self.assertEqual(state[posting.HEADLINE_KEYS[index]], ad["headline"])
                self.assertEqual(state[posting.IMAGE_STATE_KEYS[index]]["data"], uploaded[asset["path"]])
            self.assertNotIn(posting.CAROUSEL_PRIMARY_TEXT_KEYS[0], state)
            self.assertEqual(state[posting.SPORT_KEY], package["batch"]["sport_category"])
            self.assertEqual(state[posting.COUNTRY_KEY], package["batch"]["country"])
            self.assertTrue(package["batch"]["product_handle"])
            state[posting.PRIMARY_TEXT_KEYS[0]] = "manual after handoff"
            self.assertFalse(posting.consume_saved_posting_package(product_records(), state=state))
            self.assertEqual(state[posting.PRIMARY_TEXT_KEYS[0]], "manual after handoff")

    def test_partial_save_never_enables_post_now(self):
        result, workflow = completed_ad("Instant Experience", "creative_refresh")
        save_locally(result, workflow, fail=".png")
        self.assertNotIn(handoff.SAVED_PACKAGE_KEY, workflow)

    def test_refinement_csv_rejects_extra_rows_without_legacy_recursion(self):
        result, workflow = completed_ad("Instant Experience", "creative_refresh")
        with patch.object(ads.st, "session_state", {}):
            data = ads.build_instant_experience_copy_csv(result, workflow)
        rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows * 3)
        with self.assertRaisesRegex(ValueError, "Expected 3"):
            parse_posting_import_csv(buffer.getvalue().encode())

    def test_single_copy_ui_and_no_stale_options(self):
        source = '''
import streamlit as st
from unittest.mock import patch
import ads_page as ads
from tests.test_ads_posting_handoff import completed_ad
result, workflow = completed_ad("Instant Experience", "creative_refresh")
with patch.object(ads, "_render_instant_experience_copy_csv_control"):
    ads._render_instant_experience_concepts(result, workflow)
'''
        app = AppTest.from_string(source).run(timeout=20)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.file_uploader), 3)
        self.assertEqual(sum(item.label == "Primary Text / Description" for item in app.text_area), 3)
        self.assertEqual(sum(item.label == "Headline" for item in app.text_area), 3)
        self.assertFalse(any("Description 2" in item.value or "Description 3" in item.value for item in app.markdown))


class WinnerHistoryTests(unittest.TestCase):
    def test_campaign_picker_defaults_to_best_and_allows_editing_and_switching(self):
        source = '''
import streamlit as st
from unittest.mock import patch
import ads_page as ads
import ads_refresh_winners as winners
def candidates(campaign):
    return winners.rank_winner_candidates([
        {"ad_id": campaign+"-a", "campaign_id": campaign, "primary_text": campaign+" first", "headline": "first", "spend": 10, "purchase_value": 20},
        {"ad_id": campaign+"-b", "campaign_id": campaign, "primary_text": campaign+" best", "headline": "best", "spend": 1, "purchase_value": 8},
    ])
with patch.object(ads, "_load_refresh_campaigns", return_value=[{"campaign_id": "c1", "campaign_name": "NBA Previous"}, {"campaign_id": "c2", "campaign_name": "Cricket Previous"}]), patch.object(ads, "_load_refresh_winners", side_effect=candidates):
    ads._render_refresh_winner_picker()
st.text_area("Winning Primary Text", key=ads.ADS_CREATIVE_REFRESH_WINNING_PRIMARY_TEXT_KEY)
st.text_input("Winning Headline", key=ads.ADS_CREATIVE_REFRESH_WINNING_HEADLINE_KEY)
'''
        app = AppTest.from_string(source).run()
        self.assertEqual(len(app.exception), 0)
        app.selectbox[0].select("c1").run()
        self.assertEqual(app.text_area[0].value, "c1 best")
        self.assertIn("8.00x", app.selectbox[1].options[0])
        app.text_area[0].set_value("manual edit").run()
        self.assertEqual(app.text_area[0].value, "manual edit")
        app.selectbox[1].select("c1-a").run()
        self.assertEqual(app.text_area[0].value, "c1 first")
        app.selectbox[0].select("c2").run()
        self.assertEqual(app.text_area[0].value, "c2 best")
        self.assertEqual(len(app.exception), 0)

    def test_roas_is_ratio_of_sums_not_average_of_daily_ratios(self):
        value = winners.aggregate_ad_roas([
            {"spend": 10, "purchase_value": 100, "roas": 10},
            {"spend": 90, "purchase_value": 90, "roas": 1},
        ])
        self.assertEqual(value, {"spend": Decimal(100), "purchase_value": Decimal(190), "roas": Decimal("1.9")})

    def test_missing_zero_and_nonfinite_metrics_are_not_invented(self):
        for row in ({"spend": 0, "purchase_value": 0}, {"spend": 10}, {"spend": "nan", "purchase_value": 10}, {"purchase_value": 20}):
            self.assertIsNone(winners.aggregate_ad_roas([row])["roas"])
        self.assertEqual(winners.aggregate_ad_roas([{"spend": 10, "purchase_value": 0}])["roas"], 0)

    def test_best_selection_switch_and_manual_edit_persistence(self):
        rows = winners.rank_winner_candidates([
            {"ad_id": "a", "campaign_id": "c", "primary_text": "first", "headline": "a", "spend": 10, "purchase_value": 20},
            {"ad_id": "b", "campaign_id": "c", "primary_text": "best", "headline": "b", "spend": 1, "purchase_value": 8},
            {"ad_id": "unknown", "primary_text": "unknown", "headline": "unknown"},
            {"ad_id": "no copy", "spend": 1, "purchase_value": 100},
        ])
        self.assertEqual([row["ad_id"] for row in rows], ["b", "a", "unknown"])
        state = {}
        kwargs = dict(state=state, identity_key="winner", primary_key="text", headline_key="headline")
        self.assertTrue(winners.apply_winner_selection(rows[0], **kwargs))
        self.assertEqual(state["text"], "best")
        state["text"] = "manual edit"
        self.assertFalse(winners.apply_winner_selection(rows[0], **kwargs))
        self.assertEqual(state["text"], "manual edit")
        winners.apply_winner_selection(rows[1], **kwargs)
        self.assertEqual(state["text"], "first")
        winners.apply_winner_selection(None, **kwargs)
        self.assertEqual(state["text"], "first")

    def test_synced_history_queries_are_parameterized_read_only(self):
        connection = MagicMock()
        cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = []
        with patch.object(backend, "is_configured", return_value=True), patch.object(backend, "connect", return_value=connection):
            backend.list_creative_refresh_campaigns()
            backend.list_creative_refresh_winner_candidates("campaign-id")
        for call in cursor.execute.call_args_list:
            sql = call.args[0].upper()
            self.assertNotIn("INSERT", sql)
            self.assertNotIn("UPDATE", sql)
        sql, params = cursor.execute.call_args.args
        self.assertIn("SUM(purchase_value)", sql)
        self.assertIn("SUM(spend)", sql)
        self.assertNotIn("LIMIT", sql)
        self.assertEqual(params, ("campaign-id", "campaign-id"))

    def test_picker_unavailable_does_not_touch_manual_fields(self):
        state = {ads.ADS_CREATIVE_REFRESH_WINNING_PRIMARY_TEXT_KEY: "manual"}
        with patch.object(ads.st, "session_state", state), patch.object(ads, "_load_refresh_campaigns", side_effect=RuntimeError("secret")), patch.object(ads.st, "info") as info:
            ads._render_refresh_winner_picker()
        self.assertEqual(state[ads.ADS_CREATIVE_REFRESH_WINNING_PRIMARY_TEXT_KEY], "manual")
        self.assertNotIn("secret", str(info.call_args))


class TargetRelevanceTests(unittest.TestCase):
    def test_show_more_reruns_preserve_dropdown_id(self):
        source = '''
import streamlit as st
import ads_posting_page as posting
rows = [{"id": "nba", "name": "NBA"}, {"id": "nfl", "name": "NFL"}, {"id": "cricket", "name": "Cricket"}]
st.session_state.setdefault(posting.PRODUCT_SET_KEY, "nfl")
visible = posting._relevant_target_options(rows, product_title="Michael Jordan", sport="NBA", key=posting.PRODUCT_SET_KEY)
st.selectbox("Product set", visible, key=posting.PRODUCT_SET_KEY)
'''
        app = AppTest.from_string(source).run()
        self.assertEqual(app.selectbox[0].value, "nfl")
        self.assertEqual(app.selectbox[0].options, ["nba", "nfl"])
        app.toggle[0].set_value(True).run()
        self.assertEqual(app.selectbox[0].options, ["nba", "nfl", "cricket"])
        self.assertEqual(app.selectbox[0].value, "nfl")
        app.toggle[0].set_value(False).run()
        self.assertEqual(app.selectbox[0].value, "nfl")
        self.assertEqual(len(app.exception), 0)

    def test_sports_athletes_all_matches_and_ranking(self):
        cases = [
            ("NFL Framed Wall Art", "NFL", ["NFL Buyers", "nfl catalogue", "NFL Legends"]),
            ("Michael Jordan Limited Edition", "NBA", ["NBA Legends", "Michael Jordan Buyers", "Jordan Retargeting", "Michael collectors"]),
            ("Shane Warne", "Cricket", ["Cricket Buyers", "Shane Fans", "Warne collectors"]),
        ]
        for title, sport, relevant in cases:
            rows = [{"id": str(i), "name": name} for i, name in enumerate(["All Products", "Motorsport", *relevant])]
            result = relevance.rank_relevant_meta_options(rows, product_title=title, sport=sport)
            self.assertEqual({row["name"] for row in result["options"]}, set(relevant))
            self.assertIn(sport.casefold(), result["options"][0]["name"].casefold())
            all_rows = relevance.rank_relevant_meta_options(rows, product_title=title, sport=sport, show_all=True)["options"]
            self.assertEqual({row["id"] for row in all_rows}, {row["id"] for row in rows})

    def test_stopwords_acronyms_punctuation_and_token_boundaries(self):
        for sport in ("NBA", "NFL", "NHL", "MLB", "NRL", "AFL", "UFC", "F1"):
            self.assertIn(sport.lower(), relevance.extract_relevance_terms("", sport)[0])
        self.assertFalse(relevance.rank_relevant_meta_options([{"id": "1", "name": "Wall Collection"}], product_title="Sports Cave framed art limited edition")["has_context"])
        rows = [{"id": "1", "name": "MICHAEL-JORDAN / NBA"}, {"id": "2", "name": "Jordanian buyers"}]
        result = relevance.rank_relevant_meta_options(rows, product_title="Michael Jordan", sport="Basketball")
        self.assertEqual([row["id"] for row in result["options"]], ["1"])
        self.assertEqual(relevance.tokens("F-1 Racing"), ("f1", "racing"))
        ranked = relevance.rank_relevant_meta_options(
            [{"id": "other", "name": "Other"}, {"id": "jordan", "name": "Jordan"}],
            product_title="Michael Jordan", sport="Other", show_all=True,
        )
        self.assertEqual([row["id"] for row in ranked["options"]], ["jordan", "other"])

    def test_existing_id_no_match_and_show_more(self):
        rows = [{"id": "nba", "name": "NBA"}, {"id": "nfl", "name": "NFL"}]
        ranked = relevance.rank_relevant_meta_options(rows, sport="NBA", selected="nfl")
        self.assertEqual([row["id"] for row in ranked["options"]], ["nba", "nfl"])
        empty = relevance.rank_relevant_meta_options(rows, sport="Cricket")
        self.assertEqual(empty["options"], [])
        expanded = relevance.rank_relevant_meta_options(rows, sport="Cricket", show_all=True)
        self.assertEqual(expanded["options"], rows)
        state = {posting.PRODUCT_SET_KEY: "nfl"}
        with patch.object(posting.st, "session_state", state):
            visible = posting._relevant_target_options(rows, product_title="", sport="NBA", key=posting.PRODUCT_SET_KEY)
        self.assertIn("nfl", visible)
        self.assertEqual(state[posting.PRODUCT_SET_KEY], "nfl")


if __name__ == "__main__":
    unittest.main()
