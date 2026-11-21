"""Synthetic latency benchmark. No credentials, network, application or worker startup."""
import json
from pathlib import Path
from statistics import median
import sys
from threading import Event
from time import perf_counter, sleep

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from display_snapshot import Snapshots


def main():
    cache = Snapshots(workers=3)
    release = Event()
    def load():
        sleep(.2)
        return {'brief': 'synthetic saved brief', 'metrics': {'completed': 12}}
    def measure(call):
        start = perf_counter()
        call()
        return (perf_counter()-start)*1000
    try:
        baseline = measure(lambda: [load() for _ in range(3)])
        start = perf_counter()
        shell = measure(lambda: [cache.read(str(i), load) for i in range(3)])
        while any(cache.read(str(i), load)['state'] != 'ready' for i in range(3)):
            sleep(.005)
        ready = (perf_counter()-start)*1000
        warm = [measure(lambda: [cache.read(str(i), load) for i in range(3)]) for _ in range(1000)]
        cache.invalidate('0')
        cache.read('0', lambda: release.wait(3) and {})
        busy = [measure(lambda: cache.read('0', lambda: {})) for _ in range(1000)]
        result = dict(scenario='Three independent synthetic saved-data reads, 200 ms each; not production page timings',
                      sequential_baseline_ms=round(baseline,3), cold_dispatch_ms=round(shell,3),
                      all_snapshots_ready_ms=round(ready,3),
                      warm_three_panel_p50_ms=round(median(warm),3),
                      warm_three_panel_p95_ms=round(sorted(warm)[949],3),
                      blocked_refresh_read_p95_ms=round(sorted(busy)[949],3),
                      background_workers=len(cache.pool._threads),
                      queued_backlog=cache.pool._work_queue.qsize())
        out = Path(__file__).resolve().parents[1]/'docs/home-performance-evidence.json'
        out.write_text(json.dumps(result, indent=2)+'\n', encoding='utf8')
        print(json.dumps(result, indent=2))
    finally:
        release.set()
        cache.close()


if __name__ == '__main__':
    main()
