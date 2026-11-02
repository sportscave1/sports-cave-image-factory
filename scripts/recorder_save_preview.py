"""Actual Save all UI and orchestration with local disk/SQL boundaries only."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
STATE = {}


def application(source_run, destination):
    import product_upload_mockups_preview as preview
    preview.application()  # Clears credentials and forbids external HTTP.
    from tests.fixtures.recorder_disk_outputs import DiskOutputs
    from streamlit.web.server.starlette import App
    source = Path(source_run).resolve()
    if not (source / 'recorder-upload-receipt.json').is_file():
        raise ValueError('A previously accepted recorder upload run is required')
    STATE.update(source=source, disk=DiskOutputs(destination))
    return App(str(ROOT / 'tests/fixtures/recorder_save_cards.py'))


if __name__ == '__main__':
    sys.modules['recorder_save_preview'] = sys.modules[__name__]
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-run', required=True)
    parser.add_argument('--destination', required=True)
    parser.add_argument('--port', type=int, default=18964)
    args = parser.parse_args()
    uvicorn.run(application(args.source_run, args.destination), host='127.0.0.1', port=args.port)
