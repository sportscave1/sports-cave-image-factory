"""Product Upload presentation helpers; no changes to the standalone Mockups page."""
import json
from pathlib import Path
import streamlit.components.v1 as components


def focus_generation(token):
    if not token:
        return
    # One token per explicit Generate click. Polling/rerenders must not steal
    # the user's scroll position after that initial navigation.
    script = (Path(__file__).parent / 'components/product_uploads/focus_generation.js').read_text(encoding='utf-8')
    components.html('<script>const focusToken=' + json.dumps(token) + ';\n' + script + '</script>', height=0)
