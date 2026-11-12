"""Compact recommendation rows and their ChatGPT project handoff."""

from functools import lru_cache
from html import escape
from pathlib import Path
from urllib.parse import urlencode

from home_brief_calendar import MARKETS, PRODUCT_QUERY, calendar_rows, product_handle
from sports_categories import CANONICAL_SPORT_CATEGORIES

PROJECT_URL = "https://chatgpt.com/g/g-p-6a1e449948e881919c1e345006d63654/project"
TEMPLATE = Path(__file__).parent / "components" / "morning_brief_actions.html"


def _prompt(event):
    return (
        f"Sports Cave event: {event}\n\n"
        "Create the collector design. Follow the Sports Cave Designs project instructions.\n\n"
        "Search the web for the strongest authentic images of this event, including Getty Images, "
        "official event or league galleries, and other relevant sources. Show the best images here "
        "in a carousel when supported, with source links, captions, and why each works. Include Getty "
        "previews where available and identify any licensing restrictions. Use commercially cleared "
        "images in the finished artwork and keep editorial-only images as references.\n\n"
        "Then use the design-canvas PSD in Dropbox as the production reference. Inspect its exact "
        "dimensions, orientation, safe margins and limited-edition badge placement. Use the original "
        "badge and match the canvas so the result drops straight in without cropping, stretching or "
        "distortion. Make the artwork realistic, premium and collector-worthy. If the PSD or cleared "
        "images are unavailable, identify what is needed and prepare a layout for review."
    )


@lru_cache(maxsize=1)
def _template():
    return TEMPLATE.read_text(encoding="utf-8")


def article_html(item, *, heading=None, allow_ads=False):
    title = " ".join(item["title"].split())
    prompt = escape(_prompt(title), quote=True).replace("\\n", "&#10;")
    actions = (
        f'<a href="{PROJECT_URL}" target="_blank" rel="noopener noreferrer" '
        f'data-prompt="{prompt}" title="Open Sports Cave Designs and copy the prompt">Create Design</a>'
    )
    handle = product_handle(item)
    if allow_ads and handle:
        url = "/?" + urlencode({"page": "ads", PRODUCT_QUERY: handle})
        actions += f'<a href="{escape(url, quote=True)}">Create Ad</a>'
    elif allow_ads:
        actions += '<span title="This story does not identify one exact product">Create Ad</span>'
    links = "".join(
        f'<a href="{escape(link["url"], quote=True)}" target="_blank" rel="noopener noreferrer">'
        f'{escape(link["label"])}</a>' for link in item["links"]
    )
    paragraphs = []
    for line in item["recommendation"].splitlines():
        if not line.strip():
            continue
        lead, colon, detail = line.partition(": ")
        if colon and len(lead) < 32:
            paragraphs.append(f"<p><strong>{escape(lead)}:</strong> {escape(detail)}</p>")
        else:
            paragraphs.append(f"<p>{escape(line)}</p>")
    return (
        '<article class="sc-brief-row"><details>'
        f'<summary title="{escape(title, quote=True)}"><span>{escape(heading or title)}</span></summary>'
        f'<div class="sc-brief-body"><h4>{escape(title)}</h4>{"".join(paragraphs)}'
        f'<div class="sc-brief-links">{links}</div></div></details>'
        f'<div class="sc-brief-actions">{actions}</div></article>'
    )


def _date_label(day):
    return day.strftime("%d %b %Y").lstrip("0")


def _market_table(editions, market, today):
    events, news = calendar_rows(editions, market, today)
    rows = []
    for sport in CANONICAL_SPORT_CATEGORIES:
        record = events.get(sport)
        if record:
            upcoming, target, start, end, title = record
            state = "Upcoming" if upcoming else "Live"
            days = (target - today).days
            timing = f"Starts in {days}d" if upcoming else (f"Ends in {days}d" if days else "Ends today")
            dates = _date_label(start)
            if end != start:
                dates += " – " + _date_label(end)
            season = f"{escape(title)}<small>{dates}</small>"
        else:
            state, timing, season = "—", "—", "—"
        rows.append(
            f'<tr><th scope="row">{escape(sport)}</th><td><span class="sc-cal-state">{state}</span></td>'
            f'<td>{season}</td><td>{timing}</td><td>'
            f'<button type="button" class="sc-cal-news" data-sport="{escape(sport, quote=True)}" '
            f'data-market="{market}" aria-label="{escape(sport, quote=True)} {market} news and updates">'
            f'{"View updates" if sport in news else "History"}</button></td></tr>'
        )
    hidden = "" if market == MARKETS[0] else " hidden"
    return (
        f'<div class="sc-cal-wrap" data-calendar="{market}"{hidden}><table>'
        '<thead><tr><th>Sport</th><th>Status</th><th>Dates / season</th><th>Timing</th><th>News / updates</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def brief_html(edition, *, editions, today, allow_ads=False):
    rows = "".join(
        article_html(item, heading=f'{rank}. {item["title"]}', allow_ads=allow_ads)
        for rank, item in enumerate((edition or {}).get("recommendations", ()), 1)
    )
    tables = "".join(_market_table(editions, market, today) for market in MARKETS)
    return _template().replace("<!-- CALENDARS -->", tables).replace("<!-- RECOMMENDATIONS -->", rows)
