"""Compact recommendation rows and their ChatGPT project handoff."""

from functools import lru_cache
from html import escape
from pathlib import Path
import re
from urllib.parse import urlencode

from design_new_composition import (
    COMPLEMENTARY_IMAGES, COMPLETE_COMPOSITION, COLLECTOR_TYPOGRAPHY,
    PURPOSEFUL_ABSTRACT, REVIEW_RELATIONSHIPS,
)
from design_collector_assets import NEW_BADGE_LAYOUT
from design_signature_free import SIGNATURE_FREE_COMPOSITION
from design_collector_titles import NEW_DESIGN_TITLE_GUIDANCE
from design_collector_background import NEW_BACKGROUND_RESEARCH, NEW_COLLECTOR_BACKGROUND
from design_motorsport import MOTORSPORT_ARTWORK, MOTORSPORT_JSON
from design_subject_authenticity import (
    CREATE_DESIGN_AUTHENTICITY_CHECK,
)
from home_brief_calendar import MARKETS, PRODUCT_QUERY, calendar_rows, display_markets, product_handle
from psd_directory import REVIEW_FOLDER, REVIEW_METADATA_FOLDER

PROJECT_URL = "https://chatgpt.com/g/g-p-6a1e449948e881919c1e345006d63654/project"
REVIEW_SAVE_NAMING = """**Review filename and website product title**

Before saving, form the full website product title: [ARTWORK NAME] – [VERIFIED SUBJECT] Wall Art. Preserve the emotional headline, add the verified athlete/team/rivalry/event, and use one spaced en dash. Example: Forever Panda – Pablo Sandoval Wall Art. Use readable spaces, never a URL slug or headline-only filename. Keep the emotional headline on the artwork.

Use that full title for the PSD stem and JSON design_title; match the JSON basename to the saved PSD, including collision suffixes. Verify filename, JSON, Dropbox ID, revision and path together. Apply the website’s 60-character title rule without truncating or inventing identity.

"""
TEMPLATE = Path(__file__).parent / "components" / "morning_brief_actions.html"


META_AD_HEADING = re.compile(r"^(?:recommended|suggested)\b.*\bmeta\b.*\bad\b", re.I)
META_AD_COPY = re.compile(r"^(?:headline|primary text|description|cta|call to action)\s*:", re.I)

_CREATE_DESIGN_BORDER_RULES = """**Border and print safety for generation and the final layout**

Keep the decorative collector border continuous on all four sides, with its outermost detail 3% of the shorter canvas dimension inside every edge: 60 px on the 2835 × 2004 master. Use a restrained, story-specific collector detail such as a fine antique-gold rule with shorter inner returns echoing court or venue geometry. A plain rectangle alone is insufficient; avoid heavy ornament.

Extend venue tones, textures and selected abstract marks through the border into the outer framing margin, all the way to every canvas edge. Keep the border legible above these layers and faces, lettering and the plaque comfortably inside it. This framing-safe margin is separate from any printer-required bleed. Verify all four edges and corners on the rendered final PSD; correct border clearance without shrinking the artwork.

"""

_CREATE_DESIGN_COLLECTOR_BACKGROUND = NEW_COLLECTOR_BACKGROUND + PURPOSEFUL_ABSTRACT + "\n\n"

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

Read SPORTS-CAVE-LIMITED-EDITION-COLLECTOR-DESIGNS.txt once for this job. Use the current brief, the matching job instructions and the guide's shared creative standards. Treat Decision, Timing, Recommendation, Monitor or Wait in the brief as research context. Proceed through research, photographic layout review, one creative generation, assembly and inspection, then one verified final PSD and matching JSON in Design Studio Review. Display references and the artwork in chat and continue without pausing for approval.

{context}

**1. Research the story, sources and master**

Use authorised read-only Shopify reports to inspect artwork from comparable bestsellers and, where supported, a lower-selling print. Use the closest comparable sport or collector collection when evidence is sparse. Use verified storefront bestseller or approved project references if reports are unavailable. Treat unranked products as style references only. Record the evidence or gap in REVIEW NOTES. Draw original creative cues without claiming the design caused sales.

Choose a story supporters would still want to display in five years. Use a timeless player, team, rivalry or legacy angle for ordinary match results. Use an event angle for a verified landmark achievement, iconic moment or farewell. Include an accolade, statistic or year only when essential and verified, in supporting context rather than the emotional headline. Reserve a full date for supporting context on a defining day. Keep dates, scores, live rankings and changing statistics out of routine player tributes.

{NEW_DESIGN_TITLE_GUIDANCE}Use web image search to show 4–8 suitable candidates where available. Verify original source pages, story fit, identity, kit, pose, legibility and source detail at print scale. For an individual tribute, the named subject must dominate at thumbnail size. Reject obstructed crops or photos dominated by others. Make one focused search of original galleries if needed. Keep uncertain facts and unverified likenesses provisional. The user handles photo licensing separately.

{MOTORSPORT_ARTWORK}

{COMPLEMENTARY_IMAGES}{NEW_BACKGROUND_RESEARCH}Inspect the actual designs-canvas.psd for dimensions, orientation, resolution, colour profile, framing clearance, guides and collector layers. Work from a copy. If access remains unavailable, use verified dimensions where available, reserve the plaque footprint and continue independently. Keep master-dependent assembly, saves and verification pending.

**2. Prepare the complete composition before generation**

{COMPLETE_COMPOSITION}{_CREATE_DESIGN_BORDER_RULES}{_CREATE_DESIGN_TYPOGRAPHY}

{NEW_BADGE_LAYOUT}

{_CREATE_DESIGN_COLLECTOR_BACKGROUND}**Creative review before generation.** Use the original photos as the authority for every face, pose, uniform and object. Inspect the scaled layout at 250 px wide and compare facial sizes at intended print size. Check the first read, supporting image's purpose and movement toward title and plaque. Where a verified venue view is available, check its visible feature; otherwise check that the fallback makes no actual-venue claim. Correct scale, crop, contrast, spacing or title here; honour explicit locks. Record the direction in REVIEW NOTES, lock it and proceed automatically. Without master access, review the reserved footprint provisionally; defer original-layer checks until access returns.

**3. Generate the collector treatment once**

Use the reviewed layout as the exact composition reference for one creative image-generation call. Include the hero and selected secondary source with its distinct story role as placement references. Generate the surrounding venue treatment, abstract artwork and lighting around the locked photographs. Exclude the official plaque and number from generation; show only their reserved footprint in the generation reference. Keep the output flat artwork without physical frame, room or wall. Display it as **Composition draft · generation 1 of 1**.

Assemble with original masked photographs, reviewed typography, collector border and original plaque pair. Any generated people or sporting objects are placement guides only: cover them completely with verified sources and remove exposed generated silhouettes. Keep the abstract treatment adjustable. A visual criticism goes to PSD finishing and never triggers another generation.

Retry a transient tool failure once per authorised method. Retry image generation once only if a technical failure produced no usable output. Keep a photo-only fallback clearly provisional. If access requires sign-in or permission, use an already authorised method. For moderation, record the exact stated reason, use only a compliant request within the existing allowance, and never retry by disguising or bypassing a rejection. Defer dependent steps and finish independent work. Reconcile any uncertain write by verifying its exact path, identity and contents before retrying.

**4. Inspect and finish the assembled PSD**

{CREATE_DESIGN_AUTHENTICITY_CHECK}{REVIEW_RELATIONSHIPS}
**5. Save and verify one final Review PSD**

On a master copy, place the inspected composite in **FINAL POLISHED ARTWORK**, retaining the hero and any supporting photograph on separate editable masked layers. Preserve the unmodified generation in a hidden **ORIGINAL EDITABLE ARTWORK** group and document defects or limitations in hidden **REVIEW NOTES**. Retain the verified master canvas and working layers.

{REVIEW_SAVE_NAMING}

If master access was deferred, first test both plaque placements as specified above. Verify the chosen position against the final composite: both original layers visible once, number editable and aligned inside the plaque, text legible, and safe clearance from hero, title and border. Adjust only a specific placement defect with matching transforms. Save just the final **`[Product Title].psd`** directly in {REVIEW_FOLDER}/ in create-only mode. Use an unused version suffix if occupied. Confirm its Dropbox ID, path, revision and byte size. Reopen that saved revision and inspect the actual rendered artwork, master dimensions, colour profile, hidden original, safe border and both collector layers. Use Photoshop or a capable PSD parser plus a rendered preview to verify the original editable SC_EDITION_NUMBER name, text data, transform, position and alignment inside SC_EDITION_PLAQUE. If a required file check is pending, preserve available work and report the specific missing verification.

**6. Write the Smart Upload JSON and deliver**

{MOTORSPORT_JSON}

After verifying the PSD, create the matching UTF-8 **[Final PSD stem].upload.json** in {REVIEW_METADATA_FOLDER}/, in create-only mode. Create the subfolder if needed. Read the JSON back and verify it points to that exact saved PSD. Include design_title, design_story, sport, league, teams and athletes (arrays), intended_collections (confirmed Shopify IDs or handles), upload_intent (new_product), existing_shopify_product_id (null), dropbox_file_id, dropbox_revision, dropbox_path and review_status. Use null or empty arrays for unknown fields and describe missing evidence in review_notes. Use ready_for_review only when the visual, PSD and metadata checks pass. Use needs_attention for unresolved quality or metadata. A shared athlete or similar title alone does not make this a refresh. Follow any automatic queue receipt instructions.{market_note}

Display the reopened saved PSD render as **Final artwork · rendered from the saved PSD**. If saving or inspection remains pending, label the available result provisional instead. Lead with any unresolved visual failure, then report verified PSD and JSON paths and pending checks. File validity does not establish visual quality. Completion requires one full generation, verified final Review PSD, matching JSON and final display. Preserve completed work if a later step is blocked. Shopify publication is a separate action."""


@lru_cache(maxsize=1)
def _template():
    return TEMPLATE.read_text(encoding="utf-8")


def article_html(item, *, heading=None, allow_ads=False, legend=False, design_status=None, design_key=None):
    title = " ".join(item["title"].split())
    label = heading or title
    markets = display_markets(item)
    market_label = ""
    if legend and len(markets) > 1:
        market_label = f'<small class="sc-brief-secondary">Secondary: {escape(", ".join(markets[1:]))}</small>'
    elif not legend and markets:
        label += f' ({", ".join(markets)})'
    enabled = bool(design_key) and design_status == 'Needs attention'
    reason = ('Add this design to the Design Companion queue' if enabled else
              'Already in the Design Companion queue' if design_status in ('Pending', 'Opening ChatGPT', 'Generating') else
              'This design has already been made or uploaded' if design_status else
              'Queue status unavailable. Refresh Home.')
    actions = (
        f'<button type="button" data-design-key="{escape(design_key or "", quote=True)}" '
        f'title="{reason}"{ "" if enabled else " disabled"}>Add to Queue</button>'
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
        return design_statuses.get(identity(edition['date'], section, item), 'Needs attention')
    def key(section, item):
        return identity(edition['date'], section, item)
    rows = "".join(
        article_html(item, heading=f'{rank}. {item["title"]}', allow_ads=allow_ads, design_status=status("recommendations", item), design_key=key("recommendations", item))
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
    legend_rows = "".join(article_html(item, heading=f'{label} {item["title"]}', allow_ads=allow_ads, legend=True, design_status=status("legends", item), design_key=key("legends", item))
                          for label, item in legends)
    if not legend_rows:
        legend_rows = '<p class="sc-legends-empty">No Legends Brief entries for this edition.</p>'
    legend_section = ('<section class="sc-sports-stories sc-legends" aria-label="Legends Brief">'
                      f'<h3>Legends Brief</h3>{legend_rows}</section>')
    return (_template().replace("<!-- CALENDARS -->", tables)
            .replace("<!-- LEGENDS -->", legend_section).replace("<!-- RECOMMENDATIONS -->", stories))
