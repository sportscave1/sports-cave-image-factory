"""Canonical sports and revision-safe persistence for automatic Review publishing."""
import json
import pytest
from design_review_metadata import handoff_paths, parse_handoff, save_review_sport
from tests.test_design_review_title import Dropbox
from product_upload_dropbox import REVIEW


def artwork(**fields):
    provider = Dropbox()
    source = provider.save('id:art', REVIEW + '/Anthony Edwards.psd', b'psd')
    value = dict(design_title='Anthony Edwards Timberwolves Wall Art', sport='Basketball', league='NBA',
                 teams=['Minnesota Timberwolves'], athletes=['Anthony Edwards'], intended_collections=['nba'],
                 upload_intent='existing_product_refresh', existing_shopify_product_id='gid://shopify/Product/123',
                 design_origin='designs_to_refresh', review_status='needs_attention', review_notes='Check the hands.',
                 morning_design_job_id='receipt', dropbox_file_id=source['id'], dropbox_revision=source['rev'],
                 dropbox_path=source['path_display'])
    value.update(fields)
    sidecar = provider.save('id:json', handoff_paths(source['path_display'])[0], json.dumps(value).encode())
    return provider, source, sidecar, value


@pytest.mark.parametrize(('sport','league','expected'), [('Basketball','NBA','NBA'), ('basketball / nba','NBA','NBA'),
    ('','NBA','NBA'), ('Unknown','NBA','NBA'), ('Hockey','NHL','Ice Hockey'),
    ('Motorsport','F1','Formula One'), ('Soccer','','Football')])
def test_structured_sports_resolve_to_upload_categories(sport, league, expected):
    _, source, _, value = artwork(sport=sport, league=league, intended_collections=[])
    assert parse_handoff(json.dumps(value), source)['sport'] == expected


def test_saves_canonical_sport_preserving_refresh_target_and_all_quality_notes():
    provider, source, sidecar, value = artwork()
    details = save_review_sport(provider, source)
    current = provider.metadata_if_present(sidecar['id'])
    saved = json.loads(provider.files[current['id']][1])
    assert saved == dict(value, sport='NBA')
    assert current['id'] == sidecar['id'] and current['rev'] != sidecar['rev']
    assert details['sport'] == 'NBA' and details['review_status'] == 'needs_attention'
    assert details['shopify_product_id'] == value['existing_shopify_product_id']
    provider.api.upload_revision.reset_mock()
    save_review_sport(provider, source)
    provider.api.upload_revision.assert_not_called()


def test_manual_sport_is_saved_without_approving_unresolved_artwork():
    provider, source, sidecar, value = artwork(sport=None, league=None, intended_collections=[])
    details = save_review_sport(provider, source, 'NBA')
    assert details['sport'] == 'NBA' and details['review_status'] == 'needs_attention'
    assert json.loads(provider.files[sidecar['id']][1]) == dict(value, sport='NBA')


def test_sport_write_rejects_psd_revision_change():
    provider, source, sidecar, _ = artwork()
    provider.save(source['id'], source['path_display'], b'new psd')
    with pytest.raises(ValueError, match='PSD changed'):
        save_review_sport(provider, source)
    provider.api.upload_revision.assert_not_called()
    assert provider.metadata_if_present(sidecar['id']) == sidecar


def test_ambiguous_structured_evidence_does_not_guess_from_the_title():
    _, source, _, value = artwork(sport=None, league=None, intended_collections=['nba', 'cricket'])
    assert parse_handoff(json.dumps(value), source)['sport'] == ''
