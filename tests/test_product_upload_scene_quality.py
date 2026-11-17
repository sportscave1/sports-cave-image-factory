from product_upload_lifestyle import (
    AUTOMATIC_START, FILENAMES, INSTRUCTIONS, OUTPUT_MANIFEST, compose, scene_texts,
    sequential_instructions, selected_details,
)
from product_upload_scene_quality import upgrade
import mockup_product_prompts as scenes


def test_assembled_prompt_removes_conflicts_from_saved_copies_without_changing_execution():
    legacy = '''One laptop, lamp, plant, notebook or a few books may be appropriate.
Use seating, sideboards, lamps, books, plants and tables only when they improve the composition.
Keep reflections clear of important artwork details, titles and faces.
Use premium cinematic lighting, with a slightly stronger reflection toward an edge or upper area where physically appropriate.
Reference from the last image created. Selected room: heritage green-panelled study.
'''
    prompt = compose(legacy, [legacy] * 3)
    for removed in ('lamp, plant', 'books, plants', 'reflections clear of important',
                    'premium cinematic lighting', 'toward an edge or upper', 'from the last image', 'heritage green'):
        assert removed not in prompt
    for required in ('one continuous pane', 'Transparent reflections may cross', 'No plants, flowers',
                     '87 cm wide × 62 cm high', 'narrow wall-contact shadows',
                     'never lean', 'league’s home market', 'original supplied product reference'):
        assert required in prompt
    assert prompt.count(AUTOMATIC_START) == 1 and OUTPUT_MANIFEST in prompt
    assert sequential_instructions(sequential_instructions(legacy)) == sequential_instructions(legacy)
    assert upgrade(upgrade(legacy)) == upgrade(legacy)


def test_default_sets_have_three_distinct_views_walls_and_finishes_and_vary_across_runs():
    sets = set()
    for number in range(40):
        result = {'_product_upload_intake': 'one-product', 'run_dir': f'run-{number}'}
        texts = scene_texts(result, lambda n, d: d, lambda n, d: d)
        assert texts == scene_texts(result, lambda n, d: d, lambda n, d: d)
        import re
        for field in ('camera angle', 'wall colour', 'wall finish'):
            choices = [re.search('Selected ' + field + r': (.+)', text).group(1) for text in texts]
            assert len(set(choices)) == 3
        assert set(re.search(r'Selected camera angle: (.+)', t).group(1) for t in texts) == set(scenes.ANGLES[:3])
        sets.add(tuple(texts))
        prompt = compose(INSTRUCTIONS, texts)
        for index, text in enumerate(texts, 1):
            assert selected_details(text, index) in prompt
    assert len(sets) == 40


def test_custom_source_artwork_and_shared_prompt_library_are_not_modified():
    from sports_cave_prompt_blocks import SPORTS_CAVE_PREMIUM_GLASS_LIGHTING_V4
    original = SPORTS_CAVE_PREMIUM_GLASS_LIGHTING_V4
    upgraded = sequential_instructions(original)
    assert 'toward an edge or upper area' in original
    assert 'toward an edge or upper area' not in upgraded
    assert SPORTS_CAVE_PREMIUM_GLASS_LIGHTING_V4 == original
    assert 'preserve green within the original artwork' in upgraded
