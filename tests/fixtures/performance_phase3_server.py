from streamlit.web.server.starlette import App
from static_asset_compression import StaticAssetCompression
app=StaticAssetCompression(App('tests/fixtures/performance_phase3.py'))
