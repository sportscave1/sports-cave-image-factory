import unittest

import mockup_product_prompts as scenes
from product_upload_lifestyle import (
    AUTOMATIC_START, FINISHED_MOCKUPS, FILENAMES, INSTRUCTIONS, LABELS, PER_IMAGE, PROMPT_ID, compose, scene_texts,
    individual_prompt, individual_prompt_items, READ_FIRST, FINAL_CHECK,
)


class ProductUploadMasterV6Tests(unittest.TestCase):
    def test_finished_contract_in_master_saved_overrides_and_each_card(self):
        scene = 'Selected room: coastal study\nSelected camera angle: low three-quarter\nOnce Card 1 has been generated, stop and wait.'
        prompt = compose('Custom saved master: protect all artwork.', [scene] * 3)
        self.assertTrue(prompt.startswith(READ_FIRST))
        self.assertIn(AUTOMATIC_START + '\n\n' + FINISHED_MOCKUPS + '\n\n', prompt)
        self.assertEqual(prompt.count(FINISHED_MOCKUPS), 4)  # master + three independent briefs
        self.assertNotIn('stop and wait', prompt)
        self.assertEqual(prompt.count('Selected camera angle: low three-quarter'), 9)
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
        self.assertTrue(prompt.startswith(READ_FIRST))
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
        self.assertTrue(prompt.startswith(READ_FIRST))
        self.assertIn(INSTRUCTIONS, prompt)
        self.assertEqual(prompt.count(PER_IMAGE), 3)
        for label, brief in zip(LABELS, ['saved lounge', 'saved office', 'saved living room']):
            self.assertIn(label, prompt)
            self.assertIn(brief, prompt)
        for requirement in ('Generate each COMPLETE mockup in one image-generation call', 'not guaranteed pixel-identical reproduction',
                            'Where the selected product is confirmed as A1', 'If another size or verified outer measurement',
                            '1024 × 1024', 'Inspect each actual result against the reference'):
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


def test_unified_generation_migrates_shared_blocks_and_saved_mechanics():
    from sports_cave_prompt_blocks import append_sports_cave_image_realism_rules
    from product_upload_lifestyle import sequential_instructions
    legacy = '''Custom scene: heritage office. Selected camera angle: gently elevated from the right.
## 4. EXACT PRODUCT COMPOSITING — MANDATORY
Generate the new room separately, with an appropriate blank wall.
Place the original framed product into the new room through deterministic image compositing.
Preserve its source artwork pixels.
# 5. SAVED ROOM
Selected room: industrial converted garage lounge
Generate Card 1 and wait for approval.
'''
    shared = append_sports_cave_image_realism_rules(legacy)
    migrated = individual_prompt(shared)
    for forbidden in ('deterministic image compositing', 'source-preserving compositing',
                      'pixel-preserving', 'immutable', 'Generate the new room separately',
                      'wait for approval.', 'Preserve its source artwork pixels'):
        assert forbidden not in migrated
    for retained in ('Selected room: industrial converted garage lounge',
                     'Selected camera angle: gently elevated from the right',
                     'Custom scene: heritage office', 'SPORTS_CAVE_PHYSICAL_SCALE_AND_FRAME_REALISM'):
        assert retained in migrated
    assert individual_prompt(migrated) == migrated
    assert sequential_instructions(sequential_instructions(shared)) == sequential_instructions(shared)
    master = compose(shared, [shared] * 3)
    assert master.count(AUTOMATIC_START) == 1
    for text in (master, migrated, INSTRUCTIONS, PER_IMAGE):
        for required in ('COMPLETE mockup in one image-generation call',
                         'ORIGINAL supplied full-resolution framed product as the image reference',
                         'not guaranteed pixel-identical reproduction',
                         'natural frame bevel highlights', 'narrow contact shadows',
                         'noticeable but controlled window or room-light reflections',
                         'Correct material errors', '1024 × 1024'):
            assert required in text
    # Conversion is scoped to Product Upload: the shared source still has its old contract.
    assert 'immutable' in shared and 'source-preserving compositing' in shared


def test_actual_three_card_templates_are_unified_without_losing_selection():
    import image_factory as factory
    items = factory.build_lifestyle_prompt_items('Reference product', 'Motorsport', local_only=True)
    protected = individual_prompt_items(items)
    for before, after in zip(items, protected):
        if before['filename'] not in FILENAMES:
            assert before == after
            continue
        assert scenes.SCENE.search(before['prompt']).group() == scenes.SCENE.search(after['prompt']).group()
        assert 'immutable' not in after['prompt']
        assert 'source-preserving compositing' not in after['prompt']
        assert 'COMPLETE mockup in one image-generation call' in after['prompt']
        assert 'not guaranteed pixel-identical reproduction' in after['prompt']
    assert individual_prompt_items(protected) == protected


def test_summary_matches_resolved_briefs_without_drawing_again():
    from unittest.mock import patch
    from product_upload_lifestyle import selected_details
    result = {'run_dir': 'summary-test', 'final_prompt_items': [
        {'filename': name, 'prompt': scenes.build(name)} for name in FILENAMES]}
    with patch.object(scenes.random, 'choice', side_effect=AssertionError('copy must not draw')):
        texts = scene_texts(result, lambda name, default: default, lambda name, default: default)
        prompt = compose(INSTRUCTIONS, texts)
        assert prompt == compose(INSTRUCTIONS, texts)
    opening, rest = prompt.split(AUTOMATIC_START, 1)
    assert opening.startswith(READ_FIRST)
    for index, (label, text) in enumerate(zip(LABELS, texts), 1):
        selected = selected_details(text, index)
        assert f'- Image {index}: {label}. {selected}' in opening
        brief = rest.split(f'## IMAGE {index} — {label.upper()}', 1)[1]
        assert f'Assigned room category: {label}\n{selected}' in brief
        assert scenes.SCENE.search(text).group() in brief
    assert prompt.endswith(FINAL_CHECK)


def test_missing_default_scene_is_resolved_and_incomplete_set_is_rejected():
    texts = scene_texts({}, lambda name, default: default, lambda name, default: default)
    assert all(scenes.SCENE.search(text) for text in texts)
    prompt = compose(INSTRUCTIONS, texts)
    assert 'As specified in Image' not in prompt.split(AUTOMATIC_START)[0]
    import pytest
    for incomplete in (texts[:2], texts + ['extra'], [texts[0], '', texts[2]]):
        with pytest.raises(ValueError, match='three Product Uploads scene briefs'):
            compose(INSTRUCTIONS, incomplete)


def test_saved_custom_details_and_long_tail_are_complete():
    texts = [f'Selected room: Authored {label} subtype\nSelected camera angle: custom {index}\n'
             + ('Saved material and lighting instructions. ' * 3000) + f'END SAVED CARD {index}'
             for index, label in enumerate(LABELS, 1)]
    prompt = compose('Saved master: retain verified dimensions and frame.', texts)
    assert 'Saved master: retain verified dimensions and frame.' in prompt
    for index, (label, text) in enumerate(zip(LABELS, texts), 1):
        assert text in prompt
        assert f'- Image {index}: {label}. Selected room: Authored {label} subtype; Selected camera angle: custom {index}' in prompt
    assert prompt.endswith(FINAL_CHECK)


def test_complete_set_requests_downloadable_role_manifest_without_renaming_assets():
    from product_upload_lifestyle import OUTPUT_MANIFEST
    prompt = compose('Preserve saved frame dimensions.', ['saved man cave', 'saved office', 'saved living room'])
    assert prompt.count(OUTPUT_MANIFEST) == 1
    assert 'downloadable UTF-8 CSV named mockup-outputs.csv' in prompt
    assert 'columns role,filename' in prompt
    assert 'Keep random filenames unchanged' in prompt
    assert 'do not claim completion' in prompt
    assert prompt.index(OUTPUT_MANIFEST) > prompt.index('## IMAGE 3')
    assert prompt.endswith(FINAL_CHECK)
