"""Run Meta Collection Test A/Test B with validate_only and no persistent write.

This script is deliberately not imported by the Streamlit application.  It
prints redacted request shapes by default; an operator must explicitly add
``--execute`` inside an environment that already holds the secured Meta
credentials to transmit the two validate-only requests.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from meta_ads_client import get_meta_config  # noqa: E402
from meta_collection_diagnostics import (  # noqa: E402
    MetaCollectionValidateOnlyProbe,
    sanitized_collection_request_shape,
)
from meta_posting_service import build_collection_creative_payload  # noqa: E402


PETER_BROCK_ADSET_ID = "120249720389890554"
PETER_BROCK_IA1_ID = "1390026833255926"


def _parser():
    parser = argparse.ArgumentParser(
        description="Validate standalone versus inline Meta Collection creation without writes."
    )
    parser.add_argument("--adset-id", default=PETER_BROCK_ADSET_ID)
    parser.add_argument("--canvas-id", default=PETER_BROCK_IA1_ID)
    parser.add_argument("--image-hash", required=True)
    parser.add_argument("--product-set-id", required=True)
    parser.add_argument("--primary-text", required=True)
    parser.add_argument("--headline", required=True)
    parser.add_argument(
        "--execute",
        action="store_true",
        help='Transmit only requests guarded by execution_options=["validate_only"].',
    )
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    config = get_meta_config()
    creative = build_collection_creative_payload(
        name="Sports Cave validate-only Peter Brock route 1 | Collection",
        page_id=config.get("page_id"),
        instagram_user_id=config.get("instagram_user_id"),
        image_hash=args.image_hash,
        canvas_id=args.canvas_id,
        product_set_id=args.product_set_id,
        destination_url="",
        primary_text=args.primary_text,
        headline=args.headline,
    )
    report = {
        "persistent_meta_writes": False,
        "request_shapes": {
            "test_a": sanitized_collection_request_shape(mode="standalone"),
            "test_b": sanitized_collection_request_shape(
                mode="inline_ad", adset_id=args.adset_id
            ),
        },
    }
    if not args.execute:
        report["status"] = "dry_run"
        report["message"] = (
            "No Meta request was sent. Re-run with --execute only inside the secured "
            "service environment to perform validate-only Tests A and B."
        )
    else:
        probe = MetaCollectionValidateOnlyProbe(config)
        report["status"] = "validate_only_complete"
        report["results"] = probe.run_ab(
            ad_name="Sports Cave validate-only Peter Brock route 1",
            adset_id=args.adset_id,
            creative_payload=creative,
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
