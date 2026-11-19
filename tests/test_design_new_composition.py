"""New-design creative guidance stays separate from existing edit and delivery rules."""
from home_morning_brief_actions import _prompt
from design_new_composition import (
    COMPLEMENTARY_IMAGES, COMPLETE_COMPOSITION, COLLECTOR_TYPOGRAPHY,
    PURPOSEFUL_ABSTRACT, REVIEW_RELATIONSHIPS,
)
from design_collector_assets import NEW_BADGE_LAYOUT, COLLECTOR_LAYER_RULES
from design_motorsport import MOTORSPORT_ARTWORK


def test_new_design_composes_sources_type_and_badge_without_extra_checkpoints():
    prompt = _prompt('Collector', 'Verified story')
    for guidance in (COMPLEMENTARY_IMAGES, COMPLETE_COMPOSITION, COLLECTOR_TYPOGRAPHY,
                     PURPOSEFUL_ABSTRACT, REVIEW_RELATIONSHIPS, NEW_BADGE_LAYOUT):
        assert prompt.count(guidance) == 1
    assert prompt.index(COMPLEMENTARY_IMAGES) < prompt.index('**2.')
    assert prompt.count(MOTORSPORT_ARTWORK) == 1
    assert prompt.index(MOTORSPORT_ARTWORK) < prompt.index('**2.')
    assert prompt.index(COMPLETE_COMPOSITION) < prompt.index('**3.')
    assert prompt.index('**4.') < prompt.index(REVIEW_RELATIONSHIPS) < prompt.index('**5.')
    assert prompt.index('**2.') < prompt.index(NEW_BADGE_LAYOUT) < prompt.index('**3.')
    assert 'same original-source, image-quality and photographic-authenticity checks' in prompt
    assert 'For an event-specific design, supporting photographs must belong to that verified event.' in prompt
    assert 'select the strongest hero using the existing best-image rules' in prompt
    assert 'Run a focused search for that complementary photograph' in prompt
    assert 'Use a supporting photograph only when it adds meaning and remains subordinate to the hero.' in prompt
    assert 'continue with the hero and verified setting' in prompt
    assert 'Include the hero and selected secondary source with its distinct story role' in prompt
    assert "start with the supporting face smaller than the hero's face" in prompt
    assert 'selective softness only on non-essential transitions' in prompt
    assert 'At 100%, verify the supporting likeness, crop and transition into the environment' in prompt
    assert 'not additional image-generation calls' in prompt
    assert '65–85% of the main title block’s width' in prompt
    assert 'at least two badge arrangements that test different sizes and positions using PSD transforms only' in prompt
    assert prompt.count(COLLECTOR_LAYER_RULES) == 1
    assert 'Record unresolved placement or legibility as needs_attention' in prompt
    assert 'one full generation, verified final Review PSD, matching JSON and final display' in prompt
    assert 'Retry image generation once only if a technical failure produced no usable output' in prompt
    assert 'Use abstract treatment selectively:' not in prompt
    assert 'Refine their scale, alignment, line spacing and separation' not in prompt


def test_edit_inherits_shared_creative_rules():
    prompt = _prompt('Collector', 'Verified story', edit={
        'source': {'id': 'id:Original', 'rev': 'abcdef123', 'path_display': '/Review/Collector.psd'},
        'metadata': {'shopify_product_id': 'gid://shopify/Product/123'},
    })
    for guidance in (COMPLEMENTARY_IMAGES, COMPLETE_COMPOSITION, COLLECTOR_TYPOGRAPHY,
                     PURPOSEFUL_ABSTRACT, REVIEW_RELATIONSHIPS, NEW_BADGE_LAYOUT,
                     MOTORSPORT_ARTWORK):
        assert prompt.count(guidance) == 1
    assert 'USER-REQUESTED DESIGN CHANGES from the Edit text box' in prompt


def test_new_design_replaces_generation_conflicts_without_blocking_review():
    prompt = _prompt('Collector', 'Verified story')
    for obsolete in ('Keep the generation as the visual baseline',
                     'Generate the full artwork with subject',
                     'Use the strongest verified pairing by default',
                     'Test the selected supporting photograph in disconnected areas',
                     'A simple, elegant border is equally suitable',
                     'Any generated people or sporting objects are placement guides only',
                     'Completely cover generated renditions'):
        assert obsolete not in prompt
    for requirement in ('separate editable masked layers',
                        'Do not automatically paste whole source cutouts over them.',
                        'Reject assumed feelings, invented relationships with a city',
                        'Corner ornaments are optional, never the default.',
                        'Continue authorised review saves and delivery',
                        'continue without pausing for approval'):
        assert requirement in prompt


def test_layout_review_precedes_only_generation_and_final_handoff():
    prompt = _prompt('Collector', 'Verified story')
    assert prompt.index('**Creative review before generation.**') < prompt.index('**3.')
    assert 'build a scaled layout' in prompt
    assert 'one creative image-generation call' in prompt
    assert 'never triggers another generation' in prompt
    assert 'Keep the collector treatment adjustable on a separate layer or with a mask' in prompt
    assert 'Composition draft · generation 1 of 1' in prompt
    assert 'Final artwork · rendered from the saved PSD' in prompt
    assert 'reposition it or omit it' not in prompt
    assert 'Integrate the layer into the full generation' not in prompt
    assert 'Reassess the planned footprint against the generated artwork' not in prompt
    assert 'create-only mode' in prompt and 'Read the JSON back' in prompt


def test_venue_and_master_fallbacks_preserve_forward_flow():
    prompt = _prompt('Collector', 'Verified story')
    assert prompt.count('Where a verified venue view is available') >= 3
    assert 'abstract fallback makes no claim to depict the actual venue' in prompt
    assert 'otherwise use verified dimensions and a reserved plaque footprint' in prompt
    assert 'review the reserved footprint provisionally and run them once the master is available, before saving the final PSD' in prompt
    assert prompt.index('If master access was deferred, first test both plaque placements') < prompt.index('Save just the final')


def test_generation_foundation_lettering_border_and_badge_views():
    prompt = _prompt('Australia in Papaya', 'Keep the approved title.')
    layout, generation = prompt.split('**3.', 1)
    generation, finishing = generation.split('**4.', 1)
    assert 'Keep approved wording.' in layout
    assert 'Generate the finished title treatment in generation 1' in layout
    assert 'real plaque and live number visible, then hide both' in layout
    assert '3% of the shorter canvas dimension' in layout
    assert '60 px on the 2835 × 2004 master' in layout
    assert 'Scale that inset proportionally for the generation resolution' in layout
    assert 'repeat the selected border geometry above, including all four sides' in generation
    assert 'Exclude plaque, number, placeholder outlines and seals' in generation
    assert 'visible working copy' in generation
    assert 'stretched samples, generic shapes or broad photographic strips' in generation
    assert 'Limit other PSD work to a named defect or required photographic source restoration' in generation
    assert 'stray question marks' in finishing
    assert 'generation 1 beside the final render at equal 250 px widths' in finishing
    assert 'Restore surroundings from generation 1' in finishing


def test_fan_titles_and_visible_layout_decisions_reach_first_generation():
    prompt = _prompt('Collector', 'Suggested title: New Chapter')
    layout, rest = prompt.split('**3.', 1)
    for requirement in ('What do fans actually call this athlete', 'original wordplay joining two verified meanings',
                        "Treat the brief's suggested title as one candidate unless explicitly locked",
                        'Test the strongest suitable source in the actual layout',
                        'Compare the abstract layer on and off at 250 px',
                        'Test without glow, shadow or reflection',
                        'Inspect actual title lettering, visible abstraction, hero integration'):
        assert requirement in layout
    assert "Replace the brief's suggested title only when" not in prompt
    assert 'For Australia in Papaya' not in prompt
    assert 'natural hair and fabric edges and internal gaps' in rest
    assert 'without blurring the silhouette, repainting skin or fading anatomy' in rest
    assert 'one creative image-generation call' in rest
    assert 'never triggers another generation' in rest


def test_dark_arena_direction_survives_prompt_assembly_and_finishing():
    prompt = _prompt('Collector', 'Verified hockey or NBA story')
    research, rest = prompt.split('**2.', 1)
    layout, rest = rest.split('**3.', 1)
    generation, rest = rest.split('**4.', 1)
    finishing, saving = rest.split('**5.', 1)
    assert 'For hockey and NBA, retain the chosen venue feature and placement' in research
    assert prompt.count('**HOCKEY AND NBA — DARK ABSTRACT COLLECTOR DIRECTION**') == 1
    assert 'greater visual presence than the subdued arena layer' in layout
    assert 'selected venue feature retained subtly in place' in generation
    assert 'predominantly dark abstract setting, sparse team-colour marks' in finishing
    assert 'retaining the reviewed dark abstract hierarchy and subdued venue' in saving
    assert 'For sports other than hockey and NBA' in layout
    assert 'fine brushed antique-gold edges or inlays' in layout
    assert 'fine brushed antique-gold contours or inlays' in generation
    assert 'fine antique-gold detail defines the abstract forms' in finishing
    assert 'integrated gold detail and restrained team-colour balance' in saving
    assert 'one creative image-generation call' in generation
    assert 'never generate again for visual criticism' in finishing
    assert 'Do not restore malformed generated corners over a corrected border' in saving
    assert 'short inner corner returns derived from the sporting story' not in prompt


def test_action_emotion_pairing_and_required_darts_action_reach_all_shared_flows():
    from home_design_refresh import _refresh_prompt
    import morning_design_queue as queue
    variants = [
        _prompt('The Giant Killer', 'Verified darts tribute with an emotional hero.'),
        _refresh_prompt(dict(title='Current darts design', product_id='123'), 'https://example.test/products/darts'),
        _prompt('The Giant Killer', 'Verified darts tribute', edit={
            'source': {'id':'id:art', 'rev':'r1', 'path_display':'/Review/Darts.psd'},
            'metadata': {'upload_intent':'new_product'}}),
    ]
    for prompt in variants:
        research, rest = prompt.split('**2.', 1)
        layout, rest = rest.split('**3.', 1)
        generation, rest = rest.split('**4.', 1)
        finishing = rest.split('**5.', 1)[0]
        assert prompt.count(COMPLEMENTARY_IMAGES) == 1
        assert 'Darts always requires a verified throwing-action photograph' in research
        assert 'If only one suitable source is available, use a verified throwing shot as the hero' in research
        assert 'every darts layout shows genuine throwing action' in layout
        assert 'every darts design must retain its genuine throwing-action photograph' in generation
        assert 'Do not turn a reaction photograph into invented sporting action' in generation
        assert 'never two emotional shots; when a secondary is used with an emotional hero, it must show action' in finishing
        assert 'one creative image-generation call' in generation
        assert 'never generate again for visual criticism' in finishing
    key = queue.identity('2026-11-19', 'recommendations', {'title':'Darts tribute'})
    current = queue._job_prompt(key, 'Darts tribute', 'Keep the verified sporting story.')
    saved = dict(id=key, title='Darts tribute', prompt=current.replace(COMPLEMENTARY_IMAGES, 'Old optional imagery guidance.'))
    upgraded = queue._waiting_prompt(saved)
    assert COMPLEMENTARY_IMAGES in upgraded and 'Keep the verified sporting story.' in upgraded
    assert queue._receipt(dict(saved, prompt=upgraded)) == queue._receipt(saved)
    assert queue._waiting_prompt(dict(saved, prompt=upgraded)) == upgraded


def test_rivalry_direction_survives_all_shared_stages_and_queue_upgrade():
    from home_design_refresh import _refresh_prompt
    from design_collector_titles import NEW_DESIGN_TITLE_GUIDANCE
    import morning_design_queue as queue

    brief = 'Verified rivalry; select natural opposing profiles.'
    variants = [
        _prompt('Rivals', brief),
        _refresh_prompt(dict(title='Rivals', product_id='123'), 'https://example.test/rivals'),
        _prompt('Rivals', brief, edit={
            'source': {'id': 'id:rivals', 'rev': 'r1', 'path_display': '/Review/Rivals.psd'},
            'metadata': {'upload_intent': 'new_product'}}),
    ]
    for prompt in variants:
        research, rest = prompt.split('**2.', 1)
        layout, rest = rest.split('**3.', 1)
        generation, rest = rest.split('**4.', 1)
        finishing, saving = rest.split('**5.', 1)
        assert 'the left rival looks right and the right rival looks left' in research
        assert 'Never turn heads, redirect eyes, manufacture expressions' in research
        assert 'two intense opposing portraits are valid' in research
        assert 'Do not shrink or omit one rival' in layout
        assert 'background grading and hero-dominance wording must not weaken the confrontation' in layout
        assert 'carry the reviewed inward gaze, fierce natural expressions, balanced scale and interaction' in generation
        assert 'Rivalry face-offs may use two intense opposing portraits' in generation
        assert 'For rivalries, verify both primary rivals remain readable' in finishing
        assert 'both primary rivals and their face-off/competitive relationship' in saving
        assert 'one creative image-generation call' in generation
        assert 'Completion requires one full generation, verified final Review PSD, matching JSON and final display' in prompt
    assert 'same four-candidate comparison' in variants[0]
    assert 'Do not draft replacement titles' in variants[1]
    assert 'USER-REQUESTED DESIGN CHANGES from the Edit text box' in variants[2]
    key = queue.identity('2026-11-19', 'rivalries', {'title': 'Rivals'})
    current = queue._job_prompt(key, 'Rivals', brief)
    saved = dict(id=key, title='Rivals', prompt=current.replace(COMPLEMENTARY_IMAGES, 'Old source rules.').replace(NEW_DESIGN_TITLE_GUIDANCE, 'Old title rules.'))
    upgraded = queue._waiting_prompt(saved)
    assert COMPLEMENTARY_IMAGES in upgraded and NEW_DESIGN_TITLE_GUIDANCE in upgraded
    assert brief in upgraded and queue._receipt(saved) == queue._receipt(dict(saved, prompt=upgraded))
    assert queue._waiting_prompt(dict(saved, prompt=upgraded)) == upgraded
