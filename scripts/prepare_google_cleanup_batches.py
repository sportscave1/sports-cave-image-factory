"""Offline preparation only: frozen backup -> inert primary-key cleanup batches.

Extends the scope in the existing GOOGLE_REPORTING_CLEANUP_DRAFT.sql. Never
connects to a database or executes SQL. Requires an independently reviewed
isolated-restore receipt before producing a production review package.
"""
import argparse
from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path

PROJECT = 'ceyzbfpuwuuxaiqwiltz'
WORKSPACE = 'sports-cave'
CUTOFF = '2025-06-12'
BASE_KEY = ('workspace_key', 'property_id', 'source_date', 'search_type', 'data_state')
KEYS = {
    'analytics_ga4_report_snapshots': ('workspace_key', 'property_id', 'request_hash'),
    'seo_gsc_property_totals_v2': BASE_KEY,
    'seo_gsc_query_daily_v2': BASE_KEY + ('query_hash', 'country_code', 'device'),
    'seo_gsc_query_page_daily_v2': BASE_KEY + ('query_hash', 'page_hash'),
    'seo_gsc_page_daily_v2': BASE_KEY + ('page_hash', 'country_code', 'device'),
    'seo_gsc_search_appearance_daily_v2': BASE_KEY + ('appearance',),
}
EXPECTED = dict(zip(KEYS, (3936, 2164, 120193, 80984, 78904, 328)))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def literal(value):
    return "'" + value.replace("'", "''") + "'"


def export_sql():
    # Include all 268 protected historical property-total rows in the backup.
    # Use a client-side COPY/stream in one consistent read-only transaction;
    # preserve each returned JSON text line exactly, in the returned order.
    parts = ['BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;',
             "SET LOCAL statement_timeout = '120s';"]
    for table, keys in KEYS.items():
        parts.append(f"SELECT jsonb_build_object('table', '{table}', 'row_text', to_jsonb(t)::text, "
                     f"'row_sha256', encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex'))::text "
                     f"FROM public.{table} t WHERE workspace_key='{WORKSPACE}' "
                     f"ORDER BY {', '.join(keys)};")
    return '\n'.join(parts + ['ROLLBACK;']) + '\n'


def validate_entry(entry):
    table = entry['table']
    if table not in KEYS:
        raise ValueError('Non-allowlisted table')
    text = entry['row_text']
    if digest(text.encode('utf8')) != entry['row_sha256']:
        raise ValueError('Backup row checksum mismatch')
    row = json.loads(text)
    key = {k: row[k] for k in KEYS[table]}
    if any(not isinstance(v, str) for v in key.values()):
        raise ValueError('Missing or invalid primary key')
    if row['workspace_key'] != WORKSPACE:
        raise ValueError('Wrong workspace')
    if table.startswith('seo_gsc_'):
        source_date = date.fromisoformat(row['source_date'])
        if source_date.isoformat() != row['source_date']:
            raise ValueError('Noncanonical date')
        if source_date < date.fromisoformat(CUTOFF):
            if table != 'seo_gsc_property_totals_v2':
                raise ValueError('Unexpected historical row; re-review scope')
            return table, key, True
    return table, key, False


def batch_sql(table, entries):
    if table not in KEYS or not 1 <= len(entries) <= 500:
        raise ValueError('Invalid batch')
    manifest = []
    seen = set()
    for entry in entries:
        name, key, retained = validate_entry(entry)
        if name != table or retained:
            raise ValueError('Protected row in cleanup batch')
        encoded = json.dumps(key, sort_keys=True)
        if encoded in seen:
            raise ValueError('Duplicate primary key')
        seen.add(encoded)
        manifest.append({'key': key, 'row_sha256': entry['row_sha256']})
    payload = literal(json.dumps(manifest, separators=(',', ':')))
    joins = ' AND '.join(f't.{key}=k.{key}' for key in KEYS[table])
    scope = f"t.workspace_key='{WORKSPACE}'"
    if table.startswith('seo_gsc_'):
        scope += f" AND t.source_date >= DATE '{CUTOFF}'"
    tag = '$cleanup$'
    while tag in payload:
        tag = tag[:-1] + 'x$'
    body = f'''BEGIN;
SET LOCAL standard_conforming_strings = on;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';
DO {tag}
DECLARE affected bigint;
BEGIN
  WITH expected AS (SELECT value FROM jsonb_array_elements({payload}::jsonb))
  DELETE FROM public.{table} t
  USING expected e, LATERAL jsonb_populate_record(NULL::public.{table}, e.value->'key') k
  WHERE {joins} AND {scope}
    AND encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex')=e.value->>'row_sha256';
  GET DIAGNOSTICS affected = ROW_COUNT;
  IF affected <> {len(entries)} THEN
    RAISE EXCEPTION 'Frozen manifest mismatch: rollback required';
  END IF;
END {tag};
ROLLBACK;'''
    # Two gates: all statements inert, and each transaction defaults to rollback.
    return '\n'.join('-- ' + line for line in body.splitlines()) + '\n'


def prepare(backup, receipt, output):
    backup, receipt, output = Path(backup), Path(receipt), Path(output)
    check = json.loads(receipt.read_text(encoding='utf8'))
    with backup.open('rb') as source:
        sha = hashlib.file_digest(source, 'sha256').hexdigest()
    if (check.get('project') != PROJECT or check.get('backup_sha256') != sha
            or check.get('restored_export_sha256') != sha
            or check.get('isolated') is not True
            or check.get('target_project') in (None, '', PROJECT)
            or not check.get('restored_at') or check.get('retained_rows') != 268):
        raise ValueError('Matching isolated restore evidence is required')
    # Validation pass before creating any output; no partial review on bad input.
    counts, retained, seen = Counter(), 0, set()
    with backup.open(encoding='utf8') as source:
        for line in source:
            entry = json.loads(line)
            table, key, keep = validate_entry(entry)
            identity = (table, json.dumps(key, sort_keys=True))
            if identity in seen:
                raise ValueError('Duplicate primary key')
            seen.add(identity)
            if keep:
                retained += 1
            else:
                counts[table] += 1
    if dict(counts) != EXPECTED or retained != 268:
        raise ValueError('Audited counts changed; re-review required')
    output.mkdir(exist_ok=False)
    batches, buffers = [], {table: [] for table in KEYS}
    def flush(table):
        entries = buffers[table]
        if not entries:
            return
        name = f'{len(batches)+1:04d}_{table}.sql'
        sql = batch_sql(table, entries)
        (output / name).write_text(sql, encoding='utf8')
        batches.append({'file': name, 'table': table, 'rows': len(entries),
                        'sql_sha256': digest(sql.encode('utf8')),
                        'keys': [validate_entry(e)[1] for e in entries]})
        buffers[table] = []
    with backup.open(encoding='utf8') as source:
        for line in source:
            entry = json.loads(line)
            table, _, keep = validate_entry(entry)
            if not keep:
                buffers[table].append(entry)
                if len(buffers[table]) == 500:
                    flush(table)
    for table in KEYS:
        flush(table)
    with backup.open('rb') as source:
        if hashlib.file_digest(source, 'sha256').hexdigest() != sha:
            raise ValueError('Backup changed during preparation; no manifest produced')
    result = {'project': PROJECT, 'workspace': WORKSPACE, 'cutoff': CUTOFF,
              'backup_sha256': sha, 'restore_receipt_sha256': digest(receipt.read_bytes()),
              'counts': dict(counts), 'retained_rows': retained, 'batches': batches,
              'approved': False, 'executed': False}
    (output / 'manifest.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export-sql', type=Path)
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--restore-receipt', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.export_sql:
        with args.export_sql.open('x', encoding='utf8') as target:
            target.write(export_sql())
    elif args.backup and args.restore_receipt and args.output:
        prepare(args.backup, args.restore_receipt, args.output)
    else:
        parser.error('Provide --export-sql or --backup, --restore-receipt and --output')


if __name__ == '__main__':
    main()
