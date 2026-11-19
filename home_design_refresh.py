"""Store the read-only design worker's daily shortlist."""

from calendar import monthrange
from datetime import date, timedelta
from html import escape
import json
import re

from home_morning_brief_actions import PROJECT_URL, _prompt
from psd_directory import ROOT as LIVE_FOLDER
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
    "Write each suggestion as a testable creative problem and opportunity for an imagery and collector-finish upgrade. "
    "Preserve the existing edition name, title wording, quotation and sporting story or moment. "
    "Describe the subject hierarchy, image quality, background or thumbnail recognition worth "
    "investigating. Commission fresh image research and reconsider the hero, scene and "
    "composition within that same story. Treat existing artwork as the edition reference. Avoid "
    "prescribing only a crop, brightness or text-size change. Weak sales warrant investigation "
    "and a creative test. They do not establish that artwork caused the result."
)


def _refresh_prompt(row, product_url):
    """One shared creative workflow; only the brief and publication target differ."""
    evidence = row.get('evidence') or f"{row.get('sessions', 0):,} GA4 landing sessions"
    context = f"""EXISTING PRODUCT REFRESH — NEW ARTWORK FOR THE SAME LISTING

Existing edition/product title (preserve): {row['title']}
Shopify product ID: {row['product_id']}
Product page and current artwork reference: {product_url}
Research hypothesis from the Home recommendation: {row.get('suggestion') or 'Upgrade the imagery and collector finish for this existing edition.'}
Decision context: {evidence}

Inspect the listing and its current artwork; where available, use its matching master in Dropbox Live ({LIVE_FOLDER}/) for read-only reference. Preserve the existing edition name, exact headline and quotation wording, and the same subject, sporting story, event or career angle and emotional meaning. Use the artwork and listing together to distinguish the printed headline from the full product title and to establish the original story. The recommendation is an imagery and finish research lead only; any older suggestion to rename the edition or change its story is superseded by this preservation brief. Research fresh authentic photographs for that same story, and upgrade the composition, background, typography treatment and collector finish through the shared New Design workflow below. The old layout and photographs are not locked. Weak sales warrant investigation, not an assumption that the artwork caused them.

Save the new PSD and matching JSON to Design Studio Review. Leave the existing live PSD and Shopify listing untouched during design creation. This is new imagery for the same named edition and story; the exact product ID above remains the publication target. The JSON must retain that linkage for Publish Now and Publish + ads. Never create a new Shopify product for this request.
"""
    return _prompt(row['title'], context, refresh_product_id=row['product_id'], preserve_refresh_edition=True)


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
