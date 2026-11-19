"""Original user-supplied prompt preserved outside the approved footer changes."""
import hashlib
from pathlib import Path
import prompt_library
from ads_footer import COMPACT_FOOTER_RULES
import ads_page

# SHA256 of unchanged sections in the original attached Ads bundle (20 Nov 2026).
ORIGINAL_SECTIONS = {'efa0fc0971b49593dded8edd': 'f5c1f383bab59f772337962a2107c4190e430dd551d7b582f649e18c98d2f770', 'cfcfe59a08413380217b1e93': '144685cdbfc5594315ba6490cb375dfe246c85b51d35591d26d5c34eb43a91d3', '339261a70667ec5a840cfd42': '525fa29b79bb3988ac6758485f9b26cd98b982c6325cd096a8a0d41b3b0a6928', '47d29145c267dba08275967d': '57dbc441bd41a506f0ba60b0014af6798adeb358b5402c01cddcb6a34a8d0585', '1ba92c75f1d0ec42bedc1284': '2611b52d614c9788835918b02f4371d53c0fa3d19a5c57c1f7f356bbc3a994d5', '069d02a52be01c5134ce8e97': '2421ed64bab76fed5469db8d76751197f189afbbb2e299f9ef5809ac35d53ea0', '1776e750294d64f257e3c18c': '080273ce01e91e1146e4128cdf71cf636e9b017c1780b2fee14f354163fcc3b4', '22cc9062177176f35cf380df': '4d645a6645ae99df55959a1c008ac3bab6f4812f4a77e9d78a74ea867f0da20c', '91a51d174a3108ab54cb4f97': 'e0e01cbf427ee4d2c9ce1e67592d7ebf9f403141ee024ae1823f6a45e7be593e', 'ac9d844ecf17b89d0fec1518': '5f3ff0e311a52e4a6949bdd730f39f6d5fb426f09dbf6b47b2351ace7f31936e', '248efab71e6ee82fc37db2ff': 'b901bca18f4f31117197dff8154c5e0fe2111c977c13db981ef8d4cb27bc2ea3', '8c74c7a733cab9f9ae1543d3': '82baa5aa58714b8d589f8766bc918d68ee7dd2bc004d2cb5cc8d667059946f33', '6b90b7332b494163e3f6e616': '656863ac11da2e98231ad2adc1365fe08e6d5b5c0ad373c7ecac9a322d2994b9', '704462a5b422e7982db8880f': '9e873b9e5e17f55b5dab8bf6db596d7720a7e6ea8bca651b7f1930b8f8e6d8b8', '7ca8830571db316b90527e08': '101ca3ebb9c3a0b5813f0248779876c1e5646dbb570e617da6942e86d006dfed', '1c8d3ccf95140414febcbb52': '06961ed6aa643657627b01bcb25dafdf39a410bea8c7f4a5966404ab786443d2'}


def test_non_footer_original_sections_are_byte_exact():
    current = {p.key: p.text for p in prompt_library.catalog()}
    for key, expected in ORIGINAL_SECTIONS.items():
        if key == '7ca8830571db316b90527e08':
            continue  # Project execution/three-line footer alignment is covered separately.
        assert hashlib.sha256(current[key].encode()).hexdigest() == expected, key


def test_standalone_and_google_preserve_baseline_footer_with_shimmer():
    google = Path('prompts/google_demand_gen_v1.txt').read_text(encoding='utf-8')
    for prompt in (ads_page.INSTANT_EXPERIENCE_MASTER_IMAGE_PROMPT_TEMPLATE, google):
        assert 'gold shimmer' in prompt
        assert 'supporting line' in prompt.lower() or 'Line two:' in prompt
        assert 'TWO-LINE COLLECTOR FOOTER' not in prompt
        assert 'Render no supporting sentence' not in prompt
        assert 'FINAL COMPOSITOR DATA' not in prompt
    assert 'approximately bottom 20–23%' in google.replace('\n', ' ')
