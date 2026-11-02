"""Static component browser QA, with no application server or external requests.

Run: python -m unittest tests.test_ads_black_friday_browser
Requires Playwright and locally installed Microsoft Edge.
"""
import json
import unittest

from playwright.sync_api import sync_playwright

import ads_page
from ads_black_friday import build_black_friday_prompt
from tests.test_ads_black_friday import record, rendered


class BlackFridayBrowserTests(unittest.TestCase):
    def test_sizes_repeated_copy_feedback_and_legacy_clipboard(self):
        normal = record()["master_prompt"]
        variants = (
            (normal, "Copy Prompt", {}),
            (build_black_friday_prompt(normal), "Copy Black Friday Prompt",
             dict(label="Copy Black Friday Prompt", gold_accent=True, compact=True)),
        )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            try:
                page = browser.new_page()
                page.route("**/*", lambda route: route.abort())
                for prompt, label, options in variants:
                    call = rendered(prompt, **options)
                    for width in (1440, 1366, 1024, 768, 390, 320):
                        # Streamlit uses a 2:1 desktop split and stacks on mobile.
                        component_width = width - 32 if width < 640 else max(180, (width - 160) // 3)
                        page.set_viewport_size({"width": component_width, "height": call.kwargs["height"]})
                        for modern in (True, False):
                            page.set_content(call.args[0])
                            page.evaluate("""modern => {
                                window.copied = [];
                                Object.defineProperty(window, 'isSecureContext', {value: modern, configurable:true});
                                Object.defineProperty(navigator, 'clipboard', {value: {writeText: async text => window.copied.push(text)}, configurable:true});
                                document.execCommand = command => {
                                    if(command !== 'copy') throw Error('Unexpected command');
                                    window.copied.push(document.querySelector('textarea').value);
                                    return true;
                                };
                            }""", modern)
                            button = page.get_by_role("button", name=label, exact=True)
                            box = button.bounding_box()
                            self.assertGreaterEqual(box["x"], 0)
                            self.assertLessEqual(box["x"] + box["width"], component_width)
                            self.assertLessEqual(box["y"] + box["height"], call.kwargs["height"])
                            for _ in range(3):
                                page.locator("button").click()
                                self.assertEqual(page.locator("button").inner_text(), "Prompt copied")
                                self.assertEqual(page.get_by_role("status").inner_text(), "Prompt copied")
                            self.assertEqual(page.evaluate("window.copied"), [ads_page.creation_instructions(prompt)] * 3)
                            self.assertEqual(page.locator("textarea").count(), 0)
                            if options:
                                status_box = page.get_by_role("status").bounding_box()
                                self.assertLessEqual(status_box["y"] + status_box["height"], call.kwargs["height"])
                                self.assertEqual(page.locator("button").evaluate("el => getComputedStyle(el).borderTopColor"), "rgb(212, 165, 76)")
                            page.wait_for_function("label => document.querySelector('button').innerText === label", arg=label)
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
