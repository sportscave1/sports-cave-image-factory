"""Historical reporting adapter for the retired social planner.

No schema initialization and no reads from the retired task/content tables.
Existing historical activity reporting retains its aggregate shape.
"""


def collect_reporting_social_summaries(accounts, report_date):
    return {}


def reporting_team_overview(social_summaries):
    rows = list((social_summaries or {}).values())
    platform_counts = {}
    for row in rows:
        for platform, count in (row.get("posts_live_by_platform") or {}).items():
            platform_counts[platform] = platform_counts.get(platform, 0) + int(count or 0)
    scored = [float(row.get("score") or 0) for row in rows if row.get("plan_status") != "not_started"]
    return {
        "staff_count": len(rows),
        "completed_days": sum(row.get("plan_status") == "completed" for row in rows),
        "posts_live": sum(int(row.get("posts_live") or 0) for row in rows),
        "posts_live_by_platform": platform_counts,
        "average_score": round(sum(scored) / len(scored), 1) if scored else 0.0,
        "outstanding_mips": sum(int(row.get("mips_outstanding") or 0) for row in rows),
        "blockers": sum(bool(str(row.get("blockers") or "").strip()) for row in rows),
    }
