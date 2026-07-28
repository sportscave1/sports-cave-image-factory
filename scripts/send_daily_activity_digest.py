import argparse
import json
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import daily_activity_digest


def _arguments(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate or send the Sports Cave same-day staff activity report."
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Generate the report without sending or writing delivery history.",
    )
    parser.add_argument(
        "--date",
        dest="report_date",
        help="Preview one Sydney report date in YYYY-MM-DD format. Requires --preview.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = _arguments(argv)
    if args.report_date and not args.preview:
        print("A date override is available only with --preview.")
        return 2
    try:
        report_date = date.fromisoformat(args.report_date) if args.report_date else None
    except ValueError:
        print("The preview date must use YYYY-MM-DD.")
        return 2

    try:
        if args.preview:
            result = daily_activity_digest.preview_daily_digest(report_date=report_date)
            snapshot = result["snapshot"]
            print(
                json.dumps(
                    {
                        "status": "preview",
                        "report_date": snapshot["report_date"],
                        "covered_start_utc": snapshot["covered_start"].isoformat(),
                        "covered_end_utc": snapshot["covered_end"].isoformat(),
                        "subject": snapshot["subject"],
                        "summary": snapshot["summary"],
                        "attention": snapshot["attention"],
                        "staff": [
                            {
                                "name": member["display_name"],
                                "role": member["role"],
                                "actions": member["total_actions"],
                                "failed": member["failed_actions"],
                            }
                            for member in snapshot["staff"]
                        ],
                    },
                    indent=2,
                )
            )
            return 0

        result = daily_activity_digest.run_production_daily_digest()
    except Exception:
        print("Daily staff reporting could not complete. Check the protected delivery history and configuration.")
        return 1

    status = str(result.get("status") or "unknown")
    if result.get("ok"):
        print(
            f"Daily staff reporting status: {status}; "
            f"report date: {result.get('report_date') or 'current Sydney date'}."
        )
        return 0
    print(
        f"Daily staff reporting failed: {result.get('error') or 'Delivery failed.'} "
        f"Report date: {result.get('report_date') or 'current Sydney date'}."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
