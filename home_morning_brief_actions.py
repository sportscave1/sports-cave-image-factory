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
        f"Sports Cave event: {title}\n\n"
        "**MANDATORY EXECUTION ORDER**\n"
        "\n"
        "This task requires **two distinct full-artwork image generations and two confirmed Dropbox "
        "saves**:\n"
        "\n"
        "**Generate first complete artwork → inspect → save first PSD to Dropbox → regenerate the "
        "complete artwork → inspect → overwrite that same Dropbox PSD → verify and display the "
        "final result.**\n"
        "\n"
        "Do not combine, skip or reorder these checkpoints. Saving once at the end does not satisfy "
        "this workflow. Generating only a background and manually placing the athlete over it does "
        "not satisfy the second full-artwork generation.\n"
        "\n"
        "**MANDATORY CONTINUATION AND RECOVERY**\n"
        "\n"
        "Execute the entire workflow autonomously. Do not stop for ordinary design imperfections, "
        "low-resolution search results, unsuccessful generations, missing signatures or a failed "
        "first attempt.\n"
        "\n"
        "**Quality concerns require corrective action.** Search for higher-resolution originals, "
        "inspect the source pages, choose a stronger photograph from the same event, adapt the "
        "composition to the available crop, or regenerate. Do not invent missing anatomy or "
        "quietly substitute another event.\n"
        "\n"
        "**The first Dropbox save is a review checkpoint, not final production approval.** After "
        "generating and inspecting the first complete artwork, save it on a copy of the master PSD "
        "in the specified review folder. Document remaining concerns in a hidden `REVIEW NOTES` "
        "layer. Those concerns must guide the mandatory second full-artwork generation after "
        "Dropbox confirms the first save.\n"
        "\n"
        "Do not demand perfection before the first save. Do not describe a review draft as approved "
        "or print-ready.\n"
        "\n"
        "**After the first save, continue immediately to Step 8 without asking permission.** "
        "Generate the complete artwork again using the first artwork and original photographs, "
        "inspect it, make necessary corrections, and overwrite the same Dropbox PSD. Preserve the "
        "first artwork in the hidden `ORIGINAL EDITABLE ARTWORK` group.\n"
        "\n"
        "**Recover from tool failures.** Retry recoverable failures appropriately and use another "
        "available, authorised method when necessary. If the Dropbox connector cannot overwrite, "
        "attempt the overwrite through the connected Dropbox browser. Do not delete and recreate "
        "the file or use a differently named substitute.\n"
        "\n"
        "**Missing signatures must not stop the artwork.** Complete the required three-source "
        "search. If no usable authentic signature is available, omit it and record the reason; "
        "never invent one.\n"
        "\n"
        "Stop only when a required operation genuinely cannot be performed with available access "
        "and tools, after reasonable alternatives have been attempted. Identify the exact failed "
        "operation, attempts made, saved progress and smallest action needed to resume. Never claim "
        "an unperformed generation, save or overwrite succeeded.\n"
        "\n"
        "**Completion requires:** first complete generation → confirmed first PSD save → second "
        "full-artwork generation → confirmed overwrite of the same PSD and verification.\n"
        "\n"
        f"{context}\n\n"
        "List the best possible images. Show the photos in this chat first. Use web image search to "
        "aim for 4–8 images from the event. If fewer are usable after checking the original source "
        "pages, show the usable photos you found and continue. Focus on photo authenticity, image "
        "quality, and how each photo supports the artwork. I will handle photo licensing "
        "separately. Do not research, assess, or mention photo licensing, commercial-use "
        "permissions, or usage rights.\n\n"
        "Step 1. Choose the strongest usable photo as the hero, and use a supporting photo from "
        "the same shortlist only if it improves the composition. Place the actual selected "
        "image in the artwork so the athletes and sporting moment dominate the composition. Preserve "
        "recognisable faces, uniforms, and event details. Follow the project’s Collector Series "
        "references for typography, colour, depth, and visual hierarchy. Refer to the project "
        "instructions in Sports Cave Designs for how Sports Cave designs are structured.\n\n"
        "Step 2. Inspect designs-canvas.psd in Dropbox for the exact pixel dimensions, orientation, "
        "safe margins, and limited-edition badge. Preserve the "
        "original limited-edition badge and edition-number layer.\n\n"
        "Step 3. Define the composition for a realistic Sports Cave Collector Series design with "
        "a strong focal point and clear visual hierarchy.\n\n"
        "Step 4. For each featured person, search both web and image results. Check at least "
        "three distinct credible sources before skipping a signature. Use a clear, verified "
        "example and place it on a separate layer where it fits naturally with the artwork "
        "and typography. Keep the original letterforms and strokes. Refine the placement, "
        "scale, and ink finish for a premium collector look. If no example is usable, omit the "
        "signature, record the reason in REVIEW NOTES, and continue. Never invent a signature.\n\n"
        "Step 5. Use the image generation tool to generate the first complete Sports Cave "
        "Collector Series artwork. Build a cohesive vintage background with subtle textures "
        "and details from the sport or venue and restrained team colours. Integrate the original "
        "hero photo through matching light, colour, and depth while preserving the athlete’s face, "
        "anatomy, pose, and uniform. Keep any verified signature as a separate asset and show the "
        "first complete artwork in the chat before placing it on the PSD.\n\n"
        "Step 6. Inspect the generated artwork against the original photo. Check that the person "
        "looks realistic and that their face, body, and uniform are free of unintended cropping, "
        "blending, or AI distortion. Make practical corrections and record remaining concerns for "
        "Step 8. Once you have inspected a complete first artwork, proceed to the review save.\n\n"
        "Step 7. Place the first complete artwork on a copy of designs-canvas.psd as a review draft. "
        "Include any verified signatures on separate layers and document remaining concerns in a "
        "hidden REVIEW NOTES layer. Name the PSD using the intended online product title and save "
        "it to Dropbox at /Sportscave Team Folder/"
        "02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/99_PSD_NEEDS_REVIEW_DO_NOT_DELETE/. "
        "Confirm the save and continue immediately to Step 8.\n\n"
        "**STEP 8 — REQUIRED SECOND FULL-ARTWORK GENERATION, AFTER THE FIRST DROPBOX SAVE**\n"
        "\n"
        "**Entry requirement:** Step 7 must have returned confirmation that the first complete PSD "
        "was successfully saved to Dropbox. Keep its exact destination and file identity for the "
        "final overwrite.\n"
        "\n"
        "**8A. Re-read and review**\n"
        "\n"
        "Re-read `SPORTS-CAVE-LIMITED-EDITION-COLLECTOR-DESIGNS.txt`. Inspect the first complete "
        "artwork against the original photographs and use REVIEW NOTES to prioritise corrections. "
        "Identify specific improvements to composition, "
        "subject scale, integration, lighting, typography and border treatment.\n"
        "\n"
        "**8B. Generate the complete artwork again**\n"
        "\n"
        "Make a **new image-generation call** using both:\n"
        "\n"
        "- The first complete artwork as the starting concept.\n"
        "- The original source photographs as the authority for identity and sporting details.\n"
        "\n"
        "Generate a substantially improved **complete collector artwork containing the athlete or "
        "athletes, background, lighting, typography and border together**. This is a full "
        "compositional redesign—not a background-only generation, simple cleanup, upscale or manual "
        "rearrangement.\n"
        "\n"
        "You may reposition and proportionally resize subjects, rebalance the composition and "
        "redesign the environment. Preserve recognisable facial features, expressions, natural "
        "anatomy, poses, uniforms and equipment. Preserve the intended product title and factual wording.\n"
        "\n"
        "Exclude the official badge, edition number and any verified signatures from generation. "
        "Restore the existing assets afterward on separate layers.\n"
        "\n"
        "**8C. Inspect and correct**\n"
        "\n"
        "Compare the second generated artwork with the original photographs at close range and "
        "assess the whole composition at thumbnail size. Check identity, anatomy, uniform details, "
        "cropping, edges, shadows and text.\n"
        "\n"
        "Correct or regenerate where needed. If a quality concern remains after reasonable "
        "corrections, document it in REVIEW NOTES and save the best complete second artwork as "
        "a review draft.\n"
        "\n"
        "**8D. Update the existing PSD**\n"
        "\n"
        "Place the inspected second artwork in **FINAL POLISHED ARTWORK**. Keep the first artwork "
        "intact in a hidden **ORIGINAL EDITABLE ARTWORK** group.\n"
        "\n"
        "Keep any verified signatures on separate visible layers, the original badge above the "
        "artwork, and the editable edition number at the very top. Preserve the master dimensions "
        "and colour profile.\n"
        "\n"
        "**8E. Save again and verify**\n"
        "\n"
        "**Overwrite the exact Dropbox PSD saved in Step 7.** Confirm the update succeeded and "
        "verify the saved file at the original path and confirm it is the updated revision. If the "
        "connector cannot overwrite it, use the connected Dropbox browser as described above.\n"
        "\n"
        "Display the updated artwork in chat and state any remaining review concerns.\n"
        "\n"
        "**Completion requires all four checkpoints:**\n"
        "\n"
        "1. First complete artwork generated.\n"
        "2. First PSD save confirmed by Dropbox.\n"
        "3. Second complete artwork generated **after** that confirmation.\n"
        "4. Same Dropbox PSD updated and verified.\n"
        "\n"
        "Report any incomplete checkpoint plainly. Never describe the workflow as complete when one "
        "is missing."
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
