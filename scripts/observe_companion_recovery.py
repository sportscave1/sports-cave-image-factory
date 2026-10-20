"""Read-only, one-product companion diagnostics; no queue/COM/provider calls."""
import argparse
import json
import time
from pathlib import Path

import psutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=1800)
    args = parser.parse_args()
    selection = json.loads(args.selection.read_text())
    target = selection['product_gid']
    root = Path.home()/'Documents/SportsCaveAutoEditions'
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.time()
    known = {}
    last = None
    with (args.output/'samples.jsonl').open('x') as samples:
        while time.time()-started < args.seconds:
            now = time.time()
            if int(now-started) % 3 == 0 or not known:
                for f in root.glob('*/job-state.json'):
                    if f.stat().st_mtime < started-2:
                        continue
                    try:
                        row = json.loads(f.read_text())
                        if row.get('context', {}).get('product_gid') == target:
                            if any(row['context']['source'].get(k) != v for k,v in selection['source'].items()):
                                raise RuntimeError('Source identity changed; observer will not treat it as the selected job.')
                            known[f] = row
                    except (OSError, ValueError):
                        continue
            state = dict(at=now, elapsed_seconds=now-started, processes=[])
            for process in psutil.process_iter(['pid', 'name']):
                if process.pid != selection['companion_pid'] and process.info['name'].lower() != 'photoshop.exe':
                    continue
                try:
                    with process.oneshot():
                        cpu = process.cpu_times()
                        io = process.io_counters()
                        memory = process.memory_info()
                    state['processes'].append(dict(pid=process.pid, name=process.info['name'],
                        cpu_seconds=cpu.user+cpu.system, rss_bytes=memory.rss,
                        read_bytes=io.read_bytes, write_bytes=io.write_bytes))
                except psutil.Error:
                    pass
            network = psutil.net_io_counters()
            disk = psutil.disk_io_counters()
            state.update(system_network_sent_bytes=network.bytes_sent,
                         system_network_received_bytes=network.bytes_recv,
                         system_disk_read_bytes=disk.read_bytes, system_disk_write_bytes=disk.write_bytes,
                         system_available_ram_bytes=psutil.virtual_memory().available)
            for f in list(known):
                try:
                    row = json.loads(f.read_text())
                    state.update(job=f.parent.name, status=row.get('status'), phase=row.get('phase'),
                                 checkpoint_pending=row.get('checkpoint_pending'),
                                 journal_mtime=f.stat().st_mtime, started_at=row.get('started_at'))
                    observed_source = row['context']['source']
                    (args.output/'observed-source.json').write_text(json.dumps(observed_source,indent=2))
                    if f.parent.joinpath('prepared').exists():
                        files = list(f.parent.joinpath('prepared').glob('*'))
                        state['output_file_count'] = sum(p.is_file() for p in files)
                        state['output_bytes'] = sum(p.stat().st_size for p in files if p.is_file())
                    for name in ('timings.json', 'manifest.json', 'native-status.json', 'preparation.json'):
                        source = f.parent/'prepared'/name
                        destination = args.output/name
                        if source.exists():
                            payload = source.read_bytes()
                            json.loads(payload.decode('utf-8-sig'))
                            if not destination.exists() or destination.read_bytes() != payload:
                                destination.write_bytes(payload)
                    receipt = f.parent/'receipt.json'
                    value = {}
                    if receipt.exists():
                        value = json.loads(receipt.read_text())
                        if value.get('source') == observed_source:
                            (args.output/'receipt.json').write_text(json.dumps(value, indent=2))
                            state['receipt_status'] = value.get('status')
                    if row.get('status') in ('Prepared', 'Blocked', 'Cancelled'):
                        result = {k: row.get(k) for k in ('status', 'phase', 'error', 'timings', 'server_timings', 'preparation_hash', 'checkpoint_pending')}
                        if value:
                            result.update(timings=value.get('timings'), server_timings=value.get('server_timings'),
                                          preparation_hash=value.get('preparation_hash'))
                        result.update(job=f.parent.name, observed_at=now, observation_started=started,
                                      source=observed_source, started_at=row.get('started_at'))
                        (args.output/'local-result.json').write_text(json.dumps(result, indent=2))
                        if row.get('status') == 'Prepared' or not row.get('checkpoint_pending'):
                            samples.write(json.dumps(state)+'\n'); samples.flush()
                            print(json.dumps(dict(job=f.parent.name, status=row['status'], error=row.get('error'))), flush=True)
                            return
                except (OSError, ValueError):
                    continue
            samples.write(json.dumps(state)+'\n'); samples.flush()
            current = (state.get('job'), state.get('status'), state.get('phase'))
            if current != last:
                print(json.dumps(dict(job=current[0], status=current[1], phase=current[2])), flush=True)
                last = current
            time.sleep(1)
    print('Observation ended without a terminal checkpoint.', flush=True)


if __name__ == '__main__':
    main()
