"""The withdrawn Beta stays recoverable but never enters active generation."""
import hashlib
from pathlib import Path
import ads_page as ads
import ads_ie_badge as archived
from prompt_library import catalog


def test_beta_asset_is_retained_without_active_overlay_instructions():
    asset = Path('static/ads/blackened-gunmetal-sports-cave-medal.png').read_bytes()
    assert hashlib.sha256(asset).hexdigest() == archived.BADGE_SHA256
    prompt = ads.build_ads_result_record('Synthetic Edition', 'NBA', 'USA', 'Instant Experience')['master_prompt']
    assert archived.VERSION not in prompt
    assert archived.BADGE_URL not in prompt
    assert not any(row.path == 'ads_ie_badge.py' for row in catalog())
