"""Versioned email adaptation of Ads realism; intentionally no Ads module import."""
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def visual_contract():
    return Path(__file__).with_name('prompts').joinpath('sports_cave_email_visual_v1.txt').read_text(encoding='utf-8').strip()
