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
        "Step 1. Read SPORTS-CAVE-LIMITED-EDITION-COLLECTOR-DESIGNS.txt in Sports Cave Designs "
        "before generating. Follow it for Collector Series typography, colour, and composition. "
        "If it’s unavailable, say so and use the project instructions you can access. Choose "
        "the strongest usable hero photo from the carousel. Extract only the athlete, driver, "
        "or other featured subject as a clean cutout, including essential equipment or the "
        "vehicle where it matters. Remove the original background completely. Keep the subject’s "
        "real face, expression, pose, anatomy, uniform, lettering, and equipment intact. Add a "
        "supporting cutout only if it strengthens the story. Find a verified signature if "
        "available. Preserve its original strokes and use placement, scale, and ink finish "
        "to integrate it with the typography.\n\n"
        "Step 2. Once the cutout and signature are ready, use the image generation tool once "
        "to create one finished Sports Cave Collector Series artwork. Use the cutout and verified "
        "signature as inputs. Build an original vintage setting around the subject with subtle "
        "sport, venue, or team details, restrained team colours, and an even border. Keep the "
        "actual photographic subject as the hero; never use the whole source photo or redraw "
        "the face, kit, or signature. If generation alters those details or omits an asset, "
        "composite the original cutout and signature into the result in one finishing pass "
        "outside Photoshop. The first artwork you show must already include the subject and "
        "the signature when verified. Don’t show a background or layout on its own.\n\n"
        "Target 2835 × 2004 pixels, landscape (about 1.415:1). If the exact size is unavailable, "
        "use the closest landscape ratio. Build the design inside the centred 1.415:1 crop area, "
        "with an even border inset on all four sides and extra background beyond that area. "
        "On the target canvas, reserve x=212, y=1681, width=577, height=188 for the official badge. "
        "Leave it as clean background or keep any placeholder entirely within that footprint. "
        "Check the finished image once against the hero photo before showing it. Fix distorted "
        "features, kit lettering, or unintended cropping with the original cutout rather than "
        "running another generation.\n\n"
        "Step 3. Only now open a copy of designs-canvas.psd in Photoshop. Place the finished image "
        "as one artwork layer. Scale proportionally and trim only the extra background as needed "
        "to fill the canvas, keeping the border even. Keep the official SC_EDITION_PLAQUE and "
        "editable SC_EDITION_NUMBER above the artwork at their template positions so the official "
        "badge fully covers any placeholder. Save the layered PSD using the intended online "
        "product title and upload it to Dropbox at /Sportscave Team Folder/"
        "02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/99_PSD_NEEDS_REVIEW_DO_NOT_DELETE/. "
        "Confirm the saved PSD is in that folder and share its link or exact path. If Photoshop "
        "or Dropbox is unavailable, provide the finished full-resolution artwork for handoff "
        "and say which steps are still pending."
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
        if (colon and len(lead) < 42) or (line.strip().endswith(":") and len(line.strip()) < 42):
            label = lead if colon else line.strip()[:-1]
            paragraphs.append(f'<p class="sc-brief-key"><strong>{escape(label)}:</strong> {escape(detail)}</p>')
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
