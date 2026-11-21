"""Local daily claim/completion handshake shared by native scheduled runs."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from speed_optimisation import sydney_day, validate_report


def atomic(path, value):
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def begin(home):
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    day = sydney_day()
    lock = home / 'active.json'
    try:
        # Exclusive creation is the cross-process guard; no guessed lease expiry.
        with lock.open('x', encoding='utf-8') as stream:
            claim = {'id': str(uuid.uuid4()), 'date': day}
            json.dump(claim, stream)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        raise RuntimeError('A Speed run is already claimed. Inspect it; do not remove its lock blindly.')
    report_path = home / (day + '.json')
    if report_path.exists():
        lock.unlink()
        return {'status': 'already_reported', 'path': str(report_path)}
    return {'status': 'claimed', **claim}


def complete(home, run_id, value):
    home = Path(home)
    report = validate_report(value)
    lock = home / 'active.json'
    claim = json.loads(lock.read_text(encoding='utf-8'))
    if claim['id'] != run_id or report['id'] != run_id or report['date'] != claim['date']:
        raise ValueError('Report must match the exact claimed run ID and Sydney date.')
    target = home / (claim['date'] + '.json')
    if target.exists() and json.loads(target.read_text(encoding='utf-8')) != report:
        raise ValueError('Daily evidence already exists with different content.')
    atomic(target, report)
    lock.unlink()
    return {'status': 'saved', 'path': str(target), 'id': run_id}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['begin', 'complete'])
    parser.add_argument('--home', type=Path, default=ROOT / '.local-data' / 'speed')
    parser.add_argument('--run-id')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.action == 'begin':
        result = begin(args.home)
    else:
        if not args.report or not args.run_id:
            parser.error('complete requires --run-id and --report')
        result = complete(args.home, args.run_id, json.loads(args.report.read_text(encoding='utf-8')))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
