"""Read the manual Carousel reference and run Meta validate_only probes.

No persistent Meta endpoint is available from this script. Without ``--execute``
it sends no requests. With ``--execute`` it performs four Graph GETs followed by
exactly two POSTs guarded by ``execution_options=["validate_only"]``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from meta_ads_client import MetaPostingClient, get_meta_config  # noqa: E402
from meta_carousel_diagnostics import (  # noqa: E402
    MANUAL_CAROUSEL_ADSET_ID,
    MetaCarouselValidateOnlyProbe,
    reference_carousel_image_hashes,
    validate_manual_carousel_reference_contract,
)
from meta_posting_service import build_carousel_creative_payload  # noqa: E402


def _parser():
    parser = argparse.ArgumentParser(
        description=(
            "GET the known Sports Cave Carousel reference and validate one standalone "
            "creative plus one PAUSED inline Ad without persistent Meta writes."
        )
    )
    parser.add_argument(
        "--adset-id",
        default=MANUAL_CAROUSEL_ADSET_ID,
        help=(
            "Ad Set used by the inline-Ad validate_only probe. Pass a current "
            "Instant Experience Product-Set Ad Set for the critical compatibility test."
        ),
    )
    parser.add_argument(
        "--product-url",
        default="https://www.sportscaveshop.com/products/validate-only-carousel",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run GET plus validate_only requests. Never enables a persistent write.",
    )
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    report = {
        "persistent_meta_writes": "NONE",
        "target_adset_id": str(args.adset_id),
        "status": "dry_run",
    }
    if not args.execute:
        report["message"] = (
            "No Meta request was sent. Re-run with --execute in the secured service "
            "environment to perform the GET and validate_only audit."
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    config = get_meta_config()
    client = MetaPostingClient(config)
    contract = client.carousel_reference_contract()
    report["reference"] = validate_manual_carousel_reference_contract(contract)
    reference_hashes = reference_carousel_image_hashes(contract)
    cards = tuple(
        {
            "image_hash": image_hash,
            "headline": f"Sports Cave Carousel Card {index}",
            "description": f"Sports Cave Carousel Description {index}",
        }
        for index, image_hash in enumerate(reference_hashes, start=1)
    )
    primary_texts = tuple(
        f"SPORTS CAVE CAROUSEL VALIDATE ONLY {index}" for index in range(1, 6)
    )
    creative = build_carousel_creative_payload(
        name="Sports Cave Carousel validate-only",
        page_id=client.page_id,
        instagram_user_id=client.instagram_user_id,
        cards=cards,
        primary_texts=primary_texts,
        destination_url=args.product_url,
    )
    report["status"] = "validate_only_complete"
    report["results"] = MetaCarouselValidateOnlyProbe(config).run(
        ad_name="Sports Cave Carousel validate-only",
        adset_id=args.adset_id,
        creative_payload=creative,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["results"].get("validated") else 2


if __name__ == "__main__":
    raise SystemExit(main())
