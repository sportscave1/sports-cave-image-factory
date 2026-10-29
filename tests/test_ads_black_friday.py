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
    def test_only_subheadline_instructions_change_and_are_reversible(self):
        for category in ("Cricket", "Baseball", "Motorsport", "Other"):
            for country in ("Australia", "USA", "UK"):
                with self.subTest(category=category, country=country):
                    result = record(category, country)
                    normal = result["master_prompt"]
                    seasonal = build_black_friday_prompt(normal)
                    originals = re.findall(r"(?m)^SUPPORTING LINE: (.+)$", normal)
                    self.assertEqual(re.findall(r"(?m)^SUPPORTING LINE: (.+)$", seasonal), [SUBHEADLINE] * 3)
                    # Undo only the authorized edits; every remaining byte must match.
                    restored = seasonal
                    for old, new in reversed(FOOTER_REPLACEMENTS):
                        self.assertNotIn(old, seasonal)
                        restored = restored.replace(new, old)
                    lines = iter(originals)
                    restored = re.sub(r"(?m)^SUPPORTING LINE: .+$", lambda _: "SUPPORTING LINE: " + next(lines), restored)
                    self.assertEqual(restored, normal)
                    self.assertEqual(result["master_prompt"], normal)
                    self.assertEqual(build_black_friday_prompt(normal), seasonal)
                    for prefix in ("HEADLINE:", "CTA:", "SCENE:", "Camera:", "Framing:"):
                        self.assertEqual([x for x in normal.splitlines() if x.startswith(prefix)],
                                         [x for x in seasonal.splitlines() if x.startswith(prefix)])

    def test_original_render_and_clipboard_match_pre_change_function_exactly(self):
        baseline = subprocess.check_output(["git", "show", f"{BASELINE}:ads_page.py"], cwd=ROOT).decode("utf-8")
        old = next(n for n in ast.parse(baseline).body if isinstance(n, ast.FunctionDef) and n.name == "render_prompt_copy_button")
        namespace = dict(vars(ads_page))
        exec(compile(ast.Module(body=[old], type_ignores=[]), "baseline", "exec"), namespace)
        normal = record()["master_prompt"]
        with patch.object(ads_page.components, "html") as render:
            namespace[old.name](normal, "test")
        self.assertEqual(render.call_args, rendered(normal))
        # Every existing function outside the two UI integration points is unchanged.
        before = {n.name: ast.dump(n) for n in ast.parse(baseline).body if isinstance(n, ast.FunctionDef)}
        after = {n.name: ast.dump(n) for n in ast.parse((ROOT / "ads_page.py").read_text(encoding="utf-8")).body if isinstance(n, ast.FunctionDef)}
        for name in before.keys() - {"render_prompt_copy_button", "render_supported_result"}:
            self.assertEqual(before[name], after[name], name)

    def test_complete_clipboard_payload_and_feedback(self):
        normal = record()["master_prompt"]
        for text, options in ((normal, {}), (build_black_friday_prompt(normal), dict(label="Copy Black Friday Prompt", gold_accent=True, compact=True))):
            markup = rendered(text, **options).args[0]
            payload = json.loads(re.search(r"const promptText = (.*);", markup)[1])
            self.assertEqual(payload, ads_page.creation_instructions(text))
            self.assertIn('button.innerText = "Prompt copied"', markup)
            self.assertIn('status.innerText = "Prompt copied"', markup)

    def test_changed_or_legacy_templates_fail_without_altering_normal(self):
        normal = record()["master_prompt"]
        for text in ("legacy prompt", normal.replace("SUPPORTING LINE:", "SUBLINE:"), normal.replace("Supporting text is clearly secondary in softer warm off-white.", "Different typography.")):
            with self.assertRaises(ValueError):
                build_black_friday_prompt(text)


if __name__ == "__main__":
    unittest.main()
