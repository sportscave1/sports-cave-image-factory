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
    "Last 3 months": 90,
    "Last 6 months": 180,
    "Last 12 months": 365,
    "All stored data": None,
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


MAPPING_STATUS_OPTIONS = ["All", "confirmed", "suggested", "needs_review", "unmapped"]


def _date_range_days(label):
    return DATE_RANGE_OPTIONS.get(label)


def _date_range_syncable(label):
    return _date_range_days(label) is not None


def _date_range_slug(label):
    return (
        str(label or "selected_range")
        .lower()
        .replace("/", "_")
        .replace(" ", "_")
        .replace("-", "_")
    )


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
                "room_type": row.get("room_type") or "",
                "ad_angle": row.get("ad_angle") or "",
                "hook_style": row.get("hook_style") or "",
                "creative_format": row.get("tag_creative_format") or row.get("detected_creative_format") or "",
                "funnel_stage": row.get("funnel_stage") or "",
                "tag_notes": row.get("tag_notes") or "",
                "primary_text": row.get("primary_text") or "",
                "headline": row.get("headline") or "",
                "description": row.get("description") or "",
                "call_to_action": row.get("call_to_action") or "",
                "link_url": row.get("link_url") or "",
                "image_url": row.get("image_url") or row.get("thumbnail_url") or "",
            },
        )
        for key in (
            "product_handle",
            "product_title",
            "sport",
            "country_focus",
            "mockup_type",
            "room_type",
            "ad_angle",
            "hook_style",
            "creative_format",
            "funnel_stage",
            "tag_notes",
            "primary_text",
            "headline",
            "description",
            "call_to_action",
            "link_url",
            "image_url",
        ):
            if not item.get(key):
                if key == "creative_format":
                    item[key] = row.get("tag_creative_format") or row.get("detected_creative_format") or ""
                else:
                    item[key] = row.get(key) or ""
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


def _aggregate_group(rows, group_keys):
    grouped = {}
    for row in rows or []:
        key_values = tuple(str(row.get(key) or "Unknown") for key in group_keys)
        item = grouped.setdefault(
            key_values,
            {
                **{key: value for key, value in zip(group_keys, key_values)},
                "spend": 0.0,
                "impressions": 0,
                "reach": 0,
                "clicks": 0,
                "inline_link_clicks": 0,
                "purchases": 0.0,
                "purchase_value": 0.0,
                "top_campaign": "",
                "top_ad": "",
                "_top_revenue": -1.0,
            },
        )
        spend = _number(row.get("spend"))
        revenue = _number(row.get("purchase_value") or row.get("revenue"))
        item["spend"] += spend
        item["impressions"] += int(_number(row.get("impressions")))
        item["reach"] += int(_number(row.get("reach")))
        item["clicks"] += int(_number(row.get("clicks")))
        item["inline_link_clicks"] += int(_number(row.get("inline_link_clicks")))
        item["purchases"] += _number(row.get("purchases"))
        item["purchase_value"] += revenue
        if revenue > item["_top_revenue"]:
            item["_top_revenue"] = revenue
            item["top_campaign"] = row.get("campaign_name") or row.get("campaign") or ""
            item["top_ad"] = row.get("ad_name") or row.get("ad") or ""
    output = []
    for item in grouped.values():
        spend = item["spend"]
        impressions = item["impressions"]
        clicks = item["clicks"]
        purchases = item["purchases"]
        revenue = item["purchase_value"]
        output.append(
            {
                **{key: item[key] for key in group_keys},
                "Spend": _money(spend),
                "Purchases": f"{purchases:,.0f}",
                "Purchase value": _money(revenue),
                "ROAS": _ratio(revenue / spend if spend else 0),
                "CPA": _money(spend / purchases if purchases else 0),
                "CTR": _pct(clicks / impressions * 100 if impressions else 0),
                "CPC": _money(spend / clicks if clicks else 0),
                "CPM": _money(spend / impressions * 1000 if impressions else 0),
                "Top campaign": item["top_campaign"],
                "Top ad": item["top_ad"],
                "_sort": revenue,
            }
        )
    return sorted(output, key=lambda item: item["_sort"], reverse=True)


def _compact_table(rows, height=380, empty_message="No stored rows for this view yet. Use manual sync options to fetch this data."):
    clean_rows = []
    for row in rows or []:
        clean_rows.append({key: value for key, value in row.items() if not str(key).startswith("_")})
    if clean_rows:
        st.dataframe(clean_rows[:500], hide_index=True, use_container_width=True, height=height)
    else:
        ui_styles.empty_state(empty_message)


def _tag_suggestion(row):
    text = " ".join(str(row.get(key) or "") for key in ("ad", "campaign", "adset")).upper()
    suggestion = {
        "product_handle": "",
        "product_title": "",
        "sport": "",
        "country_focus": "",
        "mockup_type": row.get("mockup_type") or "",
        "room_type": row.get("room_type") or "",
        "ad_angle": row.get("ad_angle") or "",
        "hook_style": row.get("hook_style") or "",
        "creative_format": row.get("creative_format") or "",
        "funnel_stage": row.get("funnel_stage") or "",
        "notes": "Suggested from ad/campaign name. Review before saving.",
        "label": "Needs review",
    }
    if "BRUNSEN" in text:
        suggestion.update(product_title="Brunson / Knicks product mapping", sport="Basketball", country_focus="USA", label="Suggested: Brunson")
    elif "LAP OF GOD" in text or "LAP OF THE GOD" in text:
        suggestion.update(product_title="Lap of the Gods product mapping", sport="Motorsport", country_focus="Australia", label="Suggested: Lap of the Gods")
    elif "MESSI" in text:
        suggestion.update(product_title="Messi product mapping", sport="Football/Soccer", label="Suggested: Messi")
    elif "UFC" in text or "GAETHJE" in text:
        suggestion.update(product_title="UFC / Gaethje product mapping", sport="UFC/MMA", country_focus="USA", label="Suggested: UFC/Gaethje")
    elif "LEGENDS" in text:
        suggestion.update(product_title="Football legends product mapping", sport="Football/Soccer", label="Suggested: Legends needs review")
    return suggestion


def _group_creative_report(ad_rows, field):
    grouped = {}
    for row in ad_rows or []:
        key = str(row.get(field) or "").strip()
        if not key:
            continue
        item = grouped.setdefault(key, {"Value": key[:220], "Ads": 0, "Spend": 0.0, "Revenue": 0.0, "Purchases": 0.0, "Clicks": 0, "Impressions": 0})
        item["Ads"] += 1
        item["Spend"] += _number(row.get("spend"))
        item["Revenue"] += _number(row.get("revenue"))
        item["Purchases"] += _number(row.get("purchases"))
        item["Clicks"] += int(_number(row.get("clicks")))
        item["Impressions"] += int(_number(row.get("impressions")))
    output = []
    for item in grouped.values():
        spend = item["Spend"]
        revenue = item["Revenue"]
        purchases = item["Purchases"]
        clicks = item["Clicks"]
        impressions = item["Impressions"]
        output.append(
            {
                "Value": item["Value"],
                "Ads": item["Ads"],
                "Spend": _money(spend),
                "Revenue": _money(revenue),
                "Purchases": f"{purchases:,.0f}",
                "ROAS": _ratio(revenue / spend if spend else 0),
                "CPA": _money(spend / purchases if purchases else 0),
                "CTR": _pct(clicks / impressions * 100 if impressions else 0),
                "_sort": (revenue / spend if spend else 0, purchases, revenue),
            }
        )
    return sorted(output, key=lambda item: item["_sort"], reverse=True)


def _prompt_for(
    template,
    range_label,
    summary,
    ad_rows,
    country_rows=None,
    demographic_rows=None,
    platform_rows=None,
    mapping_rows=None,
    product_opportunities=None,
):
    winners, losers = _top_and_losing_rows(ad_rows)
    country_summary = _aggregate_group(country_rows or [], ["country"])[:8]
    demographic_summary = _aggregate_group(demographic_rows or [], ["age", "gender"])[:8]
    platform_summary = _aggregate_group(platform_rows or [], ["publisher_platform", "platform_position"])[:8]
    best_text = _group_creative_report(ad_rows, "primary_text")[:5]
    best_headlines = _group_creative_report(ad_rows, "headline")[:5]
    lines = [
        "Sports Cave Meta Ads Intelligence Pack",
        "",
        "Business context:",
        "Sports Cave sells premium limited-edition framed sports artwork, usually edition of 100, through Shopify.",
        "The goal is profitable revenue growth: identify ads to scale, ads to kill, creatives to refresh, products to push, and new ad concepts to launch.",
        "Important attribution warning: Meta revenue is platform attribution. Shopify/Supabase sales are actual product-level sales and may not be exact ad attribution unless UTM/ad ID matching exists.",
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
    if country_summary:
        lines.extend(["", "Country performance:"])
        for row in country_summary:
            lines.append(
                f"- {row.get('country')} | Spend {row.get('Spend')} | Revenue {row.get('Purchase value')} | "
                f"Purchases {row.get('Purchases')} | ROAS {row.get('ROAS')} | Top ad: {row.get('Top ad')}"
            )
    if demographic_summary:
        lines.extend(["", "Demographic performance:"])
        for row in demographic_summary:
            lines.append(
                f"- {row.get('age')} / {row.get('gender')} | Spend {row.get('Spend')} | Revenue {row.get('Purchase value')} | "
                f"Purchases {row.get('Purchases')} | ROAS {row.get('ROAS')}"
            )
    if platform_summary:
        lines.extend(["", "Platform placement performance:"])
        for row in platform_summary:
            lines.append(
                f"- {row.get('publisher_platform')} {row.get('platform_position')} | Spend {row.get('Spend')} | "
                f"Revenue {row.get('Purchase value')} | ROAS {row.get('ROAS')}"
            )
    if best_text:
        lines.extend(["", "Winning primary text examples:"])
        for row in best_text:
            lines.append(f"- {row.get('Value')} | ROAS {row.get('ROAS')} | Purchases {row.get('Purchases')}")
    if best_headlines:
        lines.extend(["", "Winning headline examples:"])
        for row in best_headlines:
            lines.append(f"- {row.get('Value')} | ROAS {row.get('ROAS')} | Purchases {row.get('Purchases')}")
    if mapping_rows:
        lines.extend(["", "Product mapping rows:"])
        for row in (mapping_rows or [])[:12]:
            lines.append(
                f"- {row.get('ad_name')} | Campaign: {row.get('campaign_name')} | "
                f"Product: {row.get('product_title') or row.get('product_handle') or row.get('suggested_product_title') or 'unmapped'} | "
                f"Status: {row.get('mapping_status') or 'unmapped'} | Spend {_money(row.get('spend'))} | "
                f"Purchases {_number(row.get('purchases')):,.0f} | ROAS {_ratio(row.get('roas'))} | "
                f"CPA {_money(row.get('cpa'))} | CTR {_pct(row.get('ctr'))} | Notes: {row.get('notes') or 'none'}"
            )
    if product_opportunities:
        lines.extend(["", "Product opportunity rows:"])
        for row in (product_opportunities or [])[:12]:
            lines.append(
                f"- {row.get('product_title') or row.get('product_handle') or 'Untagged'} | "
                f"Mapping: {row.get('mapping_status')} | Meta spend {_money(row.get('meta_spend'))} | "
                f"Meta purchases {_number(row.get('meta_purchases')):,.0f} | Meta ROAS {_ratio(row.get('meta_roas'))} | "
                f"Shopify/Supabase actual orders: {row.get('actual_orders') if row.get('actual_orders') not in (None, '') else 'unknown'} | "
                f"Edition remaining: {row.get('edition_remaining') if row.get('edition_remaining') not in (None, '') else 'unknown'} | "
                f"Recommendation: {row.get('recommendation')}"
            )
    instructions = {
        "Daily Ads Review": "Give me today's decision list: what to scale, watch, refresh, kill, and what to test next.",
        "Creative Pattern Finder": "Find repeatable creative patterns in the winners and explain what visual or angle patterns to reuse.",
        "Country Creative Report": "Explain what ad text, sport/product, and creative format are working by country. Create new Sports Cave ad copy and mockup prompts inspired by each country's winners.",
        "Demographic Opportunity Report": "Find the age/gender segments worth more budget or new creative tests. Recommend tailored hooks for each strong segment.",
        "Platform Placement Report": "Compare placements and recommend what creative format and copy style to use for each placement.",
        "New Ad Copy Generator": "Create 10 new primary text variations, 10 headlines, and 5 image/mockup brief ideas based on the winners. Keep style close to proven patterns, but do not copy word-for-word.",
        "New Image/Mockup Brief Generator": "Create practical image and mockup briefs based on winning products, countries, formats, and ad angles.",
        "Product Tagging Review": "Review unmapped, suggested, and needs-review ads. Tell me which mappings look safe to confirm and which need manual investigation.",
        "New Creative Based on Product Winners": "Use the product winners and mapped ads to create new Meta ad copy, hook ideas, and image/mockup briefs for the strongest products.",
        "Country/Product Creative Plan": "Create a country-by-country product creative plan using mapped products, country performance, and edition scarcity where available.",
        "Loser Diagnosis": "Diagnose why the losing ads are failing and recommend whether each needs a new hook, creative, offer, audience, or product match.",
        "Product Scaling Plan": "Recommend which products deserve more spend, which countries/sports to focus on, and the next scaling sequence.",
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


def _sync_meta_ads(range_label, days, sync_base=True, sync_country=False, sync_age_gender=False, sync_platform=False, sync_type="performance"):
    started = time.perf_counter()
    sync_log_id = supabase_backend.start_ads_sync_log(
        source="meta_ads_api",
        sync_type=sync_type,
        date_range=range_label,
    )
    config = meta_ads_client.get_meta_config()
    warnings = []
    page_counts = {}
    saved = {
        "campaigns": 0,
        "adsets": 0,
        "ads": 0,
        "creatives": 0,
        "insights": 0,
        "country_insights": 0,
        "age_gender_insights": 0,
        "platform_insights": 0,
        "rows_upserted": 0,
    }

    def fetch_step(label, fetcher, default):
        try:
            return fetcher()
        except Exception as error:
            warnings.append(f"{label}: {meta_ads_client.sanitize_meta_error(error)}")
            return default

    rows_fetched = 0
    if sync_base:
        account = fetch_step("account", lambda: meta_ads_client.fetch_meta_account(config=config), {})
        campaigns = fetch_step("campaigns", lambda: meta_ads_client.fetch_meta_campaigns(config=config), {"rows": [], "page_count": 0})
        adsets = fetch_step("adsets", lambda: meta_ads_client.fetch_meta_adsets(config=config), {"rows": [], "page_count": 0})
        ads = fetch_step("ads", lambda: meta_ads_client.fetch_meta_ads(config=config), {"rows": [], "page_count": 0})
        insights = fetch_step("insights", lambda: meta_ads_client.fetch_meta_ad_insights(days=days, config=config), {"rows": [], "page_count": 0})

        for label, payload in (("campaigns", campaigns), ("adsets", adsets), ("ads", ads), ("insights", insights)):
            page_counts[label] = payload.get("page_count", 0)
        rows_fetched += (
            (1 if account else 0)
            + len(campaigns.get("rows") or [])
            + len(adsets.get("rows") or [])
            + len(ads.get("rows") or [])
            + len(insights.get("rows") or [])
        )
        saved.update(
            supabase_backend.save_meta_ads_sync(
                account=account,
                campaigns=campaigns.get("rows"),
                adsets=adsets.get("rows"),
                ads=ads.get("rows"),
                insights=insights.get("rows"),
                date_range_label=range_label,
                account_id=config.get("ad_account_id"),
            )
        )

    if sync_country:
        country = fetch_step(
            "country breakdown",
            lambda: meta_ads_client.fetch_meta_ad_insights_country(days=days, config=config),
            {"rows": [], "page_count": 0},
        )
        page_counts["country"] = country.get("page_count", 0)
        rows_fetched += len(country.get("rows") or [])
        country_saved = supabase_backend.save_meta_ads_breakdown_insights(
            "country",
            country.get("rows"),
            account_id=config.get("ad_account_id"),
            date_range_label=range_label,
        )
        saved["country_insights"] = country_saved.get("rows", 0)
        saved["rows_upserted"] += country_saved.get("rows_upserted", 0)

    if sync_age_gender:
        age_gender = fetch_step(
            "age/gender breakdown",
            lambda: meta_ads_client.fetch_meta_ad_insights_age_gender(days=days, config=config),
            {"rows": [], "page_count": 0},
        )
        page_counts["age_gender"] = age_gender.get("page_count", 0)
        rows_fetched += len(age_gender.get("rows") or [])
        age_gender_saved = supabase_backend.save_meta_ads_breakdown_insights(
            "age_gender",
            age_gender.get("rows"),
            account_id=config.get("ad_account_id"),
            date_range_label=range_label,
        )
        saved["age_gender_insights"] = age_gender_saved.get("rows", 0)
        saved["rows_upserted"] += age_gender_saved.get("rows_upserted", 0)

    if sync_platform:
        platform = fetch_step(
            "platform breakdown",
            lambda: meta_ads_client.fetch_meta_ad_insights_platform(days=days, config=config),
            {"rows": [], "page_count": 0},
        )
        page_counts["platform"] = platform.get("page_count", 0)
        rows_fetched += len(platform.get("rows") or [])
        platform_saved = supabase_backend.save_meta_ads_breakdown_insights(
            "platform",
            platform.get("rows"),
            account_id=config.get("ad_account_id"),
            date_range_label=range_label,
        )
        saved["platform_insights"] = platform_saved.get("rows", 0)
        saved["rows_upserted"] += platform_saved.get("rows_upserted", 0)

    if rows_fetched <= 0:
        message = "; ".join(warnings) or "Meta sync returned no rows."
        supabase_backend.finish_ads_sync_log(
            sync_log_id,
            status="error" if warnings else "partial_success",
            date_range=range_label,
            rows_fetched=0,
            rows_upserted=0,
            error_message=message,
            context={"warnings": warnings},
        )
        if warnings:
            raise meta_ads_client.MetaAdsApiError(message)
        saved["warnings"] = [message]
        saved["status"] = "partial_success"
        saved["rows_fetched"] = 0
        saved["total_ms"] = int((time.perf_counter() - started) * 1000)
        return saved

    missing_performance_rows = sync_base and (saved.get("ads", 0) <= 0 or saved.get("insights", 0) <= 0)
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
        context={
            "warnings": warning_parts,
            "meta_pages": page_counts,
            "selected_syncs": {
                "base": bool(sync_base),
                "country": bool(sync_country),
                "age_gender": bool(sync_age_gender),
                "platform": bool(sync_platform),
            },
        },
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
    rows = []
    for row in ad_rows:
        suggestion = _tag_suggestion(row)
        rows.append(
        {
            "Ad ID": row.get("ad_id"),
            "Ad": row.get("ad"),
            "Tag Status": "Tagged" if (row.get("product_handle") or row.get("product_title")) else "Needs tagging",
            "Suggestion": suggestion["label"],
            "Product Handle": row.get("product_handle") or "",
            "Product": row.get("product_title") or "",
            "Sport": row.get("sport") or "",
            "Country": row.get("country_focus") or "",
            "Mockup": row.get("mockup_type") or "",
            "Room": row.get("room_type") or "",
            "Angle": row.get("ad_angle") or "",
            "Hook": row.get("hook_style") or "",
            "Format": row.get("creative_format") or "",
            "Funnel": row.get("funnel_stage") or "",
            "Notes": row.get("tag_notes") or "",
        }
        )
    return sorted(rows, key=lambda item: (item["Tag Status"] != "Needs tagging", item["Ad"] or ""))


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
            for key in (
                "product_handle",
                "product_title",
                "sport",
                "country_focus",
                "ad_angle",
                "mockup_type",
                "room_type",
                "hook_style",
                "creative_format",
            )
        ).lower()
        if query and query not in product_text:
            continue
        filtered.append(row)
    return filtered


def _filter_creative_rows(ad_rows, country, campaign, product, creative_format, action_label, min_spend):
    filtered = []
    for row in ad_rows:
        if country != "All" and country not in {row.get("country"), row.get("country_focus")}:
            continue
        if campaign != "All" and row.get("campaign") != campaign:
            continue
        if product != "All" and (row.get("product_title") or row.get("product_handle") or "Untagged") != product:
            continue
        if creative_format != "All" and (row.get("creative_format") or "unknown") != creative_format:
            continue
        if action_label != "All" and row.get("action_label") != action_label:
            continue
        if _number(row.get("spend")) < _number(min_spend):
            continue
        filtered.append(row)
    return filtered


def _creative_intelligence_table(ad_rows):
    return [
        {
            "Ad": row.get("ad"),
            "Campaign": row.get("campaign"),
            "Product tag": row.get("product_title") or row.get("product_handle") or "Untagged",
            "Country focus": row.get("country_focus") or "",
            "Creative format": row.get("creative_format") or "unknown",
            "Mockup": row.get("mockup_type") or "",
            "Primary text": row.get("primary_text") or "",
            "Headline": row.get("headline") or "",
            "Description": row.get("description") or "",
            "CTA": row.get("call_to_action") or "",
            "Spend": _money(row.get("spend")),
            "Purchases": f"{_number(row.get('purchases')):,.0f}",
            "Revenue": _money(row.get("revenue")),
            "ROAS": _ratio(row.get("roas")),
            "CPA": _money(row.get("cpa")),
            "CTR": _pct(row.get("ctr")),
            "Action": row.get("action_label"),
        }
        for row in ad_rows
    ]


def _mapping_summary(mapping_rows):
    rows = mapping_rows or []
    return {
        "total": len(rows),
        "confirmed": sum(1 for row in rows if str(row.get("mapping_status") or "") == "confirmed" or row.get("product_handle")),
        "suggested": sum(1 for row in rows if str(row.get("mapping_status") or "") == "suggested"),
        "needs_review": sum(1 for row in rows if str(row.get("mapping_status") or "") == "needs_review"),
        "unmapped": sum(1 for row in rows if not (row.get("product_handle") or row.get("product_title")) and str(row.get("mapping_status") or "unmapped") in {"", "unmapped"}),
    }


def _mapping_table_rows(mapping_rows):
    table = []
    for row in mapping_rows or []:
        table.append(
            {
                "Status": row.get("mapping_status") or "unmapped",
                "Ad": row.get("ad_name") or "",
                "Campaign": row.get("campaign_name") or "",
                "Ad Set": row.get("adset_name") or "",
                "Suggested Product": row.get("suggested_product_title") or row.get("suggested_product_handle") or "",
                "Confidence": f"{_number(row.get('suggestion_confidence')):.2f}",
                "Suggestion Reason": row.get("suggestion_reason") or "",
                "Confirmed Product": row.get("product_title") or row.get("product_handle") or "",
                "Spend": _money(row.get("spend")),
                "Purchases": f"{_number(row.get('purchases')):,.0f}",
                "ROAS": _ratio(row.get("roas")),
                "CPA": _money(row.get("cpa")),
                "Action": "Review" if row.get("mapping_status") in {"suggested", "needs_review"} else ("Done" if row.get("product_handle") else "Tag"),
                "_ad_id": row.get("ad_id"),
            }
        )
    return table


def _filter_mapping_rows(mapping_rows, status, campaign, product, min_spend, search_text):
    query = str(search_text or "").strip().lower()
    product_query = str(product or "").strip().lower()
    filtered = []
    for row in mapping_rows or []:
        row_status = str(row.get("mapping_status") or "unmapped")
        if status != "All" and row_status != status:
            continue
        if campaign != "All" and row.get("campaign_name") != campaign:
            continue
        if _number(row.get("spend")) < _number(min_spend):
            continue
        product_text = " ".join(
            str(row.get(key) or "")
            for key in ("product_handle", "product_title", "suggested_product_handle", "suggested_product_title")
        ).lower()
        if product_query and product_query not in product_text:
            continue
        search_blob = " ".join(
            str(row.get(key) or "")
            for key in ("ad_name", "campaign_name", "adset_name", "creative_name", "suggestion_reason")
        ).lower()
        if query and query not in search_blob:
            continue
        filtered.append(row)
    return filtered


def _product_option_label(row):
    handle = row.get("product_handle") or ""
    title = row.get("product_title") or handle or "Unknown product"
    remaining = row.get("edition_remaining")
    if remaining not in (None, ""):
        return f"{title} | {handle} | {remaining} editions left"
    return f"{title} | {handle}"


def _opportunity_table_rows(rows):
    return [
        {
            "Product": row.get("product_title") or row.get("product_handle") or "Untagged",
            "Mapping": row.get("mapping_status") or "",
            "Mapped ads": row.get("mapped_ads") or 0,
            "Meta spend": _money(row.get("meta_spend")),
            "Meta purchases": f"{_number(row.get('meta_purchases')):,.0f}",
            "Meta purchase value": _money(row.get("meta_purchase_value")),
            "Meta ROAS": _ratio(row.get("meta_roas")),
            "Meta CPA": _money(row.get("meta_cpa")),
            "Meta CTR": _pct(row.get("meta_ctr")),
            "Shopify/Supabase actual orders": row.get("actual_orders") if row.get("actual_orders") not in (None, "") else "Unknown",
            "Shopify/Supabase actual revenue": _money(row.get("actual_revenue")) if row.get("actual_revenue") not in (None, "") else "Unknown",
            "Edition remaining": row.get("edition_remaining") if row.get("edition_remaining") not in (None, "") else "Unknown",
            "Recommendation": row.get("recommendation") or "Directional only",
        }
        for row in rows or []
    ]


def _render_controls(config_status):
    control_cols = st.columns([1.15, 0.95, 1, 1, 0.9, 0.9])
    selected_range = control_cols[0].selectbox("Date range", list(DATE_RANGE_OPTIONS), index=0)

    def show_all_stored_message():
        st.info("All stored data uses existing Supabase history. Sync a specific date range to fetch more Meta data.")

    def show_sync_result(result, label):
        if result.get("warnings"):
            st.warning(
                "Meta returned no rows for this report and date range. "
                "Try Last 30 days or check Developer diagnostics."
            )
            return
        if label == "Performance":
            st.success(f"Performance synced: {result.get('insights', 0)} rows.")
        elif label == "Demographics":
            st.success(
                f"Demographics synced: {result.get('country_insights', 0)} country rows, "
                f"{result.get('age_gender_insights', 0)} age/gender rows."
            )
        elif label == "Platform":
            st.success(f"Platform synced: {result.get('platform_insights', 0)} rows.")

    if control_cols[1].button("Test Meta Connection", disabled=not config_status["configured"], use_container_width=True):
        try:
            result = meta_ads_client.test_meta_connection()
            st.success(f"Connection OK: {result.get('name') or result.get('account_id') or 'Meta account found'}")
        except Exception as error:
            safe_message = meta_ads_client.sanitize_meta_error(f"{type(error).__name__}: {error}")
            supabase_backend.record_ads_sync_error(safe_message, {"action": "test_meta_connection"})
            st.error("Meta connection test failed. Open Developer -> Ads Intelligence Diagnostics for details.")

    sync_days = _date_range_days(selected_range)
    if control_cols[2].button("Sync Performance", type="primary", disabled=not config_status["configured"], use_container_width=True):
        if not _date_range_syncable(selected_range):
            show_all_stored_message()
        else:
            progress = st.progress(0, text="Syncing ad-level performance...")
            try:
                result = _sync_meta_ads(
                    selected_range,
                    sync_days,
                    sync_base=True,
                    sync_country=False,
                    sync_age_gender=False,
                    sync_platform=False,
                    sync_type="performance",
                )
                progress.progress(100, text="Performance data saved to Supabase.")
                show_sync_result(result, "Performance")
            except Exception as error:
                progress.empty()
                safe_message = meta_ads_client.sanitize_meta_error(f"{type(error).__name__}: {error}")
                supabase_backend.record_ads_sync_error(safe_message, {"range": selected_range, "sync_type": "performance"})
                if "too much data" in safe_message.lower() or "reduce the amount of data" in safe_message.lower():
                    st.error("Meta returned too much data for this range. Try a shorter range or sync only Performance first.")
                else:
                    st.error("Meta performance sync issue. Open Developer -> Ads Intelligence Diagnostics for technical details.")

    if control_cols[3].button("Sync Demographics", disabled=not config_status["configured"], use_container_width=True):
        if not _date_range_syncable(selected_range):
            show_all_stored_message()
        else:
            progress = st.progress(0, text="Syncing country and age/gender reports...")
            try:
                result = _sync_meta_ads(
                    selected_range,
                    sync_days,
                    sync_base=False,
                    sync_country=True,
                    sync_age_gender=True,
                    sync_platform=False,
                    sync_type="demographics",
                )
                progress.progress(100, text="Demographics data saved to Supabase.")
                show_sync_result(result, "Demographics")
            except Exception as error:
                progress.empty()
                safe_message = meta_ads_client.sanitize_meta_error(f"{type(error).__name__}: {error}")
                supabase_backend.record_ads_sync_error(safe_message, {"range": selected_range, "sync_type": "demographics"})
                if "too much data" in safe_message.lower() or "reduce the amount of data" in safe_message.lower():
                    st.error("Meta returned too much data for this range. Try a shorter range or sync Performance first.")
                else:
                    st.error("Meta demographics sync issue. Open Developer -> Ads Intelligence Diagnostics for technical details.")

    if control_cols[4].button("Sync Platform", disabled=not config_status["configured"], use_container_width=True):
        if not _date_range_syncable(selected_range):
            show_all_stored_message()
        else:
            progress = st.progress(0, text="Syncing platform and placement report...")
            try:
                result = _sync_meta_ads(
                    selected_range,
                    sync_days,
                    sync_base=False,
                    sync_country=False,
                    sync_age_gender=False,
                    sync_platform=True,
                    sync_type="platform",
                )
                progress.progress(100, text="Platform data saved to Supabase.")
                show_sync_result(result, "Platform")
            except Exception as error:
                progress.empty()
                safe_message = meta_ads_client.sanitize_meta_error(f"{type(error).__name__}: {error}")
                supabase_backend.record_ads_sync_error(safe_message, {"range": selected_range, "sync_type": "platform"})
                if "too much data" in safe_message.lower() or "reduce the amount of data" in safe_message.lower():
                    st.error("Meta returned too much data for this range. Try a shorter range or sync Performance first.")
                else:
                    st.error("Meta platform sync issue. Open Developer -> Ads Intelligence Diagnostics for technical details.")

    if control_cols[5].button("Refresh Stored Data", use_container_width=True):
        st.rerun()
    st.caption(
        "Performance = ad spend, purchases, ROAS, CTR, CPC. "
        "Demographics = country plus age/gender. Platform = Facebook/Instagram placement performance."
    )
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
    days = _date_range_days(selected_range)
    insight_rows = supabase_backend.list_meta_ad_insights(date_range=selected_range)
    country_rows = supabase_backend.list_meta_ad_insights_country(date_range=selected_range)
    demographic_rows = supabase_backend.list_meta_ad_insights_age_gender(date_range=selected_range)
    platform_rows = supabase_backend.list_meta_ad_insights_platform(date_range=selected_range)
    mapping_rows = supabase_backend.list_ads_product_mapping_status(date_range=selected_range, limit=500)
    product_opportunities = supabase_backend.list_product_opportunities_from_ads(date_range=selected_range)
    summary = _summary(insight_rows)
    ad_rows = _aggregate_by_ad(insight_rows)
    st.caption(f"Showing Meta-attributed data for {selected_range}.")

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

    (
        war_room_tab,
        table_tab,
        demographics_tab,
        creative_intel_tab,
        mapping_tab,
        chatgpt_tab,
    ) = st.tabs(
        [
            "War Room",
            "Meta Ads Table",
            "Demographics",
            "Creative Intelligence",
            "Product Mapping",
            "ChatGPT Pack",
        ]
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
                "Meta revenue is platform attribution. Shopify/Supabase sales are actual product-level sales and may not be exact ad attribution until UTM/ad ID matching is added."
            )
            product_rows = _opportunity_table_rows(product_opportunities)
            if product_rows:
                st.dataframe(product_rows[:500], hide_index=True, use_container_width=True, height=420)
            else:
                ui_styles.empty_state("Map ads to products to unlock product-level opportunities.")

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
                file_name=f"sports_cave_meta_ads_{_date_range_slug(selected_range)}.csv",
                mime="text/csv",
                use_container_width=True,
            )
        else:
            ui_styles.empty_state(_empty_performance_message(counts) if not insight_rows else "No stored Meta rows match these filters.")

    with demographics_tab:
        _section("Demographics")
        report_view = st.radio(
            "Report",
            ["Country / Location", "Age / Gender", "Platform / Placement"],
            horizontal=True,
            label_visibility="collapsed",
        )
        active_rows = country_rows
        group_keys = ["country"]
        empty_message = "No stored rows for this report yet. Click Sync Demographics for this date range."
        if report_view == "Age / Gender":
            active_rows = demographic_rows
            group_keys = ["age", "gender"]
        elif report_view == "Platform / Placement":
            active_rows = platform_rows
            group_keys = ["publisher_platform", "platform_position"]
            empty_message = "No stored rows for this report yet. Click Sync Platform for this date range."

        demo_filter_cols = st.columns([1.2, 1.2, 0.8])
        campaign_options = ["All"] + sorted({row.get("campaign_name") for row in active_rows if row.get("campaign_name")})
        selected_campaign = demo_filter_cols[0].selectbox("Campaign", campaign_options, key=f"demo-campaign-{report_view}")
        product_query = demo_filter_cols[1].text_input("Product / mapping", key=f"demo-product-{report_view}")
        min_spend = demo_filter_cols[2].number_input("Min spend", min_value=0.0, value=0.0, step=10.0, key=f"demo-min-spend-{report_view}")
        filtered_demo_rows = []
        query = str(product_query or "").strip().lower()
        for row in active_rows:
            if selected_campaign != "All" and row.get("campaign_name") != selected_campaign:
                continue
            if _number(row.get("spend")) < min_spend:
                continue
            product_text = " ".join(str(row.get(key) or "") for key in ("product_handle", "product_title", "sport", "country_focus")).lower()
            if query and query not in product_text:
                continue
            filtered_demo_rows.append(row)
        _compact_table(_aggregate_group(filtered_demo_rows, group_keys), height=430, empty_message=empty_message)

        if report_view == "Country / Location" and filtered_demo_rows:
            _section("Country Creative Signals")
            strong_country_ads = sorted(filtered_demo_rows, key=lambda row: (_number(row.get("roas")), _number(row.get("purchase_value"))), reverse=True)[:12]
            _compact_table(
                [
                    {
                        "Country": row.get("country") or "Unknown",
                        "Ad": row.get("ad_name"),
                        "Campaign": row.get("campaign_name"),
                        "Spend": _money(row.get("spend")),
                        "Purchases": f"{_number(row.get('purchases')):,.0f}",
                        "Revenue": _money(row.get("purchase_value")),
                        "ROAS": _ratio(row.get("roas")),
                        "CTR": _pct(row.get("ctr")),
                    }
                    for row in strong_country_ads
                ],
                height=320,
            )

    with creative_intel_tab:
        _section("Creative Intelligence")
        if not ad_rows:
            ui_styles.empty_state("Sync base Meta performance to see creative copy, tags, and winner patterns.")
        else:
            filter_cols = st.columns([1, 1, 1, 1, 1, 0.7])
            country_options = ["All"] + sorted({value for row in ad_rows for value in (row.get("country"), row.get("country_focus")) if value and value != "All"})
            campaign_options = ["All"] + sorted({row.get("campaign") for row in ad_rows if row.get("campaign")})
            product_options = ["All"] + sorted({row.get("product_title") or row.get("product_handle") or "Untagged" for row in ad_rows})
            format_options = ["All"] + sorted({row.get("creative_format") or "unknown" for row in ad_rows})
            action_options = ["All"] + sorted({row.get("action_label") for row in ad_rows if row.get("action_label")})
            creative_country = filter_cols[0].selectbox("Country", country_options, key="creative-country-filter")
            creative_campaign = filter_cols[1].selectbox("Campaign", campaign_options, key="creative-campaign-filter")
            creative_product = filter_cols[2].selectbox("Product", product_options, key="creative-product-filter")
            creative_format = filter_cols[3].selectbox("Format", format_options, key="creative-format-filter")
            creative_action = filter_cols[4].selectbox("Action", action_options, key="creative-action-filter")
            creative_min_spend = filter_cols[5].number_input("Min spend", min_value=0.0, value=0.0, step=10.0, key="creative-min-spend")
            creative_rows = _filter_creative_rows(
                ad_rows,
                creative_country,
                creative_campaign,
                creative_product,
                creative_format,
                creative_action,
                creative_min_spend,
            )
            st.dataframe(_creative_intelligence_table(creative_rows)[:500], hide_index=True, use_container_width=True, height=500)
            report_left, report_right = st.columns(2)
            with report_left:
                _section("Best Primary Text")
                _compact_table(_group_creative_report(creative_rows, "primary_text")[:10], height=300)
                _section("Best Creative Format")
                _compact_table(_group_creative_report(creative_rows, "creative_format")[:10], height=260)
            with report_right:
                _section("Best Headlines")
                _compact_table(_group_creative_report(creative_rows, "headline")[:10], height=300)
                _section("Weak Copy Needing Refresh")
                weak_rows = [
                    {
                        "Ad": row.get("ad"),
                        "Primary text": row.get("primary_text") or "",
                        "Headline": row.get("headline") or "",
                        "Spend": _money(row.get("spend")),
                        "CTR": _pct(row.get("ctr")),
                        "ROAS": _ratio(row.get("roas")),
                        "Action": row.get("action_label"),
                    }
                    for row in creative_rows
                    if row.get("action_label") in {"Refresh creative", "Kill candidate", "Landing page/product issue"}
                ][:10]
                _compact_table(weak_rows, height=260)

    with mapping_tab:
        _section("Product Mapping")
        st.caption("Link Meta ads to real Sports Cave products. Suggestions are not confirmed until saved.")
        if not mapping_rows:
            ui_styles.empty_state("No Meta ads found in Supabase yet. Sync Meta data manually first.")
        else:
            mapping_summary = _mapping_summary(mapping_rows)
            ui_styles.metric_strip(
                [
                    ("Total ads", mapping_summary["total"]),
                    ("Confirmed", mapping_summary["confirmed"]),
                    ("Suggested", mapping_summary["suggested"]),
                    ("Needs review", mapping_summary["needs_review"]),
                    ("Unmapped", mapping_summary["unmapped"]),
                ]
            )
            action_cols = st.columns([1, 1.2, 1])
            if action_cols[0].button("Generate suggestions", use_container_width=True):
                result = supabase_backend.suggest_ads_product_mappings(limit=500)
                st.success(f"Generated {result.get('suggested', 0)} product mapping suggestions. Review before confirming.")
                st.rerun()
            action_cols[1].caption("Suggestions use ad/campaign names plus Edition Ops and Supabase order product data.")

            filter_cols = st.columns([1, 1.1, 1.1, 0.7, 1.2])
            status_filter = filter_cols[0].selectbox("Mapping status", MAPPING_STATUS_OPTIONS)
            campaign_options = ["All"] + sorted({row.get("campaign_name") for row in mapping_rows if row.get("campaign_name")})
            campaign_filter = filter_cols[1].selectbox("Campaign", campaign_options, key="mapping-campaign-filter")
            product_filter = filter_cols[2].text_input("Product", key="mapping-product-filter")
            min_spend_filter = filter_cols[3].number_input("Min spend", min_value=0.0, value=0.0, step=10.0, key="mapping-min-spend")
            search_filter = filter_cols[4].text_input("Search ad/campaign", key="mapping-search-filter")
            filtered_mapping_rows = _filter_mapping_rows(
                mapping_rows,
                status_filter,
                campaign_filter,
                product_filter,
                min_spend_filter,
                search_filter,
            )
            table_rows = _mapping_table_rows(filtered_mapping_rows)
            st.caption(f"Showing {min(len(table_rows), 500)} of {len(table_rows)} matching ads.")
            st.dataframe(
                [{key: value for key, value in row.items() if not key.startswith("_")} for row in table_rows[:500]],
                hide_index=True,
                use_container_width=True,
                height=420,
            )

            with st.expander("Manual mapping editor", expanded=False):
                product_candidates = supabase_backend.list_ads_product_candidates(limit=500)
                selectable_rows = filtered_mapping_rows or mapping_rows
                selectable_rows = sorted(
                    selectable_rows,
                    key=lambda row: (str(row.get("mapping_status") or "") == "confirmed", -_number(row.get("spend")), row.get("ad_name") or ""),
                )
                row_options = {f"{row.get('ad_name') or 'Unnamed ad'} ({row.get('ad_id')})": row for row in selectable_rows}
                selected_label = st.selectbox("Selected ad", list(row_options), key="product-mapping-selected-ad")
                selected_ad = row_options[selected_label]
                perf_cols = st.columns(5)
                perf_cols[0].metric("Spend", _money(selected_ad.get("spend")))
                perf_cols[1].metric("Purchases", f"{_number(selected_ad.get('purchases')):,.0f}")
                perf_cols[2].metric("ROAS", _ratio(selected_ad.get("roas")))
                perf_cols[3].metric("CPA", _money(selected_ad.get("cpa")))
                perf_cols[4].metric("CTR", _pct(selected_ad.get("ctr")))
                st.caption(
                    f"Ad: {selected_ad.get('ad_name') or ''} | Campaign: {selected_ad.get('campaign_name') or ''} | "
                    f"Ad set: {selected_ad.get('adset_name') or ''}"
                )
                candidate_options = ["Manual / keep current"]
                candidate_lookup = {}
                for candidate in product_candidates:
                    label = _product_option_label(candidate)
                    candidate_options.append(label)
                    candidate_lookup[label] = candidate
                suggested_handle = selected_ad.get("suggested_product_handle") or selected_ad.get("product_handle") or ""
                default_index = 0
                if suggested_handle:
                    for index, label in enumerate(candidate_options):
                        candidate = candidate_lookup.get(label) or {}
                        if candidate.get("product_handle") == suggested_handle:
                            default_index = index
                            break
                selected_product_label = st.selectbox("Product candidate", candidate_options, index=default_index)
                selected_product = candidate_lookup.get(selected_product_label) or {}
                with st.form("ads-product-mapping-form"):
                    col_a, col_b, col_c = st.columns(3)
                    default_handle = selected_product.get("product_handle") or selected_ad.get("product_handle") or selected_ad.get("suggested_product_handle") or ""
                    default_title = selected_product.get("product_title") or selected_ad.get("product_title") or selected_ad.get("suggested_product_title") or ""
                    product_handle = col_a.text_input("Product handle", value=default_handle)
                    product_title = col_b.text_input("Product title", value=default_title)
                    sport = col_c.text_input("Sport", value=selected_ad.get("sport") or "")
                    country_focus = col_a.text_input("Country focus", value=selected_ad.get("country_focus") or "")
                    mockup_type = col_b.text_input("Mockup type", value=selected_ad.get("mockup_type") or "")
                    room_type = col_c.text_input("Room type", value=selected_ad.get("room_type") or "")
                    ad_angle = col_a.text_input("Ad angle", value=selected_ad.get("ad_angle") or "")
                    hook_style = col_b.text_input("Hook style", value=selected_ad.get("hook_style") or "")
                    creative_format = col_c.text_input("Creative format", value=selected_ad.get("creative_format") or "")
                    funnel_stage = col_a.text_input("Funnel stage", value=selected_ad.get("funnel_stage") or "")
                    notes = st.text_area("Notes", value=selected_ad.get("notes") or "", height=80)
                    action_a, action_b, action_c = st.columns(3)
                    save_confirmed = action_a.form_submit_button("Confirm selected mapping", use_container_width=True)
                    save_review = action_b.form_submit_button("Mark needs review", use_container_width=True)
                    clear_mapping = action_c.form_submit_button("Clear mapping", use_container_width=True)
                    if save_confirmed or save_review or clear_mapping:
                        status = "confirmed" if save_confirmed else ("needs_review" if save_review else "unmapped")
                        supabase_backend.upsert_ads_creative_tag(
                            {
                                "ad_id": selected_ad.get("ad_id"),
                                "creative_id": selected_ad.get("creative_id"),
                                "product_handle": "" if clear_mapping else product_handle,
                                "product_title": "" if clear_mapping else product_title,
                                "sport": sport,
                                "country_focus": country_focus,
                                "mockup_type": mockup_type,
                                "room_type": room_type,
                                "ad_angle": ad_angle,
                                "hook_style": hook_style,
                                "creative_format": creative_format,
                                "funnel_stage": funnel_stage,
                                "notes": notes,
                                "mapping_status": status,
                                "suggested_product_handle": "" if clear_mapping else selected_ad.get("suggested_product_handle"),
                                "suggested_product_title": "" if clear_mapping else selected_ad.get("suggested_product_title"),
                                "suggestion_confidence": 0 if clear_mapping else selected_ad.get("suggestion_confidence"),
                                "suggestion_reason": "" if clear_mapping else selected_ad.get("suggestion_reason"),
                            }
                        )
                        st.success("Product mapping saved.")
                        st.rerun()

    with chatgpt_tab:
        _section("ChatGPT Analysis Pack")
        template = st.selectbox(
            "Template",
            [
                "Daily Ads Review",
                "Creative Pattern Finder",
                "Country Creative Report",
                "Demographic Opportunity Report",
                "Platform Placement Report",
                "New Ad Copy Generator",
                "New Image/Mockup Brief Generator",
                "Loser Diagnosis",
                "Product Scaling Plan",
                "Product Tagging Review",
                "New Creative Based on Product Winners",
                "Country/Product Creative Plan",
            ],
        )
        prompt_text = _prompt_for(
            template,
            selected_range,
            summary,
            ad_rows,
            country_rows=country_rows,
            demographic_rows=demographic_rows,
            platform_rows=platform_rows,
            mapping_rows=mapping_rows,
            product_opportunities=product_opportunities,
        )
        st.text_area("Copyable ChatGPT prompt/data pack", value=prompt_text, height=360)
        st.download_button(
            "Download ChatGPT Pack",
            data=prompt_text.encode("utf-8"),
            file_name=f"sports_cave_{template.lower().replace(' ', '_')}_{_date_range_slug(selected_range)}.txt",
            mime="text/plain",
            use_container_width=True,
        )
