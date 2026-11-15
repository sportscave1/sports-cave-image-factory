"""Bounded fabricated controller timings. No production config or application startup."""
import argparse
from pathlib import Path
import json
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
args = argparse.ArgumentParser()
args.add_argument('--source', type=Path, default=ROOT)
args.add_argument('--label', default='after')
args.add_argument('--sql', action='store_true', help='Use existing disposable loopback SQL fixture for synthetic send timing')
args = args.parse_args()
sys.path[:0] = [str(args.source.resolve()), str(ROOT)]
from tests.test_support_email_v2 import WorkspaceTests


def run():
    samples = {k: [] for k in ('cold_mailbox', 'warm_mailbox', 'cold_conversation', 'warm_conversation', 'manual_refresh')}
    counts = []
    for _ in range(50):
        f = WorkspaceTests()
        started = time.perf_counter()
        f.setUp()
        samples['cold_mailbox'].append((time.perf_counter()-started)*1000)
        try:
            for name, action in [('warm_mailbox', lambda: f.w.load()),
                                 ('cold_conversation', f.open), ('warm_conversation', f.open),
                                 ('manual_refresh', lambda: f.event('refresh'))]:
                started = time.perf_counter()
                action()
                samples[name].append((time.perf_counter()-started)*1000)
            counts.append({kind: sum(c[0] == kind for c in f.imap.calls) for kind in ('headers', 'body', 'attachment')})
        finally:
            f.doCleanups()
    result = {'label': args.label, 'method': '50 fabricated provider/controller iterations; no external network or browser timing; cold setup includes mocked settings and initial 50-row load',
              'samples': {k: {'n': len(v), 'median_ms': round(statistics.median(v), 3),
                              'p95_ms': round(sorted(v)[47], 3)} for k, v in samples.items()},
              'provider_calls_per_iteration': counts[0], 'call_counts_consistent': all(c == counts[0] for c in counts)}
    if args.sql:
        from tests.test_email_durable_delivery import DurableDelivery
        send_samples = {k: [] for k in ('click_to_queued_ack', 'click_to_provider_acceptance', 'click_to_sent_visibility')}
        for _ in range(50):
            f = DurableDelivery()
            f.setUp()
            times = {}
            def accepted(mime, *, mailbox, progress):
                time.sleep(.002)  # Fixed fabricated provider delay, identical before/after.
                times['accepted'] = time.perf_counter()
                progress(100, 'Sent')
                return {'status': 'accepted'}
            f.provider.submit.side_effect = accepted
            def append(folder, data):
                time.sleep(.002)
                f.imap.find_message_id.return_value = ['42']
            f.imap.append_message.side_effect = append
            started = time.perf_counter()
            f.prepare()
            send_samples['click_to_queued_ack'].append((time.perf_counter()-started)*1000)
            f.submit()
            send_samples['click_to_provider_acceptance'].append((times['accepted']-started)*1000)
            f.registry.save_sent(f.op, f.mailbox, f.imap, f.mime, 'Sent', 'append')
            assert f.imap.find_message_id('Sent', f.mime['message_id'])
            send_samples['click_to_sent_visibility'].append((time.perf_counter()-started)*1000)
        result['synthetic_send'] = {k: {'n': len(v), 'median_ms': round(statistics.median(v), 3),
                                       'p95_ms': round(sorted(v)[47], 3)} for k, v in send_samples.items()}
        result['send_method'] = 'Disposable SQL and fake SMTP/IMAP with two fixed 2 ms delays; no real email or delivery test'
    target = ROOT / 'docs/mailbox-reliability-evidence' / (args.label + '-timings.json')
    target.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    run()
