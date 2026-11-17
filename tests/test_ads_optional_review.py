"""Optional review never gates the real automatic-save/post action."""
from unittest import TestCase
from streamlit.testing.v1 import AppTest


class OptionalReviewTests(TestCase):
    def app(self, fail_review=False):
        source = """
import streamlit as st
from unittest.mock import patch
import ads_page as ads
import ads_direct_post as direct
from tests.test_ads_posting_handoff import completed_ad
result, workflow = st.session_state.setdefault('draft', completed_ad('Instant Experience'))
with patch.object(direct, 'render_settings', return_value=({}, [])), patch.object(ads.os_accounts, 'can_access_page', return_value=True), patch.object(ads, 'instant_experience_package_ready', return_value=True):
    if FAIL_REVIEW:
        with patch.object(ads, 'build_final_ad_review_copy_prompt', side_effect=ValueError('review unavailable')):
            ads._render_ads_final_actions(result, workflow)
    else:
        ads._render_ads_final_actions(result, workflow)
""".replace('FAIL_REVIEW',repr(fail_review))
        return AppTest.from_string(source).run(timeout=20)

    def test_post_now_visible_and_enabled_without_copying_optional_review(self):
        app=self.app()
        self.assertFalse(app.exception)
        button=next(b for b in app.button if b.label=='Post now')
        self.assertFalse(button.disabled)
        self.assertTrue(any('Optional:' in item.value for item in app.caption))
        self.assertTrue(any('Copy Final Review Prompt' in str(item.proto) for item in app.get('iframe')))

    def test_optional_review_failure_does_not_hide_or_disable_posting(self):
        app=self.app(True)
        self.assertFalse(app.exception)
        self.assertFalse(next(b for b in app.button if b.label=='Post now').disabled)
        self.assertTrue(any('review prompt is unavailable' in item.value for item in app.caption))

    def test_image_cards_keep_editable_copy_without_copy_description_buttons(self):
        app=AppTest.from_string("""
from unittest.mock import patch
import ads_page as ads
from tests.test_ads_posting_handoff import completed_ad
result, workflow=completed_ad('Instant Experience')
with patch.object(ads, '_process_ads_image_upload'), patch.object(ads, '_render_instant_experience_copy_csv_control'):
    ads._render_instant_experience_concepts(result, workflow)
""").run(timeout=20)
        self.assertFalse(app.exception)
        self.assertTrue(app.text_area)
        self.assertFalse(any('Copy Description' in str(item.proto) for item in app.get('iframe')))
