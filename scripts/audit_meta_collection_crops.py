"""GET-only audit of a copied Collection ad versus its source template.

No endpoint in this script performs POST, PATCH, DELETE, ad preview generation,
or validate-only creation.  Run it only where the existing secured Meta read
credentials are already configured.
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
    audit_meta_collection_crop_state,
)
from meta_collection_template_copy import (  # noqa: E402
    configured_collection_template_ad_id,
)


CURRENT_PETER_BROCK_ROUTE_1_AD_ID = "120249745246230554"


def _parser():
    parser = argparse.ArgumentParser(
        description=(
            "Read Meta crop and placement state for one copied Collection ad. "
            "This command performs GET requests only."
        )
    )
    parser.add_argument(
        "--route-ad-id",
        default=CURRENT_PETER_BROCK_ROUTE_1_AD_ID,
        help="Existing copied route ad to inspect.",
    )
    parser.add_argument(
        "--source-template-ad-id",
        default=configured_collection_template_ad_id(),
        help="Immutable source-template ad used for comparison.",
    )
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    client = MetaPostingClient(get_meta_config())
    report = audit_meta_collection_crop_state(
        client=client,
        route_ad_id=args.route_ad_id,
        source_template_ad_id=args.source_template_ad_id,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
