import hashlib
import json
from pathlib import Path
import unittest

import ads_page
import ads_carousel_winner as winner
from tests.test_ads_page import carousel_prompt_card_sections, visual_contract


def prompt(metadata=None, category="Cricket", token="winner-test", name="Shane Warne Wall Art"):
    return ads_page.build_ads_prompt(name, category, "Australia", "Carousel",
                                     product_metadata=metadata, variation_token=token)


def preferences(text):
    return json.loads(text.split("VERIFIED CAROUSEL COPY PREFERENCES\n", 1)[1].splitlines()[0])


class CarouselWinnerSystemTests(unittest.TestCase):
    def test_preferred_winner_fields_are_verified_and_fit_python_length(self):
        fields = preferences(prompt({"edition_limit": 100, "is_numbered": True, "athlete_names": ["Shane Warne"]}))
        self.assertEqual(fields, {"card_1_headline": "Shane Warne", "card_1_description": "Limited Edition",
                                  "card_4_headline": "For The Cave", "card_5_headline": "Only 100 Made",
                                  "card_5_description": "Numbered Run"})
        for value in fields.values():
            self.assertLessEqual(len(value), 17)
            self.assertNotRegex(value, r"[,.]")

    def test_numbering_requires_explicit_evidence_not_quantity_or_truthy_string(self):
        for numbered in (None, False, "false", "no"):
            fields = preferences(prompt({"edition_limit": 100, "is_numbered": numbered}))
            self.assertEqual(fields["card_5_description"], "Collector Run")
            self.assertNotEqual(fields["card_5_description"], "Numbered Run")

    def test_unknown_edition_never_defaults_to_100_even_for_baseball(self):
        for category in ("Baseball", "Cricket", "Other"):
            fields = preferences(prompt({}, category=category))
            self.assertIsNone(fields["card_1_description"])
            self.assertIsNone(fields["card_5_headline"])
            self.assertIsNone(fields["card_5_description"])

    def test_limited_status_without_quantity_and_oversize_quantity(self):
        fields = preferences(prompt({"is_limited_edition": True}))
        self.assertEqual(fields["card_1_description"], "Limited Edition")
        self.assertEqual(fields["card_5_headline"], "Limited Release")
        fields = winner.preferred_copy("Verified Identity", {}, 123456789, True, False)
        self.assertEqual(fields["card_5_headline"], "Limited Release")
        self.assertIsNone(winner.preferred_copy("A Very Long Recognisable Product Title Wall Art", {}, None, False, False)["card_1_headline"])

    def test_title_identity_and_paired_identity_without_truncated_words(self):
        for title in ("Shane Warne Wall Art", "Shane Warne Framed Art", "Shane Warne Limited Edition Wall Art"):
            self.assertEqual(winner.preferred_copy(title, {}, None, False, False)["card_1_headline"], "Shane Warne")
        self.assertEqual(winner.preferred_copy("Paired Wall Art", {"athlete_names": ["Jordan", "Bryant"]}, None, False, False)["card_1_headline"], "Jordan vs Bryant")

    def test_connected_roles_and_all_existing_copy_constraints(self):
        text = prompt({"edition_limit": 100})
        for phrase in ("FAN IDENTITY / MEMORY", "DEFINING PRODUCT HOOK", "distinct from Card 1",
                       "Do not force historical/past-tense memory", "Card 4 — Fan Ownership",
                       "For The Cave", "Numbered Run only when numbering is explicitly verified",
                       "Python len(value) semantics", "Do not cut words in half", "No duplicate headlines",
                       "No duplicate descriptions", "Variation 1 - Staccato Legacy Story",
                       "Variation 2 - Framed Greatness", "Claim Your Edition", ads_page.META_AD_URL_PARAMETERS):
            self.assertIn(phrase, text)
        self.assertNotIn("Card 2 must create display desire", text)
        self.assertNotIn("Card 4 must distil the verified emotional meaning", text)

    def test_sample_winner_card_set_passes_existing_validator(self):
        pairs = [("Shane Warne", "Limited Edition"), ("Warne Fans", "Remember This"),
                 ("King Of Spin", "The Leg Break"), ("For The Cave", "Spin Memories"),
                 ("Only 100 Made", "Numbered Run")]
        cards = [{"headline": h, "description": d} for h, d in pairs]
        self.assertEqual(ads_page.validate_carousel_cards(cards, edition_info_supplied=True), [])
        for card in cards:
            for value in card.values():
                self.assertLessEqual(len(value), 17)

    def test_room_pool_and_distinct_scenes_across_sports_and_tokens(self):
        self.assertEqual(len(winner.ROOMS), 20)
        for category in ("Cricket", "Baseball", "NBA", "NFL", "Motorsport", "Horse Racing", "Ice Hockey", "Rugby League", "Soccer", "Golf", "Other"):
            for token in range(12):
                scenes = ads_page.resolve_carousel_visual_scenes("Collector Print", category, "Australia", variation_token=str(token))
                self.assertEqual(len(scenes), 5)
                self.assertEqual(scenes[0]["room_family"], "close_up_wall_hero")
                self.assertEqual(scenes[3]["room_family"], "sports_cave")
                for field in ("room_family", "wall_family", "camera_family", "lighting_family", "furniture_family", "architecture", "artwork_placement"):
                    self.assertEqual(len({scene[field] for scene in scenes[1:]}), 4, (category, token, field))
                self.assertEqual(sum(s["wall_family"] in winner.LIGHT_WALLS for s in scenes[1:]), 2)
                self.assertLessEqual(sum(s["sport_specific_setting"] != "none" for s in scenes[1:]), 1)

    def test_sport_specific_selection_uses_supported_sport_and_aliases(self):
        for sport in ("cricket", "motorsport", "nba", "ice hockey"):
            scenes = winner.resolve_room_set(product_name="Collector", sport=sport, market="UK", variation_token="sport")
            themed = [s for s in scenes if s["sport_specific_setting"] != "none"]
            self.assertEqual(len(themed), 1)
            self.assertIn(themed[0]["room_family"], winner.SPORT_ROOMS[sport])
        for alias, canonical in (("Basketball", "NBA"), ("Soccer", "Football"), ("NHL", "Ice Hockey")):
            self.assertEqual(ads_page.resolve_carousel_visual_scenes("Collector", alias, "UK"),
                             ads_page.resolve_carousel_visual_scenes("Collector", canonical, "UK"))

    def test_token_is_repeatable_and_varies_hero_cave_and_other_rooms(self):
        def resolve(token):
            return ads_page.resolve_carousel_visual_scenes("Modern Collector", "Motorsport", "Australia", variation_token=token)
        self.assertEqual(resolve("fixed"), resolve("fixed"))
        packs = [resolve(str(n)) for n in range(20)]
        for slot in range(5):
            self.assertGreater(len({p[slot]["wall_family"] for p in packs}), 1)
            self.assertGreater(len({p[slot]["camera_family"] for p in packs}), 1)
        self.assertGreater(len({p[1]["room_family"] for p in packs}), 2)
        self.assertGreater(len({p[3]["architecture"] for p in packs}), 1)

    def test_all_five_standalone_prompts_keep_product_and_realism(self):
        sections = carousel_prompt_card_sections(visual_contract(prompt()))
        self.assertEqual(list(sections), [1, 2, 3, 4, 5])
        for card in sections.values():
            for phrase in ("STRICT PRODUCT LOCK", "FRAME AND GLASS REALISM", "real glass over the artwork", "LAST-IMAGE VARIATION LOCK",
                           "1024", "contact shadow", "Do not redraw", "CREATIVE_VARIATION_TOKEN: winner-test",
                           "Room:", "Camera:", "Light:", "Visual fingerprint", "No invented vehicles"):
                self.assertIn(phrase, card)
            self.assertNotIn("magnifying glass", card)
        self.assertIn("65-80%", sections[1])
        self.assertIn("Do not add furniture or room decor", sections[1])
        self.assertIn("Room: Premium Man Cave / Sports Cave", sections[4])
        self.assertIn("fourth distinct premium lifestyle room", sections[5])
        self.assertIn("Never alter or magnify printed pixels", sections[5])

    def test_production_module_has_no_resolved_example_identities(self):
        source = Path(winner.__file__).read_text(encoding="utf-8")
        for example in ("Don Mattingly", "Lap Of Gods", "Holden", "Murph", "Purple Sectors", "The Mountain"):
            self.assertNotIn(example, source)

    def test_other_campaigns_and_creative_refresh_match_preupgrade_bytes(self):
        rows = json.loads((Path(__file__).parent / "fixtures" / "carousel_winner_unaffected.json").read_text())
        for row in rows:
            with self.subTest(kwargs=row["kwargs"]):
                text = ads_page.build_ads_prompt(**row["kwargs"])
                self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), row["sha256"])


if __name__ == "__main__":
    unittest.main()
