"""Versioned email adaptation of Ads realism; intentionally no Ads module import."""
from functools import lru_cache
from pathlib import Path
from sports_cave_physical_realism import build as physical_realism
from sports_cave_prompt_blocks import SPORTS_CAVE_PREMIUM_VISUAL_REALISM_V3


@lru_cache(maxsize=1)
def visual_contract():
    return '\n\n'.join((
        Path(__file__).with_name('prompts').joinpath('sports_cave_email_visual_v1.txt').read_text(encoding='utf-8').strip(),
        SPORTS_CAVE_PREMIUM_VISUAL_REALISM_V3,
        physical_realism(),
    ))
