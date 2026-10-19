import unittest

import mockup_product_prompts as scenes
from product_upload_lifestyle import (
    FILENAMES, INSTRUCTIONS, LABELS, PER_IMAGE, PROMPT_ID, compose, scene_texts,
)


class ProductUploadMasterV6Tests(unittest.TestCase):
    def test_v6_master_and_per_card_requirements(self):
        self.assertEqual(PROMPT_ID, 'lifestyle::product-upload-master-v6')
        self.assertTrue(INSTRUCTIONS.startswith('# SPORTS CAVE — ULTIMATE 3-MOCKUP MASTER V6'))
        self.assertTrue(INSTRUCTIONS.endswith('**END SPORTS CAVE ULTIMATE 3-MOCKUP MASTER V6**'))
        prompt = compose(INSTRUCTIONS, ['saved lounge', 'saved office', 'saved living room'])
        self.assertTrue(prompt.startswith(INSTRUCTIONS))
        self.assertEqual(prompt.count(PER_IMAGE), 3)
        for label, brief in zip(LABELS, ['saved lounge', 'saved office', 'saved living room']):
            self.assertIn(label, prompt)
            self.assertIn(brief, prompt)
        for requirement in ('deterministic image compositing', 'If pixel-preserving compositing is unavailable',
                            'Where the selected product is confirmed as A1', 'If another size or verified outer measurement',
                            '1024 × 1024', 'Never claim artwork integrity was verified'):
            self.assertIn(requirement, PER_IMAGE)
        self.assertIn('Immediately generate Card 1 as one standalone image', INSTRUCTIONS)
        self.assertIn('Wait until Card 1 is approved', INSTRUCTIONS)
        self.assertNotIn('Artwork/paper is 841 mm wide', prompt)

    def test_saved_custom_room_and_camera_survive(self):
        briefs = [f'Authored {label}: custom wall and locked camera' for label in LABELS]
        result = {'run_dir': 'test', 'final_prompt_items': [
            {'filename': name, 'prompt': text} for name, text in zip(FILENAMES, briefs)]}
        selected = scene_texts(result, lambda name, default: default, lambda *args: 'custom saved template')
        self.assertEqual(selected, briefs)
        for brief in briefs:
            self.assertIn(brief, compose(INSTRUCTIONS, selected))

    def test_default_selections_remain_stable_across_reruns(self):
        result = {'_product_upload_intake': 'isolated-offline-test', 'final_prompt_items': [
            {'filename': name, 'prompt': scenes.build(name)} for name in FILENAMES]}
        select = lambda: scene_texts(result, lambda name, default: default, lambda name, default: default)
        self.assertEqual(select(), select())
        self.assertEqual(len(select()), 3)


if __name__ == '__main__':
    unittest.main()
