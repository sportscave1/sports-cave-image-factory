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
from design_collector_titles import NEW_DESIGN_TITLE_GUIDANCE
from design_collector_background import BACKGROUND_RESEARCH, COLLECTOR_BACKGROUND
from design_motorsport import MOTORSPORT_ARTWORK
from design_subject_authenticity import (
    CREATE_DESIGN_AUTHENTICITY_CHECK,
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
    "**Border and print safety for generation and the final layout**\n\n"
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


def _prompt(title, story, *, edit=None, primary_market=""):
    context = _story_without_meta_ad(story)
    if edit is not None:
        from design_review_prompt import build_edit_prompt
        return build_edit_prompt(title, context, edit["source"], edit["metadata"])

    market_note = (f' Include primary_market = "{primary_market}" in the design JSON for downstream ad targeting.'
                   if primary_market in {'AUS', 'USA', 'UK', 'CA', 'CAN', 'NZ'} else '')
    return f"""Sports Cave event: {title}

**Start the authorised new-design job**

Read SPORTS-CAVE-LIMITED-EDITION-COLLECTOR-DESIGNS.txt once for this job. Use the current brief, the matching job instructions and the guide's shared creative standards. Treat Decision, Timing, Recommendation, Monitor or Wait in the brief as research context. Proceed through research, one full artwork generation, inspection and finishing, then one verified final PSD and matching JSON in Design Studio Review. Display references and the artwork in chat and continue without pausing for approval.

{context}

**1. Research the story, sources and master**

Use authorised read-only Shopify reports to inspect artwork from comparable bestsellers and, where supported, a lower-selling print. Use the closest comparable sport or collector collection when evidence is sparse. Use verified storefront bestseller or approved project references if reports are unavailable. Treat unranked products as style references only. Record the evidence or gap in REVIEW NOTES. Draw original creative cues without claiming the design caused sales.

Choose a story supporters would still want to display in five years. Use a timeless player, team, rivalry or legacy angle for ordinary match results. Use an event angle for a verified landmark achievement, iconic moment or farewell. Include an accolade, statistic or year only when essential and verified. Reserve a full date for a defining day. Keep dates, scores, live rankings and changing statistics out of routine player tributes.

{NEW_DESIGN_TITLE_GUIDANCE}Use web image search to show 4–8 suitable candidates where available. Verify original source pages, story fit, identity, kit, pose, legibility and source detail at print scale. For an individual tribute, the named subject must dominate at thumbnail size. Reject obstructed crops or photos dominated by others. Make one focused search of original galleries if needed. Keep uncertain facts and unverified likenesses provisional. The user handles photo licensing separately.

{MOTORSPORT_ARTWORK}

{COMPLEMENTARY_IMAGES}{BACKGROUND_RESEARCH}Inspect the actual designs-canvas.psd for dimensions, orientation, resolution, colour profile, framing clearance, guides and collector layers. Work from a copy. If access remains unavailable, use verified dimensions where available, reserve the plaque footprint and continue independently. Keep master-dependent assembly, saves and verification pending.

**2. Prepare the complete composition before generation**

{COMPLETE_COMPOSITION}{_CREATE_DESIGN_BORDER_RULES}{_CREATE_DESIGN_TYPOGRAPHY}

{_CREATE_DESIGN_COLLECTOR_BACKGROUND}Lock the verified subjects and exact title. Use the original photos as the authority for every face, expression, anatomy, pose, uniform, object and vehicle. Plan how the hero, supporting photograph if useful, authentic setting, styling, text, framing-safe border and plaque footprint work together at print and thumbnail sizes. Confirm the story is recognisable with the title hidden. Briefly state the chosen direction and record the layout and source decisions in REVIEW NOTES.

**3. Generate the complete flat artwork once**

Send one design-specific brief with the selected original photographs, accurate scene and movement, exact title, typography, contrast, safe margins and visible collector treatment. Generate the full artwork with subject, venue, abstract depth, typography and border. Leave the official plaque and edition number for PSD assembly. Keep the output flat artwork without physical frame, room or wall. Display the complete generation in chat.

Retry a transient tool failure once per authorised method. Retry image generation once only if a technical failure produced no usable output. After any completed generation, use original photo pixels and PSD adjustments for corrections. Keep a photo-only fallback clearly provisional. If access requires sign-in or permission, use an already authorised method. For moderation, record the exact stated reason, use only a compliant request within the existing allowance, and never retry by disguising or bypassing a rejection. Defer dependent steps and finish independent work. Reconcile any uncertain write by verifying its exact path, identity and contents before retrying.

**4. Inspect and finish at 100% and thumbnail size**

{CREATE_DESIGN_AUTHENTICITY_CHECK}{REVIEW_RELATIONSHIPS}
Verify the intended collector transformation is visible, with recognisable venue features where used, authentic colours, integrated title and plaque placement, adequate framing clearance and truthful sporting details. Use source-pixel finishing, masks, typography and PSD adjustments to correct defects. Preserve the strongest verified source material. Mark unresolved quality or identity as needs_attention and retain the strongest inspected result for Review when technically valid.

**5. Assemble, save and verify one final Review PSD**

On a master copy, place the inspected artwork in **FINAL POLISHED ARTWORK**. Preserve the unmodified generation in a hidden **ORIGINAL EDITABLE ARTWORK** group and document defects or limitations in hidden **REVIEW NOTES**. Retain the verified master canvas and working layers.

{BADGE_PLACEMENT_VERIFICATION}{COLLECTOR_ASSET_PLACEMENT}Save just the final **`[Product Title].psd`** directly in {REVIEW_FOLDER}/ in create-only mode. Use an unused version suffix if occupied. Confirm its Dropbox ID, path, revision and byte size. Reopen that saved revision and inspect the actual rendered artwork, master dimensions, colour profile, hidden original, safe border and both collector layers. Use Photoshop or a capable PSD parser plus a rendered preview to verify the original editable SC_EDITION_NUMBER name, text data, transform, position and alignment inside SC_EDITION_PLAQUE. If a required file check is pending, preserve available work and report the specific missing verification.

**6. Write the Smart Upload JSON and deliver**

After verifying the PSD, create the matching UTF-8 **[Final PSD stem].upload.json** in {REVIEW_METADATA_FOLDER}/, in create-only mode. Create the subfolder if needed. Read the JSON back and verify it points to that exact saved PSD. Include design_title, design_story, sport, league, teams and athletes (arrays), intended_collections (confirmed Shopify IDs or handles), upload_intent (new_product), existing_shopify_product_id (null), dropbox_file_id, dropbox_revision, dropbox_path and review_status. Use null or empty arrays for unknown fields and describe missing evidence in review_notes. Use ready_for_review only when the visual, PSD and metadata checks pass. Use needs_attention for unresolved quality or metadata. A shared athlete or similar title alone does not make this a refresh. Follow any automatic queue receipt instructions.{market_note}

Display the inspected final artwork, or the best available provisional result if a required checkpoint is pending. Report verified PSD and JSON paths, any pending checkpoint and quality concerns separately. Completion requires one full generation, verified final Review PSD, matching JSON and final display. Preserve completed work if a later step is blocked. Shopify publication is a separate action."""


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
    prompt = escape(_prompt(title, item["recommendation"], primary_market=markets[0] if markets else ""),
                    quote=True).replace("\n", "&#10;")
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
