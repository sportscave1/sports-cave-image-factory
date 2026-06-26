import csv
import io
import time
from decimal import Decimal

import streamlit as st

import meta_ads_client
import supabase_backend


DATE_RANGE_OPTIONS = {
    "Last 7 days": 7,
    "Last 30 days": 30,
}


PERFORMANCE_COLUMNS = [
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
    "Action Label",
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


def _inject_ads_styles():
    st.markdown(
        """
        <style>
        .ads-hero {
            border: 1px solid rgba(213, 170, 86, 0.28);
            background: linear-gradient(135deg, #0d0c0a 0%, #181510 58%, #231b0d 100%);
            border-radius: 8px;
            padding: 22px 24px;
            margin-bottom: 18px;
        }
        .ads-hero h1 {
            color: #f7f0e4;
            font-size: 2.05rem;
            margin: 0 0 8px 0;
            letter-spacing: 0;
        }
        .ads-hero p {
            color: #b8aea1;
            margin: 0;
            font-size: 0.98rem;
        }
        .ads-section-title {
            color: #f6ead8;
            font-weight: 700;
            font-size: 1.05rem;
            margin: 22px 0 8px 0;
        }
        .ads-note {
            color: #a99f92;
            font-size: 0.9rem;
        }
        div[data-testid="stMetric"] {
            background: #f7f2e9;
            border: 1px solid #dfd4c5;
            border-radius: 8px;
            padding: 12px 14px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _section(title, caption=""):
    st.markdown(f'<div class="ads-section-title">{title}</div>', unsafe_allow_html=True)
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
                "Action Label": row.get("action_label"),
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
    status = "partial_success" if warnings else "success"
    warning_text = "; ".join(warnings)
    supabase_backend.finish_ads_sync_log(
        sync_log_id,
        status=status,
        date_range=range_label,
        rows_fetched=rows_fetched,
        rows_upserted=saved.get("rows_upserted", 0),
        error_message=warning_text,
        context={"warnings": warnings, "meta_pages": page_counts},
    )
    if warnings:
        supabase_backend.record_ads_sync_error(warning_text, {"range": range_label, "partial": True})
    saved["meta_pages"] = page_counts
    saved["warnings"] = warnings
    saved["status"] = status
    saved["rows_fetched"] = rows_fetched
    saved["total_ms"] = int((time.perf_counter() - started) * 1000)
    return saved


def render_page():
    _inject_ads_styles()
    st.markdown(
        """
        <div class="ads-hero">
            <h1>Ads Intelligence</h1>
            <p>Meta Ads API read-only reporting for creative decisions, product opportunities, and ChatGPT-ready analysis packs.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    config_status = meta_ads_client.safe_meta_config_status()
    sync_status = supabase_backend.get_ads_sync_status_read_only()

    _section("Meta Connection Status")
    status_cols = st.columns(6)
    status_cols[0].metric("Meta configured", "Yes" if config_status["configured"] else "No")
    status_cols[1].metric("Ad account ID", "Present" if config_status["ad_account_id_present"] else "Missing")
    status_cols[2].metric("Token", "Present" if config_status["token_present"] else "Missing")
    status_cols[3].metric("App ID", "Present" if config_status["app_id_present"] else "Missing")
    status_cols[4].metric("App secret", "Present" if config_status["app_secret_present"] else "Missing")
    status_cols[5].metric("API version", config_status["api_version"])
    st.caption("Source: Meta Ads API -> Supabase")
    st.caption(f"Last successful sync: {sync_status.get('last_successful_sync') or 'Never'}")
    if sync_status.get("last_sync_error"):
        st.warning(f"Last sync error: {sync_status.get('last_sync_error')}")

    test_cols = st.columns([1, 3])
    if test_cols[0].button("Test Meta Connection", disabled=not config_status["configured"], use_container_width=True):
        try:
            result = meta_ads_client.test_meta_connection()
            st.success(f"Connection OK: {result.get('name') or result.get('account_id') or 'Meta account found'}")
        except Exception as error:
            safe_message = meta_ads_client.sanitize_meta_error(f"{type(error).__name__}: {error}")
            supabase_backend.record_ads_sync_error(safe_message, {"action": "test_meta_connection"})
            st.error("Meta connection test failed. No Meta write actions were attempted.")
            st.caption(safe_message)

    sync_cols = st.columns([1, 1, 2])
    selected_sync_range = sync_cols[0].selectbox("Sync range", list(DATE_RANGE_OPTIONS), index=0)
    if sync_cols[1].button("Sync Meta Ads Data", disabled=not config_status["configured"], use_container_width=True):
        progress = st.progress(0, text="Starting Meta read-only sync...")
        try:
            progress.progress(15, text="Reading Meta account, campaigns, ad sets, ads, and insights...")
            result = _sync_meta_ads(selected_sync_range, DATE_RANGE_OPTIONS[selected_sync_range])
            progress.progress(100, text="Meta Ads data saved to Supabase.")
            st.success(
                "Sync complete: "
                f"{result.get('campaigns', 0)} campaigns, {result.get('adsets', 0)} ad sets, "
                f"{result.get('ads', 0)} ads, {result.get('insights', 0)} daily insight rows."
            )
            if result.get("warnings"):
                st.warning("Sync partially completed. Some Meta reads failed, but safe fetched rows were saved.")
        except Exception as error:
            progress.empty()
            safe_message = meta_ads_client.sanitize_meta_error(f"{type(error).__name__}: {error}")
            supabase_backend.record_ads_sync_error(safe_message, {"range": selected_sync_range})
            st.error("Meta sync failed. No Meta write actions were attempted.")
            st.caption(safe_message)

    range_label = st.radio("Reporting range", list(DATE_RANGE_OPTIONS), horizontal=True, label_visibility="collapsed")
    days = DATE_RANGE_OPTIONS[range_label]
    insight_rows = supabase_backend.list_meta_ad_insights(days=days)
    summary = _summary(insight_rows)
    ad_rows = _aggregate_by_ad(insight_rows)
    table_rows = _performance_table(ad_rows)

    _section("Daily War Room", "Decision metrics from Supabase-stored Meta insight rows.")
    metric_cols = st.columns(4)
    metric_cols[0].metric("Spend", _money(summary["spend"]))
    metric_cols[1].metric("Purchases", f"{summary['purchases']:,.0f}")
    metric_cols[2].metric("Purchase value", _money(summary["revenue"]))
    metric_cols[3].metric("Meta ROAS", _ratio(summary["roas"]))
    metric_cols = st.columns(5)
    metric_cols[0].metric("CPA", _money(summary["cpa"]))
    metric_cols[1].metric("CTR", _pct(summary["ctr"]))
    metric_cols[2].metric("CPC", _money(summary["cpc"]))
    metric_cols[3].metric("CPM", _money(summary["cpm"]))
    metric_cols[4].metric("Frequency", f"{summary['frequency']:.2f}")

    _section("Meta Ads Performance")
    if table_rows:
        st.dataframe(table_rows, hide_index=True, use_container_width=True)
        st.download_button(
            "Download CSV",
            data=_csv_bytes(table_rows),
            file_name=f"sports_cave_meta_ads_{days}_days.csv",
            mime="text/csv",
            use_container_width=True,
        )
    else:
        st.info("No stored Meta ad insight rows yet. Use Sync Meta Ads Data when ready.")

    winners, losers = _top_and_losing_rows(ad_rows)
    _section("Creative Winners")
    if winners:
        st.dataframe(
            [
                {
                    "Ad": row.get("ad"),
                    "Product": row.get("product_title") or row.get("product_handle") or "Untagged",
                    "Angle": row.get("ad_angle") or "Untagged",
                    "Spend": _money(row.get("spend")),
                    "Purchases": f"{row.get('purchases', 0):.0f}",
                    "ROAS": _ratio(row.get("roas")),
                    "Action": row.get("action_label"),
                }
                for row in winners
            ],
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.caption("Winner detection will appear once insight rows are stored.")

    _section("Product Opportunities")
    product_rows = {}
    for row in ad_rows:
        key = row.get("product_title") or row.get("product_handle") or "Untagged"
        product = product_rows.setdefault(key, {"Product": key, "Spend": 0, "Revenue": 0, "Purchases": 0, "Best ROAS": 0})
        product["Spend"] += row.get("spend", 0)
        product["Revenue"] += row.get("revenue", 0)
        product["Purchases"] += row.get("purchases", 0)
        product["Best ROAS"] = max(product["Best ROAS"], row.get("roas", 0))
    if product_rows:
        st.dataframe(
            [
                {
                    "Product": row["Product"],
                    "Spend": _money(row["Spend"]),
                    "Revenue": _money(row["Revenue"]),
                    "Purchases": f"{row['Purchases']:.0f}",
                    "Best ROAS": _ratio(row["Best ROAS"]),
                }
                for row in sorted(product_rows.values(), key=lambda item: item["Revenue"], reverse=True)
            ],
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.caption("Tag ads to products to unlock cleaner product-level opportunity reads.")

    _section("Creative Tagging")
    if ad_rows:
        ad_options = {f"{row.get('ad')} ({row.get('ad_id')})": row for row in ad_rows}
        selected_ad_label = st.selectbox("Ad to tag", list(ad_options))
        selected_ad = ad_options[selected_ad_label]
        with st.form("ads-creative-tag-form"):
            col_a, col_b = st.columns(2)
            product_handle = col_a.text_input("Product handle", value=selected_ad.get("product_handle") or "")
            product_title = col_b.text_input("Product title", value=selected_ad.get("product_title") or "")
            sport = col_a.text_input("Sport", value=selected_ad.get("sport") or "")
            country_focus = col_b.text_input("Country focus", value=selected_ad.get("country_focus") or "")
            mockup_type = col_a.text_input("Mockup type", value=selected_ad.get("mockup_type") or "")
            ad_angle = col_b.text_input("Ad angle", value=selected_ad.get("ad_angle") or "")
            funnel_stage = col_a.text_input("Funnel stage", value=selected_ad.get("funnel_stage") or "")
            notes = st.text_area("Notes", value=selected_ad.get("tag_notes") or "", height=90)
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
    else:
        st.caption("Sync Meta data first, then tag ads against Sports Cave products and angles.")

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
    prompt_text = _prompt_for(template, range_label, summary, ad_rows)
    st.text_area("Copyable ChatGPT prompt/data pack", value=prompt_text, height=360)
    st.download_button(
        "Download ChatGPT Pack",
        data=prompt_text.encode("utf-8"),
        file_name=f"sports_cave_{template.lower().replace(' ', '_')}_{days}_days.txt",
        mime="text/plain",
        use_container_width=True,
    )

    _section("Action Log")
    sync_log_rows = supabase_backend.list_ads_sync_logs(limit=25)
    if sync_log_rows:
        st.caption("Meta sync attempts")
        st.dataframe(
            [
                {
                    "Started At": row.get("started_at"),
                    "Finished At": row.get("finished_at"),
                    "Range": row.get("date_range"),
                    "Status": row.get("status"),
                    "Rows Fetched": row.get("rows_fetched"),
                    "Rows Upserted": row.get("rows_upserted"),
                    "Error": row.get("error_message") or "",
                }
                for row in sync_log_rows
            ],
            hide_index=True,
            use_container_width=True,
        )
    action_rows = supabase_backend.list_ads_action_log(limit=50)
    if action_rows:
        st.caption("Manual actions and tags")
        st.dataframe(
            [
                {
                    "Created At": row.get("created_at"),
                    "Type": row.get("action_type"),
                    "Status": row.get("status"),
                    "Summary": row.get("summary"),
                }
                for row in action_rows
            ],
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.caption("No ads actions logged yet.")
