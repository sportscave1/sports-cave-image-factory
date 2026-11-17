"""Presentation-only bridge between the Streamlit status and the OS top-bar slot."""
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def source():
    return (Path(__file__).parent / 'components' / 'ads_posting_status.html').read_text(encoding='utf-8')


def install(st):
    import streamlit.components.v1 as components
    components.html(source(), height=0, width=0)
