"""Compact recommendation rows and their ChatGPT project handoff."""

from functools import lru_cache
from html import escape
from pathlib import Path
import re
from urllib.parse import urlencode

from design_new_composition import (
    COMPLEMENTARY_IMAGES, COMPLETE_COMPOSITION, COLLECTOR_TYPOGRAPHY,
    PURPOSEFUL_ABSTRACT, REVIEW_RELATIONSHIPS, BADGE_PLACEMENT_VERIFICATION,
)
from design_collector_assets import COLLECTOR_ASSET_PLACEMENT
from design_signature_free import SIGNATURE_FREE_COMPOSITION
from design_collector_titles import COLLECTOR_TITLE_GUIDANCE
from design_collector_background import BACKGROUND_RESEARCH, COLLECTOR_BACKGROUND
from design_subject_authenticity import (
    CREATE_DESIGN_AUTHENTICITY_CHECK, IDENTITY_OVERRIDES_CONTINUITY,
)
from home_brief_calendar import MARKETS, PRODUCT_QUERY, calendar_rows, display_markets, product_handle
from psd_directory import REVIEW_FOLDER, REVIEW_METADATA_FOLDER

PROJECT_URL = "https://chatgpt.com/g/g-p-6a1e449948e881919c1e345006d63654/project"
TEMPLATE = Path(__file__).parent / "components" / "morning_brief_actions.html"


META_AD_HEADING = re.compile(r"^(?:recommended|suggested)\b.*\bmeta\b.*\bad\b", re.I)
META_AD_COPY = re.compile(r"^(?:headline|primary text|description|cta|call to action)\s*:", re.I)

_BORDER_STYLE_GUIDANCE = (
    "Choose a border that suits the artwork. Restrained antique gold, fine double lines or "
    "subtle heritage corners can work where they add to the design. A simple, elegant border "
    "is equally suitable. Avoid heavy ornament and vary the treatment across designs."
)

_CREATE_DESIGN_BORDER_RULES = (
    "**Border and print safety for both artwork passes and the final layout**\n\n"
    "Leave an even framing-safe margin equal to 3% of the canvas’s shorter dimension on all "
    "four sides. Measure from the canvas edge to the outermost decorative border detail, "
    "including corner ornaments. On the 2835 × 2004 master, use 60 px.\n\n"
    f"{_BORDER_STYLE_GUIDANCE}\n\n"
    "Extend the background to every canvas edge. Adjust only the border and its corner details "
    "to achieve the margin. Preserve the existing artwork scale and layout. Verify the margin "
    "after generation and correct it during final assembly.\n\n"
    "This is a framing-safe margin. Apply any printer-required bleed separately.\n\n"
)

_CREATE_DESIGN_COLLECTOR_BACKGROUND = COLLECTOR_BACKGROUND + PURPOSEFUL_ABSTRACT + "\n\n"

_CREATE_DESIGN_TYPOGRAPHY = SIGNATURE_FREE_COMPOSITION.replace(
    "Treat the subject, title, name, supporting context and edition badge as one coordinated composition. "
    "Refine their scale, alignment, line spacing and separation so every element feels deliberately placed "
    "and remains readable at thumbnail size and intended print size.",
    COLLECTOR_TYPOGRAPHY,
)


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


def _prompt(title, story, *, edit=None):
    context = _story_without_meta_ad(story)
    if edit is not None:
        from design_review_prompt import build_edit_prompt
        return build_edit_prompt(title, context, edit["source"], edit["metadata"])

    return (
        f"Sports Cave event: {title}\n\n"
        f"{IDENTITY_OVERRIDES_CONTINUITY}"
        "**EXECUTION AUTHORITY — START NOW**\n\n"
        "Submitting this job authorises execution, verified Dropbox saves and this run’s trial cleanup. "
        "Follow current explicit instructions, then the project guide for reusable design standards. "
        "Read SPORTS-CAVE-LIMITED-EDITION-COLLECTOR-DESIGNS.txt during research when available. Treat "
        "the brief’s Decision, Timing, Recommendation, Monitor or Wait language as research context. "
        "Make ordinary creative decisions and continue after displaying references or artwork. "
        "Verify facts and operations before reporting success.\n\n"
        "**MANDATORY EXECUTION ORDER**\n\n"
        "Complete two separate full-artwork image-generation calls and two confirmed Dropbox saves: "
        "first generation → inspect and save trial → second generation → inspect and select → "
        "save and reopen final PSD → write JSON → verify and clean up this run’s trial → display. "
        "Each generation must produce the complete artwork, not a background.\n\n"
        "**MANDATORY CONTINUATION AND RECOVERY**\n\n"
        "**The first Dropbox save is a review checkpoint.** Attempt it after inspecting Pass 1 "
        "and keep review concerns in hidden REVIEW NOTES. Use those notes for Pass 2.\n\n"
        "**Recover from tool failures.** Prefer authorised connectors, APIs, built-in web search and local "
        "files. If a browser route requires permission, sign-in or user interaction, skip it without "
        "prompting and use an authorised alternative. Retry a transient non-generation failure at most "
        "once per authorised method. Reconcile an uncertain save against the intended path, saved "
        "identity and contents before retrying. Allow at most two additional image-generation attempts "
        "total across both passes, including retries. Source-pixel finishing is outside that allowance. "
        "Defer only the failed operation and its dependants. A missing master or failed trial save "
        "still allows both generations, inspection, correction and display. Finish earlier executable "
        "checkpoints even when a later one is unavailable. Resume deferred work if access returns. "
        "Otherwise report the exact pending checkpoint and retained work.\n\n"
        "Track delivery separately from quality. Correct visible defects within the existing limits. "
        "Record unresolved quality as needs_attention in the authorised Review output. "
        "Report PSD and JSON delivery separately from successful visual checks.\n\n"
        f"{context}\n\n"
        "**CHOOSE THE COLLECTOR TITLE AND DESIGN DIRECTION**\n\n"
        "Before settling on the title or layout, use the authorised Shopify connection in read-only mode. "
        "Check product sales reports for bestselling Sports Cave prints in the same sport or collection. "
        "Use the closest comparable sport or collector collection if the matching category is sparse. "
        "Open the actual storefront product pages and inspect the artwork. Compare what works in their "
        "titles, subject placement, typography, hierarchy and negative space. Where sales evidence "
        "allows, contrast with a comparable lower-selling print to spot weaknesses without assuming "
        "the design caused the sales difference. Use relevant cues to inform an original design. "
        "If reports are unavailable, use a verifiable storefront bestseller listing or approved project "
        "references. Treat unranked products as style references only. Record the evidence or gap in "
        "REVIEW NOTES and continue immediately with the available references and rules below.\n\n"
        "Use the brief and recent events to decide who to feature and when to promote them. Treat its "
        "event label and any suggested title as research context. Preserve the verified reason for the "
        "edition while expressing it with lasting collector appeal. Ask whether fans would still want to display it in "
        "five years. A strong match, a single century, a weekly stat line or a narrowly defined record "
        "can justify featuring the subject. Use an enduring story for the print and omit match statistics, "
        "scores and dates. When a statistic or date is uncertain, omit it without losing the verified emotional story.\n\n"
        "Build an edition around an event only when the verified achievement has lasting collector "
        "significance, such as a championship, league or season MVP, player of the year, player of a "
        "completed landmark series such as the Ashes, an established all-time achievement, or an iconic "
        "moment or farewell fans will remember. Apply the same test to recent and historic events. "
        "Use a single concise verified statistic or accolade only if it tells that lasting story. Use a "
        "year only if it identifies the achievement or era, and a full date only when the day itself "
        "matters. Avoid live rankings, ongoing averages, changing totals and unsupported GOAT claims.\n\n"
        f"{COLLECTOR_TITLE_GUIDANCE}"
        "List the best possible images. Show the photos in this chat first. Use web image search to "
        "aim for 4–8 images that fit the chosen subject and story. If fewer are usable after checking the original source "
        "pages, show the candidates that meet the Step 1 standard. Focus on photo authenticity, image "
        "quality, and how each photo supports the artwork. I will handle photo licensing "
        "separately. Do not research, assess, or mention photo licensing, commercial-use "
        "permissions, or usage rights.\n\n"
        "**STORY-FIRST IMAGE SELECTION**\n"
        "\n"
        "Use these cues within the existing image search. Develop the title alongside the exact "
        "sporting moment or emotional reason to own the artwork. Search the named achievement, "
        "gesture, event or era alongside the subject. Where available, compare distinct authentic "
        "action, celebration, achievement and identity photos. For timeless artwork, consider the "
        "strongest verified images from the relevant career, team or era. For an event edition, focus "
        "on authentic images of that event. "
        "Rank story fit first, then emotional impact, recognisability, readable pose, composition "
        "potential and original source quality at print size. A sharp neutral portrait earns "
        "the hero spot when it best serves the story.\n"
        "\n"
        "Use the visual review of recent Sports Cave best sellers as a reference, choosing the "
        "family that fits the photograph and title. Defining action needs a readable movement "
        "and room in its direction. For achievement, look for visible evidence such as a belt, trophy, "
        "decisive action or unmistakable reaction. A paired legends or rivalry title can give "
        "both named subjects comparable weight within one coherent composition. For heritage "
        "racing, consider the correct period machine in the lower foreground with its driver "
        "or historical context above or beside it. For farewell or legacy, look for a real bow, "
        "wave, walk away or embrace and give the gesture breathing room. When a genuine photo "
        "captures the relationship, preserve the interaction. These are optional directions.\n"
        "\n"
        f"{COMPLEMENTARY_IMAGES}"
        "Use evidence relevant to this sport: readable action or celebration, the genuine trophy or "
        "equipment, and period-correct uniforms, silks, vehicles and livery. Use accurate context for "
        "heritage or paired designs and a gesture that serves the verified story.\n\n"
        "Let the photo drive the arrangement within the established Sports Cave style. Keep one "
        "clear visual priority, which can be the relationship itself in a paired design. Use "
        "supporting imagery only for a different part of the story, with quieter contrast, "
        "colour and placement. Preserve faces, anatomy, uniforms, lettering, equipment and decisive "
        "details such as the belt, ball, wheels or relevant opposition. Leave room for movement or "
        "gaze and reframe without mirroring. Keep event context accurate and avoid inventing action "
        "or presenting unrelated events as one moment. Check that the story reads at thumbnail "
        "size and that the image still communicates it with the title hidden.\n"
        "\n"
        "Step 1. **Hero photo selection — story and title together.** Compare candidates for subject prominence, "
        "emotional relevance, clarity and compositional potential. Choose the photo that best tells "
        "the named subject's collector story. In an individual-player edition, the named athlete "
        "must dominate immediately at thumbnail size. Reject photos where teammates, opponents, "
        "back views or obstructions dominate or conceal the athlete. If no candidate meets the "
        "standard, make a focused follow-up search of original galleries and alternate sources. "
        "If no suitable original is accessible, keep the composition provisional, use only verified "
        "subject details, and record the missing source without waiting. "
        "Keep an individual tribute centred on that athlete. Use one strong hero photograph when "
        "it tells the story on its own. If a second photo adds distinct value, use it as subordinate "
        "background imagery. Place the selected hero in the artwork. Preserve "
        "recognisable faces, uniforms, and event details. Follow the project’s Collector Series "
        "references for typography, colour, depth, and visual hierarchy. Refer to the project "
        "instructions in Sports Cave Designs for how Sports Cave designs are structured.\n\n"
        f"{BACKGROUND_RESEARCH}"
        "Step 2. Inspect designs-canvas.psd in Dropbox for the exact pixel dimensions, orientation, "
        "safe margins, and limited-edition badge. Preserve the "
        "original limited-edition badge and edition-number layer. If retrieval remains blocked after "
        "reasonable recovery attempts, keep the master-dependent PSD work pending. Use verified "
        "master dimensions if available. Otherwise keep the layout provisional and reserve space "
        "for the original badge and editable number to be restored from the master.\n\n"
        f"{COMPLETE_COMPOSITION}"
        f"{_CREATE_DESIGN_BORDER_RULES}"
        f"Step 4. {_CREATE_DESIGN_TYPOGRAPHY}\n\n"
        f"{_CREATE_DESIGN_COLLECTOR_BACKGROUND}"
        "Step 5. Use the image generation tool to generate the first complete Sports Cave Collector Series artwork. "
        "Use the collector background treatment above. "
        "Use the verified source photos and show the complete artwork in chat.\n\n"
        "Step 6. Inspect the generated artwork using the photographic review in Step 8C. "
        "Apply it at 100% magnification to this first generation and record remaining concerns for Pass 2.\n\n"
        "Step 7. Place the first complete artwork on a copy of designs-canvas.psd as a review draft. "
        "Document remaining concerns in a "
        "hidden REVIEW NOTES layer. Save a new file named **`[Product Title] - TRIAL.psd`** "
        "using the intended online product title. The final name is **`[Product Title].psd`**. "
        f"Save both PSDs directly in the same Dropbox review folder at {REVIEW_FOLDER}/. "
        "Check both names before saving. If either exists, choose an unused matching version "
        "suffix for both, such as `[Product Title] - v2 - TRIAL.psd` and "
        "`[Product Title] - v2.psd`. Create files without replacing existing files. "
        "Confirm the save when possible. If master retrieval or the trial save remains blocked after "
        "reasonable recovery attempts, mark the trial PSD work pending and retain the first artwork "
        "and review notes. Continue immediately to Step 8 in either case.\n\n"
        "**STEP 8 — REQUIRED SECOND FULL-ARTWORK GENERATION**\n"
        "\n"
        "When Dropbox confirms the trial save, record its file ID, path and revision for exact "
        "cleanup after final verification. If the trial save is pending, use the retained first "
        "artwork and review notes to complete the second generation and inspection.\n"
        "If the first generation is unavailable after recovery, use the verified photos and the "
        "planned composition to attempt the second pass independently.\n"
        "\n"
        "**8A. Review Pass 1**\n\n"
        "Use REVIEW NOTES and the bestseller evidence to identify the three most visible weaknesses "
        "and explicitly lock the effective composition and styling before generating again. Review "
        "title and placement at thumbnail size. Follow the identity rule when deciding what to carry forward. "
        "Use style references only where they address a weakness.\n\n"
        f"{REVIEW_RELATIONSHIPS}"
        "**8B. Second full generation — preserve what works**\n"
        "\n"
        "Carry forward the collector background treatment from Step 5. Refine it only where the "
        "artwork benefits. Use the same guidance if the first pass was unavailable.\n\n"
        "Use the same collector specifications, verified canvas and safe area for both passes. Keep "
        "meaningful sporting colours and original camera angles. Set type and accents in the established "
        "charcoal, warm-white and restrained-gold collector palette. "
        "Use contact shadows only at actual points of contact. Keep supporting effects within "
        "the collector background guidance above. "
        "Keep this flat artwork free of mockup framing, walls and rooms.\n\n"
        "Make a **new image-generation call** using both:\n"
        "\n"
        "- The first complete artwork as the visual foundation, including the strengths locked in 8A "
        "and the intended title, factual wording, story and subject. If it is unavailable, use the "
        "verified details from the planned composition. For any retry, use the strongest inspected version.\n"
        "- The original photographs as the authority for identity, expression, anatomy, pose, uniform "
        "and equipment. Use category references only to support targeted corrections.\n"
        "\n"
        "Generate a **complete Sports Cave collector artwork** with the subject, setting, lighting, "
        "typography and border integrated. A new layout is optional. Keep the athlete's successful "
        "scale and position, title treatment, background and accents unless a specific issue warrants "
        "a change. Choose another verified photo that fits the chosen story only if it fixes a source "
        "problem such as an obstructed crop or weak story fit. Keep event-specific imagery accurate.\n"
        "\n"
        "Exclude the official badge and edition number from generation. "
        "Restore the existing assets afterward on separate layers.\n"
        "\n"
        "**8C. Inspect and correct**\n\n"
        "**MANDATORY ACCEPTANCE CHECK — PRESERVE THE STRONGEST VERSION**\n\n"
        "Apply the same checklist to each generation, each correction and the assembled PSD at 100% "
        "and thumbnail size. Check identity first, then sporting details and venue, integration, "
        "subject prominence, title and typography, framing clearance and the plaque’s chosen placement. "
        "Fix the highest-impact defects. Compare side by side and keep changes that improve the whole "
        "design without weakening facial fidelity. If the first artwork still wins, use it. "
        "A failed or unverified identity never wins as an accepted final design. If no pass qualifies, "
        "save the strongest inspected candidate for Review with needs_attention.\n\n"
        f"{CREATE_DESIGN_AUTHENTICITY_CHECK}"
        "**8D. Prepare the separate final PSD**\n"
        "\n"
        "If the master is still unavailable, retain both finished artworks and review notes. Mark master-dependent assembly, saves, verification and "
        "trial cleanup as pending where applicable. Continue to the final display and status in Step 8F.\n"
        "\n"
        "If either artwork pass remains unavailable after recovery, preserve any completed artwork "
        "and mark assembly with both versions pending. Continue to Step 8F.\n"
        "\n"
        "Place the winner from 8C, or its provisional Review candidate, in **FINAL POLISHED ARTWORK**. "
        "Keep the first artwork intact in a hidden **ORIGINAL EDITABLE ARTWORK** group, even "
        "if a copy is selected for the final. Preserve other useful versions in separate hidden groups.\n"
        "\n"
        "Preserve the master dimensions "
        "and colour profile.\n\n"
        f"{BADGE_PLACEMENT_VERIFICATION}"
        f"{COLLECTOR_ASSET_PLACEMENT}"
        "**8E. Save and verify the final PSD**\n"
        "\n"
        "After inspection, save the final PSD as a new file using the matching unused names from Step 7. "
        "If the winning title changes, choose an unused pair and move only this run’s verified trial "
        "without replacing another file. Update its recorded path. If access returns, retry the pending "
        "trial first where possible, then save the final independently if the trial is still pending. "
        "Confirm final Dropbox path and byte size, reopen or download the saved PSD, and inspect visible "
        "artwork, hidden groups, dimensions, colour profile and both original collector layers. "
        "Photoshop is optional. Use Photoshop or a capable PSD parser plus a rendered preview to verify "
        "the original editable SC_EDITION_NUMBER layer, exact name, text data, transform, position and "
        "alignment inside SC_EDITION_PLAQUE. A flattened preview alone cannot verify the editable layer. "
        "Retain the trial and report the specific unverified property when any required file check fails.\n\n"
        "**SMART UPLOAD HANDOFF METADATA**\n"
        "\n"
        "After verifying the saved final PSD, record its categorisation and Dropbox identity "
        f"in a UTF-8 JSON file named [Final PSD stem].upload.json in {REVIEW_METADATA_FOLDER}/. "
        "Create this JSON subfolder if needed. Keep the final and trial PSDs directly in Review. "
        "Use create-only mode. Never write a handoff for the trial or overwrite an existing file. "
        "Confirm the sidecar's Dropbox file ID, revision and path refer to the exact saved final PSD.\n"
        "\n"
        "Include design_title, design_story, sport, league, teams and athletes (arrays), "
        "intended_collections (array of confirmed Shopify collection IDs or handles), "
        "upload_intent (new_product), existing_shopify_product_id (null), "
        "dropbox_file_id, dropbox_revision, dropbox_path, and review_status. Use ready_for_review "
        "only for a verified PSD with passing visual checks and complete required metadata. "
        "Use needs_attention for failed or unverified identity, other unresolved quality concerns or pending metadata. "
        "Identify missing fields or checks in review_notes. Use null or empty arrays for unknown "
        "values and never guess IDs or collection mappings. A shared athlete or similar title "
        "does not make a new collector concept a refresh.\n"
        "\n"
        "This metadata prepares a later upload. Save it for review without publishing or changing "
        "Shopify. If the handoff cannot be saved or confirmed, preserve the artwork, report that "
        "the metadata is pending, and continue independent work, including eligible trial cleanup.\n"
        "\n"
        "**8F. Remove the trial and display the final artwork**\n"
        "\n"
        "Only after successful final verification, use Dropbox recoverable delete on this run’s trial. "
        "Match the recorded ID, path and revision before deletion, recheck before any authorised retry "
        "and confirm deletion. When verification is incomplete, retain the trial. Report any cleanup "
        "failure as pending while reporting the confirmed final save separately.\n\n"
        "Display the inspected final artwork after cleanup, or display the strongest available result "
        "as provisional if required work remains. If neither generation produced artwork, report that "
        "and list retained work. Give exact confirmed paths, pending steps and quality concerns.\n\n"
        "**Completion requires:** both full generations, confirmed trial and final PSD saves, saved-copy "
        "and layer verification, matching JSON, confirmed trial deletion and final display. "
        "Recovery can change when independent steps run."
    )


@lru_cache(maxsize=1)
def _template():
    return TEMPLATE.read_text(encoding="utf-8")


def article_html(item, *, heading=None, allow_ads=False, legend=False, design_status=None):
    title = " ".join(item["title"].split())
    label = heading or title
    markets = display_markets(item)
    market_label = ""
    if legend and len(markets) > 1:
        market_label = f'<small class="sc-brief-secondary">Secondary: {escape(", ".join(markets[1:]))}</small>'
    elif not legend and markets:
        label += f' ({", ".join(markets)})'
    prompt = escape(_prompt(title, item["recommendation"]), quote=True).replace("\n", "&#10;")
    actions = (
        f'<a href="{PROJECT_URL}" target="_blank" rel="noopener noreferrer" '
        f'data-prompt="{prompt}" title="Open Sports Cave Designs and copy the prompt">Create Design</a>'
    )
    status_label = ''
    if design_status:
        icon, tone = {
            'Completed · uploaded': ('✓', 'complete'),
            'Ready for review': ('✓', 'complete'),
            'Uploaded · needs review': ('!', 'attention'),
            'Needs attention': ('!', 'attention'),
            'Generating': ('◌', 'running'),
            'Opening ChatGPT': ('◌', 'running'),
            'Uploaded · checking review metadata': ('◌', 'running'),
        }.get(design_status, ('○', 'pending'))
        status_label = (f'<small class="sc-brief-secondary sc-brief-status {tone}" role="status">'
                        f'<i class="sc-brief-status-icon" aria-hidden="true">{icon}</i> '
                        f'{escape(design_status)}</small>')
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
            copy_label = lead if colon else line.strip()[:-1]
            paragraphs.append(f'<p class="sc-brief-key"><strong>{escape(copy_label)}:</strong> {escape(detail)}</p>')
        else:
            paragraphs.append(f"<p>{escape(line)}</p>")
    return (
        '<article class="sc-brief-row"><details>'
        f'<summary title="{escape(label, quote=True)}"><span>{escape(label)}{market_label}{status_label}</span></summary>'
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


def _ranked_legends(items):
    grouped = {market: [] for market in MARKETS}
    other = []
    for item in items:
        markets = display_markets(item)
        if markets and markets[0] in grouped:
            grouped[markets[0]].append(item)
        else:
            other.append(item)
    ranked = [(f"{market} {rank}.", item) for market, group in grouped.items()
              for rank, item in enumerate(group, 1)]
    return ranked + [(f"{rank}.", item) for rank, item in enumerate(other, 1)]


def brief_html(edition, *, editions, today, allow_ads=False, design_statuses=None):
    from morning_design_queue import identity
    def status(section, item):
        if design_statuses is None or not edition:
            return None
        return design_statuses.get(identity(edition['date'], section, item), 'Pending')
    rows = "".join(
        article_html(item, heading=f'{rank}. {item["title"]}', allow_ads=allow_ads, design_status=status("recommendations", item))
        for rank, item in enumerate((edition or {}).get("recommendations", ()), 1)
    )
    full_brief = (edition or {}).get("full_brief")
    legends = _ranked_legends((edition or {}).get("legends", ()))
    if full_brief:
        if legends:
            full_brief += '\n\nLegends Brief\n\n' + '\n\n'.join(
                f'{label} {item["title"]}\n{item["recommendation"]}\n' + '\n'.join(
                    f'{link["label"]}: {link["url"]}' for link in item['links'])
                for label, item in legends
            )
        rows += (
            '<button type="button" class="sc-full-brief" aria-haspopup="dialog">Read the full Morning Brief</button>'
            '<dialog class="sc-cal-dialog sc-sports-full" aria-label="Full Sports Morning Brief">'
            '<header><h3>Full Morning Brief</h3><form method="dialog"><button>Close</button></form></header>'
            f'<div class="sc-full-brief-text">{escape(full_brief)}</div></dialog>'
        )
    tables = "".join(_market_table(editions, market, today) for market in MARKETS)
    stories = f'<section class="sc-sports-stories" aria-label="Sports opportunities">{rows}</section>' if rows else ""
    legend_rows = "".join(article_html(item, heading=f'{label} {item["title"]}', allow_ads=allow_ads, legend=True, design_status=status("legends", item))
                          for label, item in legends)
    if not legend_rows:
        legend_rows = '<p class="sc-legends-empty">No Legends Brief entries for this edition.</p>'
    legend_section = ('<section class="sc-sports-stories sc-legends" aria-label="Legends Brief">'
                      f'<h3>Legends Brief</h3>{legend_rows}</section>')
    return (_template().replace("<!-- CALENDARS -->", tables)
            .replace("<!-- LEGENDS -->", legend_section).replace("<!-- RECOMMENDATIONS -->", stories))
