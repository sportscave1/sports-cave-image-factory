"""Compact recommendation rows and their ChatGPT project handoff."""

from functools import lru_cache
from html import escape
from pathlib import Path
import re
from urllib.parse import urlencode

from home_brief_calendar import MARKETS, PRODUCT_QUERY, calendar_rows, product_handle

PROJECT_URL = "https://chatgpt.com/g/g-p-6a1e449948e881919c1e345006d63654/project"
TEMPLATE = Path(__file__).parent / "components" / "morning_brief_actions.html"


META_AD_HEADING = re.compile(r"^(?:recommended|suggested)\b.*\bmeta\b.*\bad\b", re.I)
META_AD_COPY = re.compile(r"^(?:headline|primary text|description|cta|call to action)\s*:", re.I)


def _story_without_meta_ad(text):
    lines = []
    ad = False
    for line in text.splitlines():
        label = line.strip().lstrip("#*- ").replace("*", "").replace("\\:", ":")
        if META_AD_HEADING.match(label):
            ad = True
            continue
        if ad and (not label or META_AD_COPY.match(label) or label.startswith(("“", '"', "‘"))):
            continue
        ad = False
        lines.append(line)
    return "\n".join(lines).strip()


def _prompt(title, story):
    context = _story_without_meta_ad(story)
    return (
        f"Sports Cave event: {title}\n\n{context}\n\n"
        "List the best possible images. Show the photos in this chat first. Use web image search to "
        "find 4–8 of the best images for this design.\n\n"
        "Step 1. Do this fully first. Once there is a carousel of images, generate the design based "
        "on the photos you showed. Choose the strongest usable photo as the hero, and use a supporting "
        "photo from the same shortlist only if it improves the composition. Place the actual selected "
        "image in the artwork so the athletes and sporting moment dominate the composition. Preserve "
        "recognisable faces, uniforms, and event details. Follow the project’s Collector Series "
        "references for typography, colour, depth, and visual hierarchy. Refer to the project "
        "instructions in Sports Cave Designs for how Sports Cave designs are structured.\n\n"
        "Step 2. Once the images are in the carousel, inspect designs-canvas.psd in Dropbox for the "
        "exact pixel dimensions, orientation, safe margins, and limited-edition badge. Preserve the "
        "original limited-edition badge and edition-number layer.\n\n"
        "Step 3. Generate this design now as a 10/10 Sports Cave–styled, realistic collector edition "
        "that is highly appealing and could become our next top seller.\n\n"
        "Step 4. Find a verified example of the featured person’s signature online. Add it as a "
        "separate layer where it fits naturally with the artwork and typography. Keep the original "
        "letterforms and strokes. Refine the placement, scale, and ink finish for a premium "
        "collector look. Skip this step if you can’t verify the signature.\n\n"
        "Step 5. Use the image generation tool to turn the base composition into a finished Sports "
        "Cave Collector Series artwork. Build a cohesive vintage background with subtle textures "
        "and details from the sport or venue and restrained team colours. Integrate the original "
        "hero photo through matching light, colour, and depth while preserving the athlete’s face, "
        "anatomy, pose, and uniform. Carry any verified signature layer into the generated design "
        "and show the finished artwork in the chat before placing it on the PSD.\n\n"
        "Step 6. Inspect the generated artwork against the original photo. Check that the person "
        "looks realistic and that their face, body, and uniform are free of unintended cropping, "
        "blending, or AI distortion. If you find a problem, regenerate or correct the design "
        "and repeat the check.\n\n"
        "Step 7. Place the final generated artwork on a copy of designs-canvas.psd. Name the PSD using "
        "the intended online product title and upload it to Dropbox at /Sportscave Team Folder/"
        "02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/99_PSD_NEEDS_REVIEW_DO_NOT_DELETE/."
    )


@lru_cache(maxsize=1)
def _template():
    return TEMPLATE.read_text(encoding="utf-8")


def article_html(item, *, heading=None, allow_ads=False):
    title = " ".join(item["title"].split())
    prompt = escape(_prompt(title, item["recommendation"]), quote=True).replace("\n", "&#10;")
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
        '<div class="sc-brief-body">'
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
        f'<div class="sc-cal-wrap" data-calendar="{market}" role="region" '
        f'aria-label="{market} sports calendar" tabindex="0"{hidden}><table>'
        '<thead><tr><th>Sport</th><th>Status</th><th>Dates / season</th><th>Timing</th><th>News / updates</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def brief_html(edition, *, editions, today, allow_ads=False):
    rows = "".join(
        article_html(item, heading=f'{rank}. {item["title"]}', allow_ads=allow_ads)
        for rank, item in enumerate((edition or {}).get("recommendations", ()), 1)
    )
    full_brief = (edition or {}).get("full_brief")
    if full_brief:
        rows += (
            '<button type="button" class="sc-full-brief" aria-haspopup="dialog">Read the full Morning Brief</button>'
            '<dialog class="sc-cal-dialog sc-sports-full" aria-label="Full Sports Morning Brief">'
            '<header><h3>Full Morning Brief</h3><form method="dialog"><button>Close</button></form></header>'
            f'<div class="sc-full-brief-text">{escape(full_brief)}</div></dialog>'
        )
    tables = "".join(_market_table(editions, market, today) for market in MARKETS)
    stories = f'<section class="sc-sports-stories" aria-label="Sports opportunities">{rows}</section>' if rows else ""
    return _template().replace("<!-- CALENDARS -->", tables).replace("<!-- RECOMMENDATIONS -->", stories)
