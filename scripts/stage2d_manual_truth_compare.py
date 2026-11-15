#!/usr/bin/env python3
"""Read-only Stage 2D comparison against manual sent-out edition truth."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


FORBIDDEN_ARGS = {
    "--apply",
    "apply",
    "--write",
    "write",
    "--sync",
    "sync",
    "--backfill",
    "backfill",
    "--repair",
    "repair",
}

DEFAULT_MANUAL_FILE = Path("input") / "manual_sent_editions_20260625.tsv"
DEFAULT_STAGE2_GLOB = "stage2_live_dry_run_*"

EXPECTED_STAGE2_FILES = (
    "safe_import_candidates.csv",
    "conflicts_needs_review.csv",
    "goat_debate_investigation.csv",
    "recovered_edition_allocations.csv",
    "recovered_certificates.csv",
    "summary.md",
)

SUMMARY_FILE = "stage2d_summary.md"
OUTPUT_FILES = (
    "import_ready_manual_matches_shopify.csv",
    "import_ready_manual_overrides_shopify.csv",
    "import_ready_shopify_only_no_manual_conflict.csv",
    "shopify_conflicts_with_manual.csv",
    "manual_truth_unmatched_to_shopify.csv",
    "duplicate_conflicts.csv",
    "skip_none_or_dash.csv",
    "proposed_supabase_import_preview.csv",
    "proposed_manual_repairs_preview.csv",
    "stage3_apply_exact_matches_prompt.md",
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    forbidden = [arg for arg in argv if arg.strip().lower() in FORBIDDEN_ARGS]
    if forbidden:
        print("Refusing to run: this Stage 2D tool is dry-run/read-only only.")
        print("Forbidden argument(s): " + ", ".join(forbidden))
        raise SystemExit(2)

    parser = argparse.ArgumentParser(
        description="Compare Stage 2 Shopify recovery against manual sent-out truth."
    )
    parser.add_argument(
        "--manual-file",
        default=str(DEFAULT_MANUAL_FILE),
        help="Tab-separated manual truth file.",
    )
    parser.add_argument(
        "--stage2-dir",
        default="",
        help="Specific Stage 2 live dry-run folder. Defaults to latest output/stage2_live_dry_run_*.",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Output folder. Defaults to output/stage2d_manual_truth_compare_YYYYMMDD_HHMM.",
    )
    return parser.parse_args(argv)


def normalize_whitespace(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\r", " ").replace("\n", " ")).strip()


def normalize_quotes(value: Any) -> str:
    text = str(value or "")
    replacements = {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u00a0": " ",
    }
    for src, target in replacements.items():
        text = text.replace(src, target)
    return text


def normalize_customer_name(value: Any) -> str:
    return normalize_whitespace(normalize_quotes(value)).lower()


def normalize_product_title(value: Any) -> str:
    return normalize_whitespace(normalize_quotes(value)).lower()


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def positive_int(value: Any) -> int | None:
    try:
        number = int(str(value or "").strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def parse_edition_raw(value: Any) -> dict[str, Any]:
    raw = normalize_whitespace(value)
    lowered = raw.lower()
    if lowered in {"", "-", "--", "*", "none", "n/a", "na"}:
        return {"status": "skip", "edition_number": None, "normalized": raw}
    match = re.search(r"#?\s*0*(\d+)(?:\s*/\s*\d+)?", raw)
    if not match:
        return {"status": "invalid", "edition_number": None, "normalized": raw}
    edition_number = positive_int(match.group(1))
    if not edition_number:
        return {"status": "invalid", "edition_number": None, "normalized": raw}
    return {"status": "ok", "edition_number": edition_number, "normalized": f"#{edition_number:03d}"}


def load_csv_rows(path: Path, delimiter: str = ",") -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        return [dict(row) for row in reader]


def write_csv(path: Path, rows: list[dict[str, Any]], preferred_fields: list[str] | None = None) -> None:
    fields: list[str] = []
    for field in preferred_fields or []:
        if field not in fields:
            fields.append(field)
    for row in rows:
        for field in row.keys():
            if field not in fields:
                fields.append(field)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or ["empty"])
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def find_latest_stage2_dir(explicit: str) -> Path | None:
    if explicit:
        path = Path(explicit)
        return path if path.exists() and path.is_dir() else None
    candidates = [
        path
        for path in Path("output").glob(DEFAULT_STAGE2_GLOB)
        if path.is_dir()
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda path: (path.name, path.stat().st_mtime), reverse=True)[0]


def ensure_output_dir(explicit: str) -> Path:
    if explicit:
        output_dir = Path(explicit)
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        output_dir = Path("output") / f"stage2d_manual_truth_compare_{stamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def shopify_identity_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("order_id") or "").strip(),
        str(row.get("line_item_shopify_id") or row.get("line_item_id") or "").strip(),
        str(row.get("quantity_index") or "").strip(),
    )


def shopify_dedupe_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("order_id") or "").strip(),
        str(row.get("line_item_shopify_id") or row.get("line_item_id") or "").strip(),
        str(row.get("product_id") or row.get("product_handle") or row.get("product_title") or "").strip().lower(),
        str(row.get("edition_number") or "").strip(),
        str(row.get("quantity_index") or "").strip(),
    )


def product_edition_key(row: dict[str, Any]) -> tuple[str, int]:
    product_key = str(
        row.get("product_handle")
        or row.get("product_id")
        or row.get("product_title")
        or ""
    ).strip().lower()
    edition_number = positive_int(row.get("edition_number")) or 0
    return product_key, edition_number


def load_stage2_inputs(stage2_dir: Path) -> dict[str, Any]:
    missing = [name for name in EXPECTED_STAGE2_FILES if not (stage2_dir / name).exists()]
    if missing:
        print("Stage 2D compare cannot run because the latest Stage 2 folder is incomplete.")
        for name in missing:
            print(f"Missing: {stage2_dir / name}")
        raise SystemExit(0)

    return {
        "safe_rows": load_csv_rows(stage2_dir / "safe_import_candidates.csv"),
        "conflict_rows": load_csv_rows(stage2_dir / "conflicts_needs_review.csv"),
        "goat_rows": load_csv_rows(stage2_dir / "goat_debate_investigation.csv"),
        "recovered_rows": load_csv_rows(stage2_dir / "recovered_edition_allocations.csv"),
        "certificate_rows": load_csv_rows(stage2_dir / "recovered_certificates.csv"),
        "summary_md": (stage2_dir / "summary.md").read_text(encoding="utf-8"),
    }


def load_manual_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        print(f"Manual truth file not found: {path}")
        raise SystemExit(0)
    rows = load_csv_rows(path, delimiter="\t")
    if not rows:
        print(f"Manual truth file is present but has no data rows yet: {path}")
        raise SystemExit(0)
    return rows


def dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        key = shopify_dedupe_key(row)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def prepare_shopify_rows(stage2_data: dict[str, Any]) -> list[dict[str, Any]]:
    safe_keys = {shopify_dedupe_key(row) for row in stage2_data["safe_rows"]}
    conflict_index: dict[tuple[str, str, str, str, str], dict[str, Any]] = {
        shopify_dedupe_key(row): row for row in stage2_data["conflict_rows"]
    }
    certificate_keys = {
        (
            str(row.get("order_id") or "").strip(),
            str(row.get("shopify_line_item_id") or "").strip(),
            str(positive_int(row.get("edition_number")) or ""),
        )
        for row in stage2_data["certificate_rows"]
    }

    prepared: list[dict[str, Any]] = []
    for row in dedupe_rows(stage2_data["recovered_rows"]):
        edition_number = positive_int(row.get("edition_number"))
        identity = shopify_identity_key(row)
        dedupe_key = shopify_dedupe_key(row)
        stage2_conflict = conflict_index.get(dedupe_key) or {}
        conflict_type = str(stage2_conflict.get("conflict_type") or "").strip()
        classification = "safe" if dedupe_key in safe_keys else "conflict" if stage2_conflict else "recovered_only"
        prepared.append(
            {
                **row,
                "edition_number_int": edition_number,
                "manual_override_bool": truthy(row.get("manual_override")),
                "customer_name_norm": normalize_customer_name(row.get("customer_name")),
                "product_title_norm": normalize_product_title(row.get("product_title")),
                "identity_key": identity,
                "dedupe_key": dedupe_key,
                "stage2_classification": classification,
                "stage2_conflict_type": conflict_type,
                "has_missing_identifier": not (
                    str(row.get("order_id") or "").strip()
                    and str(row.get("line_item_shopify_id") or row.get("line_item_id") or "").strip()
                    and (
                        str(row.get("product_handle") or "").strip()
                        or str(row.get("product_id") or "").strip()
                    )
                ),
                "has_certificate_payload": (
                    str(row.get("order_id") or "").strip(),
                    str(row.get("line_item_shopify_id") or "").strip(),
                    str(edition_number or ""),
                ) in certificate_keys,
            }
        )
    return prepared


def prepare_manual_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        parsed = parse_edition_raw(row.get("edition_raw"))
        prepared.append(
            {
                "manual_row_number": index,
                "customer_name": normalize_whitespace(row.get("customer_name")),
                "product_title": normalize_whitespace(row.get("product_title")),
                "edition_raw": normalize_whitespace(row.get("edition_raw")),
                "customer_name_norm": normalize_customer_name(row.get("customer_name")),
                "product_title_norm": normalize_product_title(row.get("product_title")),
                "manual_edition_status": parsed["status"],
                "manual_edition_number": parsed["edition_number"],
                "manual_edition_normalized": parsed["normalized"],
            }
        )
    return prepared


def build_candidate_index(shopify_rows: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    by_pair: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in shopify_rows:
        key = (row["customer_name_norm"], row["product_title_norm"])
        by_pair[key].append(row)
    for key in by_pair:
        by_pair[key] = sorted(
            by_pair[key],
            key=lambda row: (
                str(row.get("order_created_at") or ""),
                str(row.get("order_name") or ""),
                str(row.get("line_item_position") or ""),
                str(row.get("quantity_index") or ""),
            ),
        )
    return by_pair


def base_compare_record(manual_row: dict[str, Any], candidate: dict[str, Any] | None = None) -> dict[str, Any]:
    record = {
        "manual_row_number": manual_row.get("manual_row_number") or "",
        "customer_name": manual_row.get("customer_name") or "",
        "product_title": manual_row.get("product_title") or "",
        "edition_raw": manual_row.get("edition_raw") or "",
        "manual_edition_number": manual_row.get("manual_edition_number") or "",
        "manual_edition_normalized": manual_row.get("manual_edition_normalized") or "",
    }
    if candidate:
        record.update(
            {
                "order_id": candidate.get("order_id") or "",
                "order_name": candidate.get("order_name") or "",
                "order_created_at": candidate.get("order_created_at") or "",
                "line_item_shopify_id": candidate.get("line_item_shopify_id") or candidate.get("line_item_id") or "",
                "quantity_index": candidate.get("quantity_index") or "",
                "product_handle": candidate.get("product_handle") or "",
                "product_id": candidate.get("product_id") or "",
                "shopify_edition_number": candidate.get("edition_number_int") or "",
                "shopify_manual_override": "yes" if candidate.get("manual_override_bool") else "no",
                "shopify_stage2_classification": candidate.get("stage2_classification") or "",
                "shopify_stage2_conflict_type": candidate.get("stage2_conflict_type") or "",
                "has_certificate_payload": "yes" if candidate.get("has_certificate_payload") else "no",
            }
        )
    return record


def stage2_conflict_bucket(candidate: dict[str, Any]) -> str:
    conflict_type = str(candidate.get("stage2_conflict_type") or "").lower()
    if "duplicate" in conflict_type:
        return "duplicate_conflicts"
    if candidate.get("has_missing_identifier") or "missing_" in conflict_type:
        return "missing_identifier"
    if conflict_type:
        return "needs_human_review"
    return ""


def classify_manual_against_shopify(
    manual_rows: list[dict[str, Any]],
    shopify_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    candidates_by_pair = build_candidate_index(shopify_rows)
    results = {
        "import_ready_manual_matches_shopify": [],
        "import_ready_manual_overrides_shopify": [],
        "import_ready_shopify_only_no_manual_conflict": [],
        "shopify_conflicts_with_manual": [],
        "manual_truth_unmatched_to_shopify": [],
        "duplicate_conflicts": [],
        "skip_none_or_dash": [],
        "proposed_supabase_import_preview": [],
        "proposed_manual_repairs_preview": [],
        "needs_human_review": [],
        "missing_identifier": [],
    }
    touched_shopify_keys: set[tuple[str, str, str]] = set()

    duplicate_rows_seen: set[tuple[str, str, str]] = set()
    for row in shopify_rows:
        if stage2_conflict_bucket(row) == "duplicate_conflicts":
            identity = row["identity_key"]
            if identity in duplicate_rows_seen:
                continue
            duplicate_rows_seen.add(identity)
            results["duplicate_conflicts"].append(
                {
                    "classification": "duplicate_conflicts",
                    "customer_name": row.get("customer_name") or "",
                    "product_title": row.get("product_title") or "",
                    "order_name": row.get("order_name") or "",
                    "order_created_at": row.get("order_created_at") or "",
                    "line_item_shopify_id": row.get("line_item_shopify_id") or row.get("line_item_id") or "",
                    "quantity_index": row.get("quantity_index") or "",
                    "shopify_edition_number": row.get("edition_number_int") or "",
                    "shopify_stage2_conflict_type": row.get("stage2_conflict_type") or "",
                    "note": "Existing Stage 2 duplicate conflict.",
                }
            )

    for manual_row in manual_rows:
        if manual_row["manual_edition_status"] == "skip":
            results["skip_none_or_dash"].append(
                {
                    **base_compare_record(manual_row),
                    "classification": "skip_none_or_dash",
                    "note": "Manual edition_raw was none/*/dash/blank; skipped.",
                }
            )
            continue
        if manual_row["manual_edition_status"] != "ok":
            results["needs_human_review"].append(
                {
                    **base_compare_record(manual_row),
                    "classification": "needs_human_review",
                    "note": "Manual edition_raw could not be parsed.",
                }
            )
            continue

        pair_key = (manual_row["customer_name_norm"], manual_row["product_title_norm"])
        candidates = list(candidates_by_pair.get(pair_key) or [])
        if not candidates:
            results["manual_truth_unmatched_to_shopify"].append(
                {
                    **base_compare_record(manual_row),
                    "classification": "manual_truth_unmatched_to_shopify",
                    "note": "No Shopify recovered allocation row matched customer_name + product_title.",
                }
            )
            continue

        exact_candidates = [
            row for row in candidates
            if row.get("edition_number_int") == manual_row["manual_edition_number"]
        ]
        chosen: dict[str, Any] | None = None
        classification = ""
        note = ""

        if len(exact_candidates) == 1:
            chosen = exact_candidates[0]
            bucket = stage2_conflict_bucket(chosen)
            if bucket == "duplicate_conflicts":
                classification = "duplicate_conflicts"
                note = "Exact manual/shopify match exists but the Shopify row is already in a duplicate conflict set."
            elif bucket == "missing_identifier":
                classification = "missing_identifier"
                note = "Exact manual/shopify match exists but required Shopify identifiers are missing."
            elif bucket == "needs_human_review":
                classification = "needs_human_review"
                note = "Exact manual/shopify match exists but the Stage 2 row still needs human review."
            else:
                classification = "import_ready_manual_matches_shopify"
                note = "Manual truth exactly matches recovered Shopify allocation."
        elif len(exact_candidates) > 1:
            classification = "needs_human_review"
            note = "Multiple Shopify rows matched the same customer/product and edition."
        elif len(candidates) == 1:
            chosen = candidates[0]
            bucket = stage2_conflict_bucket(chosen)
            if bucket == "duplicate_conflicts":
                classification = "duplicate_conflicts"
                note = "Manual truth points to a Shopify row already flagged as a duplicate conflict."
            elif bucket == "missing_identifier":
                classification = "missing_identifier"
                note = "Manual truth points to a Shopify row missing required identifiers."
            elif bucket == "needs_human_review":
                classification = "needs_human_review"
                note = "Manual truth points to a Shopify row that still needs human review."
            else:
                classification = "import_ready_manual_overrides_shopify"
                note = "Manual truth overrides the recovered Shopify edition number for this exact customer/product match."
        else:
            classification = "needs_human_review"
            note = "Multiple Shopify rows matched the same customer/product and no unique exact-edition candidate exists."

        if chosen:
            touched_shopify_keys.add(chosen["identity_key"])
        if classification in {"needs_human_review", "duplicate_conflicts", "missing_identifier"}:
            for row in candidates:
                touched_shopify_keys.add(row["identity_key"])

        record = {
            **base_compare_record(manual_row, chosen),
            "classification": classification,
            "candidate_count": len(candidates),
            "exact_edition_candidate_count": len(exact_candidates),
            "note": note,
        }

        if classification == "import_ready_manual_matches_shopify":
            results["import_ready_manual_matches_shopify"].append(record)
        elif classification == "import_ready_manual_overrides_shopify":
            results["import_ready_manual_overrides_shopify"].append(record)
            results["proposed_manual_repairs_preview"].append(
                {
                    **record,
                    "recommended_action": "import_manual_truth_into_supabase_without_updating_shopify_yet",
                }
            )
        elif classification == "manual_truth_unmatched_to_shopify":
            results["manual_truth_unmatched_to_shopify"].append(record)
        elif classification == "duplicate_conflicts":
            results["duplicate_conflicts"].append(record)
        elif classification == "missing_identifier":
            results["missing_identifier"].append(record)
        elif classification == "needs_human_review":
            results["needs_human_review"].append(record)
        else:
            results["shopify_conflicts_with_manual"].append(record)

    conflict_identity_keys = {
        row["identity_key"]
        for row in shopify_rows
        if row.get("stage2_classification") == "conflict"
    }
    blocked_for_shopify_only = touched_shopify_keys | conflict_identity_keys
    for row in shopify_rows:
        if row["identity_key"] in blocked_for_shopify_only:
            continue
        if row.get("stage2_classification") != "safe":
            continue
        if not row.get("edition_number_int"):
            continue
        if row.get("has_missing_identifier"):
            continue
        results["import_ready_shopify_only_no_manual_conflict"].append(
            {
                "classification": "import_ready_shopify_only_no_manual_conflict",
                "customer_name": row.get("customer_name") or "",
                "product_title": row.get("product_title") or "",
                "order_name": row.get("order_name") or "",
                "order_created_at": row.get("order_created_at") or "",
                "order_id": row.get("order_id") or "",
                "line_item_shopify_id": row.get("line_item_shopify_id") or row.get("line_item_id") or "",
                "quantity_index": row.get("quantity_index") or "",
                "product_handle": row.get("product_handle") or "",
                "product_id": row.get("product_id") or "",
                "shopify_edition_number": row.get("edition_number_int") or "",
                "shopify_manual_override": "yes" if row.get("manual_override_bool") else "no",
                "has_certificate_payload": "yes" if row.get("has_certificate_payload") else "no",
                "note": "No conflicting manual truth row matched this Shopify recovered allocation.",
            }
        )

    for key in ("missing_identifier", "needs_human_review"):
        for row in results[key]:
            results["shopify_conflicts_with_manual"].append(row)

    results["proposed_supabase_import_preview"] = (
        [
            {
                **row,
                "truth_source": "manual_sent_out_list",
                "recommended_import_edition_number": row.get("manual_edition_number") or "",
            }
            for row in results["import_ready_manual_matches_shopify"]
        ]
        + [
            {
                **row,
                "truth_source": "manual_sent_out_list_override",
                "recommended_import_edition_number": row.get("manual_edition_number") or "",
            }
            for row in results["import_ready_manual_overrides_shopify"]
        ]
        + [
            {
                **row,
                "truth_source": "shopify_order_metafield",
                "recommended_import_edition_number": row.get("shopify_edition_number") or "",
            }
            for row in results["import_ready_shopify_only_no_manual_conflict"]
        ]
    )

    return results


def goat_recommendation(goat_rows: list[dict[str, Any]]) -> str:
    found_050_051 = {
        positive_int(row.get("edition_number"))
        for row in goat_rows
        if str(row.get("source") or "") != "not_found_in_fetched_shopify_order_metafields"
        and positive_int(row.get("edition_number")) in {50, 51}
    }
    found_094_095 = {
        positive_int(row.get("edition_number"))
        for row in goat_rows
        if str(row.get("source") or "") != "not_found_in_fetched_shopify_order_metafields"
        and positive_int(row.get("edition_number")) in {94, 95}
    }
    if found_050_051 and not found_094_095:
        return (
            "Trust GOAT Debate #050/#051 as the current per-order truth. Treat #094/#095 as stale local display unless a stronger source appears."
        )
    if found_050_051 and found_094_095:
        return (
            "GOAT Debate has competing truths in the fetched artifacts; hold for human review before any import."
        )
    return "GOAT Debate evidence is incomplete in the fetched artifacts; do not repair automatically."


def write_summary(
    path: Path,
    stage2_dir: Path,
    manual_file: Path,
    manual_rows: list[dict[str, Any]],
    results: dict[str, Any],
    goat_text: str,
) -> None:
    exact_matches = len(results["import_ready_manual_matches_shopify"])
    manual_overrides = len(results["import_ready_manual_overrides_shopify"])
    shopify_only = len(results["import_ready_shopify_only_no_manual_conflict"])
    conflicts = (
        len(results["shopify_conflicts_with_manual"])
        + len(results["duplicate_conflicts"])
    )
    unmatched_manual = len(results["manual_truth_unmatched_to_shopify"])
    safe_exact_matches_only = "yes" if exact_matches > 0 else "no"

    lines = [
        "# Stage 2D Manual Truth Compare",
        "",
        "Dry-run only. No Supabase writes, Shopify updates, order syncs, repairs, or certificate generation were attempted.",
        "",
        "## Inputs",
        f"- Manual truth file: `{manual_file}`",
        f"- Stage 2 source folder: `{stage2_dir}`",
        "",
        "## Counts",
        f"- Manual truth row count: {len(manual_rows)}",
        f"- Exact manual/shopify matches count: {exact_matches}",
        f"- Manual overrides needed count: {manual_overrides}",
        f"- Shopify-only import-ready count: {shopify_only}",
        f"- Conflicts count: {conflicts}",
        f"- Unmatched manual rows count: {unmatched_manual}",
        f"- Skip none/*/dash count: {len(results['skip_none_or_dash'])}",
        f"- Needs human review count: {len(results['needs_human_review'])}",
        f"- Missing identifier count: {len(results['missing_identifier'])}",
        f"- Duplicate conflicts count: {len(results['duplicate_conflicts'])}",
        "",
        "## GOAT Debate recommendation",
        f"- {goat_text}",
        "",
        "## Safety",
        f"- Safe to import exact matches only: {safe_exact_matches_only}",
        "- Safe to sync new orders: no",
        "- Safe to generate certificates: no",
        "",
        "## Truth priority applied",
        "- Manual sent-out list wins where exact customer + product match exists and the match is unique enough to trust.",
        "- Shopify order metafield wins where there is no manual sent-out row conflict.",
        "- Certificate/customer vault metafield is treated as stronger than local/session display only for annotation here; this Stage 2D script does not rewrite truth.",
        "- Product metafields are treated as counter mirrors, not per-order truth.",
        "",
        "## Files written",
    ]
    for name in OUTPUT_FILES:
        lines.append(f"- `{name}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_stage3_prompt(path: Path, output_dir: Path) -> None:
    lines = [
        "# Stage 3 Apply Exact Matches Prompt",
        "",
        "STAGE 3 APPLY EXACT MATCHES ONLY — Import reviewed exact manual/shopify matches into Supabase.",
        "",
        "Use these files from the latest Stage 2D folder:",
        f"- `{output_dir / 'import_ready_manual_matches_shopify.csv'}`",
        f"- `{output_dir / 'proposed_supabase_import_preview.csv'}`",
        "",
        "Rules:",
        "- Do not update Shopify metafields.",
        "- Do not sync new Shopify orders.",
        "- Do not generate certificates.",
        "- Do not repair manual override rows yet unless separately approved.",
        "- Do not import rows from duplicate_conflicts, manual_truth_unmatched_to_shopify, or shopify_conflicts_with_manual.",
        "",
        "Goal:",
        "- Import exact manual/shopify matches only into Supabase as the first low-risk customer-facing truth set.",
        "",
        "After import:",
        "- Re-run Stage 2D compare and report remaining manual overrides and conflicts before any new-order sync.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))

    manual_file = Path(args.manual_file)
    stage2_dir = find_latest_stage2_dir(args.stage2_dir)
    if not stage2_dir:
        print("No Stage 2 live dry-run folder was found under output/stage2_live_dry_run_*.")
        print("Run Stage 2B in Render first, or pass --stage2-dir explicitly.")
        return 0

    manual_rows = prepare_manual_rows(load_manual_rows(manual_file))
    stage2_data = load_stage2_inputs(stage2_dir)
    shopify_rows = prepare_shopify_rows(stage2_data)
    results = classify_manual_against_shopify(manual_rows, shopify_rows)
    goat_text = goat_recommendation(stage2_data["goat_rows"])

    output_dir = ensure_output_dir(args.output_dir)
    write_summary(
        output_dir / SUMMARY_FILE,
        stage2_dir,
        manual_file,
        manual_rows,
        results,
        goat_text,
    )
    write_csv(output_dir / "import_ready_manual_matches_shopify.csv", results["import_ready_manual_matches_shopify"])
    write_csv(output_dir / "import_ready_manual_overrides_shopify.csv", results["import_ready_manual_overrides_shopify"])
    write_csv(output_dir / "import_ready_shopify_only_no_manual_conflict.csv", results["import_ready_shopify_only_no_manual_conflict"])
    write_csv(output_dir / "shopify_conflicts_with_manual.csv", results["shopify_conflicts_with_manual"])
    write_csv(output_dir / "manual_truth_unmatched_to_shopify.csv", results["manual_truth_unmatched_to_shopify"])
    write_csv(output_dir / "duplicate_conflicts.csv", results["duplicate_conflicts"])
    write_csv(output_dir / "skip_none_or_dash.csv", results["skip_none_or_dash"])
    write_csv(output_dir / "proposed_supabase_import_preview.csv", results["proposed_supabase_import_preview"])
    write_csv(output_dir / "proposed_manual_repairs_preview.csv", results["proposed_manual_repairs_preview"])
    write_stage3_prompt(output_dir / "stage3_apply_exact_matches_prompt.md", output_dir)

    print(f"Stage 2D manual truth compare written to: {output_dir}")
    print("No Supabase writes, Shopify updates, syncs, repairs, or certificate generation were performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
