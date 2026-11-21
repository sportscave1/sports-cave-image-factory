"""Start a new marketing link without inheriting another visit's acquisition IDs."""
from urllib.parse import urlsplit, parse_qsl, urlencode

CLICK_AND_AD_KEYS = {"gclid", "gbraid", "wbraid", "fbclid", "msclkid", "ttclid", "placement", "site_source", "ad_id", "adset_id"}


def clean_destination(url):
    parsed = urlsplit(url)
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    kept = [(k,v) for k,v in pairs if not k.lower().startswith("utm_") and k.lower() not in CLICK_AND_AD_KEYS]
    return parsed._replace(query=urlencode(kept)).geturl() if kept != pairs else url
