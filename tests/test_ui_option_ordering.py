import ast
import unittest
from pathlib import Path

from ui_option_ordering import alphabetize_options, selected_option_index


class OptionOrderingTests(unittest.TestCase):
    def test_strings_use_case_insensitive_natural_order_and_control_positions(self):
        options = ["Other", "item 10", "beta", "All categories", " Item 2 ", "Alpha", "Select…"]

        ordered = alphabetize_options(options)

        self.assertEqual(
            ordered,
            ("Select…", "All categories", "Alpha", "beta", " Item 2 ", "item 10", "Other"),
        )
        self.assertEqual(options[0], "Other", "the shared source must not be mutated")

    def test_label_value_records_keep_objects_and_stably_order_duplicate_labels(self):
        second = {"label": "Same", "value": "b", "metadata": {"kept": True}}
        first = {"label": "Same", "value": "a", "metadata": {"kept": True}}
        options = [second, {"label": "Zulu", "value": 3}, first, {"label": "Alpha", "value": 4}]

        ordered = alphabetize_options(options)

        self.assertIs(ordered[1], first)
        self.assertIs(ordered[2], second)
        self.assertEqual([row["label"] for row in ordered], ["Alpha", "Same", "Same", "Zulu"])

    def test_none_stays_intentionally_positioned_and_custom_controls_can_be_pinned(self):
        self.assertEqual(
            alphabetize_options(
                ("Beta", "None", "Alpha", "Use selected market"),
                first=("Use selected market",),
            ),
            ("Use selected market", "None", "Alpha", "Beta"),
        )

    def test_existing_selection_resolves_to_same_underlying_value(self):
        ordered = alphabetize_options(("Zulu", "Alpha", "Beta"))
        self.assertEqual(ordered[selected_option_index(ordered, "Zulu")], "Zulu")
        self.assertEqual(selected_option_index(ordered, "missing", default=1), 1)

    def test_ads_categories_are_canonical_a_to_z_in_both_ads_flows(self):
        import ads_page

        self.assertEqual(ads_page.CATEGORY_OPTIONS[0], "Select category")
        self.assertEqual(ads_page.CATEGORY_OPTIONS[-1], "Other")
        self.assertEqual(
            ads_page.CATEGORY_OPTIONS[1:-1],
            [
                "Baseball",
                "Combat",
                "Cricket",
                "Football",
                "Golf",
                "Horse Racing",
                "Ice Hockey",
                "Motorsport",
                "NBA",
                "NFL",
                "Rugby Union",
                "Tennis",
            ],
        )

        repository = Path(__file__).resolve().parents[1]
        category_sources = {}
        for filename in ("ads_page.py", "ads_creative_refresh.py"):
            tree = ast.parse((repository / filename).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or len(node.args) < 2:
                    continue
                if not isinstance(node.func, ast.Attribute) or node.func.attr != "selectbox":
                    continue
                label = node.args[0]
                if isinstance(label, ast.Constant) and label.value == "Category":
                    category_sources[filename] = ast.unparse(node.args[1])

        self.assertEqual(
            category_sources,
            {
                "ads_page.py": "CATEGORY_OPTIONS",
                "ads_creative_refresh.py": "ads_page.CATEGORY_OPTIONS",
            },
        )


if __name__ == "__main__":
    unittest.main()
