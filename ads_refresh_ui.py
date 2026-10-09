"""Presentation helpers scoped to Creative Refresh; no generation or provider writes."""
import json


def styles(st):
    css = '''<style>
    .stMainBlockContainer:has(.st-key-ads-refresh-page-marker) {padding-top:2.5rem!important}
    .stMainBlockContainer:has(.st-key-ads-refresh-page-marker) h1 {font-size:1.65rem;padding:0 0 .3rem}
    .stMainBlockContainer:has(.st-key-ads-refresh-page-marker) h3 {font-size:1.08rem;padding:.25rem 0}
    .stMainBlockContainer:has(.st-key-ads-refresh-page-marker) [data-testid="stVerticalBlock"] {gap:.5rem}
    .stMainBlockContainer:has(.st-key-ads-refresh-page-marker) [data-testid="stVerticalBlockBorderWrapper"] {border-radius:5px;box-shadow:none}
    .stMainBlockContainer:has(.st-key-ads-refresh-page-marker) [data-testid="stFileUploaderDropzone"] {min-height:64px;padding:.3rem}
    .stMainBlockContainer:has(.st-key-ads-refresh-page-marker) button {min-height:32px;border-radius:4px}
    .st-key-ads-refresh-ie-grid [data-testid="stColumn"] {min-width:0}
    .st-key-ads-refresh-ie-grid img {max-height:190px;object-fit:contain}
    .st-key-ads-refresh-ie-grid [class*="st-key-ads-ie-concept-copy-field"] textarea {height:76px!important;min-height:76px!important;max-height:160px!important;resize:vertical!important}
    .st-key-ads-refresh-ie-grid [class*="st-key-ads-ie-concept-copy-field"]:not([class*="primary_text"]) textarea {height:50px!important;min-height:50px!important}
    @media(max-width:1050px) {
      .st-key-ads-refresh-ie-grid [data-testid="stHorizontalBlock"]:has([class*="st-key-ads-ie-concept-"]) {flex-direction:column}
      .st-key-ads-refresh-ie-grid [data-testid="stHorizontalBlock"]:has([class*="st-key-ads-ie-concept-"])>[data-testid="stColumn"] {flex:1 1 100%!important;width:100%!important}
    }
    @media(max-width:720px) {
      .st-key-ads-refresh-output-grid [data-testid="stHorizontalBlock"],
      .st-key-ads-refresh-actions [data-testid="stHorizontalBlock"] {flex-direction:column}
      .st-key-ads-refresh-output-grid [data-testid="stColumn"],
      .st-key-ads-refresh-actions [data-testid="stColumn"] {width:100%!important;flex:1 1 100%!important;min-width:0!important}
    }
    </style>'''
    css = css.replace('.stMainBlockContainer:has(.st-key-ads-refresh-page-marker)',
                      '[data-testid="stMainBlockContainer"]:has(#sc-refresh-page)')
    st.markdown(css, unsafe_allow_html=True)
    with st.container(key='ads-refresh-page-marker'):
        st.markdown('<span id="sc-refresh-page" hidden></span>', unsafe_allow_html=True)


def card_direction(result, position):
    context = result.get('creative_refresh_context') or {}
    source = context.get('source_winner') or {}
    cards = source.get('carousel_cards') or source.get('cards') or []
    card = next((c for c in cards if c.get('position') == position), {})
    direction = ' · '.join(str(card[k]) for k in ('scene', 'role') if card.get(k))
    return (f'Card {position} — Original Winner → Refreshed Card {position}',
            direction or 'Preserve this source card’s observed concept and role; create a new execution.')


def execution_review(ads, result, workflow):
    st = ads.st
    notes = workflow.setdefault('ad_notes', {})
    records = notes.get('refresh_executions') or []
    # Historical analysis is preserved, never required or marked reviewed here.
    # Generated prompts remain available without asking users to author JSON.
    records = notes.get('refresh_executions')
    if not isinstance(records, list):
        return
    available = {position: record for position, record in enumerate(records, 1)
                 if isinstance(record, dict) and record.get('image_prompt')}
    if not available:
        return
    # One reusable viewer avoids creating N heavyweight clipboard iframes/code blocks
    # on every rerun, including while the prompt section is closed.
    with st.expander('Card image prompts', expanded=False):
        position = st.selectbox('Card prompt', list(available), format_func=lambda p: f'Card {p} — Refreshed image',
                                key=f"ads-refresh-prompt-card::{result['context_key']}")
        record = available[position]
        for label in ('keep', 'change', 'improvement'):
            st.caption(f"{label.title()}: {record.get(label) or 'Not supplied'}")
        ads.render_prompt_copy_button(record['image_prompt'],
            key=f"refresh-card-prompt::{result['context_key']}::{position}", label='Copy Prompt', compact=True)
        st.code(record['image_prompt'], language=None, wrap_lines=True)
