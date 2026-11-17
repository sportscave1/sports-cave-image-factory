"""Offline, dry-run-only preview from narrowly scoped read-only source captures."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shopify_financial_repair import preview


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--provider", required=True, type=Path)
    parser.add_argument("--ids", required=True, type=Path, help="JSON array of explicit Order GIDs")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = preview(json.loads(args.ids.read_text(encoding="utf-8")),
                     json.loads(args.ledger.read_text(encoding="utf-8")),
                     json.loads(args.provider.read_text(encoding="utf-8")))
    # Never overwrite an input or an existing evidence file.
    with args.output.open("x", encoding="utf-8") as target:
        json.dump(result, target, indent=2, default=str)
    print(json.dumps({"mode": result["mode"], "rows": len(result["changes"]),
                      "operation_hash": result["operation_hash"], "apply_supported": False}))


if __name__ == "__main__":
    main()
