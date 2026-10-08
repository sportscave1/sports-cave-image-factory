"""Loopback fixture with production ASGI static-asset handling; no business APIs."""
import os
from streamlit.web.server.starlette import App

app=App('tests/fixtures/performance_phase2.py')
if os.environ.get('PHASE2_BASELINE')!='1':
    from static_asset_compression import StaticAssetCompression
    app=StaticAssetCompression(app)
