"""Small permission-scoped navigation index. Metadata only; no page imports or I/O."""
from functools import lru_cache

import os_accounts


ALIASES = {
    "crm_customers_view": ("crm", "customers", "customer intelligence"),
    "crm_segments_view": ("segments", "audiences"),
    "crm_automations_manage": ("automations", "marketing automation"),
    "crm_campaigns_manage": ("campaigns", "marketing campaigns"),
    "crm_templates_manage": ("templates", "marketing templates"),
    "crm_reports_view": ("marketing reports", "crm reports"),
    "dashboard": ("home", "dashboard"),
    "orders": ("order", "purchases"),
    "prodigi": ("fulfil", "fulfillment", "prodigi", "shipping"),
    "edition_ops": ("edition", "limited edition", "edition number", "collector number"),
    "mockups": ("mockup",),
    "product_uploads": ("upload", "product upload", "shopify product", "publish product"),
    "design_studio": ("design",),
    "ads": ("meta", "facebook ads", "campaign", "creative"),
    "ads_meta_review": ("meta review", "meta intelligence"),
    "ads_creative_refresh": ("creative refresh", "refresh creative"),
    "analytics": ("ga4", "google analytics", "traffic"),
    "seo": ("search console", "gsc", "organic"),
    "email": ("mail", "inbox", "support email", "reply"),
    "accounts_access": ("users", "staff", "permissions", "roles", "accounts"),
    "va_training": ("training", "staff training"),
}

# These features have no stable section deep link; route to their existing parent.
FEATURES = (
    ("crm_abandoned", "Abandoned Checkout", "CRM & Marketing · Automations", "crm_automations_manage", ("abandoned cart", "checkout recovery"), ("automation",), "Tool"),
    ("crm_welcome", "Welcome Series", "CRM & Marketing · Automations", "crm_automations_manage", ("welcome",), ("automation",), "Tool"),
    ("email_settings", "Email Settings", "Signatures & mailbox settings", "email", ("mail settings",), ("email", "signature"), "Setting"),
    ("email_support", "Customer Support", "Email · shared customer inbox", "email", ("customer support", "email support"), ("email", "support"), "Tool"),
    ("email_signatures", "Signatures", "Email Settings · Nathan, Maria & Company Default", "email", ("signature", "email signature"), ("email", "settings"), "Setting"),
    ("certificates", "Certificates", "Edition Ops · certificates", "edition_ops", ("certificate",), ("edition",), "Tool"),
    ("order_certificates", "Orders — Certificate status", "Orders · certificate status", "orders", (), ("certificate", "certificates"), "Tool"),
    ("email_permissions", "Accounts & Access — Email permission", "Accounts & Access · page permissions", "accounts_access", (), ("email", "permission"), "Setting"),
)


@lru_cache(maxsize=64)
def _index(allowed_routes, can_view_activity):
    allowed = set(allowed_routes)
    results = []
    for page in os_accounts.PAGE_REGISTRY:
        if page["route"] not in allowed:
            continue
        key = page["key"]
        parent = os_accounts.PAGE_BY_KEY.get(page.get("parent_key"), {})
        subtitle = "Customer Support" if key == "email" else parent.get("label", "Application page")
        results.append(dict(id=key, title=page["label"], subtitle=subtitle,
            route_key=key, group="Pages", query="", kind="Page", icon="mail" if key == "email" else "chevron",
            aliases=list(ALIASES.get(key, ())), keywords=[page["route"], subtitle], priority=0))
    for key,title,subtitle,parent,aliases,keywords,kind in FEATURES:
        if os_accounts.PAGE_BY_KEY[parent]["route"] in allowed:
            results.append(dict(id=key,title=title,subtitle=subtitle,route_key=parent,
                group="Pages",query="",kind=kind,icon="settings" if kind == "Setting" else "chevron",
                aliases=list(aliases),keywords=list(keywords),priority=10))
    if can_view_activity and "Dashboard" in allowed:
        results.append(dict(id="activity",title="Activity Log",subtitle="Home activity history",
            route_key="dashboard",group="Pages",query="",kind="Tool",icon="chevron",
            aliases=["audit", "history", "events"],keywords=[],priority=10))
    return tuple(results)


def build_app_index(allowed_routes, *, can_view_activity=False):
    # Return independent JSON-ready values; callers cannot mutate the cached registry.
    return [dict(row, aliases=list(row["aliases"]), keywords=list(row["keywords"]))
            for row in _index(tuple(sorted(set(allowed_routes))), bool(can_view_activity))]
