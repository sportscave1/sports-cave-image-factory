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
    parser = argparse.ArgumentParser(description="Reconcile one Shopify order without scanning order history.")
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument("--order-id", help="Immutable Shopify order GID or legacy numeric ID.")
    identity.add_argument("--order-name", help="Display name, used only to resolve the immutable Shopify ID.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist/repair the order. Without this flag the command is read-only.",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    result = supabase_backend.reconcile_single_shopify_order(
        shopify_order_id=args.order_id or "",
        order_name=args.order_name or "",
        apply=bool(args.apply),
    )
    print(json.dumps(result, indent=2, ensure_ascii=True, default=str))
    if not result.get("eligible"):
        return 2
    if args.apply and (not result.get("applied") or result.get("errors")):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
