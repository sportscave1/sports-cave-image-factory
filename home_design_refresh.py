"""Store the read-only design worker's daily shortlist."""

from calendar import monthrange
from datetime import date, timedelta
from html import escape
import json
import re

from design_refresh_replacement import REVIEW_REPLACEMENT_RULE
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


def _refresh_prompt(row, product_url):
    return f"""Redesign an existing Sports Cave collector artwork for review.

Product: {row["title"]}
Shopify product ID: {row["product_id"]}
Product page: {product_url}
Refresh recommendation: {row["suggestion"]}
Decision context: {row.get("evidence") or f'{row["sessions"]:,} GA4 landing sessions'}

1. Find the current master PSD in Dropbox Live: {LIVE_FOLDER}/
   Match it to this product using the product ID or handle, filename and live artwork.
   Exclude the Review folder, drafts, mockups and previous refreshes. If you cannot verify the
   match or visually inspect the PSD, ask for the exact PSD or a usable preview and stop.
   Open the original for read-only reference. Record its path and revision if available,
   inspect its artwork and preserve its canvas dimensions, orientation and print settings.

2. Diagnose the artwork and choose a creative direction.
   Treat the refresh recommendation as a hypothesis. Inspect the verified original artwork
   for collector appeal, subject hierarchy, photographic integration, typography and
   thumbnail recognition. Briefly identify its three biggest weaknesses with visual evidence.
   Describe any storefront mockup or listing presentation issues separately. State the stronger
   creative direction and which weaknesses it addresses, then execute it.

3. Use ChatGPT image generation to create a full upgraded flat artwork. Use the project's
   approved Sports Cave Collector Series references and deliver the artwork itself without a
   frame, wall or room. This refresh explicitly overrides the project's "change only the
   specified element" rule for composition, scale and placement of existing subjects,
   typography, effects, background, border and spacing. Rebuild those elements where the
   diagnosis supports it. Keep elements that already work.

   Preserve each athlete's authentic identity, facial features, expression, anatomy, pose,
   uniform, team details, era and sporting story. Keep faces realistic and free of warping.
   Preserve verified signatures and logos, and reuse the exact official plaque and edition
   assets from the source. Keep the original canvas and print settings. Where generation
   changes photographic details, restore the authentic source imagery with precise masking
   and natural blending. Match edges, lighting and grain to the composition. Reject rectangular
   source overlays, visible seams, ghosting and abrupt cutoffs.

4. Before saving, compare the original and refresh side by side at matching display sizes,
   first full-size and then at thumbnail size. After each pass and on the assembled PSD,
   compare each face at 100% with verified source photography. Check eyes and gaze, nose,
   mouth and teeth, jaw, ears, hairline, expression and natural skin texture. Correct any
   feature loss, AI warping or visible patches with precisely masked source pixels and
   recheck the blend. A candidate with unresolved facial distortion or unverified facial
   fidelity needs_attention. Require a clear, meaningful improvement in all three areas:
   - Subject hierarchy and emotional impact.
   - Composition and photographic integration.
   - Typography, spacing and collector finish.
   A larger name, tighter crop or brighter gold alone is insufficient. If the refresh is
   weaker overall, falls short on any of the three criteria or has visible defects, revise it
   and repeat the comparison before saving. Use needs_attention for unresolved issues and
   record the specific problem in review_notes.

5. Use a separate working copy to prepare a valid Photoshop PSD at the original size.
   Keep usable editable layers where available and place the generated artwork in a named
   layer. Save it in create-only mode at a unique staging path in {REVIEW_FOLDER}/, using
   [Original PSD stem] - REFRESH - STAGING - [unique run token].psd. Reopen the staged
   PSD and confirm its exact Dropbox ID, path and revision before preparing its JSON.
   Never claim an unverified save or rename a PNG or JPEG to .psd.

SMART UPLOAD HANDOFF METADATA

After the staged PSD is saved and verified, record its categorisation and Dropbox identity in
a UTF-8 JSON file named [Staged PSD stem].upload.json in {REVIEW_METADATA_FOLDER}/. Create
this JSON subfolder if needed and keep the staged PSD directly in Review.

Include design_title, design_story, sport, league, teams and athletes (arrays),
intended_collections (array of confirmed Shopify collection IDs or handles),
upload_intent (existing_product_refresh), existing_shopify_product_id (the exact Shopify
product ID above), dropbox_file_id, dropbox_revision, dropbox_path, and review_status.
Record what improved in design_story. Use the verified original product's sport and existing
collection mappings. Set review_status to ready_for_review only when the PSD is verified,
the original product link and required metadata are confirmed, and the visual comparison
passes with all visible defects resolved. Otherwise use needs_attention and document the
specific unresolved artwork issues, missing fields or incomplete checks in review_notes.
Use null or empty arrays for unknown values. Never substitute a similar product as the
refresh target.

{REVIEW_REPLACEMENT_RULE}
Display the generated artwork in chat, report what changed, and give the verified final
Dropbox paths, or the staged paths and pending steps if closeout is incomplete. If Dropbox
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
        f'<br>{escape(row["suggestion"])}</li>'
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
    saved = get_app_setting(KEY, ensure_schema_first=False) or {}
    handoff = ""
    if saved.get("date") != today.isoformat():
        body = "<p>Today's shortlist is pending.</p>"
    else:
        items = "".join(_render_candidate(row) for row in saved["candidates"])
        body = f"<ul>{items}</ul>" if items else "<p>No eligible designs were verified today.</p>"
        if items:
            body += '<p class="sc-refresh-status" role="status"></p>'
            handoff = REFRESH_HANDOFF
    return (
        '<details class="sc-meta-insight sc-design-refresh">'
        f'<summary>Designs to Refresh</summary>{body}</details>{handoff}'
    )


def _render_evidence(row):
    if "reason" in row:
        return f'{REASONS[row["reason"]]} · {escape(row["evidence"])}'
    return f'{row["sessions"]:,} GA4 landing sessions'
