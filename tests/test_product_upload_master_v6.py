import unittest

import mockup_product_prompts as scenes
from product_upload_lifestyle import (
    AUTOMATIC_START, FINISHED_MOCKUPS, FILENAMES, INSTRUCTIONS, LABELS, PER_IMAGE, PROMPT_ID, compose, scene_texts,
    individual_prompt, individual_prompt_items,
)


class ProductUploadMasterV6Tests(unittest.TestCase):
    def test_finished_contract_in_master_saved_overrides_and_each_card(self):
        scene = 'Selected room: coastal study\nSelected camera angle: low three-quarter\nOnce Card 1 has been generated, stop and wait.'
        prompt = compose('Custom saved master: protect all artwork.', [scene] * 3)
        self.assertTrue(prompt.startswith(AUTOMATIC_START + '\n\n' + FINISHED_MOCKUPS + '\n\n'))
        self.assertEqual(prompt.count(FINISHED_MOCKUPS), 4)  # master + three independent briefs
        self.assertNotIn('stop and wait', prompt)
        self.assertEqual(prompt.count('Selected camera angle: low three-quarter'), 3)
        self.assertTrue(INSTRUCTIONS.startswith(AUTOMATIC_START + '\n\n' + FINISHED_MOCKUPS))
        self.assertTrue(PER_IMAGE.startswith(FINISHED_MOCKUPS))
        self.assertNotIn('generate a blank room/frame scene and identify', prompt)
        brief = individual_prompt(scene)
        self.assertEqual(individual_prompt(brief), brief)
        items = [dict(filename=name, prompt=scene, label=label) for name, label in zip(FILENAMES, LABELS)]
        protected = individual_prompt_items(items)
        for original, item in zip(items, protected):
            self.assertTrue(item['prompt'].startswith(FINISHED_MOCKUPS))
            self.assertEqual(item['filename'], original['filename'])
            self.assertEqual(item['label'], original['label'])
            self.assertIn('Selected room: coastal study', item['prompt'])
            self.assertNotIn('stop and wait', item['prompt'])
            self.assertEqual(original['prompt'], scene)
        self.assertEqual(individual_prompt_items(protected), protected)
        unrelated = dict(filename='social-prompt.txt', prompt='unchanged')
        self.assertEqual(individual_prompt_items([unrelated]), [unrelated])

    def test_saved_override_migration_is_idempotent_and_preserves_design_locks(self):
        legacy = '''AUTOMATIC START — OLD
Generate Card 1 and wait for approval.
END AUTOMATIC START
Custom master: retain the saved coastal room and low camera.
7. Wait until Card 1 is approved, finalised or the user explicitly requests Card 2.
9. Wait for approval or explicit instruction to continue.
Do not advance to another card unless instructed.
# 21. REVISION AND APPROVAL WORKFLOW
Once Card 1 has been generated, stop and wait.
If the user approves Card 1, proceed to Card 2 when requested.
If the user requests Card 2 or Card 3 explicitly, treat that as permission to advance to the named card.
If a room or angle has already been approved or explicitly locked, do not randomise that setting.
Do not regenerate already approved cards.'''
        from product_upload_lifestyle import sequential_instructions
        migrated = sequential_instructions(AUTOMATIC_START + '\n\n' + legacy)
        self.assertEqual(sequential_instructions(migrated), migrated)
        prompt = compose(migrated, ['locked man cave', 'locked office', 'locked living room'])
        self.assertTrue(prompt.startswith(AUTOMATIC_START + '\n\n'))
        self.assertEqual(prompt.count('AUTOMATIC START —'), 1)
        self.assertEqual(prompt.count('END AUTOMATIC START'), 1)
        for conflict in ('stop and wait', 'when requested', 'unless instructed',
                         'Wait until Card 1', 'Wait for approval', 'permission to advance'):
            self.assertNotIn(conflict, prompt)
        for preserved in ('retain the saved coastal room and low camera',
                          'do not randomise that setting', 'Do not regenerate already approved cards',
                          'locked man cave', 'locked office', 'locked living room'):
            self.assertIn(preserved, prompt)

    def test_v6_master_and_per_card_requirements(self):
        self.assertEqual(PROMPT_ID, 'lifestyle::product-upload-master-v6')
        self.assertTrue(INSTRUCTIONS.startswith(AUTOMATIC_START))
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
        self.assertNotIn('Wait until Card 1 is approved', INSTRUCTIONS)
        self.assertEqual(prompt.count(AUTOMATIC_START), 1)
        self.assertEqual(prompt.count('END AUTOMATIC START'), 1)
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
