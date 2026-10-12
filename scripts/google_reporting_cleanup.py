"""Prepare an approval-gated cleanup SQL artifact; never connects to a database.

Usage: python scripts/google_reporting_cleanup.py --output <path.sql>
The generated script defaults to READ ONLY and ROLLBACK. No execute mode exists.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

PROJECT = 'ceyzbfpuwuuxaiqwiltz'
WORKSPACE = 'sports-cave'
# Freeze the reviewed historical boundary; never advance it automatically.
GSC_CUTOFF = '2025-06-12'
# Reporting facts only. No audit/run/error history, owned decisions or commerce.
CANDIDATES = (
    'analytics_ga4_report_snapshots',
    'seo_gsc_property_totals_v2',
    'seo_gsc_query_daily_v2',
    'seo_gsc_query_page_daily_v2',
    'seo_gsc_page_daily_v2',
    'seo_gsc_search_appearance_daily_v2',
    'seo_reporting_daily_metrics',
    'seo_reporting_query_daily',
    'seo_reporting_landing_page_daily',
    'seo_reporting_page_daily',
)


def prepare_sql(tables=CANDIDATES):
    tables = tuple(tables)
    if not tables or len(tables) != len(set(tables)) or any(t not in CANDIDATES for t in tables):
        raise ValueError('Only unique, allowlisted Google reporting fact tables are permitted.')
    header = f'''-- DRAFT ONLY. Prepared for project {PROJECT}, workspace {WORKSPACE}.
-- No schema drops, CASCADE, TRUNCATE, credentials or automatic execution.
-- Before any deletion: verify deployed direct readers against Google; stop old
-- worker revisions; verify a scoped export checksum and isolated restore;
-- review dependency inventory and row counts; obtain owner approval for this
-- exact list. Separate project and all audit/business records are excluded.
-- Keep the original historical exports: APIs cannot reproduce every past report.
-- To review: execute ONLY this read-only transaction in the verified project.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';
'''
    for table in tables:
        history_scope = f" AND source_date >= DATE '{GSC_CUTOFF}'" if table.startswith("seo_gsc_") else ""
        header += f"SELECT '{table}' AS table_name, COUNT(*) AS candidate_rows FROM public.{table} WHERE workspace_key='{WORKSPACE}'{history_scope};\n"
    header += 'ROLLBACK;\n\n-- The following deletion plan is intentionally INERT (commented out).\n'
    header += '-- Each table must have an approved expected row count and cutoff at execution.\n-- BEGIN;\n-- SET LOCAL lock_timeout = \'2s\';\n-- SET LOCAL statement_timeout = \'30s\';\n'
    for table in tables:
        history_scope = f" AND source_date >= DATE '{GSC_CUTOFF}'" if table.startswith("seo_gsc_") else ""
        header += f"-- DELETE FROM public.{table} WHERE workspace_key='{WORKSPACE}'{history_scope};\n"
    header += '-- ROLLBACK; -- Never change to COMMIT before separate exact-list approval.\n'
    return header


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('Output already exists; choose a new file for review.')
    args.output.write_text(prepare_sql(), encoding='utf-8')
    print(json.dumps({'project': PROJECT, 'workspace': WORKSPACE, 'tables': CANDIDATES, 'executed': False, 'output': str(args.output)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
