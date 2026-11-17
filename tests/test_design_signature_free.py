"""Signature policy is consistent across the three active design handoffs."""
from design_signature_free import SIGNATURE_FREE_COMPOSITION
from design_collector_background import BACKGROUND_RESEARCH, COLLECTOR_BACKGROUND
from design_collector_titles import COLLECTOR_TITLE_GUIDANCE
from home_design_refresh import _refresh_prompt
from home_morning_brief_actions import _prompt


def test_all_design_handoffs_use_the_same_signature_free_composition():
    new = _prompt('Collector', 'Verified sporting story')
    edit = _prompt('Collector', 'Verified sporting story', edit={
        'source': {'id': 'id:original', 'rev': 'abc', 'path_display': '/Review/Collector.psd'},
        'metadata': {},
    })
    refresh = _refresh_prompt(dict(title='Collector', product_id='123', sessions=40,
                                   suggestion='Improve hierarchy'), 'https://example.com/product')
    for prompt in (new, edit, refresh):
        assert prompt.count(SIGNATURE_FREE_COMPOSITION) == 1
        assert 'remove an existing signature only when requested' in prompt
        assert 'Preserve all other approved elements.' in prompt
        for obsolete in ('search both web and image results', 'verified signature assets',
                         'Keep verified signatures', 'Restore each verified signature',
                         'Preserve verified signatures', 'Place a verified signature',
                         'verified signature extraction and placement'):
            assert obsolete not in prompt
        assert 'SC_EDITION_NUMBER' in prompt
        assert 'SMART UPLOAD' in prompt or 'Smart Upload JSON' in prompt
        assert prompt.count(BACKGROUND_RESEARCH) == 1
        assert prompt.count(COLLECTOR_BACKGROUND) == 1
        assert prompt.count(COLLECTOR_TITLE_GUIDANCE) == 1
        assert 'four to six short candidates' in prompt
        assert 'one sentence explaining its connection' in prompt
        assert 'Never invent a commentary line, fan chant or nickname.' in prompt
        assert 'Honour explicit user locks on approved titles and artwork' in prompt
        assert 'Before the first save and during the existing second-pass review' in prompt
        assert 'Consider a few short, cinematic headline options' not in prompt
        assert 'If in doubt, use the athlete' not in prompt
        assert 'Default to timeless player' not in prompt
        assert 'title first' not in prompt
        assert 'COMPOSE THE BADGE INTO THE ARTWORK' in prompt
        assert 'Before generation, plan their intended position' in prompt
        assert 'non-destructive tonal, colour and finish adjustments are permitted' in prompt
        assert 'never change its edition text, rasterise it' in prompt
        assert 'original editable text layer with the same name' in prompt
        assert 'Do not automatically retain the master' in prompt
        assert 'Preserve the exact official badge asset' not in prompt
        assert 'continue with the original setting or a non-specific abstract environment' in prompt
        assert 'without introducing an extra approval stage' in prompt
        assert 'Do not source or replace a background when the background is locked.' in prompt
        assert 'Never fade or obscure the face, hands' in prompt
        assert 'appropriate basis for use' in prompt
        assert 'Do not repeat the same sweep, stadium placement or fade' in prompt
        assert 'Apply the treatment only to the background.' not in prompt
        assert 'Build a cohesive vintage background' not in prompt
    assert new.index(BACKGROUND_RESEARCH) < new.index('Step 3. Define the composition')
    assert edit.index(BACKGROUND_RESEARCH) < edit.index('Step 3. Define the composition')
    assert refresh.index(BACKGROUND_RESEARCH) < refresh.index('3. Generate and inspect two complete designs')
