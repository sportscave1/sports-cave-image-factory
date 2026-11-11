import unittest

import product_upload_prompt_core as app
from product_title_rules import apply_rules, naming_valid, title_state


class ProductNamingConventionTests(unittest.TestCase):
    def test_required_examples_and_three_workflows(self):
        for title in (
            'The Rivals – Brock vs Moffat Wall Art',
            'Legends Never Die – Messi vs Ronaldo Wall Art',
            'The Final Bow – Shane Warne Wall Art',
            'The Nuke – Luke Littler Wall Art',
        ):
            self.assertTrue(naming_valid(title))
            for existing, mode in ((False, 'LIVE'), (True, 'DRAFT'), (False, 'DRAFT')):
                metadata = {'product_name': title, 'customer_facing_title': title}
                prompt = app.get_product_upload_prompt(metadata, update_existing=existing, publication_mode=mode)
                self.assertIn(title, prompt)
                self.assertIn('Artwork name always comes first', prompt)
                self.assertIn('leave an existing title unchanged', prompt)
                self.assertIn(app.PRODUCT_UPLOAD_META_PROMPT, prompt)
                self.assertIn(app.PRODUCT_UPLOAD_ALT_TEXT_PROMPT, prompt)
                self.assertNotIn('Subject first, one EM DASH', prompt)
                self.assertEqual(prompt, app.apply_product_upload_prompt_updates(
                    prompt, metadata, update_existing=existing, publication_mode=mode))

    def test_current_compact_three_modes_and_saved_custom_instructions(self):
        from product_upload_prompts import build
        for mode in ('DRAFT', 'LIVE', 'UPDATE'):
            title = 'The Final Bow – Shane Warne Wall Art'
            text = build(mode, metadata={'customer_facing_title': title},
                         load=lambda key, default, **kw: default + '\nKeep the approved custom instruction.')
            self.assertIn('Original edition/design name first', text)
            self.assertIn('mandatory Wall Art suffix', text)
            self.assertIn(title, text)
            self.assertIn('Keep the approved custom instruction.', text)
            self.assertNotIn('Subject — Short Design Hook', text)
            if mode == 'UPDATE':
                self.assertIn('Never create a product', text)
                self.assertIn('preserve title, handle, description', text)
            for invalid in ('Shane Warne — The Final Bow', 'A' * 61):
                with self.assertRaises(ValueError):
                    build(mode, metadata={'customer_facing_title': invalid},
                          load=lambda key, default, **kw: default)

    def test_current_media_only_update_preserves_legacy_title(self):
        from product_upload_prompts import build
        text = build('UPDATE', metadata={'existing_product_title': 'Old legacy title'},
                     load=lambda key, default, **kw: default)
        self.assertIn('Media-only update: preserve title', text)
        self.assertIn('Old legacy title', text)
        self.assertNotIn('Title/H1: required format', text)

    def test_invalid_explicit_candidates_block_handoff(self):
        for title in ('The Nuke — Luke Littler Wall Art', 'The Nuke – Luke Littler',
                      ' – Luke Littler Wall Art', 'The Nuke –  Wall Art',
                      'The Nuke – Luke\nLittler Wall Art', ' A – B Wall Art',
                      'A – B – C Wall Art'):
            self.assertFalse(naming_valid(title), title)
            self.assertFalse(title_state(title, require_format=True)['valid'])
            with self.assertRaises(ValueError):
                apply_rules('Preserve unrelated instructions.', {'customer_facing_title': title})

    def test_blank_candidate_preserves_generation_and_media_only_workflows(self):
        self.assertTrue(title_state('', require_format=True)['valid'])
        self.assertFalse(naming_valid(''))
        prompt = app.get_product_upload_prompt({'product_name': 'Existing artwork'}, update_existing=True)
        self.assertIn('media-only updates preserve the existing title', prompt)
        self.assertIn('never rename the artwork', prompt)


if __name__ == '__main__':
    unittest.main()
