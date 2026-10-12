"""Validate the three explicitly requested CSVs, offline, retaining exports only in output/."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import statistics
import sys
import time
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psd_directory as psd

NAMES = ('edition_ops_products_333.csv', 'approved_dropbox_psds_282.csv', 'excluded_review_psds_40.csv')


def validate(snapshot, write_local=False):
    with zipfile.ZipFile(snapshot) as archive:
        manifest = json.loads(archive.read('MANIFEST.json'))
        raw = {name: archive.read(name) for name in NAMES}
    # Integrity metadata is data, never executable instructions.
    for name, data in raw.items():
        if hashlib.sha256(data).hexdigest() != manifest.get('files', {}).get(name):
            raise ValueError(f'Snapshot integrity check failed: {name}')
    rows = {name: list(csv.DictReader(io.StringIO(data.decode('utf-8-sig')))) for name, data in raw.items()}
    products, approved, excluded = [rows[name] for name in NAMES]
    if tuple(map(len, (products, approved, excluded))) != (333, 282, 40):
        raise ValueError('Snapshot row counts differ from the requested snapshot.')
    catalogue, mapping = psd.snapshot_mapping(products, approved, excluded)
    unmatched = [{'product_title': r['product_title'], 'shopify_product_gid': psd.product_id(r),
                  'state': mapping[psd.product_id(r)]['state']} for r in catalogue if not psd.link(r, mapping)]
    counts = {'products': len(catalogue), 'approved_psds': len(approved), 'excluded_review_psds': len(excluded),
              'mapped_products': sum(bool(psd.link(r, mapping)) for r in catalogue), 'unmatched_products': len(unmatched),
              'ambiguous_products': sum('ambiguous' in r['state'] for r in mapping.values()),
              'unique_mapped_file_ids': len({r['dropbox_file_id'] for r in mapping.values() if r.get('verified')})}
    times = []
    for _ in range(20):
        start = time.perf_counter()
        psd.snapshot_mapping(products, approved, excluded)
        for row in catalogue:
            psd.display_link(row, mapping)
        times.append((time.perf_counter()-start)*1000)
    counts.update({'matching_and_333_link_projection_median_ms': round(statistics.median(times), 3),
                   'matching_and_333_link_projection_max_ms': round(max(times), 3), 'network_requests': 0})
    if counts['mapped_products'] != 282 or counts['unmatched_products'] != 51 or counts['ambiguous_products']:
        raise ValueError(f'Mapping result differs from expected counts: {counts}')
    if write_local:
        folder = psd.STORE.parent / 'psd_snapshot'
        folder.mkdir(parents=True, exist_ok=True)
        for name, data in raw.items():
            (folder / name).write_bytes(data)
        # Apply only after full validation; reconcile protects any existing verified assignment.
        _, merged = psd.snapshot_mapping(products, approved, excluded, psd.directory(psd.STORE))
        if any(merged[pid].get('dropbox_file_id') != row.get('dropbox_file_id') for pid, row in mapping.items()):
            raise ValueError('Existing verified mapping conflicts; preserved without overwriting.')
        psd.save(merged, psd.STORE)
        (folder / 'validation_results.json').write_text(json.dumps(counts, indent=2), encoding='utf-8')
        (folder / 'unmatched_products_51.json').write_text(json.dumps(unmatched, indent=2), encoding='utf-8')
    return counts


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--write-local', action='store_true')
    args = parser.parse_args()
    print(json.dumps(validate(args.snapshot, args.write_local), indent=2))
