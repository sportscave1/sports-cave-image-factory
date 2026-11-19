"""The complete source-to-Review instruction survives each production renderer."""
import pytest

from home_morning_brief_actions import _prompt
from home_design_refresh import _refresh_prompt
from design_photographic_composition import (
    STORY_FIRST_CROP, GENERATE_PHOTOGRAPHIC_UNIT, FINAL_PHOTOGRAPHIC_REVIEW,
)
from design_subject_authenticity import CREATE_DESIGN_AUTHENTICITY_CHECK


def variants():
    return [
        _prompt('The Step Over', 'Iverson stepping over Lue; preserve the defining interaction.'),
        _refresh_prompt(dict(product_id='123', title='Approved Edition'), 'https://example.test/edition'),
        _prompt('Selected edit', 'Improve photographic integration', edit={
            'source': dict(id='id:source', rev='r1', path_display='/Review/Approved.psd'),
            'metadata': dict(upload_intent='new_product')}),
    ]


@pytest.mark.parametrize('prompt', variants())
def test_crop_generation_repair_and_review_are_integrated_in_existing_stages(prompt):
    research, rest = prompt.split('**2.', 1)
    layout, rest = rest.split('**3.', 1)
    generation, rest = rest.split('**4.', 1)
    finishing, save = rest.split('**5.', 1)
    assert 'visibly watermarked stock preview or agency comp' in research
    assert layout.count(STORY_FIRST_CROP) == 1
    assert 'Compose the hero, meaningful supporting moment, verified venue feature' in layout
    assert 'source fidelity does not lock the original background' in research
    assert 'both interacting bodies and the space between them' in layout
    assert 'genuine foreshortening, natural motion blur' in layout
    assert 'not optional background imagery to shrink, fade or omit' in layout
    assert generation.count(GENERATE_PHOTOGRAPHIC_UNIT) == 1
    assert 'including the people and their interaction' in generation
    assert 'not a substitute for generating the complete artwork' in generation
    assert 'lookalike is insufficient' in generation
    assert finishing.count(CREATE_DESIGN_AUTHENTICITY_CHECK) == 1
    assert 'compare the final assembled PSD directly and side by side' in finishing
    assert 'ball seams and lettering' in finishing
    assert 'restore the whole photographic interaction together' in finishing
    assert 'enough surrounding photograph to keep anatomy, light, texture and edges continuous' in finishing
    assert 'After each repair, inspect that area again' in finishing
    assert finishing.count(FINAL_PHOTOGRAPHIC_REVIEW) == 1
    assert 'name the exact affected area and the repair or stronger source still needed' in finishing
    assert 'continue the authorised Review delivery with needs_attention' in finishing
    assert 'whole-interaction repairs' in save
    assert 'Never restore a warped generated face, hand, ball' in save
    assert 'smallest coherent region' not in prompt
    assert 'expand only when necessary for facial fidelity' not in prompt
    assert 'one creative image-generation call' in prompt
    assert prompt.count('**6.') == 1
    assert 'SC_EDITION_NUMBER' in prompt and '001 / 100' in prompt
    assert 'SIGNATURE-FREE COLLECTOR COMPOSITION' in prompt
    assert 'Read the JSON back' in prompt and 'create-only mode' in prompt


def test_waiting_job_upgrades_old_finishing_rules_without_changing_its_receipts():
    import morning_design_queue as queue
    key = queue.identity('2026-11-19', 'recommendations', dict(title='The Step Over'))
    current = queue._job_prompt(key, 'The Step Over', 'Preserve both players and their interaction.')
    old = current.replace(STORY_FIRST_CROP, '').replace(GENERATE_PHOTOGRAPHIC_UNIT, '')
    old = old.replace(FINAL_PHOTOGRAPHIC_REVIEW, '')
    old += '\nQueue retry receipt: 00000000-0000-0000-0000-000000000001\n'
    old += '\nQueue output receipt: 00000000-0000-0000-0000-000000000001\n'
    job = dict(id=key, title='The Step Over', prompt=old)
    upgraded = queue._waiting_prompt(job)
    assert all(rule in upgraded for rule in (STORY_FIRST_CROP, GENERATE_PHOTOGRAPHIC_UNIT, FINAL_PHOTOGRAPHIC_REVIEW))
    assert 'Preserve both players and their interaction.' in upgraded
    assert queue._receipt(job) == queue._receipt(dict(job, prompt=upgraded))
    assert queue._waiting_prompt(dict(job, prompt=upgraded)) == upgraded


def test_refresh_and_edit_still_preserve_their_existing_authority():
    refresh, edit = variants()[1:]
    assert 'Do not draft replacement titles' in refresh
    assert 'gid://shopify/Product/123' in refresh
    assert 'existing_product_refresh' in refresh
    assert 'USER-REQUESTED DESIGN CHANGES from the Edit text box' in edit
    assert 'keeping the original file ID' in edit
    assert 'BACKUP PSD' in edit and 'staged PSD' in edit
