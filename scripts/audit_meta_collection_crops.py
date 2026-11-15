"""GET-only audit of current copied Collection ads versus their source template.

No endpoint in this script performs POST, PATCH, DELETE, or validate-only
creation. Placement previews use Meta's official GET-only ``/{ad_id}/previews``
edge. Run it only where existing secured Meta read credentials are configured.
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
from meta_collection_crop_diagnostics import (  # noqa: E402
    DEFAULT_PREVIEW_FORMATS,
    audit_meta_collection_crop_routes,
)
from meta_collection_template_copy import (  # noqa: E402
    configured_collection_template_ad_id,
)


CURRENT_PETER_BROCK_ROUTE_AD_IDS = (
    # Ad 2 first: it has the clearest current Facebook/Instagram evidence.
    "120249748088320554",
    "120249748077780554",
    "120249748105430554",
)


def _parser():
    parser = argparse.ArgumentParser(
        description=(
            "Read Meta crop and placement state for current copied Collection ads. "
            "This command performs GET requests only."
        )
    )
    parser.add_argument(
        "--route-ad-id",
        action="append",
        dest="route_ad_ids",
        help=(
            "Existing copied route Ad ID to inspect. Repeat for multiple routes. "
            "Defaults to the current Peter Brock Ad 2, Ad 1, Ad 3 sequence."
        ),
    )
    parser.add_argument(
        "--source-template-ad-id",
        default=configured_collection_template_ad_id(),
        help="Immutable source-template ad used for comparison.",
    )
    parser.add_argument(
        "--skip-previews",
        action="store_true",
        help="Skip the optional GET-only placement preview reads.",
    )
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    client = MetaPostingClient(get_meta_config())
    report = audit_meta_collection_crop_routes(
        client=client,
        route_ad_ids=args.route_ad_ids or CURRENT_PETER_BROCK_ROUTE_AD_IDS,
        source_template_ad_id=args.source_template_ad_id,
        preview_formats=() if args.skip_previews else DEFAULT_PREVIEW_FORMATS,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
