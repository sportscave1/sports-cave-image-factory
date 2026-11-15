"""Targeted, idempotent Shopify order reconciliation.

Dry-run is the default. The display name is used only to resolve the immutable
Shopify order ID; all persistence and allocation identities use Shopify IDs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import supabase_backend  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reconcile exact Shopify orders without scanning order history.")
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument(
        "--order-id",
        action="append",
        help="Immutable Shopify order GID or legacy numeric ID. Repeat for a narrow set.",
    )
    identity.add_argument("--order-name", help="Display name, used only to resolve the immutable Shopify ID.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist/repair the order. Without this flag the command is read-only.",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="Emit a new-order notification while applying. Historical repairs do not notify by default.",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.notify and not args.apply:
        raise SystemExit("--notify requires --apply.")
    identities = args.order_id or [""]
    results = [
        supabase_backend.reconcile_single_shopify_order(
            shopify_order_id=order_id,
            order_name=args.order_name or "",
            apply=bool(args.apply),
            notify=bool(args.notify),
            ensure_schema_first=False,
        )
        for order_id in identities
    ]
    output = results[0] if len(results) == 1 else {"mode": "apply" if args.apply else "dry_run", "results": results}
    print(json.dumps(output, indent=2, ensure_ascii=True, default=str))
    if any(not result.get("eligible") for result in results):
        return 2
    if args.apply and any(not result.get("applied") or result.get("errors") for result in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
