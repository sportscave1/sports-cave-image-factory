"""Reproducible local SEO critical-path benchmark with 146,453 saved rows.

This measures database-only saved-data reads and Python transformations. It does
not claim Render network, browser, or production Postgres performance.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
import json
import sqlite3
import statistics
import time


ROW_COUNT = 146_453
QUERY_COUNT = 6_200
PAGE_COUNT = 740
END_DATE = date(2026, 8, 17)
START_DATE = END_DATE - timedelta(days=27)
PREVIOUS_START = START_DATE - timedelta(days=28)
PREVIOUS_END = START_DATE - timedelta(days=1)


def build_database():
    connection = sqlite3.connect(":memory:")
    connection.execute(
        """CREATE TABLE reporting_query_daily(
            day TEXT, query TEXT, page TEXT, market TEXT, device TEXT,
            clicks REAL, impressions REAL, position_weight REAL
        )"""
    )
    rows = []
    base = END_DATE - timedelta(days=111)
    markets = ("AU", "US", "UK", "CA", "NZ")
    devices = ("mobile", "desktop", "tablet")
    for index in range(ROW_COUNT):
        day = base + timedelta(days=index % 112)
        query_id = (index * 37) % QUERY_COUNT
        page_id = (index * 19) % PAGE_COUNT
        impressions = float(5 + (index * 13) % 900)
        clicks = float((index * 7) % max(1, int(impressions / 8) + 1))
        position = float(1 + (index * 11) % 80)
        rows.append(
            (
                day.isoformat(),
                f"sports query {query_id:05d}",
                f"/collections/page-{page_id:04d}",
                markets[index % len(markets)],
                devices[index % len(devices)],
                clicks,
                impressions,
                impressions * position,
            )
        )
    connection.executemany(
        "INSERT INTO reporting_query_daily VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    connection.execute(
        "CREATE INDEX reporting_query_range ON reporting_query_daily(day, market, device, query)"
    )
    connection.execute(
        "CREATE TABLE reporting_snapshot(id TEXT, through_date TEXT, revision INTEGER)"
    )
    connection.execute(
        "INSERT INTO reporting_snapshot VALUES ('snapshot-1', ?, 42)",
        (END_DATE.isoformat(),),
    )
    connection.commit()
    return connection


def fetch(connection, sql, params=()):
    return connection.execute(sql, params).fetchall()


def old_snapshot(connection):
    query_count = 0
    # Representative inventory/health checks from the prior reader.
    for expression in (
        "COUNT(*)", "MIN(day)", "MAX(day)", "COUNT(DISTINCT query)",
        "COUNT(DISTINCT page)", "COUNT(DISTINCT market)", "COUNT(DISTINCT device)",
        "COUNT(*)", "MAX(day)", "COUNT(DISTINCT query)",
    ):
        fetch(connection, f"SELECT {expression} FROM reporting_query_daily")
        query_count += 1
    current = (START_DATE.isoformat(), END_DATE.isoformat())
    previous = (PREVIOUS_START.isoformat(), PREVIOUS_END.isoformat())
    queries = fetch(
        connection,
        """WITH current AS (
               SELECT query, SUM(clicks) clicks, SUM(impressions) impressions,
                      SUM(position_weight) weight
               FROM reporting_query_daily WHERE day BETWEEN ? AND ? GROUP BY query
           ), previous AS (
               SELECT query, SUM(clicks) clicks, SUM(impressions) impressions,
                      SUM(position_weight) weight
               FROM reporting_query_daily WHERE day BETWEEN ? AND ? GROUP BY query
           )
           SELECT current.query, current.clicks, current.impressions, current.weight,
                  COALESCE(previous.clicks, 0), COALESCE(previous.impressions, 0),
                  COALESCE(previous.weight, 0)
           FROM current LEFT JOIN previous USING(query)
           ORDER BY current.clicks DESC, current.impressions DESC LIMIT 5000""",
        (*current, *previous),
    )
    query_count += 1
    pages = fetch(
        connection,
        """SELECT page, SUM(clicks), SUM(impressions), SUM(position_weight)
           FROM reporting_query_daily WHERE day BETWEEN ? AND ?
           GROUP BY page ORDER BY SUM(clicks) DESC LIMIT 1000""",
        current,
    )
    query_count += 1
    fetch(
        connection,
        """SELECT market, device, SUM(clicks), SUM(impressions)
           FROM reporting_query_daily WHERE day BETWEEN ? AND ? GROUP BY market, device""",
        current,
    )
    query_count += 1
    fetch(
        connection,
        """SELECT day, SUM(clicks), SUM(impressions), SUM(position_weight)
           FROM reporting_query_daily WHERE day BETWEEN ? AND ? GROUP BY day""",
        current,
    )
    query_count += 1
    transformed = []
    for query, clicks, impressions, weight, old_clicks, old_impressions, old_weight in queries:
        position = weight / impressions if impressions else 0
        previous_position = old_weight / old_impressions if old_impressions else None
        transformed.append(
            {
                "query": query,
                "clicks": clicks,
                "impressions": impressions,
                "position": position,
                "change": clicks - old_clicks,
                "rank_change": previous_position - position if previous_position else 0,
            }
        )
    # The old Overview constructed every hidden view from the 5,000-row payload.
    sorted(transformed, key=lambda row: row["clicks"], reverse=True)
    sorted((row for row in transformed if 4 <= row["position"] <= 20), key=lambda row: row["impressions"], reverse=True)
    sorted(transformed, key=lambda row: row["rank_change"], reverse=True)
    sorted(transformed, key=lambda row: row["rank_change"])
    distribution = defaultdict(float)
    for row in transformed:
        distribution[int(row["position"] // 10) * 10] += row["impressions"]
    return {"queries": query_count, "returned_rows": len(queries) + len(pages), "rows": transformed}


def compact_base(connection):
    query_count = 0
    fetch(connection, "SELECT id, through_date, revision FROM reporting_snapshot LIMIT 1")
    query_count += 1
    current = (START_DATE.isoformat(), END_DATE.isoformat())
    fetch(
        connection,
        """SELECT SUM(clicks), SUM(impressions), SUM(position_weight)
           FROM reporting_query_daily WHERE day BETWEEN ? AND ?""",
        current,
    )
    query_count += 1
    fetch(
        connection,
        """SELECT day, SUM(clicks), SUM(impressions), SUM(position_weight)
           FROM reporting_query_daily WHERE day BETWEEN ? AND ? GROUP BY day""",
        current,
    )
    query_count += 1
    fetch(
        connection,
        """WITH q AS (
               SELECT query, SUM(impressions) impressions,
                      SUM(position_weight)/NULLIF(SUM(impressions), 0) position
               FROM reporting_query_daily WHERE day BETWEEN ? AND ? GROUP BY query
           ) SELECT SUM(impressions),
                    SUM(CASE WHEN position BETWEEN 1 AND 3 THEN impressions ELSE 0 END),
                    SUM(CASE WHEN position BETWEEN 4 AND 10 THEN impressions ELSE 0 END)
             FROM q""",
        current,
    )
    query_count += 1
    return query_count


def compact_queries(connection, view="top"):
    current = (START_DATE.isoformat(), END_DATE.isoformat())
    previous = (PREVIOUS_START.isoformat(), PREVIOUS_END.isoformat())
    direction = "DESC" if view != "declining" else "ASC"
    rows = fetch(
        connection,
        f"""WITH current AS (
                SELECT query, SUM(clicks) clicks, SUM(impressions) impressions,
                       SUM(position_weight) weight
                FROM reporting_query_daily WHERE day BETWEEN ? AND ? GROUP BY query
            ), previous AS (
                SELECT query, SUM(impressions) impressions, SUM(position_weight) weight
                FROM reporting_query_daily WHERE day BETWEEN ? AND ? GROUP BY query
            ), page AS (
                SELECT current.*,
                       CASE WHEN current.impressions>0 THEN current.weight/current.impressions ELSE 0 END position,
                       CASE WHEN previous.impressions>0
                            THEN previous.weight/previous.impressions-current.weight/current.impressions ELSE 0 END rank_change
                FROM current LEFT JOIN previous USING(query)
            ) SELECT * FROM page
              ORDER BY {'rank_change' if view in {'rising', 'declining'} else 'clicks'} {direction},
                       impressions DESC, query ASC LIMIT 25""",
        (*current, *previous),
    )
    return rows


def compact_pages(connection):
    return fetch(
        connection,
        """SELECT page, SUM(clicks), SUM(impressions), SUM(position_weight)
           FROM reporting_query_daily WHERE day BETWEEN ? AND ?
           GROUP BY page ORDER BY SUM(clicks) DESC, page ASC LIMIT 25""",
        (START_DATE.isoformat(), END_DATE.isoformat()),
    )


def compact_rank_distribution(connection):
    return fetch(
        connection,
        """WITH q AS (
               SELECT query, SUM(impressions) impressions,
                      SUM(position_weight)/NULLIF(SUM(impressions), 0) position
               FROM reporting_query_daily WHERE day BETWEEN ? AND ? GROUP BY query
           ) SELECT
               SUM(CASE WHEN position BETWEEN 1 AND 3 THEN impressions ELSE 0 END),
               SUM(CASE WHEN position BETWEEN 4 AND 10 THEN impressions ELSE 0 END),
               SUM(CASE WHEN position BETWEEN 11 AND 20 THEN impressions ELSE 0 END),
               SUM(CASE WHEN position BETWEEN 21 AND 50 THEN impressions ELSE 0 END),
               SUM(CASE WHEN position > 50 THEN impressions ELSE 0 END)
             FROM q""",
        (START_DATE.isoformat(), END_DATE.isoformat()),
    )


def measure(callable_, repeats=5):
    samples = []
    value = None
    for _index in range(repeats):
        started = time.perf_counter()
        value = callable_()
        samples.append((time.perf_counter() - started) * 1000)
    return round(statistics.median(samples), 2), value


def main():
    connection = build_database()
    old_ms, old = measure(lambda: old_snapshot(connection), repeats=3)
    base_ms, base_queries = measure(lambda: compact_base(connection), repeats=5)
    top_ms, top_rows = measure(lambda: compact_queries(connection, "top"), repeats=5)
    rising_ms, rising_rows = measure(lambda: compact_queries(connection, "rising"), repeats=5)
    declining_ms, declining_rows = measure(lambda: compact_queries(connection, "declining"), repeats=5)
    pages_ms, page_rows = measure(lambda: compact_pages(connection), repeats=5)
    rank_ms, _rank_rows = measure(lambda: compact_rank_distribution(connection), repeats=5)
    result = {
        "fixture_rows": ROW_COUNT,
        "scope": "local SQLite saved-data fixture; excludes Render/browser/network",
        "before": {
            "overview_ms": old_ms,
            "keywords_ms": old_ms,
            "opportunities_ms": old_ms,
            "landing_pages_ms": old_ms,
            "overview_tab_ms": old_ms,
            "queries": old["queries"],
            "returned_rows": old["returned_rows"],
        },
        "after": {
            "overview_top_queries_ms": round(base_ms + top_ms, 2),
            "keywords_ms": top_ms,
            "opportunities_ms": top_ms,
            "landing_pages_ms": pages_ms,
            "cached_top_queries_tab_ms": top_ms,
            "cached_rising_tab_ms": rising_ms,
            "cached_declining_tab_ms": declining_ms,
            "cached_rank_distribution_tab_ms": rank_ms,
            "overview_uncached_queries": base_queries + 1,
            "cached_tab_queries": 1,
            "returned_rows": len(top_rows),
            "page_rows": len(page_rows),
            "rising_rows": len(rising_rows),
            "declining_rows": len(declining_rows),
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
