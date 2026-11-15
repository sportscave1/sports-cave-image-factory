"""Audit direct, saved and rendered analytics layers from exported JSON payloads."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import analytics_reporting


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Identify the first divergence between direct GA4, saved Postgres and rendered values."
    )
    parser.add_argument("--direct", required=True, help="Canonical direct GA4 report JSON")
    parser.add_argument("--stored", required=True, help="Saved report-row JSON")
    parser.add_argument("--rendered", required=True, help="Rendered metric JSON")
    parser.add_argument("--output", help="Optional result JSON path")
    args = parser.parse_args(argv)
    result = analytics_reporting.reconcile_layers(
        _read(args.direct),
        _read(args.stored),
        _read(args.rendered),
    )
    payload = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if result["divergence"] == "none" else 1


if __name__ == "__main__":
    raise SystemExit(main())
