"""Store the read-only design worker's daily shortlist."""

from calendar import monthrange
from datetime import date, timedelta
from html import escape
import json
import re

from design_collector_assets import BADGE_FOOTPRINT, BADGE_PLACEMENT_VERIFICATION
from design_signature_free import SIGNATURE_FREE_COMPOSITION
from design_collector_titles import COLLECTOR_TITLE_GUIDANCE
from design_collector_background import BACKGROUND_RESEARCH, COLLECTOR_BACKGROUND
from design_motorsport import MOTORSPORT_ARTWORK
from design_refresh_replacement import REVIEW_REPLACEMENT_RULE
from design_subject_authenticity import AUTHENTICITY_CHECK, IDENTITY_OVERRIDES_CONTINUITY
from home_morning_brief_actions import PROJECT_URL
from psd_directory import REVIEW_FOLDER, REVIEW_METADATA_FOLDER, ROOT as LIVE_FOLDER
from sports_sales_calendar import sydney_date
from supabase_backend import connect, get_app_setting

PATH = "/ops/design-refresh/publish"
KEY = "home_design_refresh"
MAX_PAYLOAD = 8000
LEGACY_FIELDS = {"product_id", "handle", "title", "created", "image_updated",
                 "lifetime_orders", "sessions", "suggestion"}
REVIEW_FIELDS = {"product_id", "handle", "title", "reason", "evidence",
                 "sessions", "orders", "suggestion"}
REASONS = {"low_conversion": "Weak sales signal", "artwork": "Artwork review"}
RECOMMENDATION_GUIDANCE = (
    "Write each suggestion as a testable creative problem and opportunity for a complete redesign. "
    "Describe the collector appeal, story, subject hierarchy or thumbnail recognition worth "
    "investigating. Commission fresh image research and reconsider the hero, scene, title and "
    "composition. Treat existing artwork and the recommendation as research leads. Avoid "
    "prescribing only a crop, brightness or text-size change. Weak sales warrant investigation "
    "and a creative test. They do not establish that artwork caused the result."
)


def _refresh_prompt(row, product_url):
    return f"""Create a complete new Sports Cave collector design for the verified existing product.
Use the New Product / Create Design research and creative process for both full artwork passes.

{IDENTITY_OVERRIDES_CONTINUITY}Start now. Use the project guide for reusable standards and the recommendation as research context.
Product: {row["title"]}
Shopify product ID: {row["product_id"]}
Product page: {product_url}
Research hypothesis from the Home recommendation: {row["suggestion"]}
Decision context: {row.get("evidence") or f'{row["sessions"]:,} GA4 landing sessions'}
Use the recommendation to start research and follow the evidence when it points elsewhere.
Weak sales are a reason to investigate and test a creative direction. They do not establish
that the artwork caused poor sales.

1. Find the current master PSD in Dropbox Live: {LIVE_FOLDER}/
   Match it to this product using the product ID or handle, filename and live artwork.
   Exclude the Review folder, drafts, mockups and previous refreshes. If the exact master or
   render is unavailable, continue independent research, both artwork passes and display using
   verified sources. Defer any comparison, master-dependent assembly or replacement that cannot
   be verified, and report the exact missing input.
   Open the original for read-only reference. Record its path and revision if available,
   inspect its artwork and preserve its canvas dimensions, orientation and print settings.

2. Research a fresh collector concept using the New Product workflow.
   Treat the existing artwork as a comparison baseline and product-identity reference, not a
   layout to preserve. Briefly identify its three biggest visually supported weaknesses and
   describe storefront mockup or listing presentation issues separately. Independently reconsider
   the hero photograph, supporting imagery, scene, background, title, typography, composition,
   colours and border. Preserve the verified subject identity, any defining event or rivalry
   promised by the product, official collector assets, production requirements and explicit
   user locks. Develop the new concept for that same subject and existing product.

   Review relevant verified Sports Cave bestsellers in the sport or collection where reporting
   is available. Inspect the actual artwork for story, hierarchy, typography and use of space.
   Use approved Sports Cave Collector Series examples when sales evidence is unavailable.
   Use those examples as style references.

{MOTORSPORT_ARTWORK}

   Run a fresh web image search before designing. Aim to inspect 4–8 suitable candidates on
   their original source pages and show the strongest usable references in chat as a progress
   checkpoint. Compare authentic action, achievement, celebration and legacy photographs
   appropriate to the subject. Rank story fit and emotional impact first, then recognisability,
   readable pose, composition potential and source quality at print size. For a promised event
   or rivalry, keep the imagery faithful to it. Reuse a photo from the existing PSD only when
   it wins the comparison. Consider stronger alternatives even when the existing photo is
   technically sound. Develop the headline alongside the shortlisted photos using the title guidance below. Briefly state
   the strongest hero, story, title treatment and creative direction before generating.

{COLLECTOR_TITLE_GUIDANCE}{BACKGROUND_RESEARCH}{COLLECTOR_BACKGROUND}

   {BADGE_FOOTPRINT}

3. Generate and inspect two complete designs with ChatGPT image generation.
   Pass 1 must be a complete new flat design, with a materially new composition and visual
   treatment. Supply the selected authentic photographs as identity references and relevant
   Sports Cave artwork as style references. Use the old artwork only for diagnosis and comparison.
   Cosmetic changes such as repositioning portraits, resizing text or applying a filter are
   insufficient. If the same photo or title wins the research, rebuild its presentation around
   a distinctly stronger concept. Keep the planned badge footprint clear in both passes.
   Generate the artwork itself without a frame, wall or room.

   Inspect Pass 1. In a separate full image-generation call, make Pass 2 a refinement of that
   new design. Use Pass 1 for successful composition and styling. Resolve visible weaknesses within the fresh
   concept and keep the surrounding artwork free to evolve. Do not revert to the old layout.
   If Pass 1 was unavailable after recovery, use the chosen fresh concept and verified photos
   for Pass 2. Use the New Product allowance of at most two additional generation attempts
   total across both passes, including recovery. Preserve the strongest inspected work and
   report any incomplete pass.

   Apply the source-photo checklist after each pass, correction and final assembly.

{SIGNATURE_FREE_COMPOSITION}

{AUTHENTICITY_CHECK}4. Compare and score the original, Pass 1 and Pass 2 side by side at matching full and
   thumbnail display sizes. Score photographic realism, collector appeal and Sports Cave style
   from 0 to 10 for each and report the mean and a short reason. A replacement must have a
   materially new composition and visual treatment and clearly improve all three areas:
   - Subject hierarchy and emotional impact.
   - Composition and photographic integration.
   - Typography, spacing and collector finish.
   Choose the strongest eligible redesign from either pass. Facial identity and clear improvement
   are required regardless of score. If neither pass qualifies, make any feasible
   finishing corrections and compare again, keeping any additional generation within the
   existing retry cap. If issues remain, retain the current version and
   mark any staged result needs_attention with the specific problems in review_notes.

5. Use a separate working copy to prepare a valid Photoshop PSD at the original size.
   Keep usable editable layers and place the selected generated artwork in a named layer.

{BADGE_PLACEMENT_VERIFICATION}   Save in create-only mode at a unique staging path in {REVIEW_FOLDER}/, using
   [Original PSD stem] - REFRESH - STAGING - [unique run token].psd. Reopen the staged
   PSD and confirm its exact Dropbox ID, path and revision before preparing its JSON. Verify
   the original plaque and editable text layer are visible, readable and aligned at their
   chosen position and scale in the saved PSD.
   Never claim an unverified save or rename a PNG or JPEG to .psd.

SMART UPLOAD HANDOFF METADATA

After the staged PSD is saved and verified, record its categorisation and Dropbox identity in
a UTF-8 JSON file named [Staged PSD stem].upload.json in {REVIEW_METADATA_FOLDER}/. Create
this JSON subfolder if needed and keep the staged PSD directly in Review.

Include design_title, design_story, sport, league, teams and athletes (arrays),
intended_collections (array of confirmed Shopify collection IDs or handles),
upload_intent (existing_product_refresh), existing_shopify_product_id (the exact Shopify
product ID above), dropbox_file_id, dropbox_revision, dropbox_path, review_status and cleanup_status.
Record what improved in design_story. Use the verified original product's sport and existing
collection mappings. Set review_status to ready_for_review only when the PSD is verified,
the original product link and required metadata are confirmed, and the visual comparison
passes with all visible defects resolved. Otherwise use needs_attention and document the
specific unresolved artwork issues, missing fields or incomplete checks in review_notes.
Use null or empty arrays for unknown values. Never substitute a similar product as the
refresh target.

{REVIEW_REPLACEMENT_RULE}
Display the strongest generated artwork and three-design scorecard in chat. Report what
changed and give the verified final Dropbox paths, or the staged paths and pending steps if
closeout is incomplete. If Dropbox
access, visual inspection, image generation, PSD export or upload is unavailable, explain
exactly what is blocked and report only what actually completed.
"""


def _render_candidate(row):
    product_url = f'https://www.sportscaveshop.com/products/{row["handle"]}'
    prompt = escape(_refresh_prompt(row, product_url), quote=True)
    title = escape(row["title"])
    return (
        f'<li><a href="{escape(product_url, quote=True)}"><strong>{title}</strong></a>'
        f' · {_render_evidence(row)} '
        f'<a class="sc-refresh-action" href="{PROJECT_URL}" target="_blank" '
        f'rel="noopener noreferrer" aria-label="Create Refresh for {title}" '
        f'data-refresh-prompt="{prompt}">Create Refresh</a>'
        f'<br>Redesign research lead: {escape(row["suggestion"])}</li>'
    )


REFRESH_HANDOFF = """<style>
.sc-refresh-action {display:inline-block;margin:.18rem 0;padding:.12rem .42rem;
    border:1px solid #b8aa8a;border-radius:6px;color:inherit;text-decoration:none;
    font-weight:600;white-space:nowrap}
.sc-refresh-action:hover {background:#c29a43;color:#17130c}
.sc-design-refresh p.sc-refresh-status {margin:.3rem .85rem .6rem}
</style><script>{
  const panel = [...document.querySelectorAll(".sc-design-refresh")].at(-1);
  if (panel && !panel.dataset.refreshReady) {
    panel.dataset.refreshReady = "true";
    const status = panel.querySelector(".sc-refresh-status");
    panel.addEventListener("click", event => {
      const action = event.target.closest("a[data-refresh-prompt]");
      if (!action) return;
      const prompt = action.dataset.refreshPrompt;
      const copied = () => {
        status.textContent = "Prompt copied. Paste it into Sports Cave Designs and send it.";
      };
      const fallback = () => {
        const field = document.createElement("textarea");
        field.value = prompt;
        field.style.cssText = "position:fixed;left:-9999px";
        panel.append(field);
        field.select();
        let ok = false;
        try { ok = document.execCommand("copy"); } catch {}
        field.remove();
        action.focus({preventScroll:true});
        if (ok) copied();
        else {
          status.textContent = "Copy the prompt manually and paste it into Sports Cave Designs.";
          window.prompt("Copy this prompt, then paste it into Sports Cave Designs.", prompt);
        }
      };
      if (navigator.clipboard?.writeText) {
        navigator.clipboard.writeText(prompt).then(copied, fallback);
      } else {
        fallback();
      }
    });
  }
}</script>"""


def _valid_text(value, limit):
    return isinstance(value, str) and 0 < len(value.strip()) <= limit


def _valid_count(value):
    return type(value) is int and value >= 0


def _validate_review(row):
    if (row["reason"] not in REASONS or not _valid_text(row["evidence"], 220)
            or any(row[key] is not None and not _valid_count(row[key])
                   for key in ("sessions", "orders"))):
        raise ValueError
    if row["reason"] == "low_conversion" and (
            row["sessions"] is None or row["sessions"] < 30 or row["orders"] is None
            or row["orders"] * 100 >= row["sessions"]):
        raise ValueError


def recent_ids(today):
    saved = get_app_setting(KEY, ensure_schema_first=False) or {}
    earliest = (today - timedelta(days=30)).isoformat()
    return sorted(key for key, day in saved.get("recent", {}).items()
                  if earliest <= day < today.isoformat())


def parse(raw, today):
    # Keep actionable field errors outside the legacy generic error handler.
    try:
        preview = json.loads(raw)
    except (ValueError, TypeError, RecursionError):
        preview = None
    if isinstance(preview, dict) and isinstance(preview.get("candidates"), list):
        for index, row in enumerate(preview["candidates"]):
            if isinstance(row, dict):
                for field, limit in (("title", 160), ("evidence", 220), ("suggestion", 220)):
                    value = row.get(field)
                    if isinstance(value, str) and len(value.strip()) > limit:
                        raise ValueError(f"candidates[{index}].{field} exceeds {limit} characters; shorten and resubmit.")
    try:
        edition = json.loads(raw)
        if (not isinstance(edition, dict) or set(edition) != {"date", "candidates"}
                or edition["date"] != today.isoformat()):
            raise ValueError
        candidates = edition["candidates"]
        if not isinstance(candidates, list) or len(candidates) > 3:
            raise ValueError
        year, month = divmod(today.year * 12 + today.month - 7, 12)
        month += 1
        cutoff = date(year, month, min(today.day, monthrange(year, month)[1]))
        ids = set()
        for row in candidates:
            if not isinstance(row, dict) or set(row) not in (LEGACY_FIELDS, REVIEW_FIELDS):
                raise ValueError
            if (not re.fullmatch(r"[0-9]{1,20}", row["product_id"]) or row["product_id"] in ids
                    or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,250}", row["handle"])
                    or not all(_valid_text(row[key], limit)
                               for key, limit in (("title", 160), ("suggestion", 220)))):
                raise ValueError
            if set(row) == REVIEW_FIELDS:
                _validate_review(row)
            elif (type(row["lifetime_orders"]) is not int or row["lifetime_orders"] != 0
                  or not _valid_count(row["sessions"]) or row["sessions"] == 0
                  or date.fromisoformat(row["created"]) >= cutoff
                  or date.fromisoformat(row["image_updated"]) > cutoff):
                raise ValueError
            ids.add(row["product_id"])
    except (ValueError, TypeError, KeyError, RecursionError):
        raise ValueError("Enter today's verified shortlist with up to three eligible products.") from None
    return edition


def publish(raw, user):
    today = sydney_date()
    edition = parse(raw, today)
    with connect() as conn, conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO app_settings(key,value,updated_at) VALUES (%s,'{}'::jsonb,now()) ON CONFLICT DO NOTHING",
            (KEY,),
        )
        cursor.execute("SELECT value FROM app_settings WHERE key=%s FOR UPDATE", (KEY,))
        previous = cursor.fetchone()["value"]
        if previous.get("date", "") > edition["date"]:
            raise ValueError("A newer shortlist is already published.")
        earliest = (today - timedelta(days=30)).isoformat()
        recent = {key: day for key, day in previous.get("recent", {}).items() if day >= earliest}
        for row in edition["candidates"]:
            key = row["product_id"]
            if key in recent and recent[key] != edition["date"]:
                raise ValueError("A suggested product appeared in the last thirty days.")
            recent[key] = edition["date"]
        cursor.execute("UPDATE app_settings SET value=%s::jsonb,updated_at=now() WHERE key=%s",
                       (json.dumps({**edition, "recent": recent}), KEY))
    return edition


def render_html(today):
    # No catalogue, companion or prompt work until the popup is opened.
    from pathlib import Path
    return (Path(__file__).parent / 'components/home_refresh_queue.html').read_text(encoding='utf-8')


def _render_evidence(row):
    if "reason" in row:
        return f'{REASONS[row["reason"]]} · {escape(row["evidence"])}'
    return f'{row["sessions"]:,} GA4 landing sessions'
