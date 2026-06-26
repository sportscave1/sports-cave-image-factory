import csv
import io
import time
from decimal import Decimal

import streamlit as st

import meta_ads_client
import supabase_backend
import ui_styles


DATE_RANGE_OPTIONS = {
    "Last 7 days": 7,
    "Last 30 days": 30,
}


PERFORMANCE_COLUMNS = [
    "Action Label",
    "Campaign",
    "Ad Set",
    "Ad",
    "Spend",
    "Impressions",
    "CTR",
    "CPC",
    "CPM",
    "Purchases",
    "CPA",
    "Revenue",
    "ROAS",
    "Frequency",
    "Country",
    "Placement",
]


def _number(value, default=0.0):
    if isinstance(value, Decimal):
        return float(value)
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _money(value):
    return f"${_number(value):,.2f}"


def _ratio(value):
    return f"{_number(value):.2f}x"


def _pct(value):
    return f"{_number(value):.2f}%"


def _int_text(value):
    return f"{int(_number(value)):,.0f}"


def _section(title, caption=""):
    ui_styles.section_title(title)
    if caption:
        st.caption(caption)


def _action_label(row):
    spend = _number(row.get("spend"))
    impressions = _number(row.get("impressions"))
    clicks = _number(row.get("clicks"))
    purchases = _number(row.get("purchases"))
    roas = _number(row.get("roas"))
    ctr = _number(row.get("ctr"))
    frequency = _number(row.get("frequency"))
    add_to_cart = _number(row.get("add_to_cart"))
    initiate_checkout = _number(row.get("initiate_checkout"))

    # Simple V1 decision rules: transparent thresholds for triage, not automated media buying.
    if impressions < 500:
        return "Data too early"
    if spend < 20 or clicks < 20:
        return "Needs more spend"
    if purchases >= 2 and roas >= 2.5:
        return "Scale candidate"
    if ctr >= 1.5 and clicks >= 30 and purchases <= 0 and add_to_cart + initiate_checkout <= 0:
        return "Landing page/product issue"
    if spend >= 50 and purchases <= 0:
        return "Kill candidate"
    if spend >= 50 and purchases > 0 and roas < 0.8:
        return "Kill candidate"
    if frequency >= 2.5 and ctr < 1.0:
        return "Refresh creative"
    return "Watch"


def _aggregate_by_ad(rows):
    ads = {}
    for row in rows or []:
        ad_id = str(row.get("ad_id") or "")
        if not ad_id:
            continue
        item = ads.setdefault(
            ad_id,
            {
                "ad_id": ad_id,
                "creative_id": row.get("creative_id") or "",
                "status": row.get("ad_effective_status") or row.get("ad_status") or "",
                "campaign": row.get("campaign_name") or "",
                "adset": row.get("adset_name") or "",
                "ad": row.get("ad_name") or "",
                "spend": 0.0,
                "impressions": 0,
                "clicks": 0,
                "inline_link_clicks": 0,
                "purchases": 0.0,
                "revenue": 0.0,
                "add_to_cart": 0.0,
                "initiate_checkout": 0.0,
                "reach": 0,
                "frequency_total": 0.0,
                "frequency_rows": 0,
                "product_handle": row.get("product_handle") or "",
                "product_title": row.get("product_title") or "",
                "sport": row.get("sport") or "",
                "country_focus": row.get("country_focus") or "",
                "countries": set(),
                "placements": set(),
                "mockup_type": row.get("mockup_type") or "",
                "ad_angle": row.get("ad_angle") or "",
                "funnel_stage": row.get("funnel_stage") or "",
                "tag_notes": row.get("tag_notes") or "",
            },
        )
        item["spend"] += _number(row.get("spend"))
        item["impressions"] += int(_number(row.get("impressions")))
        item["clicks"] += int(_number(row.get("clicks")))
        item["inline_link_clicks"] += int(_number(row.get("inline_link_clicks")))
        item["purchases"] += _number(row.get("purchases"))
        item["revenue"] += _number(row.get("purchase_value"))
        item["add_to_cart"] += _number(row.get("add_to_cart"))
        item["initiate_checkout"] += _number(row.get("initiate_checkout"))
        item["reach"] += int(_number(row.get("reach")))
        item["frequency_total"] += _number(row.get("frequency"))
        item["frequency_rows"] += 1
        if row.get("country"):
            item["countries"].add(str(row.get("country")))
        if row.get("placement"):
            item["placements"].add(str(row.get("placement")))
    for item in ads.values():
        spend = item["spend"]
        impressions = item["impressions"]
        purchases = item["purchases"]
        revenue = item["revenue"]
        clicks = item["clicks"]
        item["ctr"] = (clicks / impressions * 100) if impressions else 0
        item["cpc"] = spend / clicks if clicks else 0
        item["cpm"] = (spend / impressions * 1000) if impressions else 0
        item["cpa"] = spend / purchases if purchases else 0
        item["roas"] = revenue / spend if spend else 0
        item["frequency"] = item["frequency_total"] / item["frequency_rows"] if item["frequency_rows"] else 0
        item["action_label"] = _action_label(item)
        item["country"] = ", ".join(sorted(item["countries"])) or "All"
        item["placement"] = ", ".join(sorted(item["placements"])) or "All"
    return sorted(ads.values(), key=lambda item: (item["roas"], item["revenue"], -item["spend"]), reverse=True)


def _summary(rows):
    spend = sum(_number(row.get("spend")) for row in rows or [])
    purchases = sum(_number(row.get("purchases")) for row in rows or [])
    revenue = sum(_number(row.get("purchase_value")) for row in rows or [])
    impressions = sum(_number(row.get("impressions")) for row in rows or [])
    clicks = sum(_number(row.get("clicks")) for row in rows or [])
    frequency_values = [_number(row.get("frequency")) for row in rows or [] if _number(row.get("frequency"))]
    return {
        "spend": spend,
        "purchases": purchases,
        "revenue": revenue,
        "roas": revenue / spend if spend else 0,
        "cpa": spend / purchases if purchases else 0,
        "ctr": clicks / impressions * 100 if impressions else 0,
        "cpc": spend / clicks if clicks else 0,
        "cpm": spend / impressions * 1000 if impressions else 0,
        "frequency": sum(frequency_values) / len(frequency_values) if frequency_values else 0,
    }


def _performance_table(ad_rows):
    table = []
    for row in ad_rows:
        table.append(
            {
                "Action Label": row.get("action_label"),
                "Campaign": row.get("campaign"),
                "Ad Set": row.get("adset"),
                "Ad": row.get("ad"),
                "Spend": _money(row.get("spend")),
                "Impressions": _int_text(row.get("impressions")),
                "CTR": _pct(row.get("ctr")),
                "CPC": _money(row.get("cpc")),
                "CPM": _money(row.get("cpm")),
                "Purchases": f"{_number(row.get('purchases')):,.0f}",
                "CPA": _money(row.get("cpa")),
                "Revenue": _money(row.get("revenue")),
                "ROAS": _ratio(row.get("roas")),
                "Frequency": f"{_number(row.get('frequency')):.2f}",
                "Country": row.get("country") or "All",
                "Placement": row.get("placement") or "All",
            }
        )
    return table


def _csv_bytes(rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=PERFORMANCE_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in PERFORMANCE_COLUMNS})
    return output.getvalue().encode("utf-8")


def _top_and_losing_rows(ad_rows):
    winners = [row for row in ad_rows if row.get("action_label") == "Scale candidate"][:8]
    if not winners:
        winners = sorted(ad_rows, key=lambda row: (row.get("roas", 0), row.get("revenue", 0)), reverse=True)[:8]
    losers = [
        row
        for row in sorted(ad_rows, key=lambda row: row.get("spend", 0), reverse=True)
        if row.get("action_label") in {"Kill candidate", "Refresh creative", "Landing page/product issue"}
    ][:8]
    return winners, losers


def _prompt_for(template, range_label, summary, ad_rows):
    winners, losers = _top_and_losing_rows(ad_rows)
    lines = [
        "Sports Cave Meta Ads Intelligence Pack",
        "",
        "Business context:",
        "Sports Cave sells premium sports wall art, framed prints, and limited edition products through Shopify.",
        "The goal is profitable revenue growth: identify ads to scale, ads to kill, creatives to refresh, and new ad concepts to launch.",
        "",
        f"Date range: {range_label}",
        "",
        "War Room summary:",
        f"- Spend: {_money(summary['spend'])}",
        f"- Purchases: {summary['purchases']:,.0f}",
        f"- Purchase value: {_money(summary['revenue'])}",
        f"- Meta ROAS: {_ratio(summary['roas'])}",
        f"- CPA: {_money(summary['cpa'])}",
        f"- CTR: {_pct(summary['ctr'])}",
        f"- CPC: {_money(summary['cpc'])}",
        f"- CPM: {_money(summary['cpm'])}",
        f"- Frequency: {summary['frequency']:.2f}",
        "",
        "Top ad data:",
    ]
    for row in winners:
        lines.append(
            f"- {row.get('ad')} | Campaign: {row.get('campaign')} | Spend {_money(row.get('spend'))} | "
            f"Revenue {_money(row.get('revenue'))} | Purchases {row.get('purchases'):.0f} | "
            f"ROAS {_ratio(row.get('roas'))} | Label: {row.get('action_label')} | "
            f"Tags: {row.get('product_title') or row.get('product_handle') or 'untagged'}, "
            f"{row.get('sport') or 'sport unknown'}, {row.get('ad_angle') or 'angle unknown'}"
        )
    lines.extend(["", "Losing or fatigued ad data:"])
    for row in losers:
        lines.append(
            f"- {row.get('ad')} | Campaign: {row.get('campaign')} | Spend {_money(row.get('spend'))} | "
            f"Revenue {_money(row.get('revenue'))} | Purchases {row.get('purchases'):.0f} | "
            f"CTR {_pct(row.get('ctr'))} | Frequency {row.get('frequency'):.2f} | Label: {row.get('action_label')} | "
            f"Notes: {row.get('tag_notes') or 'none'}"
        )
    instructions = {
        "Daily Ads Review": "Give me today's decision list: what to scale, watch, refresh, kill, and what to test next.",
        "Creative Pattern Finder": "Find repeatable creative patterns in the winners and explain what visual or angle patterns to reuse.",
        "New Ad Plan Generator": "Create a new Meta ad testing plan with hooks, angles, products, and creative briefs.",
        "Loser Diagnosis": "Diagnose why the losing ads are failing and recommend whether each needs a new hook, creative, offer, audience, or product match.",
        "Product Scaling Plan": "Recommend which products deserve more spend, which countries/sports to focus on, and the next scaling sequence.",
        "Weekly Creative Meeting Report": "Turn this into a concise meeting report with decisions, owners, creative requests, and next tests.",
    }
    lines.extend(
        [
            "",
            "Instructions for ChatGPT:",
            instructions.get(template, instructions["Daily Ads Review"]),
            "Be direct. Recommend what to kill, scale, refresh, and create next. Include the reasoning and a practical next-action list.",
        ]
    )
    return "\n".join(lines)


def _sync_meta_ads(range_label, days):
    started = time.perf_counter()
    sync_log_id = supabase_backend.start_ads_sync_log(
        source="meta_ads_api",
        sync_type="manual",
        date_range=range_label,
    )
    config = meta_ads_client.get_meta_config()
    warnings = []
    page_counts = {}

    def fetch_step(label, fetcher, default):
        try:
            return fetcher()
        except Exception as error:
            warnings.append(f"{label}: {meta_ads_client.sanitize_meta_error(error)}")
            return default

    account = fetch_step("account", lambda: meta_ads_client.fetch_meta_account(config=config), {})
    campaigns = fetch_step("campaigns", lambda: meta_ads_client.fetch_meta_campaigns(config=config), {"rows": [], "page_count": 0})
    adsets = fetch_step("adsets", lambda: meta_ads_client.fetch_meta_adsets(config=config), {"rows": [], "page_count": 0})
    ads = fetch_step("ads", lambda: meta_ads_client.fetch_meta_ads(config=config), {"rows": [], "page_count": 0})
    insights = fetch_step("insights", lambda: meta_ads_client.fetch_meta_ad_insights(days=days, config=config), {"rows": [], "page_count": 0})

    for label, payload in (("campaigns", campaigns), ("adsets", adsets), ("ads", ads), ("insights", insights)):
        page_counts[label] = payload.get("page_count", 0)

    rows_fetched = (
        (1 if account else 0)
        + len(campaigns.get("rows") or [])
        + len(adsets.get("rows") or [])
        + len(ads.get("rows") or [])
        + len(insights.get("rows") or [])
    )
    if rows_fetched <= 0:
        message = "; ".join(warnings) or "Meta sync returned no rows."
        supabase_backend.finish_ads_sync_log(
            sync_log_id,
            status="error",
            date_range=range_label,
            rows_fetched=0,
            rows_upserted=0,
            error_message=message,
            context={"warnings": warnings},
        )
        raise meta_ads_client.MetaAdsApiError(message)

    saved = supabase_backend.save_meta_ads_sync(
        account=account,
        campaigns=campaigns.get("rows"),
        adsets=adsets.get("rows"),
        ads=ads.get("rows"),
        insights=insights.get("rows"),
        date_range_label=range_label,
        account_id=config.get("ad_account_id"),
    )
    missing_performance_rows = saved.get("ads", 0) <= 0 or saved.get("insights", 0) <= 0
    status = "partial_success" if warnings or missing_performance_rows else "success"
    warning_parts = list(warnings)
    if missing_performance_rows:
        warning_parts.append(
            "Campaign structure synced, but ads or daily performance rows were not saved."
        )
    warning_text = "; ".join(warning_parts)
    supabase_backend.finish_ads_sync_log(
        sync_log_id,
        status=status,
        date_range=range_label,
        rows_fetched=rows_fetched,
        rows_upserted=saved.get("rows_upserted", 0),
        error_message=warning_text,
        context={"warnings": warning_parts, "meta_pages": page_counts},
    )
    if warnings:
        supabase_backend.record_ads_sync_error(warning_text, {"range": range_label, "partial": True})
    saved["meta_pages"] = page_counts
    saved["warnings"] = warning_parts
    saved["status"] = status
    saved["rows_fetched"] = rows_fetched
    saved["total_ms"] = int((time.perf_counter() - started) * 1000)
    return saved


def _decision_summary(ad_rows):
    labels = [
        "Scale candidate",
        "Watch",
        "Refresh creative",
        "Kill candidate",
        "Needs more spend",
        "Landing page/product issue",
        "Data too early",
    ]
    return [
        {
            "Action Label": label,
            "Ads": sum(1 for row in ad_rows if row.get("action_label") == label),
            "Spend": _money(sum(row.get("spend", 0) for row in ad_rows if row.get("action_label") == label)),
            "Revenue": _money(sum(row.get("revenue", 0) for row in ad_rows if row.get("action_label") == label)),
            "Purchases": f"{sum(row.get('purchases', 0) for row in ad_rows if row.get('action_label') == label):.0f}",
        }
        for label in labels
    ]


def _product_opportunity_rows(ad_rows):
    product_rows = {}
    for row in ad_rows:
        key = row.get("product_title") or row.get("product_handle") or "Untagged"
        product = product_rows.setdefault(key, {"Product": key, "Spend": 0, "Revenue": 0, "Purchases": 0, "Best ROAS": 0})
        product["Spend"] += row.get("spend", 0)
        product["Revenue"] += row.get("revenue", 0)
        product["Purchases"] += row.get("purchases", 0)
        product["Best ROAS"] = max(product["Best ROAS"], row.get("roas", 0))
    return [
        {
            "Product": row["Product"],
            "Spend": _money(row["Spend"]),
            "Revenue": _money(row["Revenue"]),
            "Purchases": f"{row['Purchases']:.0f}",
            "Best ROAS": _ratio(row["Best ROAS"]),
        }
        for row in sorted(product_rows.values(), key=lambda item: item["Revenue"], reverse=True)
    ]


def _creative_tag_rows(ad_rows):
    return [
        {
            "Ad ID": row.get("ad_id"),
            "Ad": row.get("ad"),
            "Product Handle": row.get("product_handle") or "",
            "Product": row.get("product_title") or "",
            "Sport": row.get("sport") or "",
            "Country": row.get("country_focus") or "",
            "Mockup": row.get("mockup_type") or "",
            "Angle": row.get("ad_angle") or "",
            "Funnel": row.get("funnel_stage") or "",
            "Notes": row.get("tag_notes") or "",
        }
        for row in ad_rows
    ]


def _filter_ad_rows(ad_rows, action_label, campaign, min_spend, product_query):
    filtered = []
    query = str(product_query or "").strip().lower()
    for row in ad_rows:
        if action_label != "All" and row.get("action_label") != action_label:
            continue
        if campaign != "All" and row.get("campaign") != campaign:
            continue
        if _number(row.get("spend")) < _number(min_spend):
            continue
        product_text = " ".join(
            str(row.get(key) or "")
            for key in ("product_handle", "product_title", "sport", "country_focus", "ad_angle", "mockup_type")
        ).lower()
        if query and query not in product_text:
            continue
        filtered.append(row)
    return filtered


def _render_controls(config_status):
    control_cols = st.columns([1.05, 1, 1.1, 0.9])
    selected_range = control_cols[0].selectbox("Date range", list(DATE_RANGE_OPTIONS), index=0)
    if control_cols[1].button("Test Meta Connection", disabled=not config_status["configured"], use_container_width=True):
        try:
            result = meta_ads_client.test_meta_connection()
            st.success(f"Connection OK: {result.get('name') or result.get('account_id') or 'Meta account found'}")
        except Exception as error:
            safe_message = meta_ads_client.sanitize_meta_error(f"{type(error).__name__}: {error}")
            supabase_backend.record_ads_sync_error(safe_message, {"action": "test_meta_connection"})
            st.error("Meta connection test failed. No Meta write actions were attempted.")
            st.caption(safe_message)
    if control_cols[2].button("Sync Meta Ads Data", type="primary", disabled=not config_status["configured"], use_container_width=True):
        progress = st.progress(0, text="Starting Meta read-only sync...")
        try:
            progress.progress(15, text="Reading Meta account, campaigns, ad sets, ads, and insights...")
            result = _sync_meta_ads(selected_range, DATE_RANGE_OPTIONS[selected_range])
            progress.progress(100, text="Meta Ads data saved to Supabase.")
            if result.get("ads", 0) > 0 and result.get("insights", 0) > 0 and not result.get("warnings"):
                st.success(
                    "Sync complete: "
                    f"{result.get('campaigns', 0)} campaigns, {result.get('adsets', 0)} ad sets, "
                    f"{result.get('ads', 0)} ads, {result.get('creatives', 0)} creatives, "
                    f"{result.get('insights', 0)} daily performance rows saved."
                )
            else:
                st.warning(
                    "Synced campaign structure. Ad performance data still needs retry. "
                    "Open Developer -> Ads Intelligence Diagnostics for technical details."
                )
        except Exception as error:
            progress.empty()
            safe_message = meta_ads_client.sanitize_meta_error(f"{type(error).__name__}: {error}")
            supabase_backend.record_ads_sync_error(safe_message, {"range": selected_range})
            st.error(
                "Meta sync issue: some reporting data failed. "
                "Open Developer -> Ads Intelligence Diagnostics for technical details."
            )
    if control_cols[3].button("Refresh Stored Data", use_container_width=True):
        st.rerun()
    return selected_range


def _latest_sync_time(sync_status, latest_sync_log):
    return (
        latest_sync_log.get("finished_at")
        or latest_sync_log.get("started_at")
        or sync_status.get("last_successful_sync")
        or ""
    )


def _latest_sync_status(latest_sync_log):
    return str(latest_sync_log.get("status") or "").strip().lower()


def _sync_status_label(sync_status, counts, latest_sync_log):
    latest_status = _latest_sync_status(latest_sync_log)
    if latest_status == "success":
        return "Synced"
    if latest_status == "partial_success":
        if int(counts.get("meta_ad_insights_daily") or 0) > 0:
            return "Synced"
        return "Partial sync"
    if latest_status == "error":
        return "Sync issue"
    if sync_status.get("last_successful_sync"):
        if int(counts.get("meta_ad_insights_daily") or 0) > 0:
            return "Synced"
        return "Needs performance retry"
    return "Needs sync"


def _empty_performance_message(counts):
    if int(counts.get("meta_campaigns") or 0) or int(counts.get("meta_adsets") or 0):
        return "Campaign structure synced, but performance rows did not sync. Open Developer diagnostics for the Meta error."
    return "No Meta performance rows yet. Test connection, then sync Last 7 days."


def _show_business_sync_warning(latest_sync_log, counts):
    latest_status = _latest_sync_status(latest_sync_log)
    has_insights = int(counts.get("meta_ad_insights_daily") or 0) > 0
    if latest_status == "success":
        return ""
    if latest_status == "partial_success" and not has_insights:
        return "Meta partially synced. Some data may be missing. Open Developer diagnostics for details."
    if latest_status == "error" and not has_insights:
        return "Meta sync issue. Open Developer diagnostics for details."
    return ""


def render_page():
    ui_styles.inject_global_ui_styles()
    ui_styles.page_header(
        "Ads Intelligence",
        "Read-only Meta performance for creative decisions and product opportunities.",
    )

    config_status = meta_ads_client.safe_meta_config_status()
    sync_status = supabase_backend.get_ads_sync_status_read_only()
    latest_sync_log = supabase_backend.get_latest_ads_sync_log()
    counts = supabase_backend.ads_table_counts()
    status_label = _sync_status_label(sync_status, counts, latest_sync_log)
    ui_styles.source_status_banner(
        [
            ("Source", "Meta Ads"),
            ("Last sync", _latest_sync_time(sync_status, latest_sync_log) or "Never"),
            ("Status", status_label),
            ("Data store", "Supabase"),
        ]
    )
    warning_message = _show_business_sync_warning(latest_sync_log, counts)
    if warning_message:
        st.warning(warning_message)

    selected_range = _render_controls(config_status)
    days = DATE_RANGE_OPTIONS[selected_range]
    insight_rows = supabase_backend.list_meta_ad_insights(days=days)
    summary = _summary(insight_rows)
    ad_rows = _aggregate_by_ad(insight_rows)

    if insight_rows:
        ui_styles.metric_strip(
            [
                ("Spend", _money(summary["spend"])),
                ("Purchases", f"{summary['purchases']:,.0f}"),
                ("Purchase value", _money(summary["revenue"])),
                ("ROAS", _ratio(summary["roas"])),
                ("CPA", _money(summary["cpa"])),
                ("CTR", _pct(summary["ctr"])),
                ("CPC", _money(summary["cpc"])),
                ("CPM", _money(summary["cpm"])),
                ("Frequency", f"{summary['frequency']:.2f}"),
            ]
        )

    war_room_tab, table_tab, tags_tab, chatgpt_tab = st.tabs(
        ["War Room", "Meta Ads Table", "Creative Tags", "ChatGPT Pack"]
    )

    with war_room_tab:
        _section("Today Action List")
        if not ad_rows:
            ui_styles.empty_state(_empty_performance_message(counts))
        else:
            st.dataframe(_decision_summary(ad_rows), hide_index=True, use_container_width=True)
            winners, losers = _top_and_losing_rows(ad_rows)
            left, right = st.columns(2)
            with left:
                _section("Scale / Winner Candidates")
                winner_rows = [
                    {
                        "Ad": row.get("ad"),
                        "Campaign": row.get("campaign"),
                        "Spend": _money(row.get("spend")),
                        "Revenue": _money(row.get("revenue")),
                        "ROAS": _ratio(row.get("roas")),
                        "Action": row.get("action_label"),
                    }
                    for row in winners[:8]
                ]
                if winner_rows:
                    st.dataframe(winner_rows, hide_index=True, use_container_width=True)
                else:
                    ui_styles.empty_state("No scale candidates yet.")
            with right:
                _section("Refresh / Kill / Diagnose")
                loser_rows = [
                    {
                        "Ad": row.get("ad"),
                        "Campaign": row.get("campaign"),
                        "Spend": _money(row.get("spend")),
                        "CTR": _pct(row.get("ctr")),
                        "ROAS": _ratio(row.get("roas")),
                        "Action": row.get("action_label"),
                    }
                    for row in losers[:8]
                ]
                if loser_rows:
                    st.dataframe(loser_rows, hide_index=True, use_container_width=True)
                else:
                    ui_styles.empty_state("No weak ads flagged yet.")
            _section("Product Opportunities")
            st.caption(
                "Most ads are currently untagged. Use Creative Tags to map ads to products so product opportunity reporting becomes accurate."
            )
            product_rows = _product_opportunity_rows(ad_rows)
            if product_rows:
                st.dataframe(product_rows, hide_index=True, use_container_width=True)
            else:
                ui_styles.empty_state("Tag ads to products to unlock product-level opportunities.")

    with table_tab:
        _section("Meta Ads Performance")
        filter_cols = st.columns([1, 1.25, 0.8, 1.2])
        action_options = ["All"] + sorted({row.get("action_label") for row in ad_rows if row.get("action_label")})
        campaign_options = ["All"] + sorted({row.get("campaign") for row in ad_rows if row.get("campaign")})
        action_filter = filter_cols[0].selectbox("Action label", action_options)
        campaign_filter = filter_cols[1].selectbox("Campaign", campaign_options)
        min_spend = filter_cols[2].number_input("Min spend", min_value=0.0, value=0.0, step=10.0)
        product_query = filter_cols[3].text_input("Product / mapping")
        filtered_rows = _filter_ad_rows(ad_rows, action_filter, campaign_filter, min_spend, product_query)
        table_rows = _performance_table(filtered_rows)
        if table_rows:
            display_rows = table_rows[:500]
            st.caption(f"Showing {len(display_rows)} of {len(table_rows)} matching ads.")
            st.dataframe(display_rows, hide_index=True, use_container_width=True, height=520)
            st.download_button(
                "Download CSV",
                data=_csv_bytes(table_rows),
                file_name=f"sports_cave_meta_ads_{days}_days.csv",
                mime="text/csv",
                use_container_width=True,
            )
        else:
            ui_styles.empty_state(_empty_performance_message(counts) if not insight_rows else "No stored Meta rows match these filters.")

    with tags_tab:
        _section("Creative Tags")
        if not ad_rows:
            ui_styles.empty_state("Sync Meta data first, then tag ads against products, sports, mockups, and angles.")
        else:
            st.dataframe(_creative_tag_rows(ad_rows), hide_index=True, use_container_width=True, height=360)
            with st.expander("Edit selected creative tags", expanded=False):
                ad_options = {f"{row.get('ad')} ({row.get('ad_id')})": row for row in ad_rows}
                selected_ad_label = st.selectbox("Ad to tag", list(ad_options))
                selected_ad = ad_options[selected_ad_label]
                with st.form("ads-creative-tag-form"):
                    col_a, col_b, col_c = st.columns(3)
                    product_handle = col_a.text_input("Product handle", value=selected_ad.get("product_handle") or "")
                    product_title = col_b.text_input("Product title", value=selected_ad.get("product_title") or "")
                    sport = col_c.text_input("Sport", value=selected_ad.get("sport") or "")
                    country_focus = col_a.text_input("Country focus", value=selected_ad.get("country_focus") or "")
                    mockup_type = col_b.text_input("Mockup type", value=selected_ad.get("mockup_type") or "")
                    ad_angle = col_c.text_input("Ad angle", value=selected_ad.get("ad_angle") or "")
                    funnel_stage = col_a.text_input("Funnel stage", value=selected_ad.get("funnel_stage") or "")
                    notes = st.text_area("Notes", value=selected_ad.get("tag_notes") or "", height=80)
                    if st.form_submit_button("Save Creative Tags", use_container_width=True):
                        supabase_backend.upsert_ads_creative_tag(
                            {
                                "ad_id": selected_ad.get("ad_id"),
                                "creative_id": selected_ad.get("creative_id"),
                                "product_handle": product_handle,
                                "product_title": product_title,
                                "sport": sport,
                                "country_focus": country_focus,
                                "mockup_type": mockup_type,
                                "ad_angle": ad_angle,
                                "funnel_stage": funnel_stage,
                                "notes": notes,
                            }
                        )
                        st.success("Creative tags saved.")

    with chatgpt_tab:
        _section("ChatGPT Analysis Pack")
        template = st.selectbox(
            "Template",
            [
                "Daily Ads Review",
                "Creative Pattern Finder",
                "New Ad Plan Generator",
                "Loser Diagnosis",
                "Product Scaling Plan",
                "Weekly Creative Meeting Report",
            ],
        )
        prompt_text = _prompt_for(template, selected_range, summary, ad_rows)
        st.text_area("Copyable ChatGPT prompt/data pack", value=prompt_text, height=360)
        st.download_button(
            "Download ChatGPT Pack",
            data=prompt_text.encode("utf-8"),
            file_name=f"sports_cave_{template.lower().replace(' ', '_')}_{days}_days.txt",
            mime="text/plain",
            use_container_width=True,
        )
