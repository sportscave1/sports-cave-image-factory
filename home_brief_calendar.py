"""Sport, market and date fields used by the ChatGPT calendar and news archive."""

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from sports_categories import CANONICAL_SPORT_CATEGORIES, normalize_sport_category, detect_sport_in_text

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


SCHEDULE_PATH = Path(__file__).parent / "data" / "home_sports_schedule.json"
MARKET_FOCUS = {
    "AUS": {"AFL", "Cricket", "Rugby League", "Rugby Union", "V8 Supercars", "Motorsport",
            "Formula One", "Horse Racing", "Tennis", "Surfing", "Swimming"},
    "USA": {"Baseball", "NBA", "NFL", "Ice Hockey", "NASCAR", "IndyCar", "Combat", "WWE",
            "Motocross", "Golf"},
    "UK": {"Football", "Darts", "Rugby Union", "Rugby League", "Cricket", "Formula One",
           "Horse Racing", "Road Racing", "Golf", "Tennis"},
}


@dataclass(frozen=True)
class ScheduleEvent:
    sport: str
    markets: tuple[str, ...]
    title: str
    start: date
    end: date
    source: str

    def status(self, today):
        if self.start > today:
            return "Upcoming"
        return "Live" if self.end >= today else "Ended"


@lru_cache(maxsize=1)
def load_schedule():
    data = json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))
    events = []
    for item in data["events"]:
        start, end = iso_day(item["start"]), iso_day(item["end"])
        source = urlsplit(item["source"])
        if (item["sport"] not in CANONICAL_SPORT_CATEGORIES or not item["markets"]
                or not set(item["markets"]).issubset((*MARKETS, "ALL"))
                or start > end or source.scheme != "https" or not source.hostname
                or source.username is not None or source.password is not None):
            raise ValueError(f"Invalid Sports Cave schedule entry: {item['title']}")
        events.append(ScheduleEvent(item["sport"], tuple(item["markets"]), item["title"],
                                    start, end, item["source"]))
    return tuple(events)


def _select_event(events, today):
    live = [event for event in events if event.status(today) == "Live"]
    if live:
        return min(live, key=lambda event: (event.end, event.start, event.title))
    upcoming = [event for event in events if event.start > today]
    if upcoming:
        return min(upcoming, key=lambda event: (event.start, event.end, event.title))
    return max(events, key=lambda event: (event.end, event.start, event.title), default=None)


def _news_scores(editions, market, today):
    scores = {}
    for edition in editions:
        age = (today - iso_day(edition["date"])).days
        for rank, item in enumerate(edition["recommendations"], 1):
            sport = item["sport"]
            if not sport or not matches_market(item, market):
                continue
            # The source brief ranks its recommendations by commercial relevance.
            score = max(0, 44 - 3 * age - 3 * rank) if age >= 0 else 0
            scores[sport] = max(score, scores.get(sport, 0))
    return scores


def calendar_rows(editions, market, today, *, schedule=None):
    schedule = load_schedule() if schedule is None else schedule
    news = _news_scores(editions, market, today)
    rows = []
    for sport in CANONICAL_SPORT_CATEGORIES:
        available = [event for event in schedule if event.sport == sport]
        market_events = [event for event in available if market in event.markets or "ALL" in event.markets]
        event = _select_event(market_events or available, today)
        relevant = bool(market_events) or sport in news
        score = (24 if sport in MARKET_FOCUS[market] else 0) + news.get(sport, 0)
        if market_events and event:
            if event.status(today) == "Live":
                score += 48
            elif event.start > today:
                score += max(0, 30 - (event.start - today).days)
            if market in event.markets:
                score += 12
        rows.append((relevant, score, sport, event, sport in news))
    rows.sort(key=lambda row: (not row[0], -row[1], row[2].casefold()))
    return [(sport, event, has_news) for _, _, sport, event, has_news in rows]
