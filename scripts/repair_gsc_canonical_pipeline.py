"""Apply additive GSC storage repair, backfill legacy rows and refetch final data.

This is intentionally an explicit production-shell command. It preserves the
legacy tables and replaces canonical data only at an atomic date/search-type
boundary, so the command is resumable and safe to rerun.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import sys

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import google_seo  # noqa: E402
import google_seo_import  # noqa: E402
import run_migrations  # noqa: E402


def _exact_selected_property(connection):
    selected = str(connection.get("gsc_site_url") or "")
    return next(
        (
            str(row.get("id") or "")
            for row in connection.get("available_gsc_properties") or []
            if google_seo.gsc_properties_match(selected, row.get("id"))
        ),
        selected,
    )


def _apply_pipeline_migrations():
    for filename in google_seo.GOOGLE_SEO_PIPELINE_MIGRATIONS:
        run_migrations.run_migrations(only=filename)


def _latest_final_date(connection_store, connection):
    config = google_seo.load_config()
    access_token, _secret = google_seo.access_token_for_connection(
        connection_store,
        config,
    )
    exact_property = _exact_selected_property(connection)
    latest = google_seo.latest_gsc_data_date(access_token, exact_property)
    if not latest:
        raise google_seo.GoogleSEOError(
            "Search Console returned no finalised source date for the selected property.",
            code="gsc_no_final_data",
            stage="gsc_repair",
        )
    return exact_property, date.fromisoformat(latest[:10])


def run_repair(*, apply_migrations, backfill_legacy, refetch_latest_14, run_worker):
    report = {"migrations_applied": False}
    if apply_migrations:
        _apply_pipeline_migrations()
        report["migrations_applied"] = True

    connection_store = google_seo.default_store()
    import_store = google_seo_import.default_import_store()
    connection = connection_store.get_connection_secret()
    property_id = _exact_selected_property(connection)
    if not property_id:
        raise google_seo_import.SEOImportError(
            "Select a Search Console property before repairing canonical data.",
            code="property_selection_required",
            retryable=False,
        )
    report["property_id"] = property_id
    report["property_key"] = google_seo.canonical_gsc_property_key(property_id)

    if backfill_legacy:
        report["legacy_backfill"] = import_store.backfill_gsc_canonical_from_legacy(
            property_id
        )

    queued = None
    if refetch_latest_14:
        property_id, end_date = _latest_final_date(connection_store, connection)
        start_date = end_date - timedelta(days=13)
        queued = import_store.queue_run(
            "GSC",
            "manual",
            property_identifier=property_id,
            requested_by="gsc-canonical-repair",
            start_date=start_date,
            end_date=end_date,
        )
        report["refetch"] = {
            "run_id": queued.get("id"),
            "status": queued.get("status"),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }

    if run_worker:
        result = google_seo_import.SEOImportWorker(
            import_store=import_store,
            connection_store=connection_store,
            worker_id="gsc-canonical-repair",
        ).run_once(source="GSC")
        report["worker_result"] = result or {"status": "no_pending_run"}
        status = str((result or {}).get("status") or "")
        if status not in {"completed"}:
            raise google_seo_import.SEOImportError(
                str((result or {}).get("error_summary") or "The canonical GSC repair did not complete."),
                code=str((result or {}).get("error_code") or "gsc_repair_incomplete"),
            )
    elif queued:
        report["next_command"] = "python google_seo_import.py worker --once"
    return report


def main(argv=None):
    load_dotenv(BASE_DIR / ".env")
    parser = argparse.ArgumentParser(description="Repair canonical Sports Cave GSC storage")
    parser.add_argument("--apply-migrations", action="store_true")
    parser.add_argument("--backfill-legacy", action="store_true")
    parser.add_argument("--refetch-latest-14", action="store_true")
    parser.add_argument("--run-worker", action="store_true")
    args = parser.parse_args(argv)
    if not any(
        (args.apply_migrations, args.backfill_legacy, args.refetch_latest_14, args.run_worker)
    ):
        parser.error("Choose at least one explicit repair action.")
    report = run_repair(
        apply_migrations=args.apply_migrations,
        backfill_legacy=args.backfill_legacy,
        refetch_latest_14=args.refetch_latest_14,
        run_worker=args.run_worker,
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
