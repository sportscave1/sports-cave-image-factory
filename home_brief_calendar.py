"""Sport, market and date fields used by the ChatGPT calendar and news archive."""

from datetime import date
import re
from urllib.parse import urlsplit

from sports_categories import normalize_sport_category, detect_sport_in_text

MARKETS = ("AUS", "USA", "UK")
MARKET_CODES = {"AUS": "AUS", "AU": "AUS", "AUSTRALIA": "AUS", "USA": "USA",
                "US": "USA", "UK": "UK", "GB": "UK", "CANADA": "CA", "CA": "CA",
                "NZ": "NZ", "ALL": "ALL"}
HISTORY_PREFIX = "home_sports_morning_brief:"
PRODUCT_QUERY = "brief_product"


def iso_day(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Use YYYY-MM-DD for calendar dates.")
    return date.fromisoformat(value)


def article_fields(item):
    # Earlier editions put the sport and markets in the opening text lines.
    opening = " ".join(item["recommendation"].splitlines()[:2])
    sport = normalize_sport_category(item.get("sport"))
    if item.get("sport") and not sport:
        raise ValueError("Use a Sports Cave sport category.")
    sport = sport or detect_sport_in_text(opening) or detect_sport_in_text(item["title"])
    raw_markets = item.get("markets")
    if raw_markets is None:
        raw_markets = re.findall(r"\b(?:AUSTRALIA|AUS|USA|US|UK|CANADA|NZ)\b", opening.upper())
    if not isinstance(raw_markets, list) or len(raw_markets) > 8 or any(
        not isinstance(value, str) or value.upper() not in MARKET_CODES for value in raw_markets
    ):
        raise ValueError("Use recognised market codes for each story.")
    markets = sorted({MARKET_CODES[value.upper()] for value in raw_markets})
    fields = {"sport": sport, "markets": markets}
    if "start_date" in item or "end_date" in item:
        start = iso_day(item.get("start_date"))
        end = iso_day(item.get("end_date", item["start_date"]))
        if end < start:
            raise ValueError("The event end cannot precede its start.")
        fields.update(start_date=start.isoformat(), end_date=end.isoformat())
    return fields


def shop_product_handle(url):
    url = urlsplit(url)
    if url.netloc.casefold() not in {"sportscaveshop.com", "www.sportscaveshop.com",
                                   "sportscave.com.au", "www.sportscave.com.au"}:
        return ""
    match = re.fullmatch(r"/products/([a-z0-9][a-z0-9-]{0,149})/?", url.path)
    return match[1] if match else ""


def product_handle(item):
    if item.get("product_url"):
        return shop_product_handle(item["product_url"])
    handles = {shop_product_handle(link["url"]) for link in item.get("links", ())} - {""}
    return next(iter(handles)) if len(handles) == 1 else ""


def matches_market(article, market):
    return market in article["markets"] or "ALL" in article["markets"]


def calendar_rows(editions, market, today):
    items = {}
    news = set()
    seen = set()
    for edition in editions:
        for item in edition["recommendations"]:
            sport = item["sport"]
            if not sport or not matches_market(item, market):
                continue
            news.add(sport)
            if "start_date" not in item:
                continue
            # The latest dates for an event take precedence over older reports.
            identity = sport, item["title"].casefold()
            if identity in seen:
                continue
            seen.add(identity)
            start = iso_day(item["start_date"])
            end = iso_day(item["end_date"])
            if end >= today:
                items.setdefault(sport, []).append((start > today, start if start > today else end,
                                                    start, end, item["title"]))
    return {sport: min(events) for sport, events in items.items()}, news
