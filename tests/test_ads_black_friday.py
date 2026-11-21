"""Offline prompt/clipboard contracts; never start the application or providers."""
import ast
import json
import re
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import ads_page
from ads_black_friday import FOOTER_REPLACEMENTS, SUBHEADLINE, build_black_friday_prompt

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "5bb13ace2f959015d3eddf94e265a35682d53e67"


def record(category="Cricket", country="Australia", token="seasonal-test"):
    return ads_page.build_ads_result_record(
        "Collector Print", category, country, "Instant Experience",
        product_url="https://example.com/products/collector", variation_token=token,
        product_metadata={"edition_limit": 100},
    )


def rendered(prompt, **kwargs):
    with patch.object(ads_page.components, "html") as render:
        ads_page.render_prompt_copy_button(prompt, "test", **kwargs)
    return render.call_args


class BlackFridayPromptTests(unittest.TestCase):
    def test_new_ads_exposes_only_original_prompt(self):
        for prompt in ("Saved original prompt", record()["master_prompt"], record(country="USA")["master_prompt"]):
            with patch.object(ads_page, "render_prompt_copy_button") as render, patch.object(ads_page.st, "columns") as columns, patch.object(ads_page.st, "caption") as caption:
                ads_page.render_new_ads_prompt_copy_buttons(prompt, "original-key")
            render.assert_called_once_with(prompt, "original-key")
            columns.assert_not_called()
            caption.assert_not_called()

    def legacy_prompt(self):
        return "ADS_IE_COMBINED_EXECUTION_V1\n" + "\n".join(old for old, _ in FOOTER_REPLACEMENTS) + "\n" + "\n".join("SUPPORTING LINE: Saved line " + str(i) for i in range(3))

    def test_current_two_line_footer_has_no_seasonal_row(self):
        for category in ("Cricket", "Baseball", "Motorsport", "Other"):
            for country in ("Australia", "USA", "UK"):
                with self.subTest(category=category, country=country):
                    normal = record(category, country)["master_prompt"]
                    self.assertEqual(build_black_friday_prompt(normal), normal)
                    self.assertNotIn("SUPPORTING LINE:", normal)
                    self.assertEqual(normal.count("\nFOOTER SECOND LINE ("), 3)

    def test_legacy_substitutions_are_reversible(self):
        normal = self.legacy_prompt()
        seasonal = build_black_friday_prompt(normal)
        self.assertEqual(re.findall(r"(?m)^SUPPORTING LINE: (.+)$", seasonal), [SUBHEADLINE] * 3)
        restored = seasonal
        for old, new in reversed(FOOTER_REPLACEMENTS):
            self.assertNotIn(old, seasonal)
            restored = restored.replace(new, old)
        lines = iter(re.findall(r"(?m)^SUPPORTING LINE: (.+)$", normal))
        restored = re.sub(r"(?m)^SUPPORTING LINE: .+$", lambda _: "SUPPORTING LINE: " + next(lines), restored)
        self.assertEqual(restored, normal)

    def test_complete_clipboard_payload_and_feedback(self):
        normal = record()["master_prompt"]
        for text, options in ((normal, {}), (build_black_friday_prompt(normal), dict(label="Copy Black Friday Prompt", gold_accent=True, compact=True))):
            markup = rendered(text, **options).args[0]
            payload = json.loads(re.search(r"const promptText = (.*);", markup)[1])
            self.assertEqual(payload, ads_page.creation_instructions(text))
            self.assertIn('button.innerText = "Prompt copied"', markup)
            self.assertIn('status.innerText = "Prompt copied"', markup)

    def test_changed_or_legacy_templates_fail_without_altering_normal(self):
        normal = self.legacy_prompt()
        for text in ("legacy prompt", normal.replace("SUPPORTING LINE:", "SUBLINE:"), normal.replace("Supporting text is clearly secondary in softer warm off-white.", "Different typography.")):
            with self.assertRaises(ValueError):
                build_black_friday_prompt(text)


if __name__ == "__main__":
    unittest.main()
