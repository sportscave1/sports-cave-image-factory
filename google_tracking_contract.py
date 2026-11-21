"""Paid-Google URL policy; report drift without changing campaigns or consent."""
from urllib.parse import parse_qsl
import re

PAID_TERM_PREFIX = "sc_google_paid_"
ACCOUNT_SUFFIX = (
    "utm_source=google&utm_medium=cpc&utm_campaign={campaignid}&utm_id={campaignid}"
    "&utm_term=sc_google_paid_{campaignid}&sc_channel=google_paid&sc_network={network}"
)
CAMPAIGN_SUFFIX = ACCOUNT_SUFFIX.replace("utm_campaign={campaignid}", "utm_campaign=PM021126")


def paid_term(value):
    value = str(value or "").strip().lower()
    return re.fullmatch(r"sc_google_paid_[1-9][0-9]{0,19}", value) is not None


def health(account, campaign):
    """Return allowlisted booleans only; provider URLs can contain private tokens."""
    suffix = campaign.get("finalUrlSuffix") or account.get("finalUrlSuffix") or ""
    pairs = parse_qsl(suffix, keep_blank_values=True)
    tags = {}
    for name, value in pairs:
        tags.setdefault(name.lower(), []).append(value)
    def exactly(name, value):
        return tags.get(name) == [value]
    campaign_id = str(campaign.get("id") or "")
    id_values = ("{campaignid}", campaign_id) if campaign_id else ("{campaignid}",)
    term_values = [PAID_TERM_PREFIX + value for value in id_values]
    checks = {
        "auto_tagging": account.get("autoTaggingEnabled") is True,
        "paid_source_medium": exactly("utm_source", "google") and exactly("utm_medium", "cpc"),
        "campaign_id": tags.get("utm_id") in [[value] for value in id_values],
        "shopify_paid_marker": tags.get("utm_term") in [[value] for value in term_values],
        "paid_channel_marker": exactly("sc_channel", "google_paid"),
        "unique_parameters": bool(pairs) and all(len(values) == 1 for values in tags.values())
            and not suffix.startswith("?") and "#" not in suffix,
    }
    return {"status": "verified" if all(checks.values()) else "attention",
            "checks": checks, "missing": [name for name, passed in checks.items() if not passed],
            "note": "Observed account/campaign settings only. Ad/asset overrides, consent and future event delivery still require evidence."}
