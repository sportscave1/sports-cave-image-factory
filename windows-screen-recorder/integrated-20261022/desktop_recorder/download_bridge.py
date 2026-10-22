"""Configure only this candidate's native-messaging receipt inbox.

The Edge adapter has no network transport. Its registered native host writes
bounded metadata receipts here; downloaded contents never enter this channel.
"""
from pathlib import Path
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import json


def configure(root, bridge):
    root, bridge = Path(root).resolve(), Path(bridge).resolve()
    if not (bridge / 'DownloadReceiptHost.exe').is_file():
        raise ValueError('Download receipt host has not been built.')
    session = str(uuid4())
    inbox = root / 'download-receipts' / session
    inbox.mkdir(parents=True)
    config = dict(session=session, events=str(inbox),
                  expires=(datetime.now(timezone.utc)+timedelta(hours=12)).isoformat())
    temporary = bridge / 'active.json.tmp'
    temporary.write_text(json.dumps(config), encoding='utf-8')
    temporary.replace(bridge / 'active.json')
    return {'SC_RECORDER_DOWNLOAD_EVENTS': str(inbox), 'SC_RECORDER_DOWNLOAD_SESSION':session}
