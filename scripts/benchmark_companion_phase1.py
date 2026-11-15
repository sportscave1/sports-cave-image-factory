"""Offline replay of retained PSD outputs. Never invokes Photoshop or a provider.

Copies must be supplied under this task's output/ directory. The source PSD and
every existing output are hashed before/after; timings are diagnostic sidecars.
First reads are labelled first-observed, not cold OS-cache measurements.
"""
import argparse
import hashlib
import json
import statistics
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import auto_editions as ae


class Sample:
    def __enter__(self):
        import psutil
        self.psutil = psutil
        self.process = psutil.Process()
        self.cpu = time.process_time()
        self.started = time.perf_counter()
        self.io = self.process.io_counters()
        self.net = psutil.net_io_counters()
        self.disk = psutil.disk_io_counters()
        self.rss = self.process.memory_info().rss
        self.available = psutil.virtual_memory().available
        self.stop = threading.Event()

        def sample():
            while not self.stop.wait(.1):
                self.rss = max(self.rss, self.process.memory_info().rss)
                self.available = min(self.available, psutil.virtual_memory().available)

        self.thread = threading.Thread(target=sample, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.wall = time.perf_counter() - self.started
        self.cpu = time.process_time() - self.cpu
        self.stop.set()
        self.thread.join()
        io = self.process.io_counters()
        net = self.psutil.net_io_counters()
        disk = self.psutil.disk_io_counters()
        self.result = dict(seconds=self.wall, cpu_seconds=self.cpu,
                           peak_sampled_rss_bytes=self.rss,
                           minimum_system_available_ram_bytes=self.available,
                           process_read_bytes=io.read_bytes-self.io.read_bytes,
                           process_write_bytes=io.write_bytes-self.io.write_bytes,
                           system_network_sent_bytes=net.bytes_sent-self.net.bytes_sent,
                           system_network_received_bytes=net.bytes_recv-self.net.bytes_recv,
                           system_disk_read_bytes=disk.read_bytes-self.disk.read_bytes,
                           system_disk_write_bytes=disk.write_bytes-self.disk.write_bytes)


def legacy(manifest, folder, number):
    proofs = [ae.compare_reference(manifest, folder, n, folder/f'reference-{n}.png')
              for n in sorted({1, number, manifest['edition_total']})]
    return proofs, ae.compare_original_outside_number(manifest, folder, number, folder/'original.png')


def checksums(folder):
    return {str(p.relative_to(folder)): ae.file_hash(p)
            for p in folder.rglob('*') if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--number', type=int, required=True)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--compare', action='store_true')
    args = parser.parse_args()
    folder = args.fixture.resolve()
    if not folder.is_relative_to((ROOT/'output').resolve()) or args.report.exists():
        parser.error('Use task-local copied inputs and a new report path.')
    if args.repeats < 3:
        parser.error('At least three repeated trials are required.')
    prepared = folder/'prepared'
    manifest = ae.validate_manifest(json.loads((prepared/'manifest.json').read_text()))
    before = checksums(folder)
    with Sample() as measured:
        source_hashes = __import__('auto_editions_performance').file_hashes(folder/'input.psd')
    if source_hashes['dropbox'] != manifest['source']['content_hash']:
        raise ValueError('Retained source does not match the pinned manifest revision.')
    result = dict(kind='offline retained real PSD output replay',
                  photoshop_executed=False, provider_requests=0,
                  cloud_ready_measured=False, cold_cache_measured=False,
                  source=manifest['source'], source_sha256=source_hashes['sha256'],
                  preparation_hash=ae.fingerprint(manifest), dimensions=manifest['dimensions'],
                  source_bytes=(folder/'input.psd').stat().st_size,
                  output_file_count=sum(p.is_file() for p in prepared.rglob('*')),
                  output_total_bytes=sum(p.stat().st_size for p in prepared.rglob('*') if p.is_file()),
                  source_hash_measurement=measured.result, runs=[])
    expected = None
    for repeat in range(args.repeats):
        order = ['legacy', 'candidate'] if args.compare else ['legacy']
        if repeat % 2:
            order.reverse()
        for mode in order:
            function = legacy if mode == 'legacy' else ae.verify_preparation_pixels
            with Sample() as measured:
                proofs = function(manifest, prepared, args.number)
            if expected is None:
                expected = proofs
            if proofs != expected:
                raise ValueError('Independent pixel or source proof changed.')
            row = dict(repeat=repeat, mode=mode, cache='first-observed' if not result['runs'] else 'warm',
                       **measured.result)
            result['runs'].append(row)
            print(json.dumps(row), flush=True)
    if checksums(folder) != before:
        raise ValueError('Source or retained outputs changed during replay.')
    result['all_input_bytes_unchanged'] = True
    result['proofs_exactly_equal'] = True
    result['proofs'] = expected
    result['summary'] = {}
    for mode in {r['mode'] for r in result['runs']}:
        rows = [r for r in result['runs'] if r['mode'] == mode]
        result['summary'][mode] = dict(median_seconds=statistics.median(r['seconds'] for r in rows),
                                      median_cpu_seconds=statistics.median(r['cpu_seconds'] for r in rows),
                                      max_rss_bytes=max(r['peak_sampled_rss_bytes'] for r in rows))
    if args.compare:
        before_time = result['summary']['legacy']['median_seconds']
        after_time = result['summary']['candidate']['median_seconds']
        result['improvement'] = dict(seconds=before_time-after_time, percent=100*(before_time-after_time)/before_time)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
