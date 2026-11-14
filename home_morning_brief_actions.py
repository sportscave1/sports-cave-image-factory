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
        "**Generate and inspect first complete artwork → confirm trial PSD save → regenerate and "
        "inspect complete artwork → confirm and verify new final PSD → confirm trial deletion → "
        "display final artwork.**\n"
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
        "**After Dropbox confirms the trial save, continue immediately to Step 8 without asking permission.** "
        "Generate the complete artwork again using the first artwork and original photographs, "
        "inspect it, make necessary corrections, and save it as a separate final PSD. Preserve the "
        "first artwork in the final PSD's hidden `ORIGINAL EDITABLE ARTWORK` group.\n"
        "\n"
        "**Recover from tool failures.** Retry recoverable failures appropriately and use another "
        "available, authorised method when necessary, including the connected Dropbox browser. "
        "If a save response is uncertain, reconcile it against the intended Dropbox path and "
        "saved file identity and contents before retrying. Keep the trial until the final PSD "
        "is verified.\n"
        "\n"
        "**Missing signatures must not stop the artwork.** Complete the required three-source "
        "search and the reference and extraction checks in Step 4 before omitting a signature. "
        "Never generate or redraw a signature.\n"
        "\n"
        "Stop only when a required operation genuinely cannot be performed with available access "
        "and tools, after reasonable alternatives have been attempted. Identify the exact failed "
        "operation, attempts made, saved progress and smallest action needed to resume. Never claim "
        "an unperformed generation, save, verification or deletion succeeded.\n"
        "\n"
        f"{context}\n\n"
        "Choose dates, statistics and achievement text according to the edition’s story. Never include "
        "them automatically.\n"
        "\n"
        "Before designing, ask: “Would this detail still help a fan understand and value this artwork "
        "five years from now?”\n"
        "\n"
        "1. **Legacy, GOAT, rivalry and identity editions:** default to a meaningful title and subject "
        "names. Add career years or achievements only when they materially strengthen the story.\n"
        "2. **Championships, iconic memories, farewells and historic events:** include the year when it "
        "identifies the achievement or era. Use a full date only when that exact day is central to the "
        "memory; otherwise place it in the product description or certificate.\n"
        "3. **Records and exceptional performances:** retain the verified statistic or concise group of "
        "statistics that makes the moment significant. Omit routine results and unrelated numbers.\n"
        "4. **Avoid information that becomes outdated:** do not use current age, live rankings, ongoing "
        "season averages or changing career totals as timeless legacy claims. If essential, explicitly "
        "anchor them to the relevant season or completed event. Describe records as achievements at that "
        "event, rather than implying they can never be surpassed.\n"
        "5. **Keep the hierarchy restrained:** subject first, collector title second, name and essential "
        "context next, official collector details last. Normally use no more than one concise "
        "achievement/statistics line and one discreet date/event line. These are maximums, not required "
        "fields.\n"
        "6. **Use meaningful headlines:** evoke the sporting story without sounding like a news headline "
        "or advertisement. Avoid “latest,” “today,” “this season” and unsupported greatness claims.\n"
        "7. **Do not remove a meaningful date merely because it is recent.** Do not add a date merely "
        "because the subject is historic. Preserve context when it creates collector value.\n"
        "\n"
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
        "scale, and ink finish for a premium collector look. A textured background alone is no "
        "reason to omit an autograph. Search for a clearer flat reference, download and inspect "
        "the strongest authentic candidates, and attempt a faithful extraction that preserves "
        "the original strokes. If the best verified source is low resolution but the strokes "
        "can be faithfully extracted, use it on a separate layer in the final collector design. "
        "Improve legibility with precise masking, contrast, and a suitable display size and ink "
        "finish. Keep all original stroke shapes and gaps. Never generate, redraw, or reconstruct "
        "the signature or fill in missing strokes. Omit it only after the search and extraction "
        "attempts fail. Record the sources checked, extraction attempted, and exact reason it "
        "failed in REVIEW NOTES, and continue.\n\n"
        "Step 5. Use the image generation tool to generate the first complete Sports Cave "
        "Collector Series artwork. Build a cohesive vintage background with subtle textures "
        "and details from the sport or venue and restrained team colours. Keep vintage texture, "
        "grain, distressing and sharpening effects off the athlete. Integrate the original "
        "hero photo through matching light, colour, and depth while preserving the athlete’s face, "
        "anatomy, pose, and uniform. Keep any verified signature as a separate asset and show the "
        "first complete artwork in the chat before placing it on the PSD.\n\n"
        "Step 6. Inspect the generated artwork against the original photo. Check that the person "
        "looks realistic and that their face, body, and uniform are free of unintended cropping, "
        "blending, or AI distortion. Apply the mandatory subject authenticity check in Step 8C "
        "at 100% magnification to this first generation, restoring altered subject regions where "
        "needed. Make practical corrections and record remaining concerns for "
        "Step 8. Once you have inspected a complete first artwork, proceed to the review save.\n\n"
        "Step 7. Place the first complete artwork on a copy of designs-canvas.psd as a review draft. "
        "Include any verified signatures on separate layers and document remaining concerns in a "
        "hidden REVIEW NOTES layer. Save a new file named **`[Product Title] - TRIAL.psd`** "
        "using the intended online product title. The final name is **`[Product Title].psd`**. "
        "Use the same Dropbox review folder for both files at /Sportscave Team Folder/"
        "02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/99_PSD_NEEDS_REVIEW_DO_NOT_DELETE/. "
        "Check both names before saving. If either exists, choose an unused matching version "
        "suffix for both, such as `[Product Title] - v2 - TRIAL.psd` and "
        "`[Product Title] - v2.psd`. Create files without replacing existing files. "
        "Confirm the save and continue immediately to Step 8.\n\n"
        "**STEP 8 — REQUIRED SECOND FULL-ARTWORK GENERATION, AFTER THE FIRST DROPBOX SAVE**\n"
        "\n"
        "**Entry requirement:** Dropbox must have confirmed the trial save in Step 7. Record the "
        "trial file ID, path and revision from that save for exact cleanup after final verification.\n"
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
        "**MANDATORY SUBJECT AUTHENTICITY CHECK**\n"
        "\n"
        "Use the original photographs as the authority for every visible subject detail. Preserve "
        "facial features, expression, anatomy, hands, natural skin texture, uniform and equipment.\n"
        "\n"
        "Apply vintage texture, grain, distressing and sharpening effects only to the background "
        "and decorative elements. Mask these effects away from the athlete. Never add artificial "
        "scars, scratches, etched lines, exaggerated pores, wrinkles, veins, mottling or plastic-looking "
        "skin. Preserve genuine marks visible in the original photograph.\n"
        "\n"
        "After each generation, compare the face, forehead, shoulders, arms, hands and uniform "
        "against the original at 100% magnification. Use the first generated artwork as a composition "
        "reference in the second pass. Use the original photos for subject details.\n"
        "\n"
        "Correct subject distortion before final verification. If generation changes these "
        "details, restore the affected regions from the original photograph with precise masking "
        "and compatible lighting and colour adjustments. Avoid repeated regeneration of damaged "
        "skin and smoothing that removes authentic detail. Recheck the restored regions at 100%.\n"
        "\n"
        "Both full-artwork generations are required. Photographic restoration is an authorised "
        "finishing step after generation. Correct other quality concerns or record them in REVIEW "
        "NOTES as needed. Keep the trial until the corrected final passes the subject check. If "
        "faithful restoration cannot be completed, save progress as a clearly labelled separate "
        "REVIEW DRAFT, keep the trial, and report the exact unresolved defect. Leave the final "
        "save and verification pending and describe the progress as a review draft.\n"
        "\n"
        "**8D. Prepare the separate final PSD**\n"
        "\n"
        "Place the inspected second artwork in **FINAL POLISHED ARTWORK**. Keep the first artwork "
        "intact in a hidden **ORIGINAL EDITABLE ARTWORK** group.\n"
        "\n"
        "Keep any verified signatures on separate visible layers, the original badge above the "
        "artwork, and the editable edition number at the very top. Preserve the master dimensions "
        "and colour profile.\n"
        "\n"
        "**8E. Save and verify the final PSD**\n"
        "\n"
        "After the subject authenticity check passes, save the final PSD as a **new file** in "
        "the same review folder using the final name "
        "chosen in Step 7. If that name becomes occupied by another file, select a new unused "
        "matching pair and move only this run's trial to the new trial name without replacing "
        "any file. Verify the moved trial's identity and update its recorded path before saving "
        "the final. Confirm the final upload, match its Dropbox path and byte size to the intended "
        "final PSD, and reopen or download the saved copy to verify its contents, including both "
        "artwork versions. If the final save or verification fails, retain the trial and continue "
        "recovery.\n"
        "\n"
        "**8F. Remove the trial and display the final artwork**\n"
        "\n"
        "Only after successful final verification, use Dropbox's recoverable delete on the exact "
        "trial file created during this run. Match its recorded file ID, path and revision before "
        "deleting. Never delete an unrelated file. This cleanup is authorised and requires no "
        "additional confirmation. Confirm the deletion. If cleanup fails, report it as pending "
        "and state that the final PSD is already saved and verified.\n"
        "\n"
        "After Dropbox confirms trial deletion, display the final artwork in chat and state any "
        "remaining review concerns.\n"
        "\n"
        "**Completion requires:** first generation → confirmed trial save → second full generation "
        "→ confirmed and verified final save → confirmed trial deletion → display final artwork.\n"
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
