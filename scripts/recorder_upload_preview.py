"""Isolated Phase 6 upload cards: real renderer/encoders, disposable SQL.

The five base images are explicitly synthetic test fixtures. Lifestyle uploads
are selected through Windows pickers from the verified retained downloads.
No model generation, cloud credentials, live intake or production writes.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))


def application():
    import product_upload_mockups_preview as preview
    local = preview.application()  # Clears credentials and denies external HTTP.
    from streamlit.web.server.starlette import App
    return App(str(ROOT / 'tests/fixtures/recorder_upload_cards.py'), routes=local._user_routes)


if __name__ == '__main__':
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=18962)
    args = parser.parse_args()
    app = application()
    try:
        uvicorn.run(app, host='127.0.0.1', port=args.port, access_log=False)
    finally:
        import product_upload_mockups_preview as preview
        db, patch, _ = preview.STATE['local'].state.fixture
        patch.undo()
        db.close()
