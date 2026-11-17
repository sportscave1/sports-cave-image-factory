"""Aggregate Orders and saved Meta reporting for the private ChatGPT connector."""

from datetime import date, datetime, time, timedelta, timezone
import os
import re
from zoneinfo import ZoneInfo

from chatgpt_crm_api import _read_connection

SYDNEY = ZoneInfo("Australia/Sydney")

ORDERS_SQL = """
WITH orders AS (
    SELECT cancelled_at IS NOT NULL AS cancelled,
           upper(coalesce(financial_status, '')) AS status,
           btrim(coalesce(total_price, '')) AS amount,
           upper(btrim(coalesce(currency, ''))) AS currency
    FROM shopify_orders
    WHERE coalesce(processed_at, created_at) >= %s
      AND coalesce(processed_at, created_at) < %s
), totals AS (
    SELECT currency, count(*) AS orders, sum(amount::numeric)::text AS order_total
    FROM orders WHERE NOT cancelled AND status IN ('PAID', 'PARTIALLY_REFUNDED')
      AND currency ~ '^[A-Z]{3}$' AND amount ~ '^[0-9]{1,18}([.][0-9]{1,8})?$'
    GROUP BY currency
)
SELECT count(*) AS orders,
       count(*) FILTER (WHERE cancelled) AS cancelled_orders,
       count(*) FILTER (WHERE NOT cancelled AND status = 'PAID') AS paid_orders,
       count(*) FILTER (WHERE NOT cancelled AND status = 'PARTIALLY_REFUNDED') AS partially_refunded_orders,
       count(*) FILTER (WHERE NOT cancelled AND status = 'REFUNDED') AS refunded_orders,
       count(*) FILTER (WHERE NOT cancelled AND status IN ('PAID', 'PARTIALLY_REFUNDED')
         AND (currency !~ '^[A-Z]{3}$' OR amount !~ '^[0-9]{1,18}([.][0-9]{1,8})?$'))
           AS paid_orders_missing_valid_amount_or_currency,
       coalesce((SELECT jsonb_agg(to_jsonb(totals) ORDER BY currency) FROM totals), '[]'::jsonb)
           AS known_paid_order_totals_by_currency
FROM orders
"""

META_SQL = """
SELECT count(*) AS saved_ad_rows,
       count(spend) AS rows_with_spend, sum(spend)::text AS known_spend,
       count(purchases) AS rows_with_purchases, sum(purchases)::text AS known_purchases,
       count(purchase_value) AS rows_with_purchase_value,
       sum(purchase_value)::text AS known_attributed_purchase_value,
       coalesce(array_agg(DISTINCT currency ORDER BY currency) FILTER (WHERE currency IS NOT NULL), '{}')
           AS currencies,
       coalesce(array_agg(DISTINCT report_time ORDER BY report_time) FILTER (WHERE report_time IS NOT NULL), '{}')
           AS reporting_times,
       count(report_time) AS rows_with_reporting_time
FROM (
    SELECT d.spend, d.purchases, d.purchase_value,
           coalesce(nullif(d.raw->'_reporting'->>'currency', ''), nullif(a.currency, '')) AS currency,
           nullif(d.raw->'_reporting'->>'action_report_time', '') AS report_time
    FROM meta_ad_insights_daily d
    LEFT JOIN meta_ad_accounts a ON a.account_id = d.account_id
    WHERE d.account_id = %s AND d.date = %s
      AND coalesce(d.country, '') = '' AND coalesce(d.placement, '') = ''
) AS rows
"""


def reporting_day(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("Supply a Sydney date as YYYY-MM-DD.")
    try:
        day = date.fromisoformat(value)
    except ValueError:
        raise ValueError("Supply a valid Sydney date.") from None
    if day < date(2000, 1, 1) or day > datetime.now(SYDNEY).date():
        raise ValueError("Supply a Sydney date from 2000 through today.")
    return day


def _read(query, params):
    with _read_connection() as connection:
        return dict(connection.execute(query, params).fetchone())


def _context(day):
    return {
        "date": day.isoformat(),
        "timezone": "Australia/Sydney",
        "day_complete": day < datetime.now(SYDNEY).date(),
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
    }


def orders_daily(day):
    start = datetime.combine(day, time.min, SYDNEY)
    end = datetime.combine(day + timedelta(days=1), time.min, SYDNEY)
    return {**_context(day), **_read(ORDERS_SQL, (start, end)),
            "basis": "Stored Shopify orders by processed time, falling back to creation time. "
                     "Known totals include paid and partially refunded orders and do not deduct refunds."}


def meta_daily(day):
    account = os.getenv("META_AD_ACCOUNT_ID", "").strip().removeprefix("act_")
    if not re.fullmatch(r"[0-9]{1,30}", account):
        raise RuntimeError("Meta reporting account unavailable.")
    data = _read(META_SQL, (account, day))
    return {**_context(day), **data,
            "basis": "Saved ad-level daily Meta reporting. Missing source values are unknown, "
                     "and attributed purchases are Meta's measurements."}
