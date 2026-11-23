"""Inventory/retire old planner data in an explicitly selected local test DB.

Never loads .env or uses application database discovery. Defaults to read-only.
The production release runbook must separately review stored file destinations.
"""
import argparse
import json
import os
from urllib.parse import urlsplit

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

TABLES = (
    "social_daily_priorities", "social_post_platforms", "social_weekly_platform_metrics",
    "social_action_requests", "social_content_jobs", "social_weekly_priorities",
    "social_daily_plans", "social_posts", "social_weekly_reports",
)


def validate_local_dsn(dsn):
    parsed = urlsplit(dsn)
    if parsed.scheme not in ("postgres", "postgresql") or parsed.hostname not in ("127.0.0.1", "::1", "localhost"):
        raise ValueError("Cleanup only accepts an explicit loopback test database URL.")
    # libpq query parameters can override hostname/database; reject overrides.
    if parsed.query or parsed.fragment:
        raise ValueError("Test database URLs may not contain query parameters or fragments.")
    if not parsed.path or parsed.path == "/":
        raise ValueError("Choose an explicit disposable test database.")
    return dsn


def inventory(cur):
    result = {"tables": {}, "generated_destinations": [], "reel_prompt_count": 0}
    for table in TABLES:
        cur.execute("SELECT to_regclass(%s) AS name", ("public." + table,))
        if cur.fetchone()["name"]:
            cur.execute(sql.SQL("SELECT count(*) AS count FROM public.{}").format(sql.Identifier(table)))
            result["tables"][table] = cur.fetchone()["count"]
    if "social_content_jobs" in result["tables"]:
        cur.execute("SELECT DISTINCT destination_path FROM public.social_content_jobs WHERE destination_path<>''")
        result["generated_destinations"] = [row["destination_path"] for row in cur.fetchall()]
    cur.execute("SELECT to_regclass('public.prompt_templates') AS name")
    if cur.fetchone()["name"]:
        cur.execute("SELECT count(*) AS count FROM public.prompt_templates WHERE module='social_reels'")
        result["reel_prompt_count"] = cur.fetchone()["count"]
    return result


def retire(cur):
    # No CASCADE: an unexpected shared dependency stops the transaction.
    cur.execute("SELECT to_regclass('public.prompt_templates') AS name")
    if cur.fetchone()["name"]:
        cur.execute("SELECT to_regclass('public.prompt_template_versions') AS name")
        if cur.fetchone()["name"]:
            cur.execute("""DELETE FROM public.prompt_template_versions WHERE prompt_key IN
                (SELECT prompt_key FROM public.prompt_templates WHERE module='social_reels')""")
        cur.execute("DELETE FROM public.prompt_templates WHERE module='social_reels'")
    for table in TABLES:
        cur.execute(sql.SQL("DROP TABLE IF EXISTS public.{}").format(sql.Identifier(table)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn-env", default="SOCIAL_CLEANUP_TEST_DSN")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    dsn = validate_local_dsn(os.environ.get(args.dsn_env, ""))
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='5000ms'")
            if not args.apply:
                cur.execute("SET TRANSACTION READ ONLY")
            before = inventory(cur)
            print(json.dumps(before, indent=2))
            if args.apply:
                retire(cur)
                print(json.dumps({"after": inventory(cur)}, indent=2))
        if args.apply:
            conn.commit()
        else:
            conn.rollback()


if __name__ == "__main__":
    main()
