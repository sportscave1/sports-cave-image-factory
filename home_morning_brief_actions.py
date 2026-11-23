"""Compact recommendation rows and their ChatGPT project handoff."""

from functools import lru_cache
from html import escape
from pathlib import Path
import re
from urllib.parse import urlencode

from design_execution_flow import CONTINUOUS_DESIGN_FLOW
from design_new_composition import (
    POSTER_IMAGE_SELECTION, COMPLEMENTARY_IMAGES, COMPLETE_COMPOSITION, COLLECTOR_TYPOGRAPHY,
    PURPOSEFUL_ABSTRACT, REVIEW_RELATIONSHIPS, CREATIVE_REVIEW,
)
from design_photographic_composition import (
    STORY_FIRST_CROP, GENERATE_PHOTOGRAPHIC_UNIT, FINAL_PHOTOGRAPHIC_REVIEW,
)
from design_collector_assets import NEW_BADGE_LAYOUT
from design_signature_free import SIGNATURE_FREE_COMPOSITION
from design_collector_titles import (
    NEW_DESIGN_TITLE_GUIDANCE, REFRESH_TITLE_GUIDANCE,
    TIMELESS_ARTWORK_GUIDANCE, TIMELESS_ARTWORK_CHECK,
)
from design_collector_background import NEW_BACKGROUND_RESEARCH, NEW_COLLECTOR_BACKGROUND
from design_motorsport import (
    MOTORSPORT_ARTWORK, MOTORSPORT_JSON, MOTORSPORT_PLACEMENT,
    MOTORSPORT_INTEGRATION, MOTORSPORT_FINISH_CHECK,
)
from design_subject_authenticity import (
    CREATE_DESIGN_AUTHENTICITY_CHECK,
)
from home_brief_calendar import MARKETS, PRODUCT_QUERY, calendar_rows, display_markets, product_handle
from psd_directory import REVIEW_FOLDER, REVIEW_METADATA_FOLDER
from sports_categories import CANONICAL_SPORT_CATEGORIES

PROJECT_URL = "https://chatgpt.com/g/g-p-6a1e449948e881919c1e345006d63654/project"
REVIEW_SAVE_NAMING = """**Review filename and website product title**

Before saving, form the full website product title: [ARTWORK NAME] – [VERIFIED SUBJECT] Wall Art. Preserve the emotional headline, add the verified athlete/team/rivalry/event, and use one spaced en dash. Example: Forever Panda – Pablo Sandoval Wall Art. Use readable spaces, never a URL slug or headline-only filename. Keep the emotional headline on the artwork.

Use that full title for the PSD stem and JSON design_title; match the JSON basename to the saved PSD, including collision suffixes. Verify filename, JSON, Dropbox ID, revision and path together. Apply the website’s 60-character title rule without truncating or inventing identity.

"""
TEMPLATE = Path(__file__).parent / "components" / "morning_brief_actions.html"


META_AD_HEADING = re.compile(r"^(?:recommended|suggested)\b.*\bmeta\b.*\bad\b", re.I)
META_AD_COPY = re.compile(r"^(?:headline|primary text|description|cta|call to action)\s*:", re.I)

_CREATE_DESIGN_BORDER_RULES = """**Story-led collector border and print safety**

Choose the border with the composition before generation. Use the established Sports Cave vocabulary of fine metallic pinlines, layered keylines, precise spacing and restrained collector accents; choose the construction that belongs to this sport, era, title and photographic treatment. A clean single hairline can suit a minimal contemporary piece; finely spaced twin keylines can suit a heritage collectible; a restrained stepped or chamfered perimeter can echo track or court geometry; small matched plaque-inspired accents can suit an archival tribute. These are options, not elements to combine or a rotation to follow. A plain refined border is valid only as a deliberate story-led choice within the complete composition, not a default repeated across designs; consider the established alternative constructions in this same layout review. Corner ornaments are optional, never the default. Vary structure when the story supports it, rather than repeating one rectangle with small changes to its corner marks. Keep the border secondary to the athlete and gold title, with restrained antique gold or a compatible muted metallic finish. Avoid bulky frames, heavy filigree, bright yellow gradients and broadcast graphics. This direction replaces mandatory corner returns, compulsory decoration and universal single-rule restrictions in older new-design guidance; honour explicit user locks and established series templates.

Show the chosen border in the scaled layout and carry its exact geometry into generation 1: line count, stroke weight, spacing, corner construction and any small accent. Use one coherent perimeter system, with an uninterrupted outer keyline on all four sides. Construct one corner and mirror or rotate that same geometry for the other three: equal offsets, stroke weights, radii or chamfer lengths, and accent dimensions. Decide whether accents join the keyline or remain detached with a measured gap, and use that relationship consistently at every corner. No accidental overlaps, stray spurs, doubled strokes, mismatched brackets or missing joins. Material grain may age the finish subtly without eroding its geometry. Record the chosen construction and its story connection briefly in REVIEW NOTES within the existing layout review; no extra approval or generation is required.

The outermost border detail sits 3% of the shorter canvas dimension inside every edge: 60 px on the 2835 × 2004 master. Scale that inset proportionally for the generation resolution. Carry venue tones, texture and selected abstract marks through the border to every canvas edge; keep visible artwork in all four outer margins. Keep faces, hands, fingertips, defining equipment, lettering and plaque visibly clear inside the innermost border detail, including accents. Check at 250 px before generation and after source restoration. For grazing or crossing, move or proportionally scale the whole source photograph minimally, preserving dominance, pose and hand-to-equipment contact; never crop, distort or fade defining details. Preserve successful title and abstraction. Framing clearance is separate from printer-required bleed.

Inspect all four sides and corners at 100% and 250 px in generation 1 and the assembled PSD. Check the selected line count, equal inset, straightness, stroke weight, keyline spacing and matched corner joins against the layout. Within the existing finishing pass, correct only defective border geometry on separate editable shape/path layers, reusing and mirroring the same corner construction. Remove or locally mask faulty generated border strokes so the repair leaves one clean system, preserving the underlying artwork and safe clearance. Retain a successful generated border; do not add another frame over it or regenerate the artwork for a border defect.

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


def _prompt(title, story, *, edit=None, primary_market="", refresh_product_id=None,
            preserve_refresh_edition=False):
    context = _story_without_meta_ad(story)
    if edit is not None:
        from design_review_prompt import build_edit_prompt
        return build_edit_prompt(title, context, edit["source"], edit["metadata"])

    handoff_fields = 'upload_intent (new_product), existing_shopify_product_id (null)'
    handoff_identity = 'A shared athlete or similar title alone does not make this a refresh.'
    if refresh_product_id is not None:
        target = str(refresh_product_id).removeprefix('gid://shopify/Product/')
        if not re.fullmatch(r'[1-9][0-9]*', target):
            raise ValueError('A refresh needs an exact existing Shopify product ID.')
        target = 'gid://shopify/Product/' + target
        handoff_fields = ('upload_intent (existing_product_refresh), '
                          f'existing_shopify_product_id ("{target}"), design_origin (designs_to_refresh)')
        handoff_identity = (
            f'This is new artwork for the existing product {target}. Keep that exact target even when '
            'the title, photographs or collector concept change. Never label this handoff new_product '
            'or substitute another target. Read back the intent, origin and exact product ID with the '
            'PSD binding. Publishing from Review must update only this existing product, preserving its '
            'ID, handle/URL, variants, sales and edition history, counters and inventory. If the target '
            'cannot be verified, retain the Review artwork as needs_attention; never create another product.'
        )
    story_guidance = 'Choose a story supporters would still want to display in five years. Use timeless player, team, rivalry or legacy angles for routine results; verified landmarks, iconic moments or farewells for event tributes. Express the story through authentic photographs and a strong emotional title. Keep results, scores, statistics, rounds, dates and times in research notes and metadata only, never as supporting artwork copy. This applies equally to routine tributes and defining-event editions.'
    title_guidance = NEW_DESIGN_TITLE_GUIDANCE
    typography = _CREATE_DESIGN_TYPOGRAPHY
    save_naming = REVIEW_SAVE_NAMING
    edition_check = ''
    if preserve_refresh_edition:
        story_guidance = 'Use the existing edition story as the research brief. Verify its subject, event or career angle, era and emotional meaning from the current artwork and listing. Find stronger authentic sources for that same story; do not replace it with a different moment or a new title concept. Preserve the emotional headline and any existing quotation. Keep verified story-defining dates, scores, rounds, times and statistics in research notes and metadata only; remove their standalone artwork captions without changing the edition story or visual direction.'
        title_guidance = REFRESH_TITLE_GUIDANCE
        typography = typography.replace(
            'Revise a conventional headline merely filling an empty corner within this layout review.',
            'Refine a conventional headline placement within this layout review while preserving the exact existing wording.',
        )
        save_naming = """**Review filename and existing website product title**

Keep the existing full website product title verbatim for JSON design_title and the PSD stem. Preserve the existing printed headline and any quotation exactly on the artwork; distinguish them from the full listing title. Use the normal safe filename handling and an unused collision suffix where required, with a matching JSON basename. A filename suffix does not rename the edition. Do not recompose, shorten or optimise the existing title to fit a new-product naming rule. Verify filename, JSON, Dropbox ID, revision and path together.

"""
        edition_check = 'Within this existing inspection, compare the headline and any quotation character by character with the original edition, and verify the same story, moment, era and emotional meaning in the new photographs and setting. Correct wording drift locally while preserving the upgraded treatment; record unresolved source or factual uncertainty under the existing needs_attention rules and continue Review delivery.\n\n'
        handoff_identity = (
            handoff_identity.replace('even when the title, photographs or collector concept change',
                                     'while its photographs, composition and collector finish are upgraded')
            + ' Keep design_title equal to the existing full product title and design_story faithful to the '
            'same edition narrative, moment and quotation; describe the preserved story rather than inventing '
            'a new concept from the new images. Verify these fields against the existing listing and artwork.'
        )
    market_note = (f' Include primary_market = "{primary_market}" in the design JSON for downstream ad targeting.'
                   if primary_market in {'AUS', 'USA', 'UK', 'CA', 'CAN', 'NZ'} else '')
    return f"""Sports Cave event: {title}

**Start the authorised new-design job**

{CONTINUOUS_DESIGN_FLOW}Read SPORTS-CAVE-LIMITED-EDITION-COLLECTOR-DESIGNS.txt once for this job. Follow the current brief, job instructions and shared creative standards. For this new-design job, the integration rules below supersede older cutout-only compositing and mandatory whole-subject replacement instructions; photographic identity and factual accuracy remain mandatory. The integrated collector composition below governs creative layout across New Design, Refresh and Edit within the requested scope. Preserve authentic photographic units while composing venue, supporting moment, abstraction, title, exact plaque footprint and border together; source fidelity does not lock the original background or dictate a photo-first layout. These directions supersede conflicting photo-first, optional collector-treatment, pasted-photo and tiny-patch defaults in older guides, including the referenced project file. Treat Decision, Timing, Recommendation, Monitor or Wait in the brief as research context. Proceed through research, composition planning, one creative generation, assembly and finishing, then one verified final PSD and matching JSON in Design Studio Review. Display references/artwork and continue without pausing for approval.

**Source brief — research context, not artwork copy**

{context}

**1. Research the story, sources and master**

Use authorised read-only Shopify reports for comparable bestsellers and a lower-selling print where supported. If unavailable, use verified storefront bestsellers or approved references in the closest comparable sport or collector collection. Treat unranked products as style references only. Record evidence or gaps in REVIEW NOTES; draw original cues without attributing sales to design.

{TIMELESS_ARTWORK_GUIDANCE}{story_guidance}

{title_guidance}{POSTER_IMAGE_SELECTION}

{MOTORSPORT_ARTWORK}

{COMPLEMENTARY_IMAGES}{NEW_BACKGROUND_RESEARCH}Inspect designs-canvas.psd dimensions, orientation, resolution, profile, clearance, guides and collector layers. Work from a copy. Without access, use verified dimensions, reserve the plaque footprint and continue independently. Keep master-dependent assembly, saves and verification pending.

**2. Prepare the complete composition before generation**

{COMPLETE_COMPOSITION}{STORY_FIRST_CROP}{MOTORSPORT_PLACEMENT}{_CREATE_DESIGN_BORDER_RULES}{typography}

{NEW_BADGE_LAYOUT}

{_CREATE_DESIGN_COLLECTOR_BACKGROUND}{CREATIVE_REVIEW}

**3. Generate the collector treatment once**

Carry the timeless artwork rule into the image-generation request: render only the locked emotional title and necessary subject names. Do not generate a score, stat, round, time, date or venue/result caption from the brief or reference images. The original edition badge is restored separately below.

{GENERATE_PHOTOGRAPHIC_UNIT}{MOTORSPORT_INTEGRATION}Use the badge-hidden reviewed layout as the composition reference for one creative image-generation call. Include the hero and selected secondary source with its distinct story role as placement references, original photographs and venue references. For rivalries, include both primary rivals and their verified opposing-profile or genuine competition sources; carry the reviewed inward gaze, fierce natural expressions, balanced scale and interaction into this single generation. Preserve both rivals as the primary read through integration and finishing; incidental supporting imagery and venue remain subordinate. Carry the exact sources, verified defining moment, signature gesture or peak action, emotional payoff, final athlete depiction count, supporting role and selected tonal hierarchy into the request. Use those selected photographs as actual image inputs, not just names or text descriptions. Preserve the researched poster moment and its decisive silhouette; do not substitute a routine pose, training kit or generic celebration during generation. For individual tributes, keep the verified action/emotion pairing: never two emotional shots. Rivalry face-offs may use two intense opposing portraits; every darts design must retain its genuine throwing-action photograph. Do not turn a reaction photograph into invented sporting action. Carry the five reviewed collector decisions into this generation: exact venue feature and its source, meaningful supporting-image role or justified exception, connecting abstract detail, title–badge anchor and border construction. For hockey and basketball, including NBA and Olympic basketball, specify the dark foundation with fine brushed antique-gold contours or inlays, sparse verified team-colour marks and the selected venue feature retained subtly in place and recognisable. For other sports preserve the chosen palette and photographic or archival foundation with restrained connecting collector abstraction. Preserve source face, expression, natural skin texture, anatomy, hand-to-equipment relationships, uniform lettering and contact. No glossy skin smoothing or invented figures. Generate the complete flat collector artwork, including a naturally integrated photographic subject, finished title lettering, venue and collector treatment. The reviewed cutout layout is a positioning and scale plan, not the final rendering style. Use the best available selected source images as identity and detail references. Resolve hair and fabric edges, source-background spill, local light direction, exposure, colour temperature, grain, sharpness, depth, contact shadows and plausible environmental overlap as one coherent scene during this generation. Preserve every facial feature, gaze, expression, age and natural skin detail; retain the real pose, anatomy, kit and equipment. Do not reinterpret identity, beautify faces, invent missing anatomy or hide weak detail under blur or effects. Avoid a sticker-like outline, bright fringe, hard rectangular crop, arbitrary waist fade or a differently lit pasted-on figure. Keep successful natural photographic transitions rather than forcing every subject into an isolated silhouette. Copy the locked title verbatim and repeat the selected border geometry above, including all four sides, line count, stroke weight, spacing, matched corner construction, optional accents and calculated inset. Use the reviewed border choice rather than default corner brackets. Exclude plaque, number, placeholder outlines and seals; generate a continuous natural surface in their reserved area. Keep the output without physical frame, room or wall. Display it as **Composition draft · generation 1 of 1**.

Inspect generation 1 beside the photographs for identity, natural texture and the selected depiction count during the finishing pass; continue delivery with any unresolved limitations recorded. Record discrepancies for local source restoration, without another generation or approval pause. Generation 1 becomes the visual master for finishing, with successful creative decisions preserved and missing selected collector elements treated as named composition defects to correct locally. On a master copy, keep its untouched original in hidden **ORIGINAL EDITABLE ARTWORK** and a visible working copy beneath **FINAL POLISHED ARTWORK** correction layers. Preserve successful lettering, abstraction, venue, lighting, controlled reflections and border, including the reviewed dark abstract hierarchy and recognisable venue for hockey and basketball. Never reconstruct working surroundings from stretched samples, generic shapes or broad photographic strips.

Place the original plaque pair at the reviewed layout transform and verify its title-group anchor in the final composite. Limit other PSD work to a named defect or required photographic source restoration, including local correction of missing selected venue detail, lost supporting imagery, disconnected abstraction, weak title–badge integration or defective border construction. Use verified source layers, editable type and paths, and source-derived collector detail; do not turn finishing into an unrelated redesign or another generation. Retain successfully integrated generated subjects when side-by-side comparison verifies faithful identity, expression, anatomy and sporting details. Do not automatically paste whole source cutouts over them. Apply the coherent original-photo repair method in the existing finishing inspection below on separate editable masked layers; preserve successful generated surroundings. Keep the abstract treatment adjustable through masks. A visual criticism never triggers another generation.

Retry a transient tool failure once per authorised method. Retry image generation once only if a technical failure produced no usable output. Keep a photo-only fallback clearly provisional. If access requires sign-in or permission, use an already authorised method. For moderation, record the exact stated reason, use only a compliant request within the existing allowance, and never retry by disguising or bypassing a rejection. Defer dependencies; finish independent work. Verify an uncertain write’s exact path, identity and contents before retrying.

**4. Inspect and finish the assembled PSD**

{CREATE_DESIGN_AUTHENTICITY_CHECK}{MOTORSPORT_FINISH_CHECK}{edition_check}{TIMELESS_ARTWORK_CHECK}{REVIEW_RELATIONSHIPS}{FINAL_PHOTOGRAPHIC_REVIEW}
**5. Save and verify one final Review PSD**

Retain the assembled layer structure, visible generation foundation, verified master settings and working layers. Document defects or limitations in hidden **REVIEW NOTES**.

{save_naming}

If master access was deferred, first test both plaque placements as specified above. Verify the chosen position against the final composite: both original layers visible once, number editable and aligned inside the plaque, text legible, and safe clearance from hero, title and border. Correct a specific placement or title-group integration defect with matching plaque-pair transforms and editable title placement, preserving the original layers and exact wording. Save just the final **`[Product Title].psd`** directly in {REVIEW_FOLDER}/ in create-only mode. Use an unused version suffix if occupied. Confirm its Dropbox ID, path, revision and byte size. Reopen that saved revision and inspect the actual rendered artwork, master dimensions, colour profile, hidden original, safe border and both collector layers. Use Photoshop or a capable PSD parser plus a rendered preview to verify the original editable SC_EDITION_NUMBER name, text data, transform, position and alignment inside SC_EDITION_PLAQUE. If a required file check is pending, preserve available work and report the specific missing verification.

In that inspection, compare sources at 100% for authenticity and generation 1 beside the final render at equal 250 px widths: hero or both primary rivals and their face-off/competitive relationship, the selected defining action and emotional payoff, abstraction, venue, reflections, lettering, border and plaque. Restore surroundings from generation 1 where finishing flattened texture, introduced seams or weakened composition, retaining the reviewed dark abstract hierarchy and recognisable subdued venue for hockey and basketball, including the quiet dark areas, integrated gold detail and restrained team-colour balance; retain source/text corrections, whole-interaction repairs, verified venue and supporting-image restorations, title–badge integration corrections and border-geometry repairs. Do not restore an incomplete generation over those verified collector-composition corrections. Never restore a warped generated face, hand, ball or other repaired detail over its verified source correction. Retain verified motorsport integration repairs as well; never reinstate a corrected cutout seam, halo or floating tyre placement from generation 1. Do not restore malformed generated corners over a corrected border. Record unresolved loss as needs_attention.

**6. Write the Smart Upload JSON and deliver**

{MOTORSPORT_JSON}

For JSON sport, use one exact canonical upload category: {', '.join(CANONICAL_SPORT_CATEGORIES)}. Basketball in the NBA must save sport="NBA" and league="NBA"; use "Ice Hockey" for NHL and "Football" for association football. For motorsport use the verified specific discipline as instructed above. Resolve this from the researched subject, league and event before writing, then read back sport with the PSD binding; never omit a known sport or use a broad alias when its canonical category is established. Retain the existing uncertainty handling for genuinely unknown sport.

After verifying the PSD, create the matching UTF-8 **[Final PSD stem].upload.json** in {REVIEW_METADATA_FOLDER}/, in create-only mode. Create the subfolder if needed. Read the JSON back and verify it points to that exact saved PSD. Include design_title, design_story, sport, league, teams and athletes (arrays), intended_collections (confirmed Shopify IDs or handles), {handoff_fields}, dropbox_file_id, dropbox_revision, dropbox_path and review_status. Use null or empty arrays for unknown fields and describe missing evidence in review_notes. Use ready_for_review when PSD and metadata checks pass and no known limitations remain; this status invites the user’s manual visual review. Use needs_attention for unresolved quality or metadata without delaying Review delivery. {handoff_identity} Follow any automatic queue receipt instructions.{market_note}

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
    enabled = bool(design_key)
    reason = ('Add this design to the Design Companion queue' if enabled else
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
            'Deleted · ready to redo': ('!', 'attention'),
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
    for field, caption in (("opportunity_status", "Recommendation"), ("sales_rationale", "Sales potential")):
        if item.get(field):
            paragraphs.append(f'<p><strong>{caption}:</strong> {escape(item[field])}</p>')
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
    saved = edition or {}
    summary = saved.get("summary")
    if not summary:
        # Earlier editions remain readable immediately, before the next scheduled run.
        text = saved.get("full_brief", "")
        summary = next((p.strip() for p in text.split('\n\n') if len(p.strip()) > 100 and not p.lstrip().startswith(('#', '{'))), '')
        summary = summary[:1800] or ' '.join(item['title'] for item in saved.get('recommendations', ()))
    rows = f'<p class="sc-daily-summary">{escape(summary)}</p>' if summary else ''
    full_brief = saved.get("full_brief") or '\n\n'.join(
        f'{item["title"]}\n{item["recommendation"]}' for item in saved.get('recommendations', ()))
    legends = _ranked_legends((edition or {}).get("legends", ()))
    if full_brief:
        if legends:
            full_brief += '\n\nLegends Brief\n\n' + '\n\n'.join(
                f'{label} {item["title"]}\n{item["recommendation"]}\n' + '\n'.join(
                    f'{link["label"]}: {link["url"]}' for link in item['links'])
                for label, item in legends
            )
        for section, caption in (("rivalries", "Rivalries Brief"), ("design_recommendations", "Design recommendations")):
            if saved.get(section) and caption.casefold() not in full_brief.casefold():
                full_brief += '\n\n' + caption + '\n\n' + '\n\n'.join(
                    f'{rank}. {item["title"]}\n{item["recommendation"]}\n'
                    + '\n'.join(f'{link["label"]}: {link["url"]}' for link in item['links'])
                    for rank, item in enumerate(saved[section], 1))
        rows += (
            '<button type="button" class="sc-full-brief" aria-haspopup="dialog">Read the full Morning Brief</button>'
            '<dialog class="sc-cal-dialog sc-sports-full" aria-label="Full Sports Morning Brief">'
            '<header><h3>Full Morning Brief</h3><form method="dialog"><button>Close</button></form></header>'
            f'<div class="sc-full-brief-text">{escape(full_brief)}</div></dialog>'
        )
    tables = "".join(_market_table(editions, market, today) for market in MARKETS)
    stories = f'<section class="sc-sports-stories" aria-label="Sports opportunities">{rows}</section>' if rows else ""
    picks = saved.get("design_recommendations", ())
    legend_rows = "".join(article_html(item, heading=f'{rank}. {item["title"]}', allow_ads=allow_ads,
                          design_status=status("design_recommendations", item), design_key=key("design_recommendations", item))
                          for rank, item in enumerate(picks[:4], 1))
    if not legend_rows:
        legend_rows = '<p class="sc-legends-empty">Fresh design recommendations are pending for this edition.</p>'
    legend_section = ('<section class="sc-sports-stories sc-legends" aria-label="Design recommendations">'
                      f'<h3>Design recommendations</h3>{legend_rows}</section>')
    return (_template().replace("<!-- CALENDARS -->", tables)
            .replace("<!-- LEGENDS -->", legend_section).replace("<!-- RECOMMENDATIONS -->", stories))
