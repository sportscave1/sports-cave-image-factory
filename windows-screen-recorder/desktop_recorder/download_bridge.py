"""Configure only this candidate's native-messaging receipt inbox.

The Edge adapter has no network transport. Its registered native host writes
bounded metadata receipts here; downloaded contents never enter this channel.
"""
from pathlib import Path
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import json
import shutil


def configure(root, bridge):
    root, bridge = Path(root).resolve(), Path(bridge).resolve()
    if not (bridge / 'DownloadReceiptHost.exe').is_file():
        raise ValueError('Download receipt host has not been built.')
    from task_recorder.server import instance_lock
    with instance_lock(bridge / 'session-config.lock'):
        return _configure_locked(root, bridge)


def _configure_locked(root, bridge):
    active = bridge / 'active.json'
    if active.exists():
        try:
            previous = json.loads(active.read_text(encoding='utf-8'))
            previous_root = Path(previous['events']).resolve().parent.parent
            expires = datetime.fromisoformat(previous['expires'])
            if expires.tzinfo is None:
                raise ValueError('Session expiry must include its time zone.')
        except (ValueError, KeyError, TypeError) as error:
            raise ValueError('Existing download session is invalid; preserve and inspect active.json before replacing it.') from error
        if expires > datetime.now(timezone.utc) and previous_root != root:
            raise ValueError('Download receipt host belongs to another unexpired candidate session; leave it unchanged.')
        backup = bridge / ('active-before-' + str(uuid4()) + '.json')
        shutil.copyfile(active, backup)
    session = str(uuid4())
    inbox = root / 'download-receipts' / session
    inbox.mkdir(parents=True)
    config = dict(session=session, events=str(inbox),
                  expires=(datetime.now(timezone.utc)+timedelta(hours=12)).isoformat())
    temporary = bridge / 'active.json.tmp'
    temporary.write_text(json.dumps(config), encoding='utf-8')
    temporary.replace(active)
    return {'SC_RECORDER_DOWNLOAD_EVENTS': str(inbox), 'SC_RECORDER_DOWNLOAD_SESSION':session}
