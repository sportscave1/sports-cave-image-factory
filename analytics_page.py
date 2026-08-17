"""Read-only Analytics workspace backed by canonical saved GA4 reports."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import json

import streamlit as st

import analytics_contracts
import analytics_navigation as navigation
import analytics_reporting
import google_seo
import navigation_runtime
import seo_live_analytics


STATE_PREFIX = "analytics-v2-"
TREND_CHOICES = {
    "Sessions": ("trend", "sessions"),
    "Active users": ("trend_active_users", "activeUsers"),
    "Views": ("trend_views", "screenPageViews"),
    "Key events": ("trend_key_events", "keyEvents"),
}


def _decimal(value):
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _rows(report):
    value = (report or {}).get("response_rows") or (report or {}).get("rows") or []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return []
    return list(value or [])


def _metadata(report):
    value = (report or {}).get("response_metadata") or (report or {}).get("metadata") or {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return {}
    return dict(value or {})


def _metric(report, name):
    rows = _rows(report)
    return None if not rows else _decimal((rows[0].get("metrics") or {}).get(name))


def _format_number(value, *, percent=False, currency=""):
    if value is None:
        return "Unavailable"
    number = float(value)
    if percent:
        return f"{number * 100:.1f}%"
    if currency:
        return f"{currency} {number:,.0f}"
    return f"{number:,.0f}"


def _quality(report):
    metadata = _metadata(report)
    embedded = dict(metadata.get("quality") or {})
    return str((report or {}).get("quality_status") or embedded.get("status") or "Unavailable")


def _property_id(connection):
    value = str((connection or {}).get("ga4_property_id") or "").strip()
    if value and not value.startswith("properties/"):
        value = f"properties/{value}"
    return value


def _exact_report(store, property_id, contract_key, period):
    if not property_id:
        return {}
    return store.report_for_period(
        property_id,
        contract_key,
        period["start_date"],
        period["end_date"],
    )


def _inject_styles():
    st.markdown(
        """
        <style>
        .sc-analytics-title { margin: 0; font-size: 2rem; line-height: 1.1; }
        .sc-analytics-subtitle { color: #68645f; margin: .3rem 0 .8rem; }
        .sc-data-note { color: #6d6963; font-size: .82rem; margin-top: -.3rem; }
        div[data-testid="stMetric"] { border: 1px solid #e3ded4; border-top: 2px solid #d5a542;
          border-radius: 7px; padding: .7rem .8rem; background: #fff; min-height: 106px; }
        div[data-testid="stMetric"] label { font-size: .82rem; }
        div[data-testid="stMetric"] [data-testid="stMetricValue"] { font-size: 1.55rem; }
        @media (max-width: 700px) {
          .sc-analytics-title { font-size: 1.65rem; }
          div[data-testid="stMetric"] { min-height: 92px; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _header(title, subtitle):
    st.markdown(f'<h1 class="sc-analytics-title">{title}</h1>', unsafe_allow_html=True)
    st.markdown(f'<p class="sc-analytics-subtitle">{subtitle}</p>', unsafe_allow_html=True)


def _filters(connection):
    timezone_name = str((connection or {}).get("ga4_property_timezone") or "Australia/Sydney")
    columns = st.columns([1.1, 1, 1, 1])
    preset = columns[0].selectbox(
        "Date range",
        analytics_contracts.DATE_PRESETS,
        index=2,
        key=f"{STATE_PREFIX}preset",
    )
    comparison = columns[1].selectbox(
        "Compare",
        analytics_contracts.COMPARISON_OPTIONS,
        index=1,
        key=f"{STATE_PREFIX}comparison",
    )
    custom_start = custom_end = None
    if preset == "Custom":
        custom_start = columns[2].date_input(
            "Start date", value=date.today(), key=f"{STATE_PREFIX}start"
        )
        custom_end = columns[3].date_input(
            "End date", value=date.today(), key=f"{STATE_PREFIX}end"
        )
    else:
        columns[2].text_input("Property timezone", timezone_name, disabled=True)
        columns[3].text_input(
            "Property",
            str((connection or {}).get("ga4_property_name") or _property_id(connection) or "Not connected"),
            disabled=True,
        )
    return analytics_contracts.resolve_date_range(
        preset,
        timezone_name=timezone_name,
        comparison=comparison,
        custom_start=custom_start,
        custom_end=custom_end,
    )


def _comparison_report(store, property_id, contract_key, period):
    if not period.get("previous_start_date"):
        return {}
    return store.report_for_period(
        property_id,
        contract_key,
        period["previous_start_date"],
        period["previous_end_date"],
    )


def _delta(current, previous, *, invert=False):
    if current is None or previous is None or not previous:
        return None
    value = (float(current) - float(previous)) / abs(float(previous)) * 100
    if invert:
        value *= -1
    return f"{value:+.1f}%"


def _metric_cards(report, previous, currency):
    definitions = (
        ("Active users", "activeUsers", False, ""),
        ("Sessions", "sessions", False, ""),
        ("Views", "screenPageViews", False, ""),
        ("Engagement rate", "engagementRate", True, ""),
        ("Key events", "keyEvents", False, ""),
        ("GA4 purchase revenue", "purchaseRevenue", False, currency),
    )
    columns = st.columns(3)
    for index, (label, metric, percent, money) in enumerate(definitions):
        current_value = _metric(report, metric)
        previous_value = _metric(previous, metric)
        columns[index % 3].metric(
            label,
            _format_number(current_value, percent=percent, currency=money),
            _delta(current_value, previous_value),
        )


def _observed_insights(report, previous):
    """Return compact deterministic observations; never predict or explain causality."""
    observations = []
    for label, metric, invert in (
        ("Active users", "activeUsers", False),
        ("Sessions", "sessions", False),
        ("Views", "screenPageViews", False),
        ("Engagement rate", "engagementRate", False),
        ("GA4 purchase revenue", "purchaseRevenue", False),
    ):
        current = _metric(report, metric)
        prior = _metric(previous, metric)
        if current is None or prior is None or not prior:
            continue
        change = (float(current) - float(prior)) / abs(float(prior)) * 100
        if abs(change) < 5:
            continue
        direction = "increased" if change > 0 else "decreased"
        observations.append((abs(change), f"{label} {direction} {abs(change):.1f}% versus the selected comparison period."))
    return [text for _magnitude, text in sorted(observations, reverse=True)[:3]]


def _table(report, dimension_labels, metric_labels, *, height=300):
    rows = []
    for item in _rows(report):
        dimensions = item.get("dimensions") or {}
        metrics = item.get("metrics") or {}
        rows.append(
            {
                **{label: dimensions.get(key, "") for key, label in dimension_labels},
                **{label: metrics.get(key, "") for key, label in metric_labels},
            }
        )
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True, height=height)
    else:
        st.caption("No saved rows are available for this exact date range.")


def _report_notice(report, store, property_id, contract_key, period):
    if report:
        quality = _quality(report)
        fetched = str(report.get("fetched_at") or "")
        preliminary = " Preliminary recent data." if period.get("preliminary") else ""
        st.caption(
            f"{quality} | Exact inclusive dates: {period['start_date']} to {period['end_date']} | "
            f"Saved: {fetched or 'unknown'}.{preliminary}"
        )
        return
    latest = store.latest_report(property_id, contract_key) if property_id else {}
    stale = str(latest.get("fetched_at") or "")
    st.info(
        "This exact report is not saved yet. Analytics refreshes run in the background; "
        + (f"the last-good snapshot was saved {stale}." if stale else "no last-good snapshot is available.")
    )


def _shopify_operational_panel(period, reader=None):
    st.subheader("Shopify operational data")
    reader = reader or seo_live_analytics.PostgresSEOLiveAnalyticsReader()
    try:
        totals = reader.shopify_operational_totals(period["start_date"], period["end_date"])
    except Exception:
        totals = {}
    by_currency = list(totals.get("store_by_currency") or [])
    columns = st.columns(max(2, min(4, len(by_currency) + 1)))
    columns[0].metric("Store orders", _format_number(totals.get("store_orders")))
    for index, row in enumerate(by_currency, start=1):
        currency = str(row.get("currency") or "Currency unavailable")
        columns[index % len(columns)].metric(
            f"Store revenue ({currency})",
            _format_number(row.get("revenue"), currency=currency if row.get("currency") else ""),
        )
    if not by_currency:
        columns[1].metric("Store revenue", "Unavailable")
    st.caption(
        "Source: paid, non-cancelled Shopify/Supabase order ledger. Revenue stays grouped by currency "
        "and is never blended with GA4 purchase or total revenue."
    )


def _overview(store, property_id, period, connection, *, operational_reader=None):
    report = _exact_report(store, property_id, "overview_totals", period)
    previous = _comparison_report(store, property_id, "overview_totals", period)
    currency = str(report.get("property_currency") or _metadata(report).get("currencyCode") or "")
    _metric_cards(report, previous, currency)
    _report_notice(report, store, property_id, "overview_totals", period)

    trend_label = st.segmented_control(
        "Performance metric",
        tuple(TREND_CHOICES),
        default="Sessions",
        key=f"{STATE_PREFIX}trend-metric",
    ) or "Sessions"
    trend_key, trend_metric = TREND_CHOICES[trend_label]
    trend = _exact_report(store, property_id, trend_key, period)
    trend_rows = [
        {
            "Date": (row.get("dimensions") or {}).get("date", ""),
            trend_label: float(_decimal((row.get("metrics") or {}).get(trend_metric))),
        }
        for row in _rows(trend)
    ]
    if trend_rows:
        st.subheader("Performance")
        st.line_chart(trend_rows, x="Date", y=trend_label, use_container_width=True)

    insights = _observed_insights(report, previous)
    if insights:
        st.subheader("Observed changes")
        for insight in insights:
            st.caption(insight)

    tabs = st.tabs(("Top pages", "Channels", "Countries", "Devices"))
    with tabs[0]:
        _table(
            _exact_report(store, property_id, "pages_screens", period),
            (("pageTitle", "Page title"), ("pagePathPlusQueryString", "Path")),
            (("screenPageViews", "Views"), ("activeUsers", "Active users"), ("keyEvents", "Key events")),
        )
    with tabs[1]:
        _table(
            _exact_report(store, property_id, "traffic_acquisition", period),
            (("sessionDefaultChannelGroup", "Channel"),),
            (("sessions", "Sessions"), ("engagementRate", "Engagement rate"), ("keyEvents", "Key events")),
        )
    with tabs[2]:
        _table(
            _exact_report(store, property_id, "countries", period),
            (("country", "Country"), ("countryId", "Code")),
            (("activeUsers", "Active users"), ("sessions", "Sessions")),
        )
    with tabs[3]:
        _table(
            _exact_report(store, property_id, "devices", period),
            (("deviceCategory", "Device"),),
            (("activeUsers", "Active users"), ("sessions", "Sessions")),
        )

    _shopify_operational_panel(period, reader=operational_reader)
    _render_connection_settings(connection)


def _traffic(store, property_id, period):
    report = _exact_report(store, property_id, "traffic_acquisition", period)
    _report_notice(report, store, property_id, "traffic_acquisition", period)
    _table(
        report,
        (("sessionDefaultChannelGroup", "Session default channel group"),),
        (
            ("sessions", "Sessions"), ("engagedSessions", "Engaged sessions"),
            ("engagementRate", "Engagement rate"), ("eventCount", "Events"),
            ("keyEvents", "Key events"), ("sessionKeyEventRate", "Session key-event rate"),
            ("totalRevenue", "GA4 total revenue"),
        ),
        height=460,
    )


def _pages(store, property_id, period):
    mode = st.segmented_control(
        "Report",
        ("Pages and screens", "Landing pages", "Events"),
        default="Pages and screens",
        key=f"{STATE_PREFIX}pages-mode",
    )
    key = {
        "Landing pages": "landing_pages",
        "Events": "events",
    }.get(mode, "pages_screens")
    report = _exact_report(store, property_id, key, period)
    _report_notice(report, store, property_id, key, period)
    if key == "landing_pages":
        _table(
            report,
            (("landingPagePlusQueryString", "Landing page"),),
            (("sessions", "Sessions"), ("activeUsers", "Active users"), ("newUsers", "New users"),
             ("engagementRate", "Engagement rate"), ("keyEvents", "Key events"), ("totalRevenue", "GA4 revenue")),
            height=480,
        )
    elif key == "pages_screens":
        _table(
            report,
            (("pageTitle", "Page title"), ("pagePathPlusQueryString", "Path")),
            (("screenPageViews", "Views"), ("activeUsers", "Active users"),
             ("eventCount", "Events"), ("keyEvents", "Key events"), ("totalRevenue", "GA4 revenue")),
            height=480,
        )
    else:
        _table(
            report,
            (("eventName", "Event"),),
            (("eventCount", "Event count"), ("totalUsers", "Total users"),
             ("keyEvents", "Key events"), ("eventValue", "Event value")),
            height=480,
        )


def _ecommerce(store, property_id, period):
    totals = _exact_report(store, property_id, "overview_totals", period)
    currency = str(totals.get("property_currency") or _metadata(totals).get("currencyCode") or "")
    columns = st.columns(3)
    columns[0].metric("Ecommerce purchases", _format_number(_metric(totals, "ecommercePurchases")))
    columns[1].metric("GA4 purchase revenue", _format_number(_metric(totals, "purchaseRevenue"), currency=currency))
    columns[2].metric("GA4 total revenue", _format_number(_metric(totals, "totalRevenue"), currency=currency))
    report = _exact_report(store, property_id, "ecommerce_products", period)
    _report_notice(report, store, property_id, "ecommerce_products", period)
    _table(
        report,
        (("itemName", "Item"), ("itemId", "Item ID")),
        (("itemsViewed", "Viewed"), ("itemsAddedToCart", "Added to cart"),
         ("itemsPurchased", "Purchased"), ("itemRevenue", "Item revenue")),
        height=460,
    )


def _realtime(store, property_id):
    report = store.latest_report(property_id, "realtime") if property_id else {}
    st.caption("Saved GA4 realtime snapshot for the last 30 minutes. This page does not poll Google.")
    _report_notice(
        report,
        store,
        property_id,
        "realtime",
        {"start_date": "realtime", "end_date": "realtime", "preliminary": True},
    )
    _table(
        report,
        (("country", "Country"), ("deviceCategory", "Device")),
        (("activeUsers", "Active users"), ("eventCount", "Events")),
        height=360,
    )


def _render_connection_settings(connection):
    with st.expander("Data Connections & Sync Settings", expanded=False):
        columns = st.columns(3)
        status = str((connection or {}).get("connection_status") or "Not connected").replace("_", " ").title()
        columns[0].metric("Google connection", status)
        columns[1].metric("GA4 property", str((connection or {}).get("ga4_property_name") or "Not selected"))
        columns[2].metric("Data through", str((connection or {}).get("ga4_data_through_date") or "Unavailable"))
        st.caption("Connection changes and manual refresh controls are available to administrators in SEO Health & Fixes.")


def _queue_custom_reports(store, property_id, route, period, connection, user):
    if period.get("preset") != "Custom":
        return
    contracts = {
        navigation.ANALYTICS_OVERVIEW_ROUTE: (
            "overview_totals", "trend", "trend_active_users", "trend_views", "trend_key_events",
            "pages_screens", "traffic_acquisition", "countries", "devices",
        ),
        navigation.ANALYTICS_TRAFFIC_ROUTE: ("traffic_acquisition",),
        navigation.ANALYTICS_PAGES_ROUTE: ("pages_screens", "landing_pages", "events"),
        navigation.ANALYTICS_ECOMMERCE_ROUTE: ("overview_totals", "ecommerce_products"),
    }.get(route, ())
    for contract_key in contracts:
        if not _exact_report(store, property_id, contract_key, period):
            store.queue_report(
                property_id,
                contract_key,
                period["start_date"],
                period["end_date"],
                currency=str((connection or {}).get("ga4_property_currency") or ""),
                requested_by=str((user or {}).get("id") or ""),
            )


def render_page(
    user,
    route,
    *,
    navigate=None,
    store=None,
    connection_store=None,
    operational_reader=None,
):
    if route not in navigation.ANALYTICS_ROUTES:
        raise ValueError(f"Unknown Analytics route: {route}")
    _inject_styles()
    title = navigation.ANALYTICS_NAV_LABELS[route]
    subtitles = {
        navigation.ANALYTICS_OVERVIEW_ROUTE: "GA4 performance from exact saved report contracts.",
        navigation.ANALYTICS_TRAFFIC_ROUTE: "Session acquisition by GA4 default channel group.",
        navigation.ANALYTICS_PAGES_ROUTE: "Pages, screens and landing-page engagement.",
        navigation.ANALYTICS_ECOMMERCE_ROUTE: "GA4 ecommerce attribution, kept distinct from Shopify operations.",
        navigation.ANALYTICS_REALTIME_ROUTE: "The latest saved realtime activity snapshot.",
    }
    _header(title, subtitles[route])
    connection_store = connection_store or google_seo.default_store()
    store = store or analytics_reporting.PostgresAnalyticsStore()
    try:
        connection = connection_store.get_connection()
    except Exception:
        connection = {}
    property_id = _property_id(connection)
    if not property_id:
        st.info("Connect and select a GA4 property to populate Analytics.")
        _render_connection_settings(connection)
        return
    try:
        if route == navigation.ANALYTICS_REALTIME_ROUTE:
            _realtime(store, property_id)
            return
        period = _filters(connection)
        _queue_custom_reports(store, property_id, route, period, connection, user)
        navigation_runtime.dispatch_selected(
            route,
            {
                navigation.ANALYTICS_OVERVIEW_ROUTE: lambda: _overview(
                    store,
                    property_id,
                    period,
                    connection,
                    operational_reader=operational_reader,
                ),
                navigation.ANALYTICS_TRAFFIC_ROUTE: lambda: _traffic(store, property_id, period),
                navigation.ANALYTICS_PAGES_ROUTE: lambda: _pages(store, property_id, period),
                navigation.ANALYTICS_ECOMMERCE_ROUTE: lambda: _ecommerce(store, property_id, period),
            },
        )
    except (analytics_reporting.AnalyticsReportingError, ValueError) as error:
        st.error(str(getattr(error, "public_message", error)))
        st.caption("The last complete saved snapshot was preserved; no partial response replaced it.")
