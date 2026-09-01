from __future__ import annotations

from collections import defaultdict

import streamlit as st

from meta_ads_client import (
    MetaAdsApiError,
    fetch_meta_account,
    fetch_meta_ad_insights_summary,
    fetch_meta_ads,
    fetch_meta_adsets,
    fetch_meta_campaigns,
)


PURCHASE_ACTIONS = {
    "purchase", "offsite_conversion.fb_pixel_purchase", "omni_purchase",
    "web_in_store_purchase", "onsite_web_purchase",
}
ADD_TO_CART_ACTIONS = {
    "add_to_cart", "offsite_conversion.fb_pixel_add_to_cart", "omni_add_to_cart",
}
CHECKOUT_ACTIONS = {
    "initiate_checkout", "offsite_conversion.fb_pixel_initiate_checkout",
    "omni_initiated_checkout",
}


def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _action_total(rows, action_types, *, field="actions"):
    total = 0.0
    for row in rows:
        for action in row.get(field) or ():
            if str(action.get("action_type") or "") in action_types:
                total += _number(action.get("value"))
    return total


def aggregate_ad_metrics(rows):
    grouped = defaultdict(list)
    for row in rows:
        if row.get("ad_id"):
            grouped[str(row["ad_id"])].append(dict(row))
    metrics = {}
    for ad_id, ad_rows in grouped.items():
        spend = sum(_number(row.get("spend")) for row in ad_rows)
        impressions = sum(_number(row.get("impressions")) for row in ad_rows)
        reach = sum(_number(row.get("reach")) for row in ad_rows)
        clicks = sum(_number(row.get("inline_link_clicks") or row.get("clicks")) for row in ad_rows)
        purchases = _action_total(ad_rows, PURCHASE_ACTIONS)
        purchase_value = _action_total(ad_rows, PURCHASE_ACTIONS, field="action_values")
        metrics[ad_id] = {
            "spend": spend,
            "impressions": impressions,
            "reach": reach,
            "frequency": impressions / reach if reach else 0.0,
            "clicks": clicks,
            "ctr": clicks / impressions * 100 if impressions else 0.0,
            "cpc": spend / clicks if clicks else 0.0,
            "cpm": spend / impressions * 1000 if impressions else 0.0,
            "purchases": purchases,
            "cpa": spend / purchases if purchases else 0.0,
            "purchase_value": purchase_value,
            "roas": purchase_value / spend if spend else 0.0,
            "add_to_cart": _action_total(ad_rows, ADD_TO_CART_ACTIONS),
            "checkout": _action_total(ad_rows, CHECKOUT_ACTIONS),
        }
    return metrics


@st.cache_data(ttl=300, show_spinner=False)
def _load_review(days):
    return {
        "account": dict(fetch_meta_account() or {}),
        "campaigns": tuple(dict(row) for row in fetch_meta_campaigns().get("rows") or ()),
        "adsets": tuple(dict(row) for row in fetch_meta_adsets().get("rows") or ()),
        "ads": tuple(dict(row) for row in fetch_meta_ads().get("rows") or ()),
        "metrics": aggregate_ad_metrics(
            tuple(fetch_meta_ad_insights_summary(days=days).get("rows") or ())
        ),
    }


def _status(row):
    return str(row.get("effective_status") or row.get("status") or "Unknown").replace("_", " ").title()


def _label(row):
    return f"{row.get('name') or row.get('id')} — {_status(row)}"


def _metric(label, value, *, currency=False, suffix=""):
    if currency:
        rendered = f"${_number(value):,.2f}"
    elif suffix:
        rendered = f"{_number(value):,.2f}{suffix}"
    else:
        rendered = f"{_number(value):,.0f}"
    st.metric(label, rendered)


def render_page():
    st.title("Meta Review")
    st.caption("Read-only campaign → ad set → ad review. This page never changes Meta objects.")

    controls = st.columns([2, 1, 5])
    days = controls[0].selectbox("Range", (7, 14, 30), index=2, format_func=lambda value: f"Last {value} days")
    if controls[1].button("Refresh Meta", use_container_width=True):
        _load_review.clear()
        st.rerun()
    try:
        data = _load_review(days)
    except MetaAdsApiError as error:
        st.error(f"Meta review is unavailable — {error}")
        return

    account = data["account"]
    st.caption(
        f"{account.get('name') or 'Meta ad account'} · "
        f"{account.get('currency') or 'currency unavailable'} · {_status(account)}"
    )
    campaigns = data["campaigns"]
    campaign_by_id = {str(row.get("id")): row for row in campaigns if row.get("id")}
    if not campaign_by_id:
        st.info("No campaigns are available to this Meta token.")
        return

    selectors = st.columns(3)
    campaign_id = selectors[0].selectbox(
        "Campaign", tuple(campaign_by_id), format_func=lambda value: _label(campaign_by_id[value])
    )
    adsets = tuple(row for row in data["adsets"] if str(row.get("campaign_id") or "") == campaign_id)
    adset_by_id = {str(row.get("id")): row for row in adsets if row.get("id")}
    adset_id = selectors[1].selectbox(
        "Ad set", tuple(adset_by_id),
        format_func=lambda value: _label(adset_by_id[value]), disabled=not adset_by_id,
    ) if adset_by_id else ""
    ads = tuple(row for row in data["ads"] if str(row.get("adset_id") or "") == adset_id)
    ad_by_id = {str(row.get("id")): row for row in ads if row.get("id")}
    ad_id = selectors[2].selectbox(
        "Ad", tuple(ad_by_id), format_func=lambda value: _label(ad_by_id[value]), disabled=not ad_by_id,
    ) if ad_by_id else ""
    if not adset_id:
        st.info("This campaign has no readable ad sets.")
        return
    if not ad_id:
        st.info("This ad set has no readable ads.")
        return

    ad = ad_by_id[ad_id]
    creative = dict(ad.get("creative") or {})
    detail, preview = st.columns([3, 1])
    with detail:
        st.subheader(str(ad.get("name") or "Ad"))
        st.caption(
            f"Campaign: {campaign_by_id[campaign_id].get('name') or campaign_id}  \n"
            f"Ad set: {adset_by_id[adset_id].get('name') or adset_id}  \n"
            f"Status: **{_status(ad)}** · Ad ID: `{ad_id}` · Creative ID: `{creative.get('id') or ''}`"
        )
    thumbnail = str(creative.get("thumbnail_url") or "")
    with preview:
        if thumbnail:
            st.image(thumbnail, caption="Creative thumbnail", use_container_width=True)
        else:
            st.caption("Creative thumbnail unavailable")

    values = dict(data["metrics"].get(ad_id) or {})
    first = st.columns(7)
    with first[0]: _metric("Spend", values.get("spend"), currency=True)
    with first[1]: _metric("Impressions", values.get("impressions"))
    with first[2]: _metric("Reach", values.get("reach"))
    with first[3]: _metric("Frequency", values.get("frequency"), suffix="×")
    with first[4]: _metric("Link clicks", values.get("clicks"))
    with first[5]: _metric("Link CTR", values.get("ctr"), suffix="%")
    with first[6]: _metric("CPM", values.get("cpm"), currency=True)
    second = st.columns(7)
    with second[0]: _metric("CPC", values.get("cpc"), currency=True)
    with second[1]: _metric("Purchases", values.get("purchases"))
    with second[2]: _metric("CPA", values.get("cpa"), currency=True)
    with second[3]: _metric("Purchase value", values.get("purchase_value"), currency=True)
    with second[4]: _metric("ROAS", values.get("roas"), suffix="×")
    with second[5]: _metric("Add to cart", values.get("add_to_cart"))
    with second[6]: _metric("Initiate checkout", values.get("checkout"))

    if not values:
        st.caption("No delivery metrics were returned for this ad and date range.")
