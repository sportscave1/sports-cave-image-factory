"""Speed-only local publisher. Reuses Studio locking and Windows DPAPI trust.

Native Codex scheduling owns the coding run. This worker reliably delivers its
reports without a signed-in browser, retries failures and exposes no code API.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts' / 'studio')]
from companion import instance_lock
from device_trust import protect
from scripts.speed_daily import atomic
from speed_optimisation import sydney_day, validate_report

ORIGIN = 'https://sports-cave-image-factory.onrender.com'
HOME = ROOT / '.local-data' / 'speed'


def configure(home=HOME):
    home.mkdir(parents=True, exist_ok=True)
    path = home / 'publisher.json'
    if path.exists():
        config = json.loads(path.read_text(encoding='utf-8'))
        token = protect(bytes.fromhex(config['protected']), True).decode()
    else:
        token = secrets.token_urlsafe(48)
        atomic(path, {'protected': protect(token.encode()).hex(), 'origin': ORIGIN})
    return {'token_sha256': hashlib.sha256(token.encode()).hexdigest(), 'origin': ORIGIN}


def session(home=HOME):
    import requests
    config = json.loads((home / 'publisher.json').read_text(encoding='utf-8'))
    if config['origin'] != ORIGIN:
        raise ValueError('Speed publisher origin changed.')
    token = protect(bytes.fromhex(config['protected']), True).decode()
    client = requests.Session()
    client.trust_env = False
    client.headers.update(Authorization='Bearer ' + token, Accept='application/json')
    return client


def review(home=HOME):
    with session(home) as client:
        response = client.get(ORIGIN + '/api/speed/companion', timeout=30, allow_redirects=False)
        response.raise_for_status()
        result = response.json()
    atomic(home / 'remote-review.json', result)
    return result


def flush(home=HOME):
    acknowledgements = home / 'published'
    acknowledgements.mkdir(parents=True, exist_ok=True)
    results = []
    with session(home) as client:
        paths = sorted(home.glob('????-??-??.json'))[-90:] + sorted((home / 'outbox').glob('*.json'))[:100]
        for path in paths:
            value = validate_report(json.loads(path.read_text(encoding='utf-8')))
            ack = acknowledgements / (value['id'] + '.json')
            if ack.exists():
                continue
            response = client.post(ORIGIN + '/api/speed/companion', json=value,
                                   timeout=30, allow_redirects=False)
            response.raise_for_status()
            receipt = response.json()
            if receipt.get('published') != value['id'] or receipt.get('date') != value['date']:
                raise RuntimeError('Speed publication receipt mismatch.')
            atomic(ack, receipt)
            results.append(receipt)
    return results


def queue(path, home=HOME):
    value = validate_report(json.loads(path.read_text(encoding='utf-8')))
    outbox = home / 'outbox'
    outbox.mkdir(parents=True, exist_ok=True)
    target = outbox / (value['id'] + '.json')
    if target.exists() and json.loads(target.read_text(encoding='utf-8')) != value:
        raise ValueError('Queued immutable report ID already has different evidence.')
    atomic(target, value)
    return {'queued': value['id']}


def worker(home=HOME):
    home.mkdir(parents=True, exist_ok=True)
    with instance_lock(home / 'companion.lock'):
        atomic(home / 'companion-state.json', {'pid': os.getpid(), 'status': 'running', 'date': sydney_day()})
        while not (home / 'stop-companion').exists():
            try:
                published = flush(home)
                state = {'pid': os.getpid(), 'status': 'running', 'published': published,
                         'checked_at': time.time()}
            except Exception as error:
                # Never persist exception text, request headers or credentials.
                state = {'pid': os.getpid(), 'status': 'retry_pending',
                         'error_type': type(error).__name__, 'checked_at': time.time()}
            atomic(home / 'companion-state.json', state)
            time.sleep(60)


def start(home=HOME):
    configure(home)
    (home / 'stop-companion').unlink(missing_ok=True)
    # A lifetime Windows lock makes duplicate native scheduler starts harmless.
    pythonw = Path(sys.executable).with_name('pythonw.exe')
    subprocess.Popen([str(pythonw if pythonw.exists() else sys.executable), '-B', __file__, 'supervise'],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=subprocess.CREATE_NO_WINDOW)
    return {'status': 'starting', 'origin': ORIGIN}


def supervise(home=HOME):
    with instance_lock(home / 'supervisor.lock'):
        pythonw = Path(sys.executable).with_name('pythonw.exe')
        while not (home / 'stop-companion').exists():
            child = subprocess.Popen([str(pythonw if pythonw.exists() else sys.executable),
                                      '-B', __file__, 'worker'],
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            child.wait()
            if not (home / 'stop-companion').exists():
                atomic(home / 'companion-state.json', {'status': 'recovering', 'checked_at': time.time()})
                time.sleep(15)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['configure', 'start', 'worker', 'supervise', 'flush', 'review', 'status', 'queue'])
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.action == 'configure': result = configure()
    elif args.action == 'start': result = start()
    elif args.action == 'worker': return worker()
    elif args.action == 'supervise': return supervise()
    elif args.action == 'flush': result = flush()
    elif args.action == 'review': result = review()
    elif args.action == 'queue':
        if not args.report: parser.error('queue requires --report')
        result = queue(args.report)
    else:
        result = json.loads((HOME / 'companion-state.json').read_text(encoding='utf-8'))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
