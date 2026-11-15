"""Validate response manifests against explicitly witnessed completed downloads.

Never scan for newest files or infer roles from order, titles, or timestamps.
Browser-added numeric collision suffixes are accepted only for the witnessed
source filename. A future gallery adapter must supply that source association.
"""
import csv
import hashlib
import io
import json
import re
from pathlib import Path, PureWindowsPath

ROLES = frozenset({'Man Cave', 'Office', 'Living Room'})


class OutputMappingError(ValueError):
    pass


def _filename(value):
    if (not isinstance(value, str) or not value or len(value) > 180
            or PureWindowsPath(value).name != value or '/' in value
            or any(c in value for c in '<>:"|?*') or value.endswith((' ', '.'))):
        raise OutputMappingError('Manifest requires a safe filename, not a path.')
    return value


def read_manifest(text):
    if not isinstance(text, str) or len(text) > 65536:
        raise OutputMappingError('CSV exceeds its bound.')
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    if reader.fieldnames != ['role', 'filename']:
        raise OutputMappingError('CSV must contain exactly role,filename.')
    rows = list(reader)
    if len(rows) != 3 or {r.get('role') for r in rows} != ROLES:
        raise OutputMappingError('CSV must contain each required role exactly once.')
    if any(set(r) != {'role', 'filename'} for r in rows):
        raise OutputMappingError('CSV contains unexpected columns.')
    names = [_filename(r['filename']) for r in rows]
    if len({n.casefold() for n in names}) != 3 or any(not n.lower().endswith('.png') for n in names):
        raise OutputMappingError('CSV must identify three distinct PNG originals.')
    return rows


def collision_name(source, actual):
    source, actual = _filename(source), _filename(actual)
    stem, suffix = source.rsplit('.', 1)
    return bool(re.fullmatch(re.escape(stem) + r'(?: \([1-9][0-9]*\))?\.' + re.escape(suffix), actual, re.I))


def reconcile(text, witnesses):
    """Witnesses must come from a successful per-source download observation.

    Each carries source_filename, exact path, and SHA256 of verified completed
    bytes. Caller owns browser/source correlation; this pure validator does not
    manufacture it from file presence. Files are checked again before mapping.
    """
    rows = read_manifest(text)
    if len(witnesses) != 3:
        raise OutputMappingError('Exactly three completed download witnesses required.')
    by_source = {}
    seen_paths, seen_hashes = set(), set()
    for witness in witnesses:
        source = _filename(witness['source_filename'])
        key = source.casefold()
        path = Path(witness['path'])
        digest = witness['sha256']
        if not path.is_absolute() or not collision_name(source, path.name):
            raise OutputMappingError('Downloaded filename is not bound to its source.')
        if key in by_source or str(path.resolve()).casefold() in seen_paths:
            raise OutputMappingError('Ambiguous source or reused destination.')
        if not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest):
            raise OutputMappingError('A completed-file digest is required.')
        if not path.is_file() or not 8 <= path.stat().st_size <= 50 * 1024 * 1024:
            raise OutputMappingError('Completed PNG is missing or exceeds its bound.')
        data = path.read_bytes()
        if data[:8] != b'\x89PNG\r\n\x1a\n' or hashlib.sha256(data).hexdigest() != digest:
            raise OutputMappingError('Completed PNG changed after its download witness.')
        if digest in seen_hashes:
            raise OutputMappingError('Three distinct output images are required.')
        seen_paths.add(str(path.resolve()).casefold()); seen_hashes.add(digest)
        by_source[key] = dict(path=str(path.resolve()), sha256=digest, source_filename=source)
    missing = [r['filename'] for r in rows if r['filename'].casefold() not in by_source]
    if missing:
        raise OutputMappingError('CSV filenames have no matching source download witness: ' + ', '.join(missing))
    return [dict(role=r['role'], **by_source[r['filename'].casefold()]) for r in rows]


def export_verified_mapping(receipt_path):
    """Export corrected filenames from native per-image witnesses, preserving CSV.

    The native action has already verified each response role binding against
    its selected gallery title and original hash. CSV aliases are not treated
    as evidence of file identity and are never silently renamed.
    """
    path = Path(receipt_path)
    receipt = json.loads(path.read_text(encoding='utf-8-sig'))
    rows = receipt['images']
    original = Path(receipt['original_csv']).read_bytes()
    if hashlib.sha256(original).hexdigest() != receipt['original_csv_sha256']:
        raise OutputMappingError('Original response CSV changed.')
    original_rows = read_manifest(original.decode('utf-8-sig'))
    stream = io.StringIO(newline='')
    writer = csv.writer(stream); writer.writerow(['role', 'filename'])
    for row in rows:
        writer.writerow([row['role'], row['source_filename']])
    verified = reconcile(stream.getvalue(), rows)
    corrected = io.StringIO(newline='')
    writer = csv.writer(corrected); writer.writerow(['role', 'filename'])
    for row in verified:
        writer.writerow([row['role'], Path(row['path']).name])
    result = dict(request_id=receipt['request_id'], conversation=receipt['conversation'],
                  native_receipt=str(path.resolve()), original_csv=str(Path(receipt['original_csv']).resolve()),
                  original_csv_rows=original_rows, mapping_basis=receipt['mapping_basis'], images=verified)
    csv_path = path.with_suffix('.mapped.csv')
    json_path = path.with_suffix('.mapped.json')
    csv_path.write_text(corrected.getvalue(), encoding='utf-8')
    json_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    return dict(manifest=str(json_path), csv=str(csv_path), images=verified)


def verify_upload_mapping(manifest, bindings):
    """Phase 6 preflight: no upload may use relabelled or changed output bytes."""
    if (manifest['request_id'] != bindings['request_id']
            or manifest['conversation'] != bindings['conversation']):
        raise OutputMappingError('Upload manifest belongs to another request.')
    expected = {row['role']: row for row in bindings['images']}
    actual = manifest['images']
    if len(bindings['images']) != 3 or set(expected) != ROLES or len(actual) != 3 or {row['role'] for row in actual} != ROLES:
        raise OutputMappingError('Upload manifest must have exactly three roles.')
    directory = Path(bindings['directory'])
    if not directory.is_absolute():
        raise OutputMappingError('Upload directory must be absolute.')
    directory = directory.resolve()
    for row in actual:
        source = expected[row['role']]
        path = Path(row['path'])
        if (row['sha256'] != source['sha256'] or row['source_filename'] != source['filename']
                or not path.is_absolute() or not path.is_file() or path.resolve().parent != directory
                or not collision_name(source['filename'], path.name)
                or hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']):
            raise OutputMappingError('Role, path or original bytes changed; no upload allowed.')
    return {row['role']: row['path'] for row in actual}


def verify_upload_receipt(receipt, manifest, bindings, *, intake, run_dir):
    """Verify local accepted originals; this does not prove native replay itself.

    Intake and run_dir must be observed before uploading, not taken from the
    returned receipt. Preserve synthetic_base when reporting fixture evidence.
    """
    verify_upload_mapping(manifest, bindings)
    slots = {'Man Cave': '01-man-cave-prompt.txt', 'Office': '02-office-prompt.txt',
             'Living Room': '03-living-room-prompt.txt'}
    root = Path(run_dir)
    if not intake or receipt.get('intake') != intake or not root.is_absolute():
        raise OutputMappingError('Upload receipt belongs to another intake or run.')
    ready = receipt.get('readiness', {})
    if (ready.get('complete') is not True or ready.get('ready_count') != 8
            or ready.get('required_count') != 8 or ready.get('missing_labels') != []):
        raise OutputMappingError('All eight product images must be accepted.')
    originals = receipt.get('originals', {})
    if set(originals) != set(slots.values()):
        raise OutputMappingError('Exactly three accepted lifestyle originals required.')
    accepted = {}
    for row in manifest['images']:
        slot = slots[row['role']]
        item = originals[slot]
        path = Path(item['path'])
        expected = root / 'uploaded-originals' / (Path(slot).stem + '.png')
        if (not path.is_absolute() or path.resolve() != expected.resolve()
                or not path.is_file() or path.stat().st_size > 50 * 1024 * 1024
                or item.get('sha256') != row['sha256']
                or hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']):
            raise OutputMappingError('Accepted original does not match its role and current run.')
        accepted[row['role']] = str(path)
    return dict(intake=intake, originals=accepted, synthetic_base=receipt.get('synthetic_base'))
