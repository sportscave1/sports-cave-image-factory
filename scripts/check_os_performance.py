"""Synthetic CI regression ceilings, not authenticated production speed claims."""
import argparse
import json
from pathlib import Path
import statistics


def check(startup, pages):
    failures = []
    def require(condition, name):
        if not condition:
            failures.append(name)
    normal = startup.get("normal", [])
    require(len(normal) >= 3, "three fresh-browser transport samples")
    require(bool(startup.get("slow")), "throttled transport coverage")
    require(bool(startup.get("restarts")), "server restart coverage")
    encoded = []
    for key in ("normal", "slow"):
        for sample in startup.get(key, []):
            cold, reopened = sample["cold"], sample["reopened"]
            require(bool(cold["assets"]), "nonempty downloaded bundles")
            require(sum(a["transferBytes"] for a in reopened["assets"]) == 0, "zero cached bundle transfer")
            require(not sample["errors"] and not sample["external_requests"], "no browser or external-network errors")
            require(cold["usableMs"] <= (15000 if key == "slow" else 5000), key + " cold fixture ceiling")
            if key == "normal":
                encoded.append(sum(a["encodedBytes"] for a in cold["assets"]))
    require(bool(encoded) and statistics.median(encoded) <= 850000, "median frontend encoding <=850000 bytes")
    require(any(h["encoding"] == "br" for s in normal for h in s["cold"]["assetHeaders"].values()), "Brotli actually delivered")
    rows = [r for r in pages.get("results", []) if r["mode"] == "after"]
    require(any(r.get("route") == "Home" and "ready_ms" in r for r in rows), "Home browser coverage")
    require(any(r.get("route") == "Orders" and r.get("simulated_read_seconds") == 1.4 for r in rows), "slow Orders browser coverage")
    for row in rows:
        if "ready_ms" in row:
            require(row["full_app_runs_for_navigation"] == 1, "no completion full-app rerun")
            require(row["ready_ms"] <= 4000, "page synthetic read ceiling")
        if "search_ms" in row:
            require(row["search_full_app_reruns"] == 0, "no search full-app rerun")
        if row.get("route") == "Orders" and row.get("simulated_read_seconds") == 1.4:
            require(row.get("previous_rows_visible_during_search") is True, "retain rows during slow search")
    return failures


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--startup", type=Path, required=True)
    parser.add_argument("--pages", type=Path, required=True)
    args = parser.parse_args()
    failures = check(json.loads(args.startup.read_text()), json.loads(args.pages.read_text()))
    print(json.dumps({"passed": not failures, "failures": failures}, indent=2))
    raise SystemExit(bool(failures))
