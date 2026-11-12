"""Compact recommendation rows and their ChatGPT project handoff."""

from functools import lru_cache
from html import escape
from pathlib import Path
from urllib.parse import urlencode

from home_brief_calendar import MARKETS, PRODUCT_QUERY, calendar_rows, product_handle

PROJECT_URL = "https://chatgpt.com/g/g-p-6a1e449948e881919c1e345006d63654/project"
TEMPLATE = Path(__file__).parent / "components" / "morning_brief_actions.html"


def _prompt(event):
    return (
        f"Sports Cave event: {event}\n\n"
        "Deliver one finished, photo-led Sports Cave Collector Series wall-art print. Follow the "
        "Sports Cave Designs project instructions. The limited-edition badge is a small brand element "
        "on the artwork. Do not create a certificate, authenticity card, mockup, or empty photo frame.\n\n"
        "Show the photos in this chat first. Use web image search to find 4–8 authentic photos "
        "from Getty Images, official event or league galleries, and other credible sources. Display "
        "the actual photo previews in a native image carousel. If this chat cannot render a carousel, "
        "show the actual previews in an inline gallery or individually. A table of links alone does "
        "not complete this step. Under the previews, add the source link, photographer or agency "
        "credit, what each image shows, and whether its commercial use is verified. Label archival "
        "photos by their actual match and date. If the event is upcoming, use authentic lead-up or "
        "rivalry photos and frame the design as a preview.\n\n"
        "Create the print from the photos you showed. Choose the strongest usable photo as the "
        "hero, and use a supporting photo from the same shortlist only if it improves the composition. "
        "Place the actual selected image in the artwork so the athletes and sporting moment dominate "
        "the composition. Preserve recognisable faces, uniforms, and event details. Follow the "
        "project's Collector Series references for typography, colour, depth, and visual hierarchy. "
        "Use photos cleared for the intended wall-art reproduction and compositing.\n\n"
        "Match the production canvas. Inspect designs-canvas.psd in Dropbox for the exact pixel "
        "dimensions, orientation, safe margins and badge position. Preserve the original limited-edition "
        "badge and edition-number layer. Build the print at the PSD's exact size so it fits without "
        "cropping, stretching, or distortion. Display the finished artwork in chat and attach a "
        "full-resolution export. Identify the photo or photos used. If the PSD is inaccessible, "
        "show the image shortlist and ask for the file before claiming a production fit.\n\n"
        "Step 1. List all shortlisted images and display their actual previews in chat.\n"
        "Step 2. Start generating a 10/10 Sports Cave–styled limited-edition design using the "
        "selected photos. Make it realistic, premium and worthy of a collector."
    )


@lru_cache(maxsize=1)
def _template():
    return TEMPLATE.read_text(encoding="utf-8")


def article_html(item, *, heading=None, allow_ads=False):
    title = " ".join(item["title"].split())
    prompt = escape(_prompt(title), quote=True).replace("\n", "&#10;")
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
        f'<div class="sc-brief-body"><h4>{escape(title)}</h4>'
        f'<div class="sc-brief-copy">{"".join(paragraphs)}</div>'
        f'<div class="sc-brief-links">{links}</div></div></details>'
        f'<div class="sc-brief-actions">{actions}</div></article>'
    )


def _date_label(day):
    return day.strftime("%d %b %Y").lstrip("0")


def _market_table(editions, market, today):
    rows = []
    for sport, event, has_news in calendar_rows(editions, market, today):
        if event:
            state = event.status(today)
            if state == "Upcoming":
                timing = f"Starts in {(event.start - today).days}d"
            elif state == "Live":
                days = (event.end - today).days
                timing = f"Ends in {days}d" if days else "Ends today"
            else:
                timing = f"Ended {(today - event.end).days}d ago"
            dates = _date_label(event.start)
            if event.end != event.start:
                dates += " – " + _date_label(event.end)
            outside_market = market not in event.markets and "ALL" not in event.markets
            if outside_market:
                dates += " · " + " / ".join(event.markets)
            season = (f'<a href="{escape(event.source, quote=True)}" target="_blank" rel="noopener noreferrer">'
                      f'{escape(event.title)}</a><small>{escape(dates)}</small>')
        else:
            state, timing, season = "TBC", "—", "Dates to be confirmed"
        rows.append(
            f'<tr><th scope="row">{escape(sport)}</th><td><span class="sc-cal-state" data-state="{state.lower()}">{state}</span></td>'
            f'<td>{season}</td><td>{timing}</td><td>'
            f'<button type="button" class="sc-cal-news" data-sport="{escape(sport, quote=True)}" '
            f'data-market="{market}" aria-label="{escape(sport, quote=True)} {market} news and updates">'
            f'{"View updates" if has_news else "History"}</button></td></tr>'
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
