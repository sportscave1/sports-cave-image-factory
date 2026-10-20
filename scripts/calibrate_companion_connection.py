"""Explicit, bounded WAN trial. Never auto-runs or writes companion settings.

Run only in an authorised idle window with the installed singleton stopped.
Uses Cloudflare's documented disposable speed-test receiver, never provider or
customer storage. Reports conservative application goodput, not wire capacity.
"""
import argparse
import json
import math
import random
import statistics
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from companion_transfer import Controller, post_file, burst_allowance

SIZE = 8 * 1024**2
UPLOAD = 'https://speed.cloudflare.com/__up'
PROBES = {
    'edge': 'https://speed.cloudflare.com/__down?bytes=0',
    'os_health': 'https://sports-cave-image-factory.onrender.com/_stcore/health',
}


def propose(rows):
    """Require three stable successful observations; choose the slowest rate."""
    if len(rows) != 3 or any(r['status'] != 200 or r['bytes'] != SIZE or r['seconds'] < 2 for r in rows):
        return None
    rates = [r['mbps'] for r in rows]
    if any(not math.isfinite(r) or r <= 0 for r in rates) or max(rates) / min(rates) > 1.35:
        return None
    return math.floor(min(rates) * 100) / 100


def summary(rows):
    result = {}
    for name in PROBES:
        selected = [r for r in rows if r['target'] == name]
        good = sorted(r['ms'] for r in selected if r['ok'])
        result[name] = dict(count=len(selected), failures=sum(not r['ok'] for r in selected),
                            median_ms=statistics.median(good) if good else None,
                            p95_ms=good[math.ceil(.95*len(good))-1] if good else None)
    return result


def main(output):
    import psutil
    import requests
    # This is a diagnostic transfer process, never a second preparation worker.
    for p in psutil.process_iter(['cmdline']):
        command = p.info['cmdline'] or []
        if any(str(c).endswith('companion.py') for c in command):
            raise RuntimeError('Close the idle companion normally before calibration.')
    home = Path.home() / 'Documents/SportsCaveAutoEditions'
    settings_file = home / 'transfer-settings.json'
    saved = settings_file.read_bytes()
    assert json.loads(saved)['settings']['mode'] == 'Maximum speed'
    assert not (Path.home() / 'Documents/SportsCavePrintJobs/processor.lock').exists()
    before = {str(p):p.read_bytes() for p in home.glob('*/job-state.json')}
    assert all(json.loads(v).get('status') not in ('Working', 'Recovering') and
               not json.loads(v).get('checkpoint_pending') for v in before.values())
    output.mkdir(parents=True, exist_ok=False)
    packet = output / 'synthetic.bin'
    packet.write_bytes(random.Random(20261020).randbytes(SIZE))
    deadline = time.monotonic()+240
    c = Controller()  # Deliberately no settings path: selected Maximum is untouched.
    c.configure(dict(mode='Maximum speed'))
    probes = []
    trials = []
    stop = threading.Event()
    session = requests.Session()

    def probe(phase):
        for name, url in PROBES.items():
            start = time.monotonic()
            try:
                response = session.get(url, timeout=(3, 4), allow_redirects=False)
                ok = response.status_code == 200 and len(response.content) < 4096
                response.close()
            except requests.RequestException:
                ok = False
            probes.append(dict(phase=phase, target=name, ok=ok, ms=round((time.monotonic()-start)*1000, 3)))

    def monitor(phase):
        count = 0
        while not stop.wait(.75) and count < 16:
            with c.cv:
                active = c.active or {}
                body_active = active.get('state') == 'Uploading' and 0 < active.get('transport_bytes', 0) < SIZE
            if body_active:
                probe(phase)
                count += 1

    result = dict(payload_budget_bytes=5*SIZE, deadline_seconds=240, trials=trials, probes=probes,
                  raw_wire_capacity_measured=False, actual_browsing_experience_measured=False,
                  settings_written=False, receiver=UPLOAD)
    try:
        for _ in range(5):probe('idle')
        for index in range(5):
            if time.monotonic() > deadline:raise TimeoutError('Bounded calibration deadline reached.')
            phase = 'maximum' if index < 3 else 'balanced_candidate'
            if index == 3:
                sustainable = propose(trials)
                result['recommended_sustainable_mbps'] = sustainable
                if sustainable is None:
                    result['outcome'] = 'Insufficient stable observations; keep Maximum selected.'
                    break
                cap = sustainable*.75
                result['candidate_cap_mbps'] = cap
                c.configure(dict(mode='Manual', manual_mbps=cap))
            stop.clear()
            thread = threading.Thread(target=monitor, args=(phase,), daemon=True)
            thread.start()
            start = time.monotonic()
            try:
                response, trace = post_file(c, UPLOAD, packet, {'Content-Type':'application/octet-stream'},
                                           timeout=(10, 30), stopped=lambda: time.monotonic()>deadline)
                elapsed = time.monotonic()-start
                response.raise_for_status()
                # Endpoint success means the finite POST completed; it does not
                # supply our protocol's independently signed receipt or hash.
                row = dict(phase=phase, status=response.status_code, bytes=trace['transport_bytes'],
                           seconds=elapsed, mbps=SIZE*8/elapsed/1_000_000,
                           trace={k:v for k,v in trace.items() if isinstance(v,(int,float,bool)) or k=='state'})
                trials.append(row)
                print(json.dumps({k:v for k,v in row.items() if k!='trace'}), flush=True)
                response.close()
            finally:
                stop.set()
                thread.join(10)
                assert not thread.is_alive(), 'Control probe must finish before the next transfer.'
            (output/'measurements.json').write_text(json.dumps(result, indent=2))
        result['latency'] = {phase:summary([r for r in probes if r['phase']==phase])
                             for phase in ('idle','maximum','balanced_candidate')}
        result['application_bytes_sent'] = sum(r['bytes'] for r in trials)
        if len(trials)==5:
            rate = result['candidate_cap_mbps']*1_000_000/8
            result['cap_compliant'] = all(r['bytes'] <= rate*r['seconds']+burst_allowance(rate) for r in trials[3:])
            result['outcome'] = 'Measured; review capped responsiveness before applying any settings.'
    finally:
        stop.set()
        packet.unlink(missing_ok=True)
        result['maximum_selection_unchanged'] = settings_file.read_bytes()==saved
        result['customer_journals_unchanged'] = all(Path(k).read_bytes()==v for k,v in before.items())
        (output/'measurements.json').write_text(json.dumps(result, indent=2))
        session.close()
        if c.session:c.session.close()
    print(json.dumps({k:v for k,v in result.items() if k not in ('trials','probes')}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorised-idle-window', action='store_true', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    main(args.output)
