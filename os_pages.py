import csv
import gc
import html
import io
import importlib
import json
import os
import re
import textwrap
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

import db
import prompt_store
import shopify_sync
import supabase_backend
from services import r2_storage


CERTIFICATE_OUTPUT_DIR = db.BASE_DIR / "output" / "certificates"
SUPABASE_PAGE_CACHE_TTL_SECONDS = int(os.getenv("SUPABASE_PAGE_CACHE_TTL_SECONDS", "45"))
PRODUCT_CACHE_DISPLAY_LIMIT = 5000
ORDER_SCREEN_CACHE_LIMIT = int(os.getenv("SUPABASE_ORDER_SCREEN_CACHE_LIMIT", "1500"))
DEFAULT_PAGE_SIZE = 50
DEVELOPER_PAGE_PASSWORD = os.getenv("DEVELOPER_PAGE_PASSWORD", "sportscave1993")

QUICK_LINKS = (
    ("shopify_admin_url", "Open Shopify Admin"),
    ("live_product_url", "Open Live Product Page"),
    ("prodigi_product_url", "Open Prodigi Product"),
    ("google_drive_root_folder_url", "Open Root Drive Folder"),
)

PRODUCT_EXPORT_FIELDS = (
    "id",
    "product_name",
    "handle",
    "sport_category",
    "country_focus",
    "status",
    "readiness_status",
    "shopify_product_id",
    "shopify_admin_url",
    "live_product_url",
    "shopify_sync_status",
    "shopify_last_synced_at",
    "shopify_remote_updated_at",
    "shopify_variant_count",
    "shopify_image_count",
    "prodigi_product_id",
    "prodigi_product_url",
    "prodigi_notes",
    *(asset["url_field"] for asset in db.ASSET_DEFINITIONS),
    "google_drive_root_folder_url",
    *(f"{asset['key']}_status" for asset in db.ASSET_DEFINITIONS),
    "overall_asset_readiness",
    "edition_limit",
    "editions_sold",
    "editions_remaining",
    "next_edition_number",
    "edition_status",
    "notes",
    "created_at",
    "updated_at",
    "archived_at",
)

LIMITED_EDITION_EXPORT_FIELDS = (
    "product_title",
    "handle",
    "shopify_product_id",
    "shopify_status",
    "edition_limit",
    "next_available_edition",
    "editions_sold",
    "editions_remaining",
    "edition_status",
    "psd_file_url",
    "updated_at",
)

PRODIGI_DASHBOARD_URL = (
    "https://dashboard.prodigi.com/connect-sales-channel/shopify?"
    "code=8cb5baf40dc839d456b331fbf23fd82c&"
    "hmac=3caa9f14ab6565fc1b41d4fa44fe7873d069895aa75192e93ff3a82fdd28de30&"
    "host=YWRtaW4uc2hvcGlmeS5jb20vc3RvcmUvc3BvcnRzY2F2ZS1uYg&"
    "shop=sportscave-nb.myshopify.com&"
    "state=We_6XjylWzROi8kCdXMTLECYFxjp80JZvK82DUf9Xzo&"
    "timestamp=1782278816"
)
PRODIGI_REFERENCE_MAPPINGS = (
    {
        "sports_cave_variant": "Black / XL - 62 × 87 cm (24.4 × 34.3 in)",
        "sports_cave_frame": "Black",
        "sports_cave_size": "XL - 62 × 87 cm",
        "prodigi_size": "A1",
        "prodigi_product_option": "Classic Frame",
        "prodigi_product": 'Classic Frame, EMA 200gsm Fine Art Print, No Mount / No Mat, Perspex Glaze, 59.4x84.1cm / 23.4x33.1" (A1)',
        "prodigi_code": "GLOBAL-CFP-A1",
        "prodigi_frame_colour": "Black",
    },
    {
        "sports_cave_variant": "Black / L - 45 × 62 cm (17.7 × 24.4 in)",
        "sports_cave_frame": "Black",
        "sports_cave_size": "L - 45 × 62 cm",
        "prodigi_size": "A2",
        "prodigi_product_option": "Classic Frame",
        "prodigi_product": 'Classic Frame, EMA 200gsm Fine Art Print, No Mount / No Mat, Perspex Glaze, 42x59.4cm/16.5x23.4" (A2)',
        "prodigi_code": "GLOBAL-CFP-A2",
        "prodigi_frame_colour": "Black",
    },
    {
        "sports_cave_variant": "Black / M - 30 × 45 cm (11.8 × 17.7 in)",
        "sports_cave_frame": "Black",
        "sports_cave_size": "M - 30 × 45 cm",
        "prodigi_size": "A3",
        "prodigi_product_option": "Classic Frame",
        "prodigi_product": 'Classic Frame, EMA 200gsm Fine Art Print, No Mount / No Mat, Perspex Glaze, 29.7x42cm / 11.7x16.5" (A3)',
        "prodigi_code": "GLOBAL-CFP-A3",
        "prodigi_frame_colour": "Black",
    },
    {
        "sports_cave_variant": "Black / S- 21 × 30 cm (8.3 × 11.8 in)",
        "sports_cave_frame": "Black",
        "sports_cave_size": "S - 21 × 30 cm",
        "prodigi_size": "A4",
        "prodigi_product_option": "Classic Frame",
        "prodigi_product": 'Classic Frame, EMA 200gsm Fine Art Print, No Mount / No Mat, Perspex Glaze, 21x29.7cm / 8.3x11.7" (A4)',
        "prodigi_code": "GLOBAL-CFP-A4",
        "prodigi_frame_colour": "Black",
    },
    {
        "sports_cave_variant": "Oak / XL - 62 × 87 cm (24.4 × 34.3 in)",
        "sports_cave_frame": "Oak",
        "sports_cave_size": "XL - 62 × 87 cm",
        "prodigi_size": "A1",
        "prodigi_product_option": "Classic Frame",
        "prodigi_product": 'Classic Frame, EMA 200gsm Fine Art Print, No Mount / No Mat, Perspex Glaze, 59.4x84.1cm / 23.4x33.1" (A1)',
        "prodigi_code": "GLOBAL-CFP-A1",
        "prodigi_frame_colour": "Natural",
    },
    {
        "sports_cave_variant": "Oak / L - 45 × 62 cm (17.7 × 24.4 in)",
        "sports_cave_frame": "Oak",
        "sports_cave_size": "L - 45 × 62 cm",
        "prodigi_size": "A2",
        "prodigi_product_option": "Classic Frame",
        "prodigi_product": 'Classic Frame, EMA 200gsm Fine Art Print, No Mount / No Mat, Perspex Glaze, 42x59.4cm/16.5x23.4" (A2)',
        "prodigi_code": "GLOBAL-CFP-A2",
        "prodigi_frame_colour": "Natural",
    },
    {
        "sports_cave_variant": "Oak / M - 30 × 45 cm (11.8 × 17.7 in)",
        "sports_cave_frame": "Oak",
        "sports_cave_size": "M - 30 × 45 cm",
        "prodigi_size": "A3",
        "prodigi_product_option": "Classic Frame",
        "prodigi_product": 'Classic Frame, EMA 200gsm Fine Art Print, No Mount / No Mat, Perspex Glaze, 29.7x42cm / 11.7x16.5" (A3)',
        "prodigi_code": "GLOBAL-CFP-A3",
        "prodigi_frame_colour": "Natural",
    },
    {
        "sports_cave_variant": "Oak / S- 21 × 30 cm (8.3 × 11.8 in)",
        "sports_cave_frame": "Oak",
        "sports_cave_size": "S - 21 × 30 cm",
        "prodigi_size": "A4",
        "prodigi_product_option": "Classic Frame",
        "prodigi_product": 'Classic Frame, EMA 200gsm Fine Art Print, No Mount / No Mat, Perspex Glaze, 21x29.7cm / 8.3x11.7" (A4)',
        "prodigi_code": "GLOBAL-CFP-A4",
        "prodigi_frame_colour": "Natural",
    },
    {
        "sports_cave_variant": "White / XL - 62 × 87 cm (24.4 × 34.3 in)",
        "sports_cave_frame": "White",
        "sports_cave_size": "XL - 62 × 87 cm",
        "prodigi_size": "A1",
        "prodigi_product_option": "Classic Frame",
        "prodigi_product": 'Classic Frame, EMA 200gsm Fine Art Print, No Mount / No Mat, Perspex Glaze, 59.4x84.1cm / 23.4x33.1" (A1)',
        "prodigi_code": "GLOBAL-CFP-A1",
        "prodigi_frame_colour": "White",
    },
    {
        "sports_cave_variant": "White / L - 45 × 62 cm (17.7 × 24.4 in)",
        "sports_cave_frame": "White",
        "sports_cave_size": "L - 45 × 62 cm",
        "prodigi_size": "A2",
        "prodigi_product_option": "Classic Frame",
        "prodigi_product": 'Classic Frame, EMA 200gsm Fine Art Print, No Mount / No Mat, Perspex Glaze, 42x59.4cm/16.5x23.4" (A2)',
        "prodigi_code": "GLOBAL-CFP-A2",
        "prodigi_frame_colour": "White",
    },
    {
        "sports_cave_variant": "White / M - 30 × 45 cm (11.8 × 17.7 in)",
        "sports_cave_frame": "White",
        "sports_cave_size": "M - 30 × 45 cm",
        "prodigi_size": "A3",
        "prodigi_product_option": "Classic Frame",
        "prodigi_product": 'Classic Frame, EMA 200gsm Fine Art Print, No Mount / No Mat, Perspex Glaze, 29.7x42cm / 11.7x16.5" (A3)',
        "prodigi_code": "GLOBAL-CFP-A3",
        "prodigi_frame_colour": "White",
    },
    {
        "sports_cave_variant": "White / S- 21 × 30 cm (8.3 × 11.8 in)",
        "sports_cave_frame": "White",
        "sports_cave_size": "S - 21 × 30 cm",
        "prodigi_size": "A4",
        "prodigi_product_option": "Classic Frame",
        "prodigi_product": 'Classic Frame, EMA 200gsm Fine Art Print, No Mount / No Mat, Perspex Glaze, 21x29.7cm / 8.3x11.7" (A4)',
        "prodigi_code": "GLOBAL-CFP-A4",
        "prodigi_frame_colour": "White",
    },
    {
        "sports_cave_variant": "Unframed / XL - 62 × 87 cm (24.4 × 34.3 in)",
        "sports_cave_frame": "Unframed",
        "sports_cave_size": "XL - 62 × 87 cm",
        "prodigi_size": "A1",
        "prodigi_product_option": "Fine Art Paper",
        "prodigi_product": 'EMA, Enhanced Matte Art Paper, 200gsm, 59.4x84.1cm / 23.4x33.1" (A1)',
        "prodigi_code": "GLOBAL-FAP-A1",
        "prodigi_frame_colour": "No frame",
    },
    {
        "sports_cave_variant": "Unframed / L - 45 × 62 cm (17.7 × 24.4 in)",
        "sports_cave_frame": "Unframed",
        "sports_cave_size": "L - 45 × 62 cm",
        "prodigi_size": "A2",
        "prodigi_product_option": "Fine Art Paper",
        "prodigi_product": 'EMA, Enhanced Matte Art Paper, 200gsm, 42x59.4cm / 16.5x23.4" (A2)',
        "prodigi_code": "GLOBAL-FAP-A2",
        "prodigi_frame_colour": "No frame",
    },
    {
        "sports_cave_variant": "Unframed / M - 30 × 45 cm (11.8 × 17.7 in)",
        "sports_cave_frame": "Unframed",
        "sports_cave_size": "M - 30 × 45 cm",
        "prodigi_size": "A3",
        "prodigi_product_option": "Fine Art Paper",
        "prodigi_product": 'EMA, Enhanced Matte Art Paper, 200gsm, 29.7x42cm / 11.7x16.5" (A3)',
        "prodigi_code": "GLOBAL-FAP-A3",
        "prodigi_frame_colour": "No frame",
    },
    {
        "sports_cave_variant": "Unframed / S- 21 × 30 cm (8.3 × 11.8 in)",
        "sports_cave_frame": "Unframed",
        "sports_cave_size": "S - 21 × 30 cm",
        "prodigi_size": "A4",
        "prodigi_product_option": "Fine Art Paper",
        "prodigi_product": 'EMA, Enhanced Matte Art Paper, 200gsm, 21x29.7cm / 8.3x11.7" (A4)',
        "prodigi_code": "GLOBAL-FAP-A4",
        "prodigi_frame_colour": "No frame",
    },
)
PRODIGI_SIZE_OPTIONS = tuple(
    {
        "shopify_size": size,
        "prodigi_size": next(row["prodigi_size"] for row in PRODIGI_REFERENCE_MAPPINGS if row["sports_cave_frame"] == "Black" and row["sports_cave_size"].startswith(size)),
        "dimensions": re.sub(
            r"^[A-Z]+\s*-\s*",
            "",
            next(row["sports_cave_variant"].split("/", 1)[1].strip() for row in PRODIGI_REFERENCE_MAPPINGS if row["sports_cave_frame"] == "Black" and row["sports_cave_size"].startswith(size)),
        ),
        "framed_name": next(row["prodigi_product"] for row in PRODIGI_REFERENCE_MAPPINGS if row["sports_cave_frame"] == "Black" and row["sports_cave_size"].startswith(size)),
        "framed_code": next(row["prodigi_code"] for row in PRODIGI_REFERENCE_MAPPINGS if row["sports_cave_frame"] == "Black" and row["sports_cave_size"].startswith(size)),
        "unframed_name": next(row["prodigi_product"] for row in PRODIGI_REFERENCE_MAPPINGS if row["sports_cave_frame"] == "Unframed" and row["sports_cave_size"].startswith(size)),
        "unframed_code": next(row["prodigi_code"] for row in PRODIGI_REFERENCE_MAPPINGS if row["sports_cave_frame"] == "Unframed" and row["sports_cave_size"].startswith(size)),
    }
    for size in ("XL", "L", "M", "S")
)
PRODIGI_FRAME_OPTIONS = (
    ("Black", "Black", "Sports Cave Black Frame"),
    ("Oak", "Natural", "Sports Cave Oak Frame"),
    ("White", "White", "Sports Cave White Frame"),
    ("Unframed", "No frame", "Sports Cave Unframed"),
)
PRODIGI_SUPPORT_EMAIL = "pro@prodigi.com"
PRODIGI_TRACKER_PATH = db.BASE_DIR / "output" / "_cache" / "prodigi_fulfillments.json"
PRODIGI_TRACKER_VERSION = 1
PRODIGI_STATUS_OPTIONS = (
    "Needs Review",
    "Submitted",
    "Ready to Send",
    "Submitted to Prodigi",
    "In Production",
    "Awaiting Tracking",
    "Shipped",
    "Fulfilled in Shopify",
    "Hold / Issue",
)
PRODIGI_ACTIONABLE_STATUS_ORDER = {status: index for index, status in enumerate(PRODIGI_STATUS_OPTIONS)}
PRODIGI_ACTIVE_STATUSES = {
    "Needs Review",
    "Ready to Send",
    "Submitted to Prodigi",
    "In Production",
    "Awaiting Tracking",
    "Shipped",
    "Hold / Issue",
}
PRODIGI_TRACKER_EXPORT_COLUMNS = (
    "row_id",
    "prodigi_status",
    "shopify_order_name",
    "shopify_order_number",
    "date",
    "customer_name",
    "customer_email",
    "product_title",
    "shopify_variant_title",
    "edition_number",
    "edition_total",
    "frame",
    "size",
    "sports_cave_frame",
    "sports_cave_size",
    "prodigi_size",
    "prodigi_product_option",
    "prodigi_product_name",
    "prodigi_code",
    "prodigi_product_code",
    "prodigi_frame_colour",
    "shipping_method",
    "certificate_status",
    "double_checked",
    "certificate_visual_checked",
    "certificate_customer_checked",
    "certificate_product_checked",
    "certificate_edition_checked",
    "frame_colour_checked",
    "prodigi_option_checked",
    "shipping_checked",
    "submitted_confirmed",
    "checked_by",
    "checked_at",
    "prodigi_order_id",
    "tracking_number",
    "tracking_url",
    "carrier",
    "notes",
    "shopify_order_id",
    "shopify_line_item_id",
    "shopify_product_id",
    "shopify_variant_id",
    "shopify_fulfillment_status",
    "date_sent_to_prodigi",
    "submitted_at",
    "date_shipped",
    "date_fulfilled_in_shopify",
    "qa_completed",
    "qa_confirmed",
    "qa_notes",
    "qa_completed_at",
    "qa_answers",
    "linked_order_line_id",
    "issue_reason",
    "blockers",
    "source",
    "created_at",
    "updated_at",
)
PRODIGI_EDITABLE_FIELDS = (
    "prodigi_status",
    "prodigi_order_id",
    "tracking_number",
    "tracking_url",
    "carrier",
    "notes",
    "shipping_method",
    "double_checked",
)
PRODIGI_GOOGLE_SHEET_HEADERS = (
    "Date Sent",
    "Shopify Order #",
    "Customer Name",
    "Edition Name",
    "Edition No.",
    "Frame",
    "Size",
    "Prodigi Product Option",
    "Shipping",
    "Status",
    "Notes",
)


def render_page_intro(title, purpose, next_step, mistake_tip=None):
    st.title(title)
    st.caption(purpose)
    with st.container(border=True):
        st.markdown("**How-to video**")
        st.caption("Video walkthrough will be added in a later phase.")
        st.write(f"**Next step:** {next_step}")
        if mistake_tip:
            st.caption(f"Avoid mistakes: {mistake_tip}")


def prodigi_reference_rows():
    return [
        {
            "Sports Cave Variant": row["sports_cave_variant"],
            "Sports Cave Frame": row["sports_cave_frame"],
            "Sports Cave Size": row["sports_cave_size"],
            "Prodigi Product": row["prodigi_product"],
            "Prodigi Code": row["prodigi_code"],
            "Prodigi Frame Colour": row["prodigi_frame_colour"],
        }
        for row in PRODIGI_REFERENCE_MAPPINGS
    ]


def _prodigi_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _prodigi_clean(value):
    return str(value or "").strip()


def _prodigi_int(value, default=0):
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.findall(r"\d+", str(value or ""))
    return int(digits[0]) if digits else default


def _prodigi_bool(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"1", "true", "yes", "y", "checked", "double checked"}


def _prodigi_normalise_order_name(value):
    raw = _prodigi_clean(value)
    if not raw:
        return ""
    digits = re.findall(r"\d+", raw)
    return f"SC{digits[-1]}" if digits else raw.replace("#", "").casefold()


def _prodigi_normalise_text(value):
    return re.sub(r"\s+", " ", _prodigi_clean(value)).casefold()


def _prodigi_normalise_variant(value):
    text = _prodigi_clean(value)
    replacements = {
        "\u00d7": "x",
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"\s*/\s*", " / ", text)
    text = re.sub(r"\s*-\s*", " - ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().casefold()


def _prodigi_frame_from_variant(variant, fallback=""):
    text = _prodigi_normalise_variant(f"{variant} {fallback}")
    if "unframed" in text:
        return "Unframed"
    if "black" in text:
        return "Black"
    if "oak" in text or "natural" in text:
        return "Oak"
    if "white" in text:
        return "White"
    return ""


def _prodigi_size_from_variant(variant, fallback=""):
    text = _prodigi_normalise_variant(f"{variant} {fallback}").upper()
    size_text = text.split("/", 1)[1] if "/" in text else text
    for size in ("XL", "L", "M", "S"):
        if re.search(rf"(^|[^A-Z0-9]){size}([^A-Z0-9]|$)", size_text):
            return size
    return ""


def _prodigi_mapping_key(frame, size):
    clean_frame = _prodigi_frame_from_variant(frame, frame) or _prodigi_clean(frame)
    clean_size = _prodigi_size_from_variant(size, size) or _prodigi_clean(size).upper()
    return clean_frame, clean_size


def prodigi_mapping_for_variant(variant, fallback=""):
    return prodigi_mapping_for_frame_size(*_prodigi_mapping_key(f"{variant} {fallback}", f"{variant} {fallback}"))


def prodigi_mapping_for_frame_size(frame, size):
    clean_frame, clean_size = _prodigi_mapping_key(frame, size)
    mapping = next(
        (
            row
            for row in PRODIGI_REFERENCE_MAPPINGS
            if row["sports_cave_frame"] == clean_frame
            and row["sports_cave_size"].split(" ", 1)[0] == clean_size
        ),
        None,
    )
    if not mapping:
        return {
            "frame": clean_frame,
            "size": clean_size,
            "prodigi_size": "",
            "prodigi_product_option": "",
            "prodigi_code": "",
            "prodigi_frame": "",
            "prodigi_product_name": "",
        }
    return {
        "frame": clean_frame,
        "size": clean_size,
        "prodigi_size": mapping["prodigi_size"],
        "prodigi_product_option": mapping["prodigi_product_option"],
        "prodigi_code": mapping["prodigi_code"],
        "prodigi_frame": mapping["prodigi_frame_colour"],
        "prodigi_product_name": mapping["prodigi_product"],
        "prodigi_frame_colour": mapping["prodigi_frame_colour"],
        "sports_cave_variant": mapping["sports_cave_variant"],
        "sports_cave_size": mapping["sports_cave_size"],
    }


def prodigi_required_confirmation_question(row):
    code = row.get("prodigi_product_code") or row.get("prodigi_code") or ""
    product = row.get("prodigi_product_name") or ""
    frame_colour = row.get("prodigi_frame_colour") or row.get("prodigi_frame") or ""
    if row.get("frame") == "Unframed" or frame_colour == "No frame":
        suffix = "No frame"
    else:
        suffix = f"Frame colour: {frame_colour or '-'}"
    return f"Is the selected Prodigi variant exactly {code} - {product}, {suffix}?"


def prodigi_shopify_variant_label(row):
    frame = row.get("sports_cave_frame") or row.get("frame") or ""
    size = row.get("size") or ""
    if frame and size:
        return f"{frame} / {size}"
    return row.get("variant_title") or row.get("shopify_variant_title") or ""


def prodigi_variant_copy_text(row):
    return "\n".join(
        [
            f"Expected Prodigi variant: {row.get('prodigi_product_name') or ''}",
            f"Prodigi code: {row.get('prodigi_product_code') or row.get('prodigi_code') or ''}",
            f"Frame colour: {row.get('prodigi_frame_colour') or row.get('prodigi_frame') or ''}",
        ]
    )


def prodigi_reference_table_html(rows):
    headers = ("Sports Cave Variant", "Sports Cave Frame", "Sports Cave Size", "Prodigi Product", "Prodigi Code", "Prodigi Frame Colour")
    header_html = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    body_rows = []
    for row in rows:
        cells = []
        for header in headers:
            value = html.escape(str(row.get(header) or ""))
            class_name = "prodigi-code-cell" if header == "Prodigi Code" else ""
            cells.append(f'<td class="{class_name}">{value}</td>')
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"""
    <style>
      .prodigi-reference-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 0.84rem;
      }}
      .prodigi-reference-table th {{
        position: sticky;
        top: 0;
        background: #151515;
        color: #f5efe2;
        text-align: left;
        padding: 0.55rem 0.6rem;
        border-bottom: 1px solid rgba(218, 179, 92, 0.35);
      }}
      .prodigi-reference-table td {{
        color: #efe9dd;
        padding: 0.52rem 0.6rem;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        vertical-align: top;
      }}
      .prodigi-reference-scroll {{
        max-height: 470px;
        overflow: auto;
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 8px;
      }}
      .prodigi-code-cell {{
        color: #dab35c !important;
        font-weight: 800;
        white-space: nowrap;
      }}
    </style>
    <div class="prodigi-reference-scroll">
      <table class="prodigi-reference-table">
        <thead><tr>{header_html}</tr></thead>
        <tbody>{''.join(body_rows)}</tbody>
      </table>
    </div>
    """


def prodigi_product_option_display(row):
    if (row.get("frame") or "") == "Unframed" or row.get("prodigi_product_option") == "Fine Art Paper":
        return "EMA, Enhanced Matte Art Paper, 200gsm"
    if row.get("prodigi_product_option") or row.get("prodigi_code"):
        return "Classic Frame, EMA 200gsm Fine Art Print, No Mount / No Mat, Perspex Glaze"
    return ""


def prodigi_tracker_row_id(row):
    order_id = _prodigi_clean(row.get("shopify_order_id") or row.get("order_id") or row.get("shopify_order_name") or row.get("order"))
    line_id = _prodigi_clean(row.get("shopify_line_item_id") or row.get("line_item_id") or row.get("product_title") or row.get("product"))
    unit_index = _prodigi_int(row.get("line_item_unit_index"), 0) or _prodigi_int(row.get("allocation_index"), 0)
    if not unit_index:
        unit_index = _prodigi_int(row.get("edition_offset"), 0) + 1
    return "|".join([order_id or "order-missing", line_id or "line-missing", str(max(unit_index, 1))])


def _prodigi_status_from_sheet(value):
    raw = _prodigi_normalise_text(value)
    if not raw:
        return ""
    if "fulfill" in raw:
        return "Fulfilled in Shopify"
    if "ship" in raw or "tracking" in raw:
        return "Shipped"
    if "await" in raw:
        return "Awaiting Tracking"
    if "production" in raw:
        return "In Production"
    if "submitted" in raw or "prodigi" in raw or "sent" in raw:
        return "Submitted"
    if "double" in raw or "checked" in raw:
        return "Ready to Send"
    if "hold" in raw or "issue" in raw or "review" in raw:
        return "Hold / Issue"
    if "ready" in raw:
        return "Ready to Send"
    return value if value in PRODIGI_STATUS_OPTIONS else "Needs Review"


def prodigi_submission_blockers(row):
    blockers = []
    if not _prodigi_clean(row.get("shopify_order_id") or row.get("shopify_order_name")):
        blockers.append("Missing Shopify order line")
    if not _prodigi_clean(row.get("shopify_line_item_id")):
        blockers.append("Missing Shopify line item")
    if not _prodigi_clean(row.get("shopify_product_id") or row.get("product_title")):
        blockers.append("Product not matched")
    if not _prodigi_clean(row.get("frame")):
        blockers.append("Missing frame")
    if not _prodigi_clean(row.get("size")):
        blockers.append("Missing size")
    if not _prodigi_clean(row.get("prodigi_size")):
        blockers.append("Missing Prodigi size")
    if not _prodigi_clean(row.get("prodigi_code")):
        blockers.append("Missing Prodigi code")
    if not _prodigi_clean(row.get("shipping_method")):
        blockers.append("Missing shipping method")
    if not _prodigi_int(row.get("edition_number"), 0):
        blockers.append("Missing edition number")
    if (
        _prodigi_clean(row.get("date_sent_to_prodigi"))
        or _prodigi_clean(row.get("prodigi_order_id"))
        or row.get("prodigi_status") in {"Submitted", "Submitted to Prodigi", "In Production", "Shipped", "Fulfilled in Shopify"}
    ):
        blockers.append("Already submitted")
    return blockers


def _prodigi_default_status(row):
    blockers = [blocker for blocker in prodigi_submission_blockers(row) if blocker != "Already submitted"]
    if blockers:
        return "Needs Review"
    return "Ready to Send"


def _prodigi_certificate_generated(row):
    status = _prodigi_normalise_text(row.get("certificate_status"))
    return bool(
        "generated" in status
        or "uploaded" in status
        or "ready" in status
        or row.get("certificate_pdf_path")
        or row.get("certificate_pdf_url")
    )


def _prodigi_certificate_uploaded(row):
    status = _prodigi_normalise_text(row.get("certificate_status"))
    return bool("uploaded" in status or "ready" in status or row.get("certificate_pdf_url") or row.get("shopify_file_url"))


def _prodigi_submitted(row):
    return bool(
        row.get("prodigi_status") in {"Submitted", "Submitted to Prodigi", "In Production", "Awaiting Tracking", "Shipped", "Fulfilled in Shopify"}
        or _prodigi_clean(row.get("date_sent_to_prodigi"))
        or _prodigi_clean(row.get("prodigi_order_id"))
    )


def _prodigi_tracking_exists(row):
    return bool(_prodigi_clean(row.get("tracking_number")) or _prodigi_clean(row.get("tracking_url")))


def _prodigi_fulfilled(row):
    return bool(
        row.get("prodigi_status") == "Fulfilled in Shopify"
        or row.get("shopify_fulfillment_status") == "Fulfilled in Shopify"
        or _prodigi_clean(row.get("date_fulfilled_in_shopify"))
    )


def prodigi_progress_checks(row):
    return {
        "Edition": bool(_prodigi_int(row.get("edition_number"), 0)),
        "Cert": _prodigi_certificate_uploaded(row),
        "Prodigi": bool(row.get("prodigi_size") and row.get("prodigi_product_option") and row.get("prodigi_code")),
        "Shipping": bool(_prodigi_clean(row.get("shipping_method"))),
        "Submitted": _prodigi_submitted(row),
        "Tracking": _prodigi_tracking_exists(row),
        "Fulfilled": _prodigi_fulfilled(row),
    }


def prodigi_progress_text(row):
    checks = prodigi_progress_checks(row)
    return " | ".join(f"{name} {'✅' if ok else '⬜'}" for name, ok in checks.items())


def prodigi_manual_submit_blockers(row):
    blockers = []
    blockers.extend(prodigi_submission_blockers(row))
    if not _prodigi_bool(row.get("frame_colour_checked")):
        blockers.append("Frame colour not checked")
    if not _prodigi_bool(row.get("prodigi_option_checked")):
        blockers.append("Prodigi option not checked")
    if not _prodigi_bool(row.get("shipping_checked")):
        blockers.append("Shipping not checked")
    if not _prodigi_bool(row.get("submitted_confirmed")):
        blockers.append("Submission not confirmed")
    return blockers


def prodigi_fulfillment_blockers(row):
    blockers = []
    if not _prodigi_submitted(row):
        blockers.append("Not submitted to Prodigi")
    if not _prodigi_tracking_exists(row):
        blockers.append("Tracking missing")
    if not _prodigi_certificate_uploaded(row):
        blockers.append("Certificate not uploaded")
    return blockers


def prodigi_tracker_row_from_order(order_row, stored=None):
    stored = stored or {}
    variant = order_row.get("variant") or order_row.get("variant_title") or ""
    frame = stored.get("frame") or _prodigi_frame_from_variant(variant)
    size = stored.get("size") or _prodigi_size_from_variant(variant)
    mapping = prodigi_mapping_for_frame_size(frame, size)
    edition_number = _prodigi_int(order_row.get("edition_number") or order_row.get("edition"), 0)
    created_at = stored.get("created_at") or _prodigi_now_iso()
    row = {
        "row_id": stored.get("row_id") or prodigi_tracker_row_id(order_row),
        "edition_order_id": stored.get("edition_order_id") or order_row.get("edition_order_id") or "",
        "shopify_order_id": order_row.get("shopify_order_id") or stored.get("shopify_order_id") or "",
        "shopify_order_name": order_row.get("order") or order_row.get("order_name") or stored.get("shopify_order_name") or "",
        "shopify_order_number": order_row.get("order") or order_row.get("order_name") or stored.get("shopify_order_number") or stored.get("shopify_order_name") or "",
        "shopify_line_item_id": order_row.get("shopify_line_item_id") or stored.get("shopify_line_item_id") or "",
        "customer_name": order_row.get("customer") or order_row.get("customer_name") or stored.get("customer_name") or "",
        "customer_email": order_row.get("customer_email") or stored.get("customer_email") or "",
        "product_title": order_row.get("product") or order_row.get("product_title") or stored.get("product_title") or "",
        "shopify_product_id": order_row.get("shopify_product_id") or stored.get("shopify_product_id") or "",
        "shopify_variant_id": order_row.get("variant_id") or order_row.get("shopify_variant_id") or stored.get("shopify_variant_id") or "",
        "variant_title": variant or stored.get("variant_title") or "",
        "shopify_variant_title": variant or stored.get("shopify_variant_title") or stored.get("variant_title") or "",
        "edition_number": edition_number,
        "edition_total": _prodigi_int(order_row.get("edition_total") or stored.get("edition_total"), 100),
        "frame": mapping.get("frame") or frame,
        "size": mapping.get("size") or size,
        "sports_cave_frame": mapping.get("frame") or frame,
        "sports_cave_size": mapping.get("sports_cave_size") or mapping.get("size") or size,
        "prodigi_size": stored.get("prodigi_size") or mapping.get("prodigi_size") or "",
        "prodigi_product_option": stored.get("prodigi_product_option") or mapping.get("prodigi_product_option") or "",
        "prodigi_code": stored.get("prodigi_code") or mapping.get("prodigi_code") or "",
        "prodigi_frame": stored.get("prodigi_frame") or mapping.get("prodigi_frame") or "",
        "prodigi_product_name": stored.get("prodigi_product_name") or mapping.get("prodigi_product_name") or "",
        "prodigi_product_code": stored.get("prodigi_product_code") or mapping.get("prodigi_code") or "",
        "prodigi_frame_colour": stored.get("prodigi_frame_colour") or mapping.get("prodigi_frame_colour") or mapping.get("prodigi_frame") or "",
        "prodigi_order_id": stored.get("prodigi_order_id") or "",
        "shipping_method": stored.get("shipping_method") or order_row.get("shipping") or order_row.get("shipping_method") or "",
        "prodigi_status": stored.get("prodigi_status") or stored.get("status") or "",
        "shopify_fulfillment_status": stored.get("shopify_fulfillment_status") or "",
        "tracking_number": stored.get("tracking_number") or stored.get("tracking") or "",
        "tracking_url": stored.get("tracking_url") or "",
        "carrier": stored.get("carrier") or "",
        "certificate_status": order_row.get("certificate") or order_row.get("certificate_status") or stored.get("certificate_status") or "",
        "certificate_pdf_url": order_row.get("certificate_pdf_url") or stored.get("certificate_pdf_url") or "",
        "shopify_file_url": order_row.get("shopify_file_url") or stored.get("shopify_file_url") or "",
        "date": order_row.get("date") or stored.get("date") or "",
        "date_sent_to_prodigi": stored.get("date_sent_to_prodigi") or "",
        "submitted_at": stored.get("submitted_at") or "",
        "date_shipped": stored.get("date_shipped") or "",
        "date_fulfilled_in_shopify": stored.get("date_fulfilled_in_shopify") or "",
        "qa_completed": _prodigi_bool(stored.get("qa_completed")),
        "qa_confirmed": _prodigi_bool(stored.get("qa_confirmed")),
        "qa_notes": stored.get("qa_notes") or "",
        "qa_completed_at": stored.get("qa_completed_at") or "",
        "qa_answers": stored.get("qa_answers") or {},
        "linked_order_line_id": stored.get("linked_order_line_id") or order_row.get("shopify_line_item_id") or stored.get("shopify_line_item_id") or "",
        "issue_reason": stored.get("issue_reason") or "",
        "double_checked": _prodigi_bool(stored.get("double_checked")),
        "certificate_visual_checked": _prodigi_bool(stored.get("certificate_visual_checked")),
        "certificate_customer_checked": _prodigi_bool(stored.get("certificate_customer_checked")),
        "certificate_product_checked": _prodigi_bool(stored.get("certificate_product_checked")),
        "certificate_edition_checked": _prodigi_bool(stored.get("certificate_edition_checked")),
        "frame_colour_checked": _prodigi_bool(stored.get("frame_colour_checked")),
        "prodigi_option_checked": _prodigi_bool(stored.get("prodigi_option_checked")),
        "shipping_checked": _prodigi_bool(stored.get("shipping_checked")),
        "submitted_confirmed": _prodigi_bool(stored.get("submitted_confirmed")),
        "checked_by": stored.get("checked_by") or "",
        "checked_at": stored.get("checked_at") or "",
        "notes": stored.get("notes") or "",
        "source": stored.get("source") or "orders_snapshot",
        "created_at": created_at,
        "updated_at": stored.get("updated_at") or created_at,
    }
    row["blockers"] = "; ".join(blocker for blocker in prodigi_submission_blockers(row) if blocker != "Already submitted")
    if not row["prodigi_status"]:
        row["prodigi_status"] = _prodigi_default_status(row)
    return row


def load_prodigi_tracker_state(path=None):
    if path is None and supabase_backend.is_configured():
        try:
            rows = supabase_backend.list_prodigi_dispatch_rows(limit=1500)
            updated_at = max((str(row.get("updated_at") or "") for row in rows), default="")
            return {"version": PRODIGI_TRACKER_VERSION, "rows": rows, "updated_at": updated_at, "source": "supabase"}
        except Exception as error:
            supabase_backend.log_app_error("prodigi_dispatch_load_failed", str(error), {"source": "prodigi_page"})
    target = Path(path or PRODIGI_TRACKER_PATH)
    if not target.exists():
        return {"version": PRODIGI_TRACKER_VERSION, "rows": [], "updated_at": ""}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {"version": PRODIGI_TRACKER_VERSION, "rows": [], "updated_at": ""}
    payload.setdefault("version", PRODIGI_TRACKER_VERSION)
    payload.setdefault("rows", [])
    payload.setdefault("updated_at", "")
    return payload


def save_prodigi_tracker_rows(rows, path=None):
    if path is None and supabase_backend.is_configured():
        try:
            result = supabase_backend.upsert_prodigi_dispatch_rows(rows or [])
            return {
                "version": PRODIGI_TRACKER_VERSION,
                "updated_at": _prodigi_now_iso(),
                "rows": rows or [],
                "source": "supabase",
                **result,
            }
        except Exception as error:
            supabase_backend.log_app_error("prodigi_dispatch_save_failed", str(error), {"source": "prodigi_page"})
    payload = {
        "version": PRODIGI_TRACKER_VERSION,
        "updated_at": _prodigi_now_iso(),
        "rows": rows or [],
    }
    target = Path(path or PRODIGI_TRACKER_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def build_prodigi_tracker_rows(order_rows, stored_rows=None):
    stored_by_id = {row.get("row_id"): row for row in stored_rows or [] if row.get("row_id")}
    rows = []
    seen = set()
    for order_row in order_rows or []:
        row_id = prodigi_tracker_row_id(order_row)
        tracker_row = prodigi_tracker_row_from_order(order_row, stored_by_id.get(row_id))
        rows.append(tracker_row)
        seen.add(tracker_row["row_id"])
    for row in stored_rows or []:
        if row.get("row_id") and row["row_id"] not in seen:
            preserved = prodigi_tracker_row_from_order(row, row)
            preserved["source"] = row.get("source") or "tracker_import"
            rows.append(preserved)
    return sort_prodigi_tracker_rows(rows)


def sort_prodigi_tracker_rows(rows):
    def key(row):
        status_rank = PRODIGI_ACTIONABLE_STATUS_ORDER.get(row.get("prodigi_status"), 99)
        date_value = row.get("date") or row.get("created_at") or ""
        order_number = _prodigi_int(row.get("shopify_order_name"), 0)
        date_digits = "".join(re.findall(r"\d+", str(date_value or "")))
        date_number = int(date_digits[:14] or 0)
        return (status_rank, -date_number, -order_number)

    return sorted(rows or [], key=key)


def prodigi_copy_details(row):
    lines = [
        f"Shopify Order #: {row.get('shopify_order_name') or ''}",
        f"Customer: {row.get('customer_name') or ''}",
        f"Product: {row.get('product_title') or ''}",
        f"Shopify Variant: {row.get('variant_title') or row.get('shopify_variant_title') or ''}",
        f"Edition #: #{_prodigi_int(row.get('edition_number'), 0):03d}" if _prodigi_int(row.get("edition_number"), 0) else "Edition #:",
        f"Frame: {row.get('frame') or ''}",
        f"Size: {row.get('size') or ''}",
        f"Prodigi Size: {row.get('prodigi_size') or ''}",
        f"Prodigi Product: {row.get('prodigi_product_name') or prodigi_product_option_display(row)}",
        f"Prodigi Code: {row.get('prodigi_product_code') or row.get('prodigi_code') or ''}",
        f"Prodigi Frame Colour: {row.get('prodigi_frame_colour') or row.get('prodigi_frame') or ''}",
        f"Shipping: {row.get('shipping_method') or ''}",
    ]
    return "\n".join(lines)


def export_prodigi_tracker_csv(rows):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=PRODIGI_TRACKER_EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows or []:
        writer.writerow({key: row.get(key, "") for key in PRODIGI_TRACKER_EXPORT_COLUMNS})
    return buffer.getvalue().encode("utf-8-sig")


def _prodigi_csv_text(uploaded_or_text):
    if uploaded_or_text is None:
        return ""
    if isinstance(uploaded_or_text, str):
        return uploaded_or_text
    if isinstance(uploaded_or_text, bytes):
        return uploaded_or_text.decode("utf-8-sig", errors="replace")
    return uploaded_or_text.getvalue().decode("utf-8-sig", errors="replace")


def _prodigi_csv_key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _prodigi_csv_value(row, *aliases):
    normalised = {_prodigi_csv_key(key): value for key, value in (row or {}).items()}
    for alias in aliases:
        key = _prodigi_csv_key(alias)
        if key in normalised:
            return normalised[key]
    return ""


def _prodigi_import_match_key(row):
    return (
        _prodigi_normalise_order_name(row.get("shopify_order_name") or row.get("Shopify Order #")),
        _prodigi_normalise_text(row.get("product_title") or row.get("Edition Name")),
        _prodigi_normalise_text(row.get("frame") or row.get("Frame")),
        _prodigi_normalise_text(row.get("size") or row.get("Size")),
        _prodigi_int(row.get("edition_number") or row.get("Edition No."), 0),
    )


def _prodigi_import_row_from_csv(csv_row):
    order_name = _prodigi_csv_value(csv_row, "Shopify Order #", "shopify_order_name", "Order #", "Order")
    product_title = _prodigi_csv_value(csv_row, "Edition Name", "product_title", "Product")
    frame = _prodigi_csv_value(csv_row, "Frame")
    size = _prodigi_csv_value(csv_row, "Size")
    mapping = prodigi_mapping_for_frame_size(frame, size)
    status = _prodigi_status_from_sheet(_prodigi_csv_value(csv_row, "Status", "prodigi_status"))
    date_sent = _prodigi_csv_value(csv_row, "Date Sent", "date_sent_to_prodigi")
    row = {
        "row_id": "",
        "shopify_order_name": order_name,
        "customer_name": _prodigi_csv_value(csv_row, "Customer Name", "customer_name"),
        "product_title": product_title,
        "edition_number": _prodigi_int(_prodigi_csv_value(csv_row, "Edition No.", "edition_number"), 0),
        "frame": mapping.get("frame") or frame,
        "size": mapping.get("size") or size,
        "prodigi_size": _prodigi_csv_value(csv_row, "Prodigi Size", "prodigi_size") or mapping.get("prodigi_size") or "",
        "prodigi_product_option": _prodigi_csv_value(csv_row, "Prodigi Product Option", "prodigi_product_option") or mapping.get("prodigi_product_option") or "",
        "prodigi_code": _prodigi_csv_value(csv_row, "Prodigi Code", "prodigi_code") or mapping.get("prodigi_code") or "",
        "shipping_method": _prodigi_csv_value(csv_row, "Shipping", "shipping_method"),
        "prodigi_status": status or "Needs Review",
        "notes": _prodigi_csv_value(csv_row, "Notes", "notes"),
        "date_sent_to_prodigi": date_sent,
        "source": "csv_import",
        "created_at": _prodigi_now_iso(),
        "updated_at": _prodigi_now_iso(),
    }
    row["row_id"] = "imported|" + "|".join(str(part or "") for part in _prodigi_import_match_key(row))
    return prodigi_tracker_row_from_order(row, row)


def import_prodigi_tracker_csv(uploaded_or_text, current_rows):
    text = _prodigi_csv_text(uploaded_or_text)
    if not text.strip():
        return {"rows": current_rows or [], "read": 0, "matched": 0, "created": 0, "warnings": ["CSV was empty."]}
    reader = csv.DictReader(io.StringIO(text))
    rows = [dict(row) for row in current_rows or []]
    by_key = {_prodigi_import_match_key(row): index for index, row in enumerate(rows)}
    read = matched = created = 0
    warnings = []
    for csv_row in reader:
        read += 1
        imported = _prodigi_import_row_from_csv(csv_row)
        key = _prodigi_import_match_key(imported)
        if key in by_key:
            index = by_key[key]
            existing = dict(rows[index])
            for field in (
                "prodigi_status",
                "notes",
                "shipping_method",
                "prodigi_product_option",
                "prodigi_size",
                "prodigi_code",
                "date_sent_to_prodigi",
            ):
                if imported.get(field):
                    existing[field] = imported[field]
            existing["updated_at"] = _prodigi_now_iso()
            rows[index] = prodigi_tracker_row_from_order(existing, existing)
            matched += 1
        else:
            imported["prodigi_status"] = "Needs Review"
            rows.append(prodigi_tracker_row_from_order(imported, imported))
            by_key[key] = len(rows) - 1
            created += 1
            warnings.append(f"Imported unmatched row for {imported.get('shopify_order_name') or 'order missing'} as Needs Review.")
    return {"rows": sort_prodigi_tracker_rows(rows), "read": read, "matched": matched, "created": created, "warnings": warnings}


def apply_prodigi_bulk_action(rows, selected_ids, action, value=""):
    selected = set(selected_ids or [])
    updated = []
    changed = 0
    now = _prodigi_now_iso()
    errors = []
    for row in rows or []:
        item = dict(row)
        if item.get("row_id") not in selected:
            updated.append(item)
            continue
        if action == "double_checked":
            item["double_checked"] = True
            item["checked_at"] = now
            item["prodigi_status"] = "Ready to Send"
        elif action == "submitted":
            blockers = prodigi_manual_submit_blockers(item)
            if blockers:
                errors.append(f"{item.get('shopify_order_name')}: {', '.join(blockers)}")
                updated.append(item)
                continue
            item["prodigi_status"] = "Submitted"
            item["date_sent_to_prodigi"] = item.get("date_sent_to_prodigi") or now
        elif action == "hold":
            item["prodigi_status"] = "Hold / Issue"
        elif action == "status":
            item["prodigi_status"] = value if value in PRODIGI_STATUS_OPTIONS else item.get("prodigi_status")
        elif action == "shipping":
            item["shipping_method"] = value
        elif action == "note":
            note = _prodigi_clean(value)
            if note:
                item["notes"] = "\n".join(part for part in [item.get("notes"), note] if part)
        item["updated_at"] = now
        item = prodigi_tracker_row_from_order(item, item)
        updated.append(item)
        changed += 1
    return {"rows": sort_prodigi_tracker_rows(updated), "changed": changed, "errors": errors}


def status_badge(status):
    status_class = re.sub(r"[^a-z0-9]+", "-", str(status or "").lower()).strip("-")
    return f'<span class="sc-status sc-status-{status_class}">{status or "Not Set"}</span>'


def render_product_thumbnail(image_url, *, key="", width=46):
    image_url = str(image_url or "").strip()
    if image_url:
        st.image(image_url, width=width)
        return
    st.markdown(
        f"""
        <div class="sc-product-thumb-empty" aria-label="{html.escape(key or 'Artwork thumbnail missing')}">
            SC
        </div>
        """,
        unsafe_allow_html=True,
    )


def format_optional_number(value):
    return "Not Set" if value is None else str(value)


def format_updated_at(value):
    if not value:
        return "Unknown"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.strftime("%d %b %Y, %H:%M")
    except (TypeError, ValueError):
        return str(value)


def format_order_date(value):
    if not value:
        return "Unknown"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.strftime("%d %b, %I:%M %p").replace(" 0", " ")
    except (TypeError, ValueError):
        return str(value)


def customer_display_name(value):
    cleaned = str(value or "").strip()
    if not cleaned or "@" in cleaned:
        return "Customer missing"
    return cleaned


def split_variant_title(value):
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
    if not cleaned:
        return "Variant missing", ""
    if " - " in cleaned:
        first, second = cleaned.split(" - ", 1)
        return first.strip(), second.strip()
    return cleaned, ""


def safe_filename_part(value):
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "").strip().lower())
    return cleaned.strip("-") or "sports-cave"


def escape_pdf_text(value):
    return str(value or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_simple_certificate_pdf(path, lines):
    width = 841.89
    height = 595.28
    content = [
        "0.043 0.043 0.051 rg",
        f"0 0 {width:.2f} {height:.2f} re f",
        "0.831 0.647 0.298 RG",
        "3 w",
        "42 42 758 512 re S",
        "0.831 0.647 0.298 rg",
        "72 470 698 2 re f",
        "0.961 0.949 0.918 rg",
    ]
    for text, x, y, size, color in lines:
        if color == "gold":
            content.append("0.831 0.647 0.298 rg")
        else:
            content.append("0.961 0.949 0.918 rg")
        content.append(f"BT /F1 {size} Tf {x} {y} Td ({escape_pdf_text(text)}) Tj ET")
    stream = "\n".join(content).encode("latin-1", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 841.89 595.28] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(pdf))


def generate_certificate_pdf(assignment_id):
    details = db.get_assignment_certificate_details(assignment_id)
    if not details:
        raise ValueError("The edition assignment could not be found.")
    order_name = details.get("order_name") or details.get("order_number") or "order"
    product_name = details.get("product_title") or "Sports Cave Artwork"
    edition_number = int(details.get("edition_number") or 0)
    edition_limit = int(details.get("edition_limit") or 0)
    handle = details.get("product_handle") or safe_filename_part(product_name)
    certificate_id = f"SC-{safe_filename_part(order_name).upper()}-{edition_number:04d}"
    purchase_date = format_updated_at(details.get("processed_at") or details.get("created_at"))
    filename = (
        f"certificate_{safe_filename_part(order_name)}_{safe_filename_part(handle)}"
        f"_edition_{edition_number}.pdf"
    )
    pdf_path = CERTIFICATE_OUTPUT_DIR / filename
    lines = [
        ("SPORTS CAVE", 72, 505, 40, "gold"),
        ("CERTIFICATE OF AUTHENTICITY", 72, 455, 24, "white"),
        (product_name[:72], 72, 365, 26, "white"),
        (f"Edition #{edition_number} of {edition_limit}", 72, 315, 30, "gold"),
        (f"Order: {order_name}", 72, 250, 17, "white"),
        (f"Collector: {details.get('customer_name') or 'Sports Cave Collector'}", 72, 220, 17, "white"),
        (f"Date: {purchase_date}", 72, 190, 17, "white"),
        (f"Certificate ID: {certificate_id}", 72, 160, 15, "white"),
        (
            "This certifies this Sports Cave artwork as part of a limited edition collector release.",
            72,
            105,
            15,
            "white",
        ),
        ("Sports Cave Limited Edition Certificate", 72, 72, 13, "gold"),
    ]
    write_simple_certificate_pdf(pdf_path, lines)
    db.save_assignment_certificate(assignment_id, pdf_path, certificate_id)
    return str(pdf_path)


def build_products_csv(products):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=PRODUCT_EXPORT_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for product in products:
        writer.writerow({field: product.get(field, "") for field in PRODUCT_EXPORT_FIELDS})
    return buffer.getvalue()


def limited_edition_item_key(product):
    raw_key = product.get("legacy_resource_id") or product.get("shopify_product_id") or product.get("shopify_handle")
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", str(raw_key or "product")).strip("-") or "product"


def build_limited_editions_csv(products):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=LIMITED_EDITION_EXPORT_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for product in products:
        writer.writerow(
            {
                "product_title": product.get("product_title") or "",
                "handle": product.get("shopify_handle") or "",
                "shopify_product_id": product.get("shopify_product_id") or "",
                "shopify_status": product.get("status") or "",
                "edition_limit": product.get("edition_limit") or "",
                "next_available_edition": product.get("next_available_edition") or "",
                "editions_sold": product.get("editions_sold") or 0,
                "editions_remaining": product.get("editions_remaining") if product.get("editions_remaining") is not None else "",
                "edition_status": product.get("edition_status") or "",
                "psd_file_url": product.get("psd_file_url") or "",
                "updated_at": product.get("edition_updated_at") or product.get("updated_at") or "",
            }
        )
    return buffer.getvalue()


def build_limited_editions_template_csv():
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=LIMITED_EDITION_EXPORT_FIELDS)
    writer.writeheader()
    return buffer.getvalue()


def build_supabase_products_csv(rows, asset_map):
    fields = (
        "product_title",
        "shopify_handle",
        "shopify_product_id",
        "edition_total",
        "next_edition_number",
        "remaining_editions",
        "sold_count",
        "remaining_count",
        "edition_status",
        "edition_display_text",
        "metafields_sync_status",
        "metafields_synced_at",
        "active",
        "sold_out",
        *supabase_backend.ASSET_TYPES,
        "admin_url",
        "online_store_url",
    )
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows or []:
        record = {field: row.get(field, "") for field in fields}
        for asset_type in supabase_backend.ASSET_TYPES:
            record[asset_type] = (asset_map.get(row.get("shopify_handle")) or {}).get(asset_type, "")
        writer.writerow(record)
    return buffer.getvalue()


def csv_value(row, field, fallback=""):
    value = row.get(field)
    if value is None:
        return fallback
    return str(value).strip()


def csv_int_value(row, field, fallback):
    value = csv_value(row, field, "")
    if value == "":
        return fallback
    return int(value)


def import_limited_editions_csv(uploaded_file):
    raw_data = uploaded_file.getvalue()
    text = raw_data.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("The CSV has no header row.")

    imported_rows = 0
    updated_rows = 0
    skipped_rows = 0
    errors = []

    for line_number, row in enumerate(reader, start=2):
        imported_rows += 1
        shopify_product_id = csv_value(row, "shopify_product_id")
        handle = csv_value(row, "handle")
        product_title = csv_value(row, "product_title")
        matched_id = db.find_shopify_edition_product_for_import(shopify_product_id, handle, product_title)
        if not matched_id:
            skipped_rows += 1
            errors.append(f"Line {line_number}: no cached Shopify product matched.")
            continue

        current = db.get_shopify_edition_product(matched_id)
        if not current:
            skipped_rows += 1
            errors.append(f"Line {line_number}: matched product could not be loaded.")
            continue

        try:
            edition_limit = csv_int_value(row, "edition_limit", current.get("edition_limit") or 100)
            next_available = csv_int_value(
                row,
                "next_available_edition",
                current.get("next_available_edition") or 1,
            )
            editions_sold = csv_int_value(row, "editions_sold", current.get("editions_sold") or 0)
            if edition_limit < 1:
                raise ValueError("edition_limit must be positive.")
            if next_available < 1 or next_available > edition_limit + 1:
                raise ValueError("next_available_edition must be between 1 and edition_limit + 1.")
            if editions_sold < 0:
                raise ValueError("editions_sold cannot be negative.")
            if editions_sold > edition_limit:
                raise ValueError("editions_sold cannot exceed edition_limit.")

            db.update_shopify_edition_product(
                matched_id,
                edition_limit=edition_limit,
                next_available_edition=next_available,
                editions_sold=editions_sold,
                psd_file_url=csv_value(row, "psd_file_url", current.get("psd_file_url") or ""),
                prodigi_url=current.get("prodigi_url") or "",
                prodigi_product_id=current.get("prodigi_product_id") or "",
                notes=current.get("edition_notes") or "",
                allow_oversold=False,
            )
            updated_rows += 1
        except Exception as error:
            skipped_rows += 1
            errors.append(f"Line {line_number}: {error}")

    return {
        "imported_rows": imported_rows,
        "updated_rows": updated_rows,
        "skipped_rows": skipped_rows,
        "errors": errors[:10],
    }


def select_index(options, value, default=0):
    try:
        return options.index(value)
    except ValueError:
        return default


def allow_local_sqlite_fallback():
    return os.getenv("ENABLE_LOCAL_SQLITE_FALLBACK", "true").lower() == "true"


def render_supabase_required_notice(page_title):
    st.title(page_title)
    st.error("Cloud storage is not connected, so this page cannot save or load shared records right now.")
    st.info(
        "Reconnect the shared database from the deployment settings, then refresh. Existing orders, "
        "products, edition numbers, and certificates are not changed by this message."
    )


def supabase_cache_version(key):
    session_key = f"{key}-cache-version"
    st.session_state.setdefault(session_key, 0)
    return int(st.session_state[session_key])


def bump_supabase_cache_version(*keys):
    for key in keys:
        session_key = f"{key}-cache-version"
        st.session_state[session_key] = int(st.session_state.get(session_key, 0)) + 1


def render_supabase_load_warning(action, error, key_prefix, *, using_saved_screen_data=False):
    if using_saved_screen_data:
        st.warning(f"{action} could not be refreshed right now. Showing the last saved screen data.")
    else:
        st.warning(f"{action} could not be refreshed. Existing saved data is still kept.")


def perf_log(message):
    try:
        print(message, flush=True)
    except (OSError, ValueError):
        pass


@st.cache_data(ttl=SUPABASE_PAGE_CACHE_TTL_SECONDS, show_spinner=False)
def cached_supabase_sync_state(cache_version):
    return supabase_backend.get_sync_state()


@st.cache_data(ttl=SUPABASE_PAGE_CACHE_TTL_SECONDS, show_spinner=False)
def cached_supabase_limited_products(search, limit, offset, cache_version):
    started = time.perf_counter()
    rows = supabase_backend.list_edition_products(
        search=search,
        limit=int(limit),
        offset=int(offset or 0),
    )
    elapsed = time.perf_counter() - started
    perf_log(f"PERF LimitedEditions query rows={len(rows)} time={elapsed:.3f}s")
    return rows


@st.cache_data(ttl=SUPABASE_PAGE_CACHE_TTL_SECONDS, show_spinner=False)
def cached_supabase_product_asset_map(handles, cache_version):
    return supabase_backend.get_product_asset_map(list(handles or ()))


@st.cache_data(ttl=SUPABASE_PAGE_CACHE_TTL_SECONDS, show_spinner=False)
def cached_supabase_limited_dataset(limit, cache_version):
    return {
        "products": supabase_backend.list_edition_products(search="", limit=int(limit)),
        "asset_map": supabase_backend.get_product_asset_map(),
    }


@st.cache_data(ttl=SUPABASE_PAGE_CACHE_TTL_SECONDS, show_spinner=False)
def cached_supabase_order_summary(cache_version):
    return supabase_backend.get_order_summary()


@st.cache_data(ttl=SUPABASE_PAGE_CACHE_TTL_SECONDS, show_spinner=False)
def cached_supabase_order_summaries(search, sort, status_filter, page_size, cache_version):
    page_size = min(int(page_size or 60), 100)
    fetch_limit = min(max(page_size * 3, page_size), 450)
    while True:
        raw_rows = supabase_backend.list_orders(
            search=search,
            sort=sort,
            status_filter=status_filter,
            limit=fetch_limit,
        )
        order_summaries = _group_supabase_order_rows(raw_rows)
        if len(order_summaries) >= page_size or fetch_limit >= 450 or len(raw_rows) < fetch_limit:
            return order_summaries[:page_size]
        fetch_limit = min(fetch_limit * 2, 450)


@st.cache_data(ttl=SUPABASE_PAGE_CACHE_TTL_SECONDS, show_spinner=False)
def cached_supabase_orders_dataset(limit, cache_version, search="", status_filter="Needs Action"):
    started = time.perf_counter()
    requested_limit = max(int(limit or 50), 50)
    filter_target = requested_limit + 1
    max_query_limit = max(min(ORDER_SCREEN_CACHE_LIMIT, 2500), requested_limit)
    query_limit = min(max(requested_limit * 4, requested_limit), max_query_limit)
    db_status_filter = {
        "Needs Edition": "Needs edition",
        "Assigned": "Assigned",
        "Product Missing": "Errors",
        "Sold Out Issue": "Errors",
        "Errors": "Errors",
    }.get(str(status_filter or "").strip(), "All")
    filtered_summaries = []
    summary = {}

    while True:
        raw_rows = supabase_backend.list_orders(
            search=search,
            sort="Shopify updated",
            status_filter=db_status_filter,
            limit=int(query_limit),
        )
        grouped_summaries = _group_supabase_order_rows(raw_rows)
        filtered_summaries = _filter_supabase_order_summaries(
            grouped_summaries,
            search=search,
            sort="Date newest",
            status_filter=status_filter,
            page_size=filter_target,
        )
        if (
            len(filtered_summaries) >= filter_target
            or query_limit >= max_query_limit
            or len(raw_rows) < query_limit
        ):
            summary = supabase_backend.get_order_summary()
            break
        query_limit = min(query_limit * 2, max_query_limit)

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    visible_summaries = filtered_summaries[:requested_limit]
    perf_log(f"ACTION_ROWS_QUERY count={len(visible_summaries)} time={elapsed_ms}ms")
    perf_log(f"PERF Orders query rows={len(visible_summaries)} time={elapsed_ms / 1000:.3f}s")
    return {
        "summary": summary,
        "order_summaries": visible_summaries,
        "has_more": len(filtered_summaries) > requested_limit,
    }


def load_supabase_screen_snapshot(snapshot_key, cache_version, loader):
    data_key = f"{snapshot_key}-data"
    version_key = f"{snapshot_key}-version"
    current_version = int(cache_version or 0)
    has_existing_snapshot = data_key in st.session_state
    if has_existing_snapshot and st.session_state.get(version_key) == current_version:
        return st.session_state[data_key], False, None
    try:
        snapshot = loader()
    except Exception as error:
        if has_existing_snapshot:
            return st.session_state[data_key], True, error
        raise
    st.session_state[data_key] = snapshot
    st.session_state[version_key] = current_version
    return snapshot, False, None


@st.cache_data(ttl=20, show_spinner=False)
def cached_shopify_orders_mirror_page(search_query, after_cursor, refresh_key):
    config = shopify_sync.get_config()
    return shopify_sync.fetch_orders_page(
        after=after_cursor or None,
        page_size=50,
        config=config,
        query=search_query,
        default_paid_unfulfilled_filter=False,
    )


@st.cache_data(ttl=20, show_spinner=False)
def cached_order_line_assignment_snapshot(line_item_ids, refresh_key):
    return supabase_backend.get_order_line_assignment_snapshot(list(line_item_ids or ()))


def render_local_cache_notice():
    st.warning(
        "Shared cloud storage is not connected in this environment. Showing saved local data for now; "
        "existing live orders, products, edition numbers, and certificates are not changed."
    )


def render_shopify_scope_diagnostics(config, key_prefix):
    st.caption(
        f"Shopify auth: {config.get('auth_mode') or 'Missing credentials'} | "
        f"Store: {config.get('store_domain') or 'Missing'} | "
        f"API: {config.get('api_version') or 'Missing'}"
    )
    st.caption(
        "SHOPIFY_ADMIN_ACCESS_TOKEN: "
        + ("Found (legacy fallback)" if config.get("has_legacy_admin_token") else "Missing (OK when client credentials are configured)")
    )
    if not config.get("configured"):
        if config.get("client_id") and not config.get("client_secret"):
            st.warning("SHOPIFY_CLIENT_SECRET is missing.")
        elif config.get("client_secret") and not config.get("client_id"):
            st.warning("SHOPIFY_CLIENT_ID is missing.")
        elif not config.get("client_id") and not config.get("client_secret") and not config.get("access_token"):
            st.warning(
                "Missing Shopify credentials. Add SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET, "
                "or legacy SHOPIFY_ADMIN_ACCESS_TOKEN."
            )
        return
    if st.button("Test Shopify token and scopes", key=f"{key_prefix}-test-shopify-token", use_container_width=True):
        try:
            result = shopify_sync.test_connection(config=config)
            st.success(f"Connected to {result.get('name')} ({result.get('myshopify_domain')}).")
            scopes = result.get("scopes") or []
            if scopes:
                st.caption("Returned scopes: " + ", ".join(scopes))
                scope_status = result.get("scope_status") or {}
                scope_columns = st.columns(3)
                for index, scope_name in enumerate(
                    ("read_products", "write_products", "read_orders", "write_orders", "read_customers", "write_files")
                ):
                    if scope_status.get(scope_name):
                        scope_columns[index % len(scope_columns)].success(scope_name)
                    else:
                        scope_columns[index % len(scope_columns)].warning(f"{scope_name} missing")
                if not scope_status.get("write_orders"):
                    st.warning("write_orders is required to save certificate metafields back to Shopify orders.")
                if not scope_status.get("write_files"):
                    st.warning("write_files is required to upload certificate PDFs to Shopify Files.")
            else:
                st.caption("Scope list is unavailable for the legacy admin token fallback.")
        except Exception as error:
            st.error("Shopify token test failed.")
            st.exception(error)


def go_to_product(product_id, edit=False):
    st.session_state.selected_product_id = int(product_id)
    st.session_state.editing_product_id = int(product_id) if edit else None
    st.session_state.pending_page = "Products"
    st.rerun()


def render_focus_list(title, products, empty_message):
    with st.container(border=True):
        st.markdown(f"**{title}**")
        if not products:
            st.caption(empty_message)
            return

        for product in products[:6]:
            columns = st.columns([4, 1])
            columns[0].write(product["product_name"])
            with columns[1]:
                if st.button("Open", key=f"focus-open-{title}-{product['id']}", use_container_width=True):
                    go_to_product(product["id"])
        if len(products) > 6:
            st.caption(f"Plus {len(products) - 6} more products.")


def render_supabase_dashboard_page():
    st.subheader("Today's Focus")
    st.caption("Start with the live order and edition screens.")
    focus_columns = st.columns(3)
    focus_columns[0].info("Open Orders to sync paid orders and check edition assignments.")
    focus_columns[1].info("Open Limited Editions to confirm edition totals or import a correction CSV.")
    focus_columns[2].info("Open Files when PSD links or production assets need attention.")


def render_dashboard_page():
    render_page_intro(
        "Sports Cave OS",
        "Order, edition, product, and file control centre.",
        "Start with Today's Focus, then open the products that need attention.",
        "Finish missing product data before moving a product to Live.",
    )
    render_supabase_dashboard_page()
    return

    st.subheader("Dashboard")
    st.caption("The daily command screen for product readiness, missing files, and edition priorities.")
    metrics, focus = db.get_dashboard_data()
    metric_specs = (
        ("Shopify products synced", metrics["shopify_products_synced"]),
        ("Orders synced", metrics["orders_synced"]),
        ("Orders needing editions", metrics["orders_needing_assignment"]),
        ("Orders assigned today", metrics["orders_assigned_today"]),
        ("Certificate PDFs generated", metrics["certificate_pdfs_generated"]),
        ("Products missing edition setup", metrics["shopify_missing_edition_setup"]),
        ("Products missing PSD", metrics["shopify_missing_psd"]),
        ("Products missing Prodigi", metrics["shopify_missing_prodigi"]),
        ("Products needing widget sync", metrics["shopify_needs_widget_sync"]),
        ("Final editions", metrics["shopify_final_editions"]),
        ("Sold out editions", metrics["shopify_sold_out"]),
        ("Internal products", metrics["total_products"]),
        ("Ready for upload", metrics["ready_for_upload"]),
        ("Live products missing files", metrics["live_missing_files"]),
    )
    metric_columns = st.columns(3)
    for index, (label, value) in enumerate(metric_specs):
        metric_columns[index % 3].metric(label, value)

    st.subheader("Today's Focus")
    st.caption("These lists are generated from the product database, so the next useful task is always visible.")
    focus_columns = st.columns(4)
    with focus_columns[0]:
        render_focus_list("Missing PSD", focus["missing_psd"], "Every product has a PSD link.")
        render_focus_list("Missing final JPG", focus["missing_final_jpg"], "Every product has a final JPG link.")
    with focus_columns[1]:
        render_focus_list("Missing WebP folder", focus["missing_webp"], "Every product has a WebP folder.")
        render_focus_list("Missing mockups", focus["missing_mockup"], "Every product has a mockup folder.")
    with focus_columns[2]:
        render_focus_list("Needs asset review", focus["assets_needing_review"], "No asset packs need review.")
        render_focus_list("Live but missing files", focus["live_missing_files"], "No live products are missing core files.")
    with focus_columns[3]:
        render_focus_list("Missing Prodigi", focus["missing_prodigi"], "Every product has Prodigi details.")
        render_focus_list("Missing edition limit", focus["missing_edition_limit"], "Every internal product has an edition limit.")


def shopify_match_suggestion(remote_product, internal_products):
    remote_title = db.normalize_match_value(remote_product.get("title"))
    if not remote_title:
        return None
    matches = [
        product["id"]
        for product in internal_products
        if db.normalize_match_value(product.get("product_name")) == remote_title
    ]
    return matches[0] if len(matches) == 1 else None


def render_shopify_remote_details(remote_product, item_key):
    detail_is_open = st.session_state.get("shopify_detail_id") == remote_product["shopify_product_id"]
    if st.button(
        "Hide Synced Details" if detail_is_open else "Load Synced Details",
        key=f"shopify-details-{item_key}",
    ):
        st.session_state.shopify_detail_id = None if detail_is_open else remote_product["shopify_product_id"]
        st.rerun()
    if not detail_is_open:
        return

    full_product = db.get_shopify_product(remote_product["shopify_product_id"])
    if not full_product:
        st.warning("The cached Shopify details could not be found.")
        return
    tags = full_product.get("tags") or []
    collections = full_product.get("collections") or []
    variants = full_product.get("variants") or []
    metafields = full_product.get("metafields") or []
    with st.container(border=True):
        st.write(f"**Vendor:** {full_product.get('vendor') or 'Not set'}")
        st.write(f"**Product type:** {full_product.get('product_type') or 'Not set'}")
        st.write(f"**Tags:** {', '.join(tags) if tags else 'None'}")
        st.write(
            "**Collections:** "
            + (", ".join(item.get("title") or "Untitled" for item in collections) if collections else "None")
        )
        if variants:
            st.markdown("**Variants**")
            variant_rows = []
            for variant in variants:
                option_text = ", ".join(
                    f"{option.get('name')}: {option.get('value')}"
                    for option in variant.get("selected_options") or []
                )
                variant_rows.append(
                    {
                        "Variant": variant.get("title") or "Default",
                        "Options": option_text,
                        "SKU": variant.get("sku") or "",
                        "Price": variant.get("price") or "",
                        "Inventory": variant.get("inventory_quantity"),
                    }
                )
            st.dataframe(variant_rows, use_container_width=True, hide_index=True)
        if metafields:
            st.caption(f"{len(metafields)} metafield values cached. Values are not edited from Sports Cave OS in Phase 4.")


def render_shopify_sync_panel():
    config = shopify_sync.get_config()
    token_status = shopify_sync.get_token_status(config)
    summary = db.get_shopify_summary()
    latest_run = db.get_latest_shopify_sync_run()

    st.subheader("Shopify edition sync")
    st.caption(
        "Manual Shopify metadata sync for product matching, edition workflows, and storefront metafield foundations. "
        "This does not run automatically during mockup generation."
    )

    notice = st.session_state.pop("shopify_sync_notice", None)
    if notice:
        st.success(notice)

    status_columns = st.columns(4)
    status_columns[0].metric("Connection", "Configured" if config["configured"] else "Not configured")
    status_columns[1].metric("Cached Shopify products", summary["total"])
    status_columns[2].metric("Matched", summary["matched"])
    status_columns[3].metric("Needs matching", summary["unmatched"])

    st.caption(
        f"Store domain: {config['store_domain'] or 'Missing'} | "
        f"API version: {config['api_version'] or 'Missing'} | Auth: {config['auth_mode']} | "
        f"Last catalog sync: {format_updated_at(summary['last_synced_at']) if summary['last_synced_at'] else 'Never'}"
    )
    if latest_run:
        st.caption(
            f"Latest run: {latest_run['status']} | {latest_run['products_seen']} products | "
            f"{latest_run['pages_synced']} pages"
        )

    if not config["configured"]:
        st.warning(
            "Shopify is not connected yet. Configure SHOPIFY_STORE_DOMAIN, SHOPIFY_API_VERSION, "
            "and either SHOPIFY_ADMIN_ACCESS_TOKEN or SHOPIFY_CLIENT_ID plus SHOPIFY_CLIENT_SECRET "
            "in Render environment variables."
        )
    elif token_status["auth_mode"] == "Client credentials mode":
        st.caption(
            "Client credentials are configured. A temporary access token is requested only when Test or Sync is clicked."
        )

    action_columns = st.columns([1, 1, 2])
    test_clicked = action_columns[0].button(
        "Test Shopify Connection",
        disabled=not config["configured"],
        use_container_width=True,
    )
    sync_clicked = action_columns[1].button(
        "Sync Shopify Products",
        type="primary",
        disabled=not config["configured"],
        use_container_width=True,
    )
    action_columns[2].caption(
        "Sync runs only when this button is clicked. It does not run during mockup generation or normal page loads."
    )

    if test_clicked:
        try:
            with st.spinner("Testing Shopify connection..."):
                shop = shopify_sync.test_connection(config=config)
            st.success(
                f"Connected to {shop['name']} ({shop['myshopify_domain']}). "
                f"Shopify served API version {shop['api_version']}."
            )
        except Exception as error:
            st.error("Could not connect to Shopify.")
            st.error(str(error))

    if sync_clicked:
        run_id = db.start_shopify_sync(config["store_domain"], config["api_version"])
        progress = st.progress(0, text="Starting Shopify catalog sync...")
        products_seen = 0
        pages_synced = 0
        try:
            for page in shopify_sync.iter_catalog_pages(config=config):
                db.upsert_shopify_products(page["products"])
                products_seen += len(page["products"])
                pages_synced += 1
                db.update_shopify_sync_run(
                    run_id,
                    products_seen=products_seen,
                    pages_synced=pages_synced,
                    api_version=page.get("api_version"),
                )
                percent = min(int(products_seen / config["max_products"] * 100), 99)
                progress.progress(percent, text=f"Synced {products_seen} Shopify products...")
                del page
                gc.collect()
            matched_count = db.auto_match_shopify_products()
            db.update_shopify_sync_run(
                run_id,
                status="Complete",
                products_seen=products_seen,
                pages_synced=pages_synced,
            )
            progress.progress(100, text="Shopify catalog sync complete.")
            st.session_state.shopify_sync_notice = (
                f"Synced {products_seen} Shopify products. {matched_count} new exact matches were connected."
            )
            st.rerun()
        except Exception as error:
            db.update_shopify_sync_run(
                run_id,
                status="Failed",
                products_seen=products_seen,
                pages_synced=pages_synced,
                error_message=str(error),
            )
            progress.empty()
            st.error("Shopify sync failed. Existing cached products were kept.")
            st.error(str(error))

    st.subheader("Cached Shopify products")
    filter_columns = st.columns([2, 1, 1, 1])
    search = filter_columns[0].text_input("Search Shopify products", placeholder="Title or handle")
    status_filter = filter_columns[1].selectbox("Shopify status", ["All", "ACTIVE", "DRAFT", "ARCHIVED"])
    match_filter = filter_columns[2].selectbox("Match status", ["All", "Unmatched", "Matched"])
    display_limit = filter_columns[3].selectbox("Show", [25, 50, 100], index=0)

    remote_products = db.list_shopify_products(search, status_filter, match_filter)
    internal_products = db.list_products(include_archived=False)
    internal_by_id = {product["id"]: product for product in internal_products}
    st.caption(f"Showing {min(len(remote_products), display_limit)} of {len(remote_products)} cached Shopify products")
    if not remote_products:
        st.info("No cached Shopify products match these filters. Connect Shopify and run a manual sync first.")
        return

    for remote in remote_products[:display_limit]:
        item_key = remote.get("legacy_resource_id") or str(abs(hash(remote["shopify_product_id"])))
        with st.container(border=True):
            summary_columns = st.columns([3, 1, 1, 1.3])
            summary_columns[0].markdown(f"**{remote['title']}**")
            summary_columns[0].caption(remote.get("handle") or "Handle missing")
            summary_columns[1].markdown(status_badge(f"Shopify {remote['status'].title()}"), unsafe_allow_html=True)
            summary_columns[2].write(f"{remote['variant_count']} variants")
            summary_columns[2].caption(f"{remote.get('image_count')} images")
            summary_columns[3].caption("Shopify updated")
            summary_columns[3].write(format_updated_at(remote.get("remote_updated_at")))

            link_columns = st.columns([1, 1, 3])
            if remote.get("admin_url"):
                link_columns[0].link_button("Open Shopify Admin", remote["admin_url"], use_container_width=True)
            if remote.get("online_store_url"):
                link_columns[1].link_button("Open Live Product", remote["online_store_url"], use_container_width=True)

            if remote.get("matched_product_id"):
                st.success(
                    f"Matched to {remote.get('matched_product_name') or 'internal product'} "
                    f"via {remote.get('match_source') or 'manual match'}."
                )
                match_actions = st.columns([1, 1, 3])
                if match_actions[0].button("Open Product", key=f"shopify-open-{item_key}", use_container_width=True):
                    go_to_product(remote["matched_product_id"])
                if match_actions[1].button("Unmatch", key=f"shopify-unmatch-{item_key}", use_container_width=True):
                    db.unmatch_shopify_product(remote["shopify_product_id"])
                    st.rerun()
            else:
                suggestion = shopify_match_suggestion(remote, internal_products)
                if suggestion:
                    st.info(f"Suggested internal match: {internal_by_id[suggestion]['product_name']}")
                match_columns = st.columns([3, 1, 1])
                product_options = [None, *internal_by_id.keys()]
                default_index = product_options.index(suggestion) if suggestion in product_options else 0
                selected_product_id = match_columns[0].selectbox(
                    "Match to internal product",
                    product_options,
                    index=default_index,
                    format_func=lambda value: "Choose a product" if value is None else internal_by_id[value]["product_name"],
                    key=f"shopify-match-select-{item_key}",
                )
                if match_columns[1].button(
                    "Confirm Match",
                    key=f"shopify-match-{item_key}",
                    disabled=selected_product_id is None,
                    use_container_width=True,
                ):
                    db.match_shopify_product(remote["shopify_product_id"], selected_product_id)
                    st.rerun()
                if match_columns[2].button(
                    "Create Product",
                    key=f"shopify-create-{item_key}",
                    use_container_width=True,
                ):
                    product_id = db.create_product_from_shopify(remote["shopify_product_id"])
                    go_to_product(product_id)

            render_shopify_remote_details(remote, item_key)


def render_shopify_sync_page():
    render_page_intro(
        "Shopify Sync",
        "A manual, lightweight Shopify catalog sync for matching live store products to Sports Cave master records.",
        "Test the connection, sync the catalog, then resolve any unmatched products.",
        "Check the handle and product title before confirming a manual match.",
    )
    render_shopify_sync_panel()

    notice = st.session_state.pop("shopify_sync_notice", None)
    if notice:
        st.success(notice)

    status_columns = st.columns(4)
    status_columns[0].metric("Connection", "Configured" if config["configured"] else "Not configured")
    status_columns[1].metric("Shopify products cached", summary["total"])
    status_columns[2].metric("Matched", summary["matched"])
    status_columns[3].metric("Needs matching", summary["unmatched"])

    st.caption(
        f"Store domain: {config['store_domain'] or 'Missing'} | "
        f"API version: {config['api_version'] or 'Missing'} | Auth: {config['auth_mode']} | "
        f"Last catalog sync: {format_updated_at(summary['last_synced_at']) if summary['last_synced_at'] else 'Never'}"
    )
    if latest_run:
        st.caption(
            f"Latest run: {latest_run['status']} | {latest_run['products_seen']} products | "
            f"{latest_run['pages_synced']} pages"
        )

    if not config["configured"]:
        st.warning(
            "Shopify is not connected yet. Configure SHOPIFY_STORE_DOMAIN, SHOPIFY_API_VERSION, "
            "and either SHOPIFY_ADMIN_ACCESS_TOKEN or SHOPIFY_CLIENT_ID plus SHOPIFY_CLIENT_SECRET "
            "in Render environment variables."
        )
    elif token_status["auth_mode"] == "Client credentials mode":
        st.caption(
            "Client credentials are configured. A temporary access token is requested only when Test or Sync is clicked."
        )

    action_columns = st.columns([1, 1, 2])
    test_clicked = action_columns[0].button(
        "Test Shopify Connection",
        disabled=not config["configured"],
        use_container_width=True,
    )
    sync_clicked = action_columns[1].button(
        "Sync Shopify Products",
        type="primary",
        disabled=not config["configured"],
        use_container_width=True,
    )
    action_columns[2].caption(
        "Sync runs only when this button is clicked. It does not run during mockup generation or normal page loads."
    )

    if test_clicked:
        try:
            with st.spinner("Testing Shopify connection..."):
                shop = shopify_sync.test_connection(config=config)
            st.success(
                f"Connected to {shop['name']} ({shop['myshopify_domain']}). "
                f"Shopify served API version {shop['api_version']}."
            )
        except Exception as error:
            st.error("Could not connect to Shopify.")
            st.error(str(error))

    if sync_clicked:
        run_id = db.start_shopify_sync(config["store_domain"], config["api_version"])
        progress = st.progress(0, text="Starting Shopify catalog sync...")
        products_seen = 0
        pages_synced = 0
        try:
            for page in shopify_sync.iter_catalog_pages(config=config):
                db.upsert_shopify_products(page["products"])
                products_seen += len(page["products"])
                pages_synced += 1
                db.update_shopify_sync_run(
                    run_id,
                    products_seen=products_seen,
                    pages_synced=pages_synced,
                    api_version=page.get("api_version"),
                )
                percent = min(int(products_seen / config["max_products"] * 100), 99)
                progress.progress(percent, text=f"Synced {products_seen} Shopify products...")
                del page
                gc.collect()
            matched_count = db.auto_match_shopify_products()
            db.update_shopify_sync_run(
                run_id,
                status="Complete",
                products_seen=products_seen,
                pages_synced=pages_synced,
            )
            progress.progress(100, text="Shopify catalog sync complete.")
            st.session_state.shopify_sync_notice = (
                f"Synced {products_seen} Shopify products. {matched_count} new exact matches were connected."
            )
            st.rerun()
        except Exception as error:
            db.update_shopify_sync_run(
                run_id,
                status="Failed",
                products_seen=products_seen,
                pages_synced=pages_synced,
                error_message=str(error),
            )
            progress.empty()
            st.error("Shopify sync failed. Existing cached products were kept.")
            st.error(str(error))

    st.subheader("Shopify Product Matching")
    filter_columns = st.columns([2, 1, 1, 1])
    search = filter_columns[0].text_input("Search Shopify products", placeholder="Title or handle")
    status_filter = filter_columns[1].selectbox("Shopify status", ["All", "ACTIVE", "DRAFT", "ARCHIVED"])
    match_filter = filter_columns[2].selectbox("Match status", ["All", "Unmatched", "Matched"])
    display_limit = filter_columns[3].selectbox("Show", [25, 50, 100], index=0)

    remote_products = db.list_shopify_products(search, status_filter, match_filter)
    internal_products = db.list_products(include_archived=False)
    internal_by_id = {product["id"]: product for product in internal_products}
    st.caption(f"Showing {min(len(remote_products), display_limit)} of {len(remote_products)} cached Shopify products")
    if not remote_products:
        st.info("No cached Shopify products match these filters. Connect Shopify and run a manual sync first.")
        return

    for remote in remote_products[:display_limit]:
        item_key = remote.get("legacy_resource_id") or str(abs(hash(remote["shopify_product_id"])))
        with st.container(border=True):
            summary_columns = st.columns([3, 1, 1, 1.3])
            summary_columns[0].markdown(f"**{remote['title']}**")
            summary_columns[0].caption(remote.get("handle") or "Handle missing")
            summary_columns[1].markdown(status_badge(f"Shopify {remote['status'].title()}"), unsafe_allow_html=True)
            summary_columns[2].write(f"{remote['variant_count']} variants")
            summary_columns[2].caption(f"{remote['image_count']} images")
            summary_columns[3].caption("Shopify updated")
            summary_columns[3].write(format_updated_at(remote.get("remote_updated_at")))

            link_columns = st.columns([1, 1, 3])
            if remote.get("admin_url"):
                link_columns[0].link_button("Open Shopify Admin", remote["admin_url"], use_container_width=True)
            if remote.get("online_store_url"):
                link_columns[1].link_button("Open Live Product", remote["online_store_url"], use_container_width=True)

            if remote.get("matched_product_id"):
                st.success(
                    f"Matched to {remote.get('matched_product_name') or 'internal product'} "
                    f"via {remote.get('match_source') or 'manual match'}."
                )
                match_actions = st.columns([1, 1, 3])
                if match_actions[0].button("Open Product", key=f"shopify-open-{item_key}", use_container_width=True):
                    go_to_product(remote["matched_product_id"])
                if match_actions[1].button("Unmatch", key=f"shopify-unmatch-{item_key}", use_container_width=True):
                    db.unmatch_shopify_product(remote["shopify_product_id"])
                    st.rerun()
            else:
                suggestion = shopify_match_suggestion(remote, internal_products)
                if suggestion:
                    st.info(f"Suggested internal match: {internal_by_id[suggestion]['product_name']}")
                match_columns = st.columns([3, 1, 1])
                product_options = [None, *internal_by_id.keys()]
                default_index = product_options.index(suggestion) if suggestion in product_options else 0
                selected_product_id = match_columns[0].selectbox(
                    "Match to internal product",
                    product_options,
                    index=default_index,
                    format_func=lambda value: "Choose a product" if value is None else internal_by_id[value]["product_name"],
                    key=f"shopify-match-select-{item_key}",
                )
                if match_columns[1].button(
                    "Confirm Match",
                    key=f"shopify-match-{item_key}",
                    disabled=selected_product_id is None,
                    use_container_width=True,
                ):
                    db.match_shopify_product(remote["shopify_product_id"], selected_product_id)
                    st.rerun()
                if match_columns[2].button(
                    "Create Product",
                    key=f"shopify-create-{item_key}",
                    use_container_width=True,
                ):
                    product_id = db.create_product_from_shopify(remote["shopify_product_id"])
                    go_to_product(product_id)

            render_shopify_remote_details(remote, item_key)


def product_form_fields(prefix, product=None):
    product = product or {}
    left, right = st.columns(2)
    with left:
        product_name = st.text_input("Product name *", value=product.get("product_name", ""), key=f"{prefix}-name")
        handle = st.text_input("Handle", value=product.get("handle", ""), key=f"{prefix}-handle")
        sport_category = st.selectbox(
            "Sport category",
            list(db.SPORT_CATEGORIES),
            index=select_index(list(db.SPORT_CATEGORIES), product.get("sport_category", "Other"), len(db.SPORT_CATEGORIES) - 1),
            key=f"{prefix}-sport",
        )
        country_focus = st.selectbox(
            "Country focus",
            list(db.COUNTRY_FOCUS_OPTIONS),
            index=select_index(list(db.COUNTRY_FOCUS_OPTIONS), product.get("country_focus", "Global"), len(db.COUNTRY_FOCUS_OPTIONS) - 1),
            key=f"{prefix}-country",
        )
        status = st.selectbox(
            "Status",
            list(db.PRODUCT_STATUSES),
            index=select_index(list(db.PRODUCT_STATUSES), product.get("status", "Idea")),
            key=f"{prefix}-status",
        )
        shopify_product_id = st.text_input(
            "Shopify product ID",
            value=product.get("shopify_product_id", ""),
            key=f"{prefix}-shopify-id",
        )
        prodigi_product_id = st.text_input(
            "Prodigi product ID",
            value=product.get("prodigi_product_id", ""),
            key=f"{prefix}-prodigi-id",
        )
        prodigi_product_url = st.text_input(
            "Prodigi product URL",
            value=product.get("prodigi_product_url", ""),
            key=f"{prefix}-prodigi-url",
        )
    with right:
        shopify_admin_url = st.text_input(
            "Shopify admin URL",
            value=product.get("shopify_admin_url", ""),
            key=f"{prefix}-shopify-url",
        )
        live_product_url = st.text_input(
            "Live product URL",
            value=product.get("live_product_url", ""),
            key=f"{prefix}-live-url",
        )
        psd_file_url = st.text_input("PSD file URL", value=product.get("psd_file_url", ""), key=f"{prefix}-psd")
        final_jpg_url = st.text_input(
            "Final JPG URL", value=product.get("final_jpg_url") or product.get("jpg_file_url", ""), key=f"{prefix}-jpg"
        )
        webp_folder_url = st.text_input(
            "WebP folder URL", value=product.get("webp_folder_url", ""), key=f"{prefix}-webp"
        )
        mockup_folder_url = st.text_input(
            "Mockup folder URL", value=product.get("mockup_folder_url", ""), key=f"{prefix}-mockup"
        )
        size_guide_url = st.text_input(
            "Size guide URL", value=product.get("size_guide_url", ""), key=f"{prefix}-size-guide"
        )
        lifestyle_folder_url = st.text_input(
            "Lifestyle folder URL", value=product.get("lifestyle_folder_url", ""), key=f"{prefix}-lifestyle"
        )
        prompt_pack_url = st.text_input(
            "Prompt pack URL", value=product.get("prompt_pack_url", ""), key=f"{prefix}-prompt-pack"
        )
        product_upload_zip_url = st.text_input(
            "Product upload ZIP URL", value=product.get("product_upload_zip_url", ""), key=f"{prefix}-upload-zip"
        )
        certificate_folder_url = st.text_input(
            "Certificate folder URL",
            value=product.get("certificate_folder_url", ""),
            key=f"{prefix}-certificate",
        )
        ads_social_folder_url = st.text_input(
            "Ads/social folder URL", value=product.get("ads_social_folder_url", ""), key=f"{prefix}-ads-social"
        )
        google_drive_root_folder_url = st.text_input(
            "Google Drive root product folder URL",
            value=product.get("google_drive_root_folder_url", ""),
            key=f"{prefix}-drive-root",
        )
        prodigi_notes = st.text_area(
            "Prodigi notes",
            value=product.get("prodigi_notes", ""),
            key=f"{prefix}-prodigi-notes",
            height=90,
        )
    notes = st.text_area("VA notes", value=product.get("notes", ""), key=f"{prefix}-notes", height=120)
    return {
        "shopify_product_id": shopify_product_id,
        "product_name": product_name,
        "handle": handle,
        "sport_category": sport_category,
        "country_focus": country_focus,
        "status": status,
        "shopify_admin_url": shopify_admin_url,
        "live_product_url": live_product_url,
        "prodigi_product_id": prodigi_product_id,
        "prodigi_product_url": prodigi_product_url,
        "prodigi_notes": prodigi_notes,
        "psd_file_url": psd_file_url,
        "jpg_file_url": final_jpg_url,
        "final_jpg_url": final_jpg_url,
        "webp_folder_url": webp_folder_url,
        "mockup_folder_url": mockup_folder_url,
        "size_guide_url": size_guide_url,
        "lifestyle_folder_url": lifestyle_folder_url,
        "prompt_pack_url": prompt_pack_url,
        "product_upload_zip_url": product_upload_zip_url,
        "certificate_folder_url": certificate_folder_url,
        "ads_social_folder_url": ads_social_folder_url,
        "google_drive_root_folder_url": google_drive_root_folder_url,
        "notes": notes,
    }


def render_add_product_form():
    with st.container(border=True):
        st.subheader("Add New Product")
        with st.form("add-product-form", clear_on_submit=True):
            payload = product_form_fields("add-product")
            submitted = st.form_submit_button("Save Product", type="primary", use_container_width=True)

        if submitted:
            if not payload["product_name"].strip():
                st.error("Product name is required.")
            else:
                product_id = db.create_product(payload)
                st.session_state.show_add_product = False
                st.session_state.selected_product_id = product_id
                st.success("Product saved.")
                st.rerun()


def render_product_row(product):
    with st.container(border=True):
        summary = st.columns([3.1, 1.25, 1.35, 1.45, 1.45])
        summary[0].markdown(f"**{product['product_name']}**")
        summary[0].caption(product.get("handle") or "Handle missing")
        summary[1].write(product.get("sport_category") or "Other")
        summary[1].caption(product.get("country_focus") or "Global")
        summary[2].markdown(status_badge(product.get("status")), unsafe_allow_html=True)
        summary[3].write(f"{format_optional_number(product.get('editions_remaining'))} remaining")
        summary[3].markdown(status_badge(product.get("edition_status") or "Not Set"), unsafe_allow_html=True)
        summary[4].caption("Last updated")
        summary[4].write(format_updated_at(product.get("updated_at")))

        st.markdown(
            " ".join(
                status_badge(value)
                for value in (
                    product.get("readiness_status"),
                    product.get("overall_asset_readiness"),
                    f"Prodigi {product.get('prodigi_status')}",
                    product.get("shopify_sync_status"),
                )
            ),
            unsafe_allow_html=True,
        )

        actions = st.columns([1, 1, 1, 4])
        with actions[0]:
            if st.button("Open Product", key=f"open-product-{product['id']}", use_container_width=True):
                go_to_product(product["id"])
        with actions[1]:
            if st.button("Edit Product", key=f"edit-product-{product['id']}", use_container_width=True):
                go_to_product(product["id"], edit=True)
        with actions[2]:
            if product.get("status") == "Archived":
                if st.button("Restore", key=f"restore-product-{product['id']}", use_container_width=True):
                    db.restore_product(product["id"])
                    st.rerun()
            else:
                with st.popover("Archive", use_container_width=True):
                    st.caption("Archive hides this product from normal VA lists. No data is deleted.")
                    confirm_archive = st.checkbox(
                        "I understand",
                        key=f"confirm-archive-{product['id']}",
                    )
                    if st.button(
                        "Archive Product",
                        key=f"archive-product-{product['id']}",
                        disabled=not confirm_archive,
                        use_container_width=True,
                    ):
                        db.archive_product(product["id"])
                        st.rerun()


def render_supabase_products_page():
    page_started = time.perf_counter()
    render_page_intro(
        "Products",
        "Fast Supabase catalogue view for Sports Cave product records.",
        "Search or page through saved products. Open Limited Editions for counter edits.",
        "This page does not call Shopify unless you use sync tools elsewhere.",
    )

    controls = st.columns([2.4, 0.8, 0.8, 1.0])
    search = controls[0].text_input(
        "Search products",
        placeholder="Product title, Shopify handle, or SKU",
        key="supabase-products-search",
    )
    if "supabase-products-page" not in st.session_state:
        st.session_state["supabase-products-page"] = 0
    filter_signature = search.strip().lower()
    if st.session_state.get("supabase-products-filter-signature") != filter_signature:
        st.session_state["supabase-products-filter-signature"] = filter_signature
        st.session_state["supabase-products-page"] = 0

    page_size = DEFAULT_PAGE_SIZE
    current_page = max(int(st.session_state.get("supabase-products-page", 0) or 0), 0)
    offset = current_page * page_size
    cache_version = supabase_cache_version("limited")

    db_started = time.perf_counter()
    try:
        products = cached_supabase_limited_products(search, page_size + 1, offset, cache_version)
    except Exception as error:
        supabase_backend.log_app_error("products_page_load_failed", str(error), {"source": "products_page"})
        st.error("Products are not available right now. The saved Supabase data was not changed.")
        perf_log(f"PERF Products total={(time.perf_counter() - page_started):.3f}s db={(time.perf_counter() - db_started):.3f}s render=0.000s rows=0")
        return
    db_elapsed = time.perf_counter() - db_started
    perf_log(f"PERF Products query rows={min(len(products), page_size)} time={db_elapsed:.3f}s")

    has_next = len(products) > page_size
    visible_products = products[:page_size]
    controls[1].download_button(
        "Export shown",
        data=build_supabase_products_csv(visible_products, {}),
        file_name="sports-cave-products-shown.csv",
        mime="text/csv",
        use_container_width=True,
    )
    if controls[2].button("Limited Editions", use_container_width=True):
        st.session_state.pending_page = "Limited Editions"
        st.rerun()
    controls[3].caption(f"Page {current_page + 1} | {len(visible_products)} shown")

    render_started = time.perf_counter()
    if not visible_products:
        st.info("No saved Supabase products match this search yet.")
    else:
        header = st.columns([2.4, 1.35, 0.9, 0.9, 1.1, 0.9])
        for column, label in zip(header, ("Product", "Handle", "Next", "Remaining", "Status", "Open")):
            column.caption(label)
        for index, product in enumerate(visible_products):
            row = st.columns([2.4, 1.35, 0.9, 0.9, 1.1, 0.9])
            row[0].write(product.get("product_title") or "Untitled product")
            row[1].caption(product.get("shopify_handle") or "-")
            row[2].write(product.get("next_edition_number") or "-")
            row[3].write(product.get("remaining_count") if product.get("remaining_count") is not None else "-")
            row[4].write(str(product.get("status") or product.get("edition_status") or "Active").replace("_", " ").title())
            with row[5]:
                if product.get("admin_url"):
                    st.link_button("Shopify", product["admin_url"], use_container_width=True)
                elif product.get("online_store_url"):
                    st.link_button("Storefront", product["online_store_url"], use_container_width=True)
                else:
                    st.caption("Saved")

    pager = st.columns([0.8, 0.8, 2.8])
    if pager[0].button("Previous", disabled=current_page <= 0, use_container_width=True, key="supabase-products-prev"):
        st.session_state["supabase-products-page"] = max(current_page - 1, 0)
        st.rerun()
    if pager[1].button("Next", disabled=not has_next, use_container_width=True, key="supabase-products-next"):
        st.session_state["supabase-products-page"] = current_page + 1
        st.rerun()
    pager[2].caption("Products are read from Supabase/Postgres only. Shopify product sync stays manual.")
    render_elapsed = time.perf_counter() - render_started
    perf_log(
        f"PERF Products total={(time.perf_counter() - page_started):.3f}s "
        f"db={db_elapsed:.3f}s render={render_elapsed:.3f}s rows={len(visible_products)}"
    )


def render_products_page():
    if supabase_backend.is_configured():
        render_supabase_products_page()
        return

    selected_product_id = st.session_state.get("selected_product_id")
    if selected_product_id:
        render_product_detail_page(selected_product_id)
        return

    render_page_intro(
        "Products",
        "One master record for every Sports Cave artwork, file link, product status, and edition setting.",
        "Search for an existing product or add a new master record.",
        "Check for an existing product before adding another one.",
    )

    actions = st.columns([1.2, 1.2, 1.2, 1.4])
    with actions[0]:
        if st.button("Add New Product", type="primary", use_container_width=True):
            st.session_state.show_add_product = not st.session_state.get("show_add_product", False)
    with actions[1]:
        export_products = db.products_for_export()
        st.download_button(
            "Export Products CSV",
            data=build_products_csv(export_products),
            file_name="sports-cave-products.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with actions[2]:
        if st.button("Open Limited Editions", use_container_width=True):
            st.session_state.pending_page = "Limited Editions"
            st.rerun()
    if st.session_state.get("show_add_product"):
        render_add_product_form()

    filter_columns = st.columns([2.2, 1.1, 1.1, 1.1, 1.2])
    search = filter_columns[0].text_input("Search products", placeholder="Product name or handle")
    sport_filter = filter_columns[1].selectbox("Sport category", ["All", *db.SPORT_CATEGORIES])
    country_filter = filter_columns[2].selectbox("Country focus", ["All", *db.COUNTRY_FOCUS_OPTIONS])
    status_filter = filter_columns[3].selectbox("Status", ["All", *db.PRODUCT_STATUSES])
    edition_filter = filter_columns[4].selectbox("Edition status", ["All", *db.EDITION_STATUSES[:-1]])

    products = db.list_products(
        search=search,
        sport_category=sport_filter,
        country_focus=country_filter,
        status=status_filter,
        edition_status=edition_filter,
        include_archived=status_filter == "Archived",
    )
    st.caption(f"{len(products)} product{'s' if len(products) != 1 else ''} found")
    if not products:
        st.info("No products match these filters yet.")
        return

    header = st.columns([3.1, 1.25, 1.35, 1.45, 1.45])
    for column, label in zip(
        header,
        ("Product / Handle", "Sport / Country", "Product status", "Edition", "Updated"),
    ):
        column.caption(label)
    for product in products:
        render_product_row(product)


def render_product_overview(product):
    st.subheader("Product Overview")
    overview_columns = st.columns(6)
    overview_columns[0].markdown("**Handle**")
    overview_columns[0].write(product.get("handle") or "Missing")
    overview_columns[1].markdown("**Sport**")
    overview_columns[1].write(product.get("sport_category") or "Other")
    overview_columns[2].markdown("**Country**")
    overview_columns[2].write(product.get("country_focus") or "Global")
    overview_columns[3].markdown("**Product status**")
    overview_columns[3].markdown(status_badge(product.get("status")), unsafe_allow_html=True)
    overview_columns[4].markdown("**Readiness**")
    overview_columns[4].markdown(status_badge(product.get("readiness_status")), unsafe_allow_html=True)
    overview_columns[5].markdown("**Asset readiness**")
    overview_columns[5].markdown(
        status_badge(product.get("overall_asset_readiness")),
        unsafe_allow_html=True,
    )

    edit_requested = st.session_state.get("editing_product_id") == product["id"]
    with st.expander("Edit Product Overview", expanded=edit_requested):
        with st.form(f"edit-product-{product['id']}"):
            left, right = st.columns(2)
            product_name = left.text_input("Product name *", value=product.get("product_name") or "")
            handle = left.text_input("Handle", value=product.get("handle") or "")
            sport_category = left.selectbox(
                "Sport category",
                list(db.SPORT_CATEGORIES),
                index=select_index(list(db.SPORT_CATEGORIES), product.get("sport_category"), len(db.SPORT_CATEGORIES) - 1),
            )
            country_focus = left.selectbox(
                "Country focus",
                list(db.COUNTRY_FOCUS_OPTIONS),
                index=select_index(list(db.COUNTRY_FOCUS_OPTIONS), product.get("country_focus"), len(db.COUNTRY_FOCUS_OPTIONS) - 1),
            )
            status = right.selectbox(
                "Product status",
                list(db.PRODUCT_STATUSES),
                index=select_index(list(db.PRODUCT_STATUSES), product.get("status")),
            )
            shopify_product_id = right.text_input(
                "Shopify product ID",
                value=product.get("shopify_product_id") or "",
            )
            shopify_admin_url = right.text_input(
                "Shopify admin URL",
                value=product.get("shopify_admin_url") or "",
            )
            live_product_url = right.text_input(
                "Live product URL",
                value=product.get("live_product_url") or "",
            )
            form_actions = st.columns(2)
            submitted = form_actions[0].form_submit_button(
                "Save Product Changes",
                type="primary",
                use_container_width=True,
            )
            cancelled = form_actions[1].form_submit_button("Cancel", use_container_width=True)
        if submitted:
            if not product_name.strip():
                st.error("Product name is required.")
            else:
                db.update_product_fields(
                    product["id"],
                    product_name=product_name,
                    handle=handle,
                    sport_category=sport_category,
                    country_focus=country_focus,
                    status=status,
                    shopify_product_id=shopify_product_id,
                    shopify_admin_url=shopify_admin_url,
                    live_product_url=live_product_url,
                )
                st.session_state.editing_product_id = None
                st.rerun()
        if cancelled:
            st.session_state.editing_product_id = None
            st.rerun()


def render_quick_links(product):
    st.subheader("Quick Links")
    columns = st.columns(3)
    links = [
        (asset["url_field"], asset["open_label"], product["asset_statuses"][asset["key"]])
        for asset in db.ASSET_DEFINITIONS
    ]
    links.extend((field, label, "Connected" if product.get(field) else "Missing") for field, label in QUICK_LINKS)
    for index, (field, label, link_status) in enumerate(links):
        with columns[index % 3]:
            with st.container(border=True):
                st.markdown(f"**{label.replace('Open ', '')}**")
                if product.get(field):
                    st.markdown(status_badge(link_status), unsafe_allow_html=True)
                    st.link_button(label, product[field], use_container_width=True)
                else:
                    st.markdown(status_badge("Missing"), unsafe_allow_html=True)


def render_asset_card(product, asset):
    asset_key = asset["key"]
    status = product["asset_statuses"][asset_key]
    with st.container(border=True):
        header = st.columns([2.2, 1.2])
        header[0].markdown(f"**{asset['label']}**")
        header[1].markdown(status_badge(status), unsafe_allow_html=True)
        updated_at = product["asset_updated_at"].get(asset_key)
        st.caption(f"Updated {format_updated_at(updated_at)}")
        if product.get(asset["url_field"]):
            st.link_button(asset["open_label"], product[asset["url_field"]], use_container_width=True)
        else:
            st.caption("Missing")


def render_asset_group_editor(product, group_name, assets):
    with st.expander(f"Edit {group_name}"):
        with st.form(f"asset-group-{product['id']}-{group_name}"):
            updates = {}
            for asset in assets:
                fields = st.columns([2.2, 1])
                url = fields[0].text_input(
                    f"{asset['label']} URL",
                    value=product.get(asset["url_field"]) or "",
                    key=f"asset-url-{product['id']}-{asset['key']}",
                )
                manual_status = product["asset_manual_statuses"].get(asset["key"], "Automatic")
                automatic_status = "Connected" if product.get(asset["url_field"]) else "Missing"
                status_options = (automatic_status, "Needs Review", "Approved")
                selected_status = manual_status if manual_status in {"Needs Review", "Approved"} else automatic_status
                status = fields[1].selectbox(
                    f"{asset['label']} status",
                    status_options,
                    index=select_index(status_options, selected_status),
                    key=f"asset-status-{product['id']}-{asset['key']}",
                    help="Missing and Connected follow the URL automatically. Needs Review and Approved are manual.",
                )
                updates[asset["key"]] = {"url": url, "manual_status": status}
            submitted = st.form_submit_button(
                f"Save {group_name}",
                type="primary",
                use_container_width=True,
            )
        if submitted:
            db.update_product_assets(product["id"], updates)
            st.success(f"{group_name} updated.")
            st.rerun()


def recommended_drive_structure(product_name):
    return "\n".join(
        (
            "Sports Cave Products",
            f"└── {product_name or '[Product Name]'}",
            "    ├── 01 PSD",
            "    ├── 02 Final JPG",
            "    ├── 03 Shopify Images WebP",
            "    ├── 04 Mockups",
            "    ├── 05 Lifestyle ChatGPT",
            "    ├── 06 Prompt Pack",
            "    ├── 07 Certificates",
            "    └── 08 Ads Social",
        )
    )


def render_drive_folder_helper(product):
    st.subheader("Recommended Google Drive Folder Structure")
    st.caption("Use this standard structure so every VA can find the correct product assets quickly.")
    st.code(recommended_drive_structure(product.get("product_name")), language=None)

    with st.form(f"drive-root-{product['id']}"):
        root_url = st.text_input(
            "Google Drive Root Product Folder URL",
            value=product.get("google_drive_root_folder_url") or "",
        )
        submitted = st.form_submit_button("Save Root Drive Folder", type="primary")
    if submitted:
        db.update_product_fields(product["id"], google_drive_root_folder_url=root_url)
        st.rerun()
    if product.get("google_drive_root_folder_url"):
        st.link_button(
            "Open Product Drive Folder",
            product["google_drive_root_folder_url"],
        )


def render_file_hub(product):
    st.subheader("File Hub")
    st.markdown("**Overall asset readiness**")
    st.markdown(status_badge(product.get("overall_asset_readiness")), unsafe_allow_html=True)
    st.caption("Automatic statuses stay Connected while a URL exists. Use Needs Review or Approved for manual control.")

    for group_name in db.ASSET_GROUP_NAMES:
        assets = [asset for asset in db.ASSET_DEFINITIONS if asset["group"] == group_name]
        st.markdown(f"### {group_name}")
        columns = st.columns(2)
        for index, asset in enumerate(assets):
            with columns[index % 2]:
                render_asset_card(product, asset)
        render_asset_group_editor(product, group_name, assets)

    st.divider()
    render_drive_folder_helper(product)


def render_prodigi_mapping(product):
    st.subheader("Prodigi Mapping")
    st.markdown(
        status_badge("Connected" if product.get("prodigi_product_id") else "Missing"),
        unsafe_allow_html=True,
    )
    with st.form(f"prodigi-form-{product['id']}"):
        prodigi_id = st.text_input("Prodigi Product ID", value=product.get("prodigi_product_id") or "")
        prodigi_url = st.text_input("Prodigi Product URL", value=product.get("prodigi_product_url") or "")
        prodigi_notes = st.text_area("Prodigi notes", value=product.get("prodigi_notes") or "", height=110)
        submitted = st.form_submit_button("Save Prodigi Mapping", type="primary")
    if submitted:
        db.update_product_fields(
            product["id"],
            prodigi_product_id=prodigi_id,
            prodigi_product_url=prodigi_url,
            prodigi_notes=prodigi_notes,
        )
        st.rerun()


def render_shopify_product_sync(product):
    st.subheader("Shopify Connection")
    remote = product.get("shopify_match")
    st.markdown(status_badge(product.get("shopify_sync_status")), unsafe_allow_html=True)
    if not remote:
        st.caption("This product is not matched to a cached Shopify product yet.")
        if st.button("Open Limited Editions", key=f"product-shopify-sync-{product['id']}"):
            st.session_state.pending_page = "Limited Editions"
            st.rerun()
        return

    st.write(f"**Shopify title:** {remote.get('title') or 'Missing'}")
    st.write(f"**Shopify handle:** {remote.get('handle') or 'Missing'}")
    detail_columns = st.columns(3)
    detail_columns[0].metric("Variants", remote.get("variant_count", 0))
    detail_columns[1].metric("Images", remote.get("image_count", 0))
    detail_columns[2].metric("Status", (remote.get("status") or "Unknown").title())
    st.caption(
        f"Last synced {format_updated_at(remote.get('synced_at'))}. "
        f"Shopify updated {format_updated_at(remote.get('remote_updated_at'))}."
    )
    action_columns = st.columns(3)
    if remote.get("admin_url"):
        action_columns[0].link_button("Open Shopify Admin", remote["admin_url"], use_container_width=True)
    if remote.get("online_store_url"):
        action_columns[1].link_button("Open Live Product", remote["online_store_url"], use_container_width=True)
    if action_columns[2].button("Review in Limited Editions", key=f"review-shopify-{product['id']}", use_container_width=True):
        st.session_state.pending_page = "Limited Editions"
        st.rerun()


def render_edition_tracking(product):
    st.subheader("Limited Edition Tracking")
    supabase_handle = (
        product.get("handle")
        or (product.get("shopify_match") or {}).get("handle")
        or product.get("shopify_handle")
        or ""
    )
    if supabase_backend.is_configured() and supabase_handle:
        try:
            run_state = supabase_backend.get_edition_counter_state(supabase_handle)
        except Exception:
            run_state = None
        if run_state:
            st.caption("Active Supabase edition run")
            run_columns = st.columns(6)
            run_columns[0].metric("Edition", run_state.get("edition_name") or "Original Edition")
            run_columns[1].metric("Latest sent", run_state.get("latest_sent") or 0)
            run_columns[2].metric("Next", run_state.get("next_edition_number") or 1)
            run_columns[3].metric("Total", run_state.get("edition_total") or 100)
            run_columns[4].metric("Remaining", run_state.get("remaining_editions") or 0)
            run_columns[5].markdown(status_badge(run_state.get("status") or "active"), unsafe_allow_html=True)
            if st.button("Edit in Limited Editions", key=f"product-run-edit-{product['id']}", use_container_width=True):
                st.session_state.pending_page = "Limited Editions"
                st.rerun()

    edition_columns = st.columns(5)
    edition_columns[0].metric("Edition limit", format_optional_number(product.get("edition_limit")))
    edition_columns[1].metric("Sold", product.get("editions_sold") or 0)
    edition_columns[2].metric("Remaining", format_optional_number(product.get("editions_remaining")))
    edition_columns[3].metric("Next number", format_optional_number(product.get("next_edition_number")))
    edition_columns[4].markdown("**Edition status**")
    edition_columns[4].markdown(status_badge(product.get("edition_status") or "Not Set"), unsafe_allow_html=True)

    with st.form(f"edition-form-{product['id']}"):
        enabled = st.checkbox("Set an edition limit", value=product.get("edition_limit") is not None)
        form_columns = st.columns(2)
        limit_value = form_columns[0].number_input(
            "Edition limit",
            min_value=1,
            value=max(int(product.get("edition_limit") or 100), 1),
            disabled=not enabled,
        )
        sold_value = form_columns[1].number_input(
            "Editions sold",
            min_value=0,
            value=max(int(product.get("editions_sold") or 0), 0),
            disabled=not enabled,
        )
        submitted = st.form_submit_button("Save Edition Tracking", type="primary")
    if submitted:
        db.update_limited_edition(product["id"], limit_value if enabled else None, sold_value if enabled else 0)
        st.success("Edition tracking updated.")
        st.rerun()


def render_va_notes(product):
    st.subheader("VA Notes")
    with st.form(f"notes-form-{product['id']}"):
        notes = st.text_area("Internal comments", value=product.get("notes") or "", height=140)
        submitted = st.form_submit_button("Save VA Notes")
    if submitted:
        db.update_product_fields(product["id"], notes=notes)
        st.success("VA notes saved.")
        st.rerun()


def readiness_items(product):
    return db.get_readiness_items(product)


def render_check_items(items, key_prefix):
    columns = st.columns(2)
    for index, (label, is_ready) in enumerate(items):
        marker = "COMPLETE" if is_ready else "MISSING"
        columns[index % 2].markdown(
            f'<div class="sc-check sc-check-{"ready" if is_ready else "missing"}" '
            f'data-check="{key_prefix}-{index}"><strong>{marker}</strong> {label}</div>',
            unsafe_allow_html=True,
        )


def render_readiness_checklist(product):
    st.subheader("Product Readiness Checklist")
    required_items = db.get_required_readiness_items(product)
    optional_items = db.get_optional_readiness_items(product)
    completed = sum(is_ready for _, is_ready in required_items)
    st.markdown("**Overall readiness**")
    st.markdown(status_badge(product.get("readiness_status")), unsafe_allow_html=True)
    st.progress(
        completed / len(required_items),
        text=f"{completed} of {len(required_items)} required upload checks complete",
    )
    st.markdown("**Required for Ready for Upload**")
    render_check_items(required_items, "required")
    st.markdown("**Optional but visible**")
    render_check_items(optional_items, "optional")


def render_product_detail_page(product_id):
    product = db.get_product(product_id)
    if not product:
        st.error("This product record could not be found.")
        if st.button("Back to Limited Editions"):
            st.session_state.selected_product_id = None
            st.session_state.pending_page = "Limited Editions"
            st.rerun()
        return

    detail_actions = st.columns([1, 1, 1, 3])
    with detail_actions[0]:
        if st.button("Back to Limited Editions", use_container_width=True):
            st.session_state.selected_product_id = None
            st.session_state.editing_product_id = None
            st.session_state.pending_page = "Limited Editions"
            st.rerun()
    with detail_actions[1]:
        if st.button("Edit Product", key=f"detail-edit-{product['id']}", use_container_width=True):
            st.session_state.editing_product_id = product["id"]
            st.rerun()
    with detail_actions[2]:
        if product.get("status") == "Archived":
            if st.button("Restore Product", use_container_width=True):
                db.restore_product(product["id"])
                st.rerun()
        else:
            with st.popover("Archive Product", use_container_width=True):
                st.caption("This hides the product from normal lists without deleting its data.")
                confirm = st.checkbox("I understand", key=f"detail-archive-confirm-{product['id']}")
                if st.button("Confirm Archive", disabled=not confirm, use_container_width=True):
                    db.archive_product(product["id"])
                    st.rerun()

    render_page_intro(
        product["product_name"],
        "The master command centre for this product's files, links, edition settings, and VA readiness.",
        "Complete the missing checklist items, then update the product status.",
        "Use this single record instead of creating product information in separate chats or notes.",
    )
    render_product_overview(product)
    st.divider()
    render_quick_links(product)
    st.divider()
    render_file_hub(product)
    st.divider()
    detail_columns = st.columns(2)
    with detail_columns[0]:
        render_shopify_product_sync(product)
    with detail_columns[1]:
        render_prodigi_mapping(product)
    st.divider()
    render_va_notes(product)
    st.divider()
    render_edition_tracking(product)
    st.divider()
    render_readiness_checklist(product)


def render_files_page():
    render_page_intro(
        "File Hub",
        "One lightweight view of every product file link so VAs can fix missing assets quickly.",
        "Choose a missing-file filter, then open the product to connect the correct link.",
        "Connect links to the master product record rather than storing them in separate notes.",
    )

    if supabase_backend.is_configured():
        try:
            supabase_asset_rows = supabase_backend.list_product_assets("")
        except Exception:
            supabase_asset_rows = []
        psd_shortcuts = sorted(
            [
                row
                for row in supabase_asset_rows
                if row.get("asset_type") == "psd_master_file"
                and (row.get("asset_url") or row.get("google_drive_file_url"))
            ],
            key=lambda item: (item.get("product_title") or item.get("shopify_handle") or "").lower(),
        )
        if psd_shortcuts:
            with st.expander("PSD Shortcuts from Supabase", expanded=False):
                st.caption("Alphabetical Drive shortcuts imported from the PSD CSV. These are links only; no PSD files are stored in the app.")
                shortcut_header = st.columns([2.3, 1.2, 0.9])
                for column, label in zip(shortcut_header, ("Product", "Handle", "PSD")):
                    column.markdown(f"**{label}**")
                for row in psd_shortcuts:
                    url = row.get("asset_url") or row.get("google_drive_file_url")
                    columns = st.columns([2.3, 1.2, 0.9])
                    columns[0].write(row.get("product_title") or row.get("asset_name") or "PSD file")
                    columns[1].caption(row.get("shopify_handle") or "")
                    columns[2].link_button("Open PSD", url, use_container_width=True)

    file_filter = st.selectbox(
        "File status filter",
        (
            "All products",
            "Missing PSD",
            "Missing JPG",
            "Missing WebP",
            "Missing Mockups",
            "Missing Size Guide",
            "Missing Lifestyle",
            "Missing Prompt Pack",
            "Missing ZIP",
            "Missing Certificate Folder",
            "Missing Ads/Social Folder",
            "Needs Review",
            "Approved",
            "All Connected",
        ),
    )
    try:
        products = db.list_file_hub_products(file_filter)
    except Exception as error:
        st.warning("The legacy local file hub is unavailable, but Supabase PSD shortcuts above can still be used.")
        st.caption(str(error))
        return
    st.caption(f"{len(products)} product{'s' if len(products) != 1 else ''} shown")
    if not products:
        st.success("No products match this file filter.")
        return

    for product in products:
        with st.container(border=True):
            summary = st.columns([3, 1.3, 2, 0.9])
            summary[0].markdown(f"**{product['product_name']}**")
            summary[0].caption(product.get("handle") or "Handle missing")
            summary[1].markdown(status_badge(product.get("status")), unsafe_allow_html=True)
            summary[2].markdown(
                status_badge(product.get("overall_asset_readiness")),
                unsafe_allow_html=True,
            )
            with summary[3]:
                if st.button("Open", key=f"file-open-{product['id']}", use_container_width=True):
                    go_to_product(product["id"])

            asset_columns = st.columns(5)
            for index, asset in enumerate(db.ASSET_DEFINITIONS):
                with asset_columns[index % 5]:
                    st.caption(asset["short_label"])
                    st.markdown(
                        status_badge(product["asset_statuses"][asset["key"]]),
                        unsafe_allow_html=True,
                    )

            connected_assets = [
                asset for asset in db.ASSET_DEFINITIONS if product.get(asset["url_field"])
            ]
            if product.get("google_drive_root_folder_url"):
                connected_assets.append(
                    {
                        "key": "drive-root",
                        "url_field": "google_drive_root_folder_url",
                        "open_label": "Open Root Drive Folder",
                    }
                )
            if connected_assets:
                with st.expander("Open connected assets"):
                    link_columns = st.columns(4)
                    for index, asset in enumerate(connected_assets):
                        with link_columns[index % 4]:
                            st.link_button(
                                asset["open_label"],
                                product[asset["url_field"]],
                                use_container_width=True,
                            )


def render_upload_workflow_card(product, stage):
    with st.container(border=True):
        columns = st.columns([3.2, 1.5, 2.8, 0.9])
        columns[0].markdown(f"**{product['product_name']}**")
        columns[0].caption(product.get("handle") or "Handle missing")
        columns[1].markdown(status_badge(product.get("readiness_status")), unsafe_allow_html=True)
        missing = product.get("missing_items") or []
        if missing:
            missing_preview = ", ".join(missing[:3])
            if len(missing) > 3:
                missing_preview += f" +{len(missing) - 3} more"
            columns[2].caption(f"Missing: {missing_preview}")
        else:
            columns[2].caption("No readiness items missing.")
        with columns[3]:
            if st.button(
                "Open",
                key=f"upload-stage-{stage}-{product['id']}",
                use_container_width=True,
            ):
                go_to_product(product["id"])


def render_product_uploads_workflow():
    render_page_intro(
        "Product Uploads",
        "The VA workflow board for preparing and reviewing products before Shopify connection is added.",
        "Open the next product in its current stage and clear the missing readiness items.",
        "Only move a product forward after its master product record is updated.",
    )

    stages = (
        "Artwork Ready",
        "Mockups Ready",
        "Upload In Progress",
        "Ready for Review",
        "Live",
        "Needs Fixing",
    )
    products = db.list_products(include_archived=False)
    counts = {stage: sum(product.get("status") == stage for product in products) for stage in stages}
    metric_columns = st.columns(3)
    for index, stage in enumerate(stages):
        metric_columns[index % 3].metric(stage, counts[stage])

    st.subheader("Upload Workflow")
    for stage in stages:
        stage_products = [product for product in products if product.get("status") == stage]
        with st.expander(f"{stage} ({len(stage_products)})", expanded=bool(stage_products)):
            if not stage_products:
                st.caption("No products in this stage.")
                continue
            for product in stage_products:
                render_upload_workflow_card(product, stage)


def render_local_limited_editions():
    search = st.text_input("Find product", placeholder="Product name or handle")
    status_filter = st.selectbox("Edition status", ["All", *db.EDITION_STATUSES[:-1]])
    editions = db.list_limited_editions(status_filter, search=search)
    st.caption(f"{len(editions)} product{'s' if len(editions) != 1 else ''} shown")

    if not editions:
        st.info("No products match this edition status yet.")
        return

    header = st.columns([2.5, 1, 1, 1, 1, 1, 1.4, 1.3, 0.8])
    for column, label in zip(
        header,
        ("Product", "Shopify", "Limit", "Sold", "Remaining", "Next", "Edition status", "Last synced", "Detail"),
    ):
        column.caption(label)

    for item in editions:
        with st.container(border=True):
            columns = st.columns([2.5, 1, 1, 1, 1, 1, 1.4, 1.3, 0.8])
            columns[0].markdown(f"**{item['product_name']}**")
            columns[0].caption(item.get("sport_category") or "Other")
            columns[1].write("Matched" if item.get("shopify_product_id") else "None")
            columns[2].write(format_optional_number(item.get("edition_limit")))
            columns[3].write(item.get("editions_sold") or 0)
            columns[4].write(format_optional_number(item.get("editions_remaining")))
            columns[5].write(format_optional_number(item.get("next_edition_number")))
            columns[6].markdown(status_badge(item.get("edition_status")), unsafe_allow_html=True)
            columns[7].write(item.get("last_synced_at") or "Local only")
            with columns[8]:
                if st.button("Open", key=f"edition-open-{item['product_id']}", use_container_width=True):
                    go_to_product(item["product_id"])


def render_copy_text_button(text, key, label):
    safe_label = html.escape(label)
    text_json = json.dumps(text)

    components.html(
        f"""
        <div style="padding-top:2px;">
          <button
            id="copy-prodigi-button-{key}"
            type="button"
            style="width:100%;border:1px solid #D4A54C;border-radius:14px;padding:10px 14px;background:#F5F2EA;color:#0B0B0D;font-weight:700;font-size:0.95rem;cursor:pointer;box-sizing:border-box;"
          >
            {safe_label}
          </button>
        </div>
        <script>
        (() => {{
          const button = document.getElementById("copy-prodigi-button-{key}");
          const originalLabel = button.innerText;
          const copyText = {text_json};

          async function copyValue(event) {{
            event.preventDefault();
            try {{
              if (navigator.clipboard && window.isSecureContext) {{
                await navigator.clipboard.writeText(copyText);
              }} else {{
                const textarea = document.createElement("textarea");
                textarea.value = copyText;
                textarea.style.position = "fixed";
                textarea.style.opacity = "0";
                document.body.appendChild(textarea);
                textarea.focus();
                textarea.select();
                document.execCommand("copy");
                document.body.removeChild(textarea);
              }}
            }} catch (error) {{
              const textarea = document.createElement("textarea");
              textarea.value = copyText;
              textarea.style.position = "fixed";
              textarea.style.opacity = "0";
              document.body.appendChild(textarea);
              textarea.focus();
              textarea.select();
              document.execCommand("copy");
              document.body.removeChild(textarea);
            }}

            button.innerText = "Copied";
            setTimeout(() => {{
              button.innerText = originalLabel;
            }}, 1400);
          }}

          button.addEventListener("click", copyValue);
        }})();
        </script>
        """,
        height=56,
    )


def load_edition_widget_liquid():
    snippet_path = Path("shopify/snippets/sports-cave-edition-widget.liquid")
    if not snippet_path.exists():
        return "", snippet_path
    return snippet_path.read_text(encoding="utf-8"), snippet_path


def load_edition_widget_liquid_snippets():
    snippet_specs = (
        (
            "Sports Cave Remaining Pill",
            Path("shopify/snippets/sports-cave-remaining-pill.liquid"),
            360,
        ),
        (
            "Sports Cave Numbered Edition Bar",
            Path("shopify/snippets/sports-cave-numbered-edition-bar.liquid"),
            420,
        ),
    )
    snippets = []
    for label, path, height in snippet_specs:
        snippets.append(
            {
                "label": label,
                "path": path,
                "height": height,
                "code": path.read_text(encoding="utf-8") if path.exists() else "",
            }
        )
    return snippets


def render_prodigi_option_card(frame_label, frame_colour, size_option, is_unframed=False):
    shopify_variant = f"{frame_label} / {size_option['shopify_size']}"
    product_name = size_option["unframed_name"] if is_unframed else size_option["framed_name"]
    product_code = size_option["unframed_code"] if is_unframed else size_option["framed_code"]
    frame_note = "No frame / Fine Art Paper" if is_unframed else frame_colour

    with st.container(border=True):
        st.markdown(f"**{shopify_variant}**")
        st.caption(f"Shopify size {size_option['shopify_size']} = Prodigi size {size_option['prodigi_size']} • {size_option['dimensions']}")
        st.markdown("**Prodigi product name**")
        st.write(product_name)
        st.markdown("**Prodigi product code**")
        st.code(product_code, language=None)
        st.markdown("**Frame colour to select**")
        st.write(frame_note)

        button_columns = st.columns(2)
        with button_columns[0]:
            render_copy_text_button(product_name, f"{frame_label.lower()}-{size_option['shopify_size'].lower()}-name", "Copy Product Name")
        with button_columns[1]:
            render_copy_text_button(product_code, f"{frame_label.lower()}-{size_option['shopify_size'].lower()}-code", "Copy Product Code")


def render_prodigi_page_legacy():
    st.title("Prodigi")
    st.caption(
        "Simple Sports Cave-to-Prodigi matching. Copy the exact product name and product code, then double-check the frame and size before sending the order to production."
    )

    st.link_button("Open Prodigi Dashboard", PRODIGI_DASHBOARD_URL, use_container_width=False)
    st.markdown(
        "**Prodigi support for errors or warranty:** "
        f"[{PRODIGI_SUPPORT_EMAIL}](mailto:{PRODIGI_SUPPORT_EMAIL})"
    )

    st.info(
        "Quick check: XL = A1, L = A2, M = A3, S = A4. Oak on Sports Cave = Natural in Prodigi. "
        "Framed orders use Classic Frame. Unframed orders use Fine Art Paper."
    )

    st.subheader("1. Size map")
    size_columns = st.columns(4)
    for column, size_option in zip(size_columns, PRODIGI_SIZE_OPTIONS):
        with column:
            with st.container(border=True):
                st.markdown(f"### {size_option['shopify_size']}")
                st.caption(f"Prodigi size {size_option['prodigi_size']}")
                st.write(size_option["dimensions"])

    st.subheader("2. Frame map")
    frame_columns = st.columns(4)
    for column, (shopify_frame, prodigi_frame, prodigi_note) in zip(frame_columns, PRODIGI_FRAME_OPTIONS):
        with column:
            with st.container(border=True):
                st.markdown(f"### {shopify_frame}")
                st.caption(f"Prodigi frame colour: {prodigi_frame}")
                st.write(prodigi_note)

    st.subheader("3. Exact Prodigi options")
    tabs = st.tabs(["Black", "Oak", "White", "Unframed"])
    frame_tabs = (
        ("Black", "Black", False),
        ("Oak", "Natural", False),
        ("White", "White", False),
        ("Unframed", "No frame / Fine Art Paper", True),
    )
    for tab, (frame_label, frame_colour, is_unframed) in zip(tabs, frame_tabs):
        with tab:
            st.caption(
                "Copy the product name or product code, then match the frame colour exactly before submitting the order."
            )
            for row_start in range(0, len(PRODIGI_SIZE_OPTIONS), 2):
                row_columns = st.columns(2)
                for column, size_option in zip(row_columns, PRODIGI_SIZE_OPTIONS[row_start:row_start + 2]):
                    with column:
                        render_prodigi_option_card(frame_label, frame_colour, size_option, is_unframed=is_unframed)

    with st.container(border=True):
        st.markdown("**Final check before production**")
        st.write("1. Match the Shopify size to the Prodigi size: XL=A1, L=A2, M=A3, S=A4.")
        st.write("2. Match the frame colour: Black, Natural, White, or Unframed.")
        st.write("3. Copy the exact product name or code from the matching card.")
        st.write("4. Check the order one more time before sending it to production.")


def _prodigi_active_rows(rows):
    return [row for row in rows or [] if row.get("prodigi_status") in PRODIGI_ACTIVE_STATUSES]


def _prodigi_rows_for_tab(rows, tab_name):
    if tab_name == "Ready to Send":
        return [row for row in rows if row.get("prodigi_status") == "Ready to Send"]
    if tab_name == "Needs Review":
        return [row for row in rows if row.get("prodigi_status") in {"Needs Review", "Hold / Issue"}]
    if tab_name == "Awaiting Tracking":
        return [
            row
            for row in rows
            if row.get("prodigi_status") in {"Submitted to Prodigi", "In Production", "Awaiting Tracking", "Shipped"}
            and not _prodigi_fulfilled(row)
        ]
    if tab_name == "History":
        return [row for row in rows if row.get("prodigi_status") == "Fulfilled in Shopify"]
    return rows


def _prodigi_save_row_update(rows, row_id, updates):
    updated_rows = []
    updated_row = None
    for row in rows or []:
        if row.get("row_id") != row_id:
            updated_rows.append(row)
            continue
        merged = dict(row)
        merged.update(updates or {})
        merged["updated_at"] = _prodigi_now_iso()
        updated_row = prodigi_tracker_row_from_order(merged, merged)
        updated_rows.append(updated_row)
    save_prodigi_tracker_rows(updated_rows)
    return updated_rows, updated_row


def _prodigi_row_by_id(rows, row_id):
    return next((row for row in rows or [] if row.get("row_id") == row_id), None)


def _prodigi_check_status(ok, manual=False):
    if ok:
        return "✅"
    return "☐" if manual else "⚠"


def prodigi_checklist_sections(row):
    duplicate_ok = "Duplicate" not in str(row.get("blockers") or "")
    return [
        (
            "Edition QA",
            [
                ("Edition number assigned", bool(_prodigi_int(row.get("edition_number"), 0)), "auto"),
                ("Edition number matches product", bool(row.get("shopify_product_id") or row.get("product_title")), "auto"),
                ("No duplicate edition number", duplicate_ok, "auto"),
                ("Product edition total exists", bool(_prodigi_int(row.get("edition_total"), 0)), "auto"),
            ],
        ),
        (
            "Certificate QA",
            [
                ("Certificate generated", _prodigi_certificate_generated(row), "auto"),
                ("Certificate visually checked", _prodigi_bool(row.get("certificate_visual_checked")), "manual"),
                ("Certificate customer name checked", _prodigi_bool(row.get("certificate_customer_checked")), "manual"),
                ("Certificate product title checked", _prodigi_bool(row.get("certificate_product_checked")), "manual"),
                ("Certificate edition number checked", _prodigi_bool(row.get("certificate_edition_checked")), "manual"),
                ("Certificate uploaded to Shopify/customer account", _prodigi_certificate_uploaded(row), "auto"),
            ],
        ),
        (
            "Prodigi QA",
            [
                ("Shopify variant mapped correctly", bool(row.get("frame") and row.get("size")), "auto"),
                ("Frame colour checked", _prodigi_bool(row.get("frame_colour_checked")), "manual"),
                ("Size checked", bool(row.get("size")), "auto"),
                ("Prodigi size checked", bool(row.get("prodigi_size")), "auto"),
                ("Prodigi product option checked", _prodigi_bool(row.get("prodigi_option_checked")), "manual"),
                ("Prodigi code checked", bool(row.get("prodigi_code")), "auto"),
            ],
        ),
        (
            "Shipping QA",
            [
                ("Shipping method exists", bool(row.get("shipping_method")), "auto"),
                ("Express/standard checked", _prodigi_bool(row.get("shipping_checked")), "manual"),
                ("Customer delivery details present", bool(row.get("customer_name") or row.get("customer_email")), "auto"),
            ],
        ),
        (
            "Submission QA",
            [
                ("Submitted to Prodigi", _prodigi_submitted(row), "auto"),
                ("Date sent to Prodigi", bool(row.get("date_sent_to_prodigi")), "auto"),
                ("Prodigi order ID added if available", bool(row.get("prodigi_order_id")) or _prodigi_submitted(row), "auto"),
                ("Submission manually confirmed", _prodigi_bool(row.get("submitted_confirmed")), "manual"),
            ],
        ),
        (
            "Tracking / Shopify Fulfilment QA",
            [
                ("Tracking number added", bool(row.get("tracking_number")), "auto"),
                ("Tracking URL/carrier added", bool(row.get("tracking_url") or row.get("carrier")), "auto"),
                ("Shopify fulfilment completed", _prodigi_fulfilled(row), "auto"),
                ("Final status marked Fulfilled", row.get("prodigi_status") == "Fulfilled in Shopify", "auto"),
            ],
        ),
    ]


def _render_prodigi_checklist_dialog(rows):
    row_id = st.session_state.get("prodigi-checklist-row-id")
    if not row_id:
        return rows
    row = _prodigi_row_by_id(rows, row_id)
    if not row:
        st.session_state["prodigi-checklist-row-id"] = ""
        return rows

    @st.dialog(f"Prodigi QA Checklist: {row.get('shopify_order_name') or 'Order'}", width="large")
    def _checklist_dialog():
        st.caption(row.get("product_title") or "")
        st.write(prodigi_progress_text(row))
        if row.get("blockers"):
            st.warning(row["blockers"])

        manual_values = {}
        for section, items in prodigi_checklist_sections(row):
            st.markdown(f"**{section}**")
            for label, ok, check_type in items:
                if check_type == "manual":
                    field = {
                        "Certificate visually checked": "certificate_visual_checked",
                        "Certificate customer name checked": "certificate_customer_checked",
                        "Certificate product title checked": "certificate_product_checked",
                        "Certificate edition number checked": "certificate_edition_checked",
                        "Frame colour checked": "frame_colour_checked",
                        "Prodigi product option checked": "prodigi_option_checked",
                        "Express/standard checked": "shipping_checked",
                        "Submission manually confirmed": "submitted_confirmed",
                    }.get(label)
                    manual_values[field] = st.checkbox(
                        label,
                        value=bool(ok),
                        key=f"prodigi-checklist-{field}-{safe_filename_part(row_id)}",
                    )
                else:
                    st.checkbox(
                        f"{label} {_prodigi_check_status(ok)}",
                        value=bool(ok),
                        disabled=True,
                        key=f"prodigi-checklist-auto-{safe_filename_part(label)}-{safe_filename_part(row_id)}",
                    )

        prodigi_order_id = st.text_input(
            "Prodigi order ID",
            value=row.get("prodigi_order_id") or "",
            key=f"prodigi-checklist-order-id-{safe_filename_part(row_id)}",
        )
        tracking_number = st.text_input(
            "Tracking number",
            value=row.get("tracking_number") or "",
            key=f"prodigi-checklist-tracking-{safe_filename_part(row_id)}",
        )
        tracking_url = st.text_input(
            "Tracking URL",
            value=row.get("tracking_url") or "",
            key=f"prodigi-checklist-tracking-url-{safe_filename_part(row_id)}",
        )
        carrier = st.text_input(
            "Carrier",
            value=row.get("carrier") or "",
            key=f"prodigi-checklist-carrier-{safe_filename_part(row_id)}",
        )
        notes = st.text_area(
            "Notes",
            value=row.get("notes") or "",
            height=110,
            key=f"prodigi-checklist-notes-{safe_filename_part(row_id)}",
        )

        actions = st.columns([1, 1, 1, 1, 1])
        base_updates = {
            **manual_values,
            "prodigi_order_id": prodigi_order_id,
            "tracking_number": tracking_number,
            "tracking_url": tracking_url,
            "carrier": carrier,
            "notes": notes,
        }
        if actions[0].button("Save", type="primary", use_container_width=True):
            _prodigi_save_row_update(rows, row_id, base_updates)
            st.success("Checklist saved.")
            st.rerun()
        if actions[1].button("Mark Submitted", use_container_width=True):
            candidate = prodigi_tracker_row_from_order({**row, **base_updates}, {**row, **base_updates})
            blockers = prodigi_manual_submit_blockers(candidate)
            if blockers:
                st.error(", ".join(blockers))
            else:
                _prodigi_save_row_update(
                    rows,
                    row_id,
                    {**base_updates, "prodigi_status": "Submitted to Prodigi", "date_sent_to_prodigi": row.get("date_sent_to_prodigi") or _prodigi_now_iso()},
                )
                st.success("Marked submitted.")
                st.rerun()
        if actions[2].button("Mark Fulfilled", use_container_width=True):
            candidate = prodigi_tracker_row_from_order({**row, **base_updates}, {**row, **base_updates})
            blockers = prodigi_fulfillment_blockers(candidate)
            if blockers:
                st.error(", ".join(blockers))
            else:
                _prodigi_save_row_update(
                    rows,
                    row_id,
                    {**base_updates, "prodigi_status": "Fulfilled in Shopify", "date_fulfilled_in_shopify": row.get("date_fulfilled_in_shopify") or _prodigi_now_iso()},
                )
                st.success("Marked fulfilled.")
                st.rerun()
        if actions[3].button("Hold / Issue", use_container_width=True):
            _prodigi_save_row_update(rows, row_id, {**base_updates, "prodigi_status": "Hold / Issue"})
            st.rerun()
        if actions[4].button("Close", use_container_width=True):
            st.session_state["prodigi-checklist-row-id"] = ""
            st.rerun()

    _checklist_dialog()
    return rows


PRODIGI_DISPATCH_REQUIRED_FIELDS = (
    "artwork_upload",
    "product_option",
    "frame",
    "size",
    "shipping",
    "sent_to_production",
    "final_check",
)


PRODIGI_DISPATCH_REASON_LABELS = {
    "certificate": "Certificate not uploaded",
    "artwork_upload": "Artwork quality not confirmed",
    "product_option": "Prodigi variant not confirmed",
    "frame": "Frame mismatch",
    "size": "Prodigi variant mismatch",
    "edition_number": "Edition number mismatch",
    "shipping": "Shipping not confirmed",
    "sent_to_production": "Not sent to production",
    "final_check": "Final check failed",
}


def _prodigi_parse_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        return value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
                return date.fromisoformat(text)
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).date()


def _prodigi_dispatch_date(row):
    return _prodigi_parse_date(row.get("date_sent_to_prodigi") or row.get("created_at") or row.get("date"))


def _prodigi_display_date(value):
    parsed = _prodigi_parse_date(value)
    return parsed.isoformat() if parsed else _prodigi_clean(value)


def _prodigi_is_limited_edition(row):
    return bool(_prodigi_int(row.get("edition_number"), 0))


def _prodigi_edition_label(row):
    edition = _prodigi_int(row.get("edition_number"), 0)
    if not edition:
        return "Not Required"
    total = _prodigi_int(row.get("edition_total"), 100)
    return f"#{edition:03d} / {total}" if total else f"#{edition:03d}"


def _prodigi_existing_dispatch_row(rows, row_id):
    return next((row for row in rows or [] if row.get("row_id") == row_id), None)


def _prodigi_dispatch_status(row):
    status = row.get("prodigi_status") or ""
    if status == "Submitted to Prodigi":
        return "Submitted"
    return status or "Needs Review"


def _prodigi_dispatch_log_candidates(rows):
    candidates = []
    for row in rows or []:
        status = _prodigi_dispatch_status(row)
        if status in {"Submitted", "Needs Review"} and (
            row.get("source") == "prodigi_dispatch_log"
            or row.get("date_sent_to_prodigi")
            or row.get("qa_answers")
            or row.get("issue_reason")
            or row.get("prodigi_order_id")
            or status == "Submitted"
        ):
            candidates.append(row)
    return sort_prodigi_tracker_rows(candidates)


def _prodigi_search_blob(row):
    return _prodigi_normalise_text(
        " ".join(
            str(row.get(key) or "")
            for key in (
                "shopify_order_name",
                "customer_name",
                "customer_email",
                "product_title",
                "variant_title",
                "edition_number",
                "shipping_method",
                "prodigi_code",
                "notes",
                "issue_reason",
            )
        )
    )


def prodigi_find_order_rows(order_rows, search_text, stored_rows=None):
    query = _prodigi_clean(search_text)
    if not query:
        return []
    normalised_order = _prodigi_normalise_order_name(query)
    normalised_query = _prodigi_normalise_text(query)
    looks_like_order = bool(re.search(r"(#?\s*SC\s*\d+)|^\d{3,}$", query, flags=re.IGNORECASE))

    if looks_like_order:
        matched_raw = [
            row
            for row in order_rows or []
            if _prodigi_normalise_order_name(row.get("order") or row.get("order_name") or row.get("shopify_order_name")) == normalised_order
        ]
    else:
        matched_raw = []

    if not matched_raw:
        matched_raw = [
            row
            for row in order_rows or []
            if normalised_query
            and normalised_query
            in _prodigi_normalise_text(
                " ".join(
                    str(row.get(key) or "")
                    for key in ("order", "order_name", "shopify_order_name", "customer", "customer_name", "product", "product_title")
                )
            )
        ]

    stored_by_id = {row.get("row_id"): row for row in stored_rows or [] if row.get("row_id")}
    rows = [prodigi_tracker_row_from_order(row, stored_by_id.get(prodigi_tracker_row_id(row))) for row in matched_raw]
    return sort_prodigi_tracker_rows(rows)


def _prodigi_log_timing(label, started_at, extra=""):
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    suffix = f" {extra}" if extra else ""
    print(f"PERF Prodigi {label}: {elapsed_ms} ms{suffix}")


def prodigi_load_dispatch_summary():
    started = time.perf_counter()
    if supabase_backend.is_configured():
        try:
            summary = supabase_backend.get_prodigi_dispatch_summary()
            _prodigi_log_timing("dispatch summary", started, f"rows={summary.get('rows_saved', 0)}")
            return summary
        except Exception as error:
            supabase_backend.log_app_error("prodigi_dispatch_summary_failed", str(error), {"source": "prodigi_page"})
    _prodigi_log_timing("dispatch summary", started, "source=unavailable rows=0")
    return {"rows_saved": 0, "last_saved_at": ""}


def prodigi_load_dispatch_rows(tab_name="Last 7 Days", search_text="", limit=50):
    started = time.perf_counter()
    limit_value = max(min(int(limit or 50), 150), 1)
    if supabase_backend.is_configured():
        kwargs = {"limit": limit_value, "search": search_text}
        if not _prodigi_clean(search_text):
            if tab_name == "Last 7 Days":
                kwargs["days"] = 7
            elif tab_name == "Needs Review":
                kwargs["status"] = "Needs Review"
            elif tab_name == "Submitted":
                kwargs["status"] = "Submitted"
                kwargs["days"] = 7
            elif tab_name == "History":
                kwargs["older_than_days"] = 7
        try:
            rows = supabase_backend.list_prodigi_dispatch_rows(**kwargs)
            _prodigi_log_timing("dispatch rows", started, f"view={tab_name} rows={len(rows)}")
            return rows
        except Exception as error:
            supabase_backend.log_app_error("prodigi_dispatch_rows_failed", str(error), {"source": "prodigi_page", "view": tab_name})
    _prodigi_log_timing("dispatch rows", started, f"view={tab_name} source=unavailable rows=0")
    return []


def prodigi_find_order_rows_from_cache(search_text):
    query = _prodigi_clean(search_text)
    if not query:
        return [], []
    started = time.perf_counter()
    if supabase_backend.is_configured():
        try:
            order_allocator = importlib.import_module("order_allocator")
            raw_rows = supabase_backend.list_orders(search=query, sort="Date newest", status_filter="All", limit=50)
            order_rows = order_allocator._snapshot_rows_from_supabase_order_rows(raw_rows)
            existing_rows = prodigi_load_dispatch_rows("Search", search_text=query, limit=100)
            matches = prodigi_find_order_rows(order_rows, query, existing_rows)
            _prodigi_log_timing("order lookup", started, f"source=supabase rows={len(matches)}")
            return matches, existing_rows
        except Exception as error:
            supabase_backend.log_app_error("prodigi_order_lookup_failed", str(error), {"source": "prodigi_page", "query": query})

    order_allocator = importlib.import_module("order_allocator")
    orders_snapshot = order_allocator.load_orders_snapshot()
    matches = prodigi_find_order_rows(orders_snapshot.get("rows") or [], query, [])
    _prodigi_log_timing("order lookup", started, f"source=local_snapshot rows={len(matches)}")
    return matches, []


def prodigi_save_dispatch_row(base_row, *, status, notes="", qa_answers=None):
    _, saved = prodigi_upsert_dispatch_row([], base_row, status=status, notes=notes, qa_answers=qa_answers)
    if not supabase_backend.is_configured():
        raise RuntimeError("Supabase dispatch storage is not configured.")
    started = time.perf_counter()
    supabase_backend.upsert_prodigi_dispatch_row(saved)
    _prodigi_log_timing("dispatch save", started, f"status={status} row_id={saved.get('row_id') or ''}")
    return saved


def prodigi_dispatch_rows_for_tab(rows, tab_name, search_text="", *, today=None):
    today = today or date.today()
    search = _prodigi_normalise_text(search_text)
    candidates = _prodigi_dispatch_log_candidates(rows)
    if search:
        return [row for row in candidates if search in _prodigi_search_blob(row)][:150]

    seven_days_ago = today - timedelta(days=7)
    if tab_name == "Last 7 Days":
        return [
            row
            for row in candidates
            if (sent_date := _prodigi_dispatch_date(row)) and seven_days_ago <= sent_date <= today
        ][:150]
    if tab_name == "Needs Review":
        return [row for row in candidates if _prodigi_dispatch_status(row) == "Needs Review"][:150]
    if tab_name == "Submitted":
        return [
            row
            for row in candidates
            if _prodigi_dispatch_status(row) == "Submitted"
            and (sent_date := _prodigi_dispatch_date(row))
            and seven_days_ago <= sent_date <= today
        ][:150]
    if tab_name == "History":
        return [
            row
            for row in candidates
            if not (sent_date := _prodigi_dispatch_date(row)) or sent_date < seven_days_ago
        ][:150]
    return candidates[:150]


def prodigi_dispatch_table_records(rows):
    records = []
    for row in rows or []:
        edition_number = _prodigi_int(row.get("edition_number"), 0)
        records.append(
            {
                "Submitted At": row.get("submitted_at") or _prodigi_display_date(row.get("date_sent_to_prodigi")) or row.get("updated_at") or "",
                "Status": _prodigi_dispatch_status(row),
                "Order": row.get("shopify_order_name") or row.get("shopify_order_number") or "",
                "Customer": row.get("customer_name") or "",
                "Product": row.get("product_title") or "",
                "Variant": row.get("shopify_variant_title") or row.get("variant_title") or "",
                "Size": row.get("sports_cave_size") or row.get("size") or "",
                "Frame": row.get("sports_cave_frame") or row.get("frame") or "",
                "Prodigi Code": row.get("prodigi_product_code") or row.get("prodigi_code") or "",
                "Prodigi Product": row.get("prodigi_product_name") or prodigi_product_option_display(row),
                "Edition": f"#{edition_number:03d}" if edition_number else "",
                "QA": "Yes" if _prodigi_bool(row.get("qa_confirmed")) else "No",
                "Notes": row.get("notes") or row.get("qa_notes") or row.get("issue_reason") or "",
            }
        )
    return records


def prodigi_default_qa_answers(row):
    limited = _prodigi_is_limited_edition(row)
    answers = {
        "certificate": "Yes" if _prodigi_certificate_uploaded(row) else ("No" if limited else "Not Required"),
        "artwork_upload": None,
        "product_option": None,
        "frame": None,
        "size": None,
        "edition_number": None if limited else "Not Required",
        "shipping": None,
        "sent_to_production": None,
        "final_check": None,
    }
    stored = row.get("qa_answers") or {}
    if isinstance(stored, str):
        try:
            stored = json.loads(stored)
        except (TypeError, ValueError):
            stored = {}
    if isinstance(stored, dict):
        answers.update({key: value for key, value in stored.items() if key in answers})
    return answers


def prodigi_dispatch_issue_reasons(row, answers):
    reasons = []
    for field, label in PRODIGI_DISPATCH_REASON_LABELS.items():
        if field == "certificate" and not _prodigi_is_limited_edition(row):
            continue
        if answers.get(field) == "No":
            reasons.append(label)
    return reasons


def prodigi_line_confirmation_defaults(row):
    stored = row.get("qa_answers") or {}
    if isinstance(stored, str):
        try:
            stored = json.loads(stored)
        except (TypeError, ValueError):
            stored = {}
    if not isinstance(stored, dict):
        stored = {}
    confirmed = row.get("qa_confirmed") or stored.get("product_confirmation") == "Yes"
    notes = row.get("qa_notes") or stored.get("product_confirmation_notes") or ""
    return {"confirmed": bool(confirmed), "notes": str(notes or "")}


def prodigi_dispatch_blockers(row, answers):
    blockers = []
    if not row.get("shopify_order_name"):
        blockers.append("Missing Shopify order")
    if not row.get("product_title"):
        blockers.append("Product not matched")
    if not row.get("frame"):
        blockers.append("Missing frame")
    if not row.get("size"):
        blockers.append("Missing size")
    if not row.get("prodigi_product_option") or not row.get("prodigi_code") or not row.get("prodigi_size"):
        blockers.append("Missing Prodigi mapping")
    if not row.get("shipping_method"):
        blockers.append("Missing shipping method")

    limited = _prodigi_is_limited_edition(row)
    if limited and not _prodigi_certificate_uploaded(row):
        blockers.append("Generate/upload certificate before dispatch completion.")
    for field in PRODIGI_DISPATCH_REQUIRED_FIELDS:
        if answers.get(field) != "Yes":
            blockers.append(PRODIGI_DISPATCH_REASON_LABELS[field])
    if limited and answers.get("edition_number") != "Yes":
        blockers.append(PRODIGI_DISPATCH_REASON_LABELS["edition_number"])
    return blockers


def prodigi_upsert_dispatch_row(rows, base_row, *, status, notes="", qa_answers=None):
    qa_answers = qa_answers or {}
    now = _prodigi_now_iso()
    row_id = base_row.get("row_id") or prodigi_tracker_row_id(base_row)
    today_sent = date.today().isoformat()
    issue_reasons = prodigi_dispatch_issue_reasons(base_row, qa_answers)
    qa_confirmed = status == "Submitted" and all(
        qa_answers.get(field) in {"Yes", "Not Required"}
        for field in (
            "certificate",
            "artwork_upload",
            "product_option",
            "frame",
            "size",
            "edition_number",
            "shipping",
            "sent_to_production",
            "final_check",
        )
    )
    qa_notes = str(qa_answers.get("product_confirmation_notes") or notes or "")
    updated_rows = []
    saved = None
    found = False
    for existing in rows or []:
        if existing.get("row_id") == row_id:
            found = True
            merged = dict(existing)
            merged.update(base_row)
        else:
            updated_rows.append(existing)
            continue
        merged.update(
            {
                "row_id": row_id,
                "prodigi_status": status,
                "date_sent_to_prodigi": merged.get("date_sent_to_prodigi") or today_sent,
                "notes": notes,
                "qa_completed": status == "Submitted",
                "qa_completed_at": now if status == "Submitted" else merged.get("qa_completed_at") or "",
                "qa_confirmed": qa_confirmed,
                "qa_notes": qa_notes,
                "qa_answers": qa_answers,
                "linked_order_line_id": base_row.get("shopify_line_item_id") or base_row.get("linked_order_line_id") or "",
                "issue_reason": "; ".join(issue_reasons) if status == "Needs Review" else "",
                "shopify_order_number": base_row.get("shopify_order_number") or base_row.get("shopify_order_name") or "",
                "shopify_variant_title": base_row.get("shopify_variant_title") or base_row.get("variant_title") or "",
                "sports_cave_frame": base_row.get("sports_cave_frame") or base_row.get("frame") or "",
                "sports_cave_size": base_row.get("sports_cave_size") or base_row.get("size") or "",
                "prodigi_product_name": base_row.get("prodigi_product_name") or "",
                "prodigi_product_code": base_row.get("prodigi_product_code") or base_row.get("prodigi_code") or "",
                "prodigi_frame_colour": base_row.get("prodigi_frame_colour") or base_row.get("prodigi_frame") or "",
                "submitted_at": now if status == "Submitted" else merged.get("submitted_at") or "",
                "source": "prodigi_dispatch_log",
                "updated_at": now,
            }
        )
        saved = prodigi_tracker_row_from_order(merged, merged)
        updated_rows.append(saved)
    if not found:
        merged = dict(base_row)
        merged.update(
            {
                "row_id": row_id,
                "prodigi_status": status,
                "date_sent_to_prodigi": today_sent,
                "notes": notes,
                "qa_completed": status == "Submitted",
                "qa_completed_at": now if status == "Submitted" else "",
                "qa_confirmed": qa_confirmed,
                "qa_notes": qa_notes,
                "qa_answers": qa_answers,
                "linked_order_line_id": base_row.get("shopify_line_item_id") or base_row.get("linked_order_line_id") or "",
                "issue_reason": "; ".join(issue_reasons) if status == "Needs Review" else "",
                "shopify_order_number": base_row.get("shopify_order_number") or base_row.get("shopify_order_name") or "",
                "shopify_variant_title": base_row.get("shopify_variant_title") or base_row.get("variant_title") or "",
                "sports_cave_frame": base_row.get("sports_cave_frame") or base_row.get("frame") or "",
                "sports_cave_size": base_row.get("sports_cave_size") or base_row.get("size") or "",
                "prodigi_product_name": base_row.get("prodigi_product_name") or "",
                "prodigi_product_code": base_row.get("prodigi_product_code") or base_row.get("prodigi_code") or "",
                "prodigi_frame_colour": base_row.get("prodigi_frame_colour") or base_row.get("prodigi_frame") or "",
                "submitted_at": now if status == "Submitted" else "",
                "source": "prodigi_dispatch_log",
                "created_at": base_row.get("created_at") or now,
                "updated_at": now,
            }
        )
        saved = prodigi_tracker_row_from_order(merged, merged)
        updated_rows.append(saved)
    return sort_prodigi_tracker_rows(updated_rows), saved


def render_prodigi_page():
    page_started = time.perf_counter()
    st.title("Prodigi Dispatch Log")
    st.caption("Search an order, confirm the Prodigi checks, then save it to the dispatch log.")
    st.link_button("Open Prodigi Dashboard", PRODIGI_DASHBOARD_URL, use_container_width=False)
    print("Prodigi Shopify fetch skipped on initial load")
    print("Prodigi full order snapshot skipped on initial load")

    with st.expander("Prodigi Reference", expanded=False):
        st.markdown(prodigi_reference_table_html(prodigi_reference_rows()), unsafe_allow_html=True)
        st.caption(f"Support: {PRODIGI_SUPPORT_EMAIL}")

    dispatch_summary = prodigi_load_dispatch_summary()

    search_columns = st.columns([3.2, 1])
    search_value = search_columns[0].text_input(
        "Enter Shopify Order #",
        placeholder="#",
        key="prodigi-dispatch-order-search",
    )
    if search_columns[1].button("Find Order", use_container_width=True, key="prodigi-dispatch-find-order"):
        query = _prodigi_clean(search_value)
        if not query:
            st.warning("Enter a Shopify order number first.")
        else:
            matches, existing_rows = prodigi_find_order_rows_from_cache(query)
            st.session_state["prodigi_dispatch_matches"] = matches
            st.session_state["prodigi_dispatch_existing_rows"] = existing_rows
            st.session_state["prodigi_dispatch_last_query"] = query
            st.session_state["prodigi_dispatch_selected_row_id"] = matches[0]["row_id"] if len(matches) == 1 else ""
            if not matches:
                st.session_state["prodigi_dispatch_selected_row_id"] = ""
            st.rerun()

    matches = st.session_state.get("prodigi_dispatch_matches") or []
    existing_dispatch_rows = st.session_state.get("prodigi_dispatch_existing_rows") or []
    last_query = st.session_state.get("prodigi_dispatch_last_query") or ""

    if last_query and not matches:
        st.warning("Order not found. Sync New Orders first, then try again.")

    selected_row = None
    product_confirmations = {}
    if matches:
        selected_id = st.session_state.get("prodigi_dispatch_selected_row_id") or (matches[0]["row_id"] if len(matches) == 1 else "")
        selected_row = next((row for row in matches if row.get("row_id") == selected_id), None)
        summary_row = matches[0]
        with st.container(border=True):
            st.markdown("**Order Summary**")
            summary_columns = st.columns(5)
            summary_columns[0].write(f"Order: {summary_row.get('shopify_order_name') or '-'}")
            summary_columns[1].write(f"Customer: {summary_row.get('customer_name') or '-'}")
            summary_columns[2].write(f"Date: {summary_row.get('date') or '-'}")
            summary_columns[3].write(f"Email: {summary_row.get('customer_email') or '-'}")
            summary_columns[4].write(f"Shipping: {summary_row.get('shipping_method') or '-'}")

        st.markdown("**Select Artwork Line**")
        header = st.columns([0.8, 2.8, 0.8, 1.4, 1.4, 1.2])
        for column, label in zip(header, ("Select", "Product", "Edition #", "Variant", "Shipping", "Certificate Status")):
            column.caption(label)
        for row in matches:
            row_id = row.get("row_id")
            row_key = safe_filename_part(row_id or "")
            with st.container(border=True):
                columns = st.columns([0.8, 2.8, 0.8, 1.4, 1.4, 1.2])
                if len(matches) == 1:
                    columns[0].write("Selected")
                elif columns[0].button("Select", key=f"prodigi-dispatch-select-{row_key}", use_container_width=True):
                    st.session_state["prodigi_dispatch_selected_row_id"] = row_id
                    st.rerun()
                columns[1].write(row.get("product_title") or "-")
                columns[2].write(f"#{_prodigi_int(row.get('edition_number'), 0):03d}" if _prodigi_int(row.get("edition_number"), 0) else "Not Required")
                columns[3].write(row.get("variant_title") or "-")
                columns[4].write(row.get("shipping_method") or "-")
                columns[5].write(row.get("certificate_status") or "-")

        st.markdown("**Prodigi Product Confirmation**")
        for row in matches:
            row_id = row.get("row_id") or ""
            row_key = safe_filename_part(row_id)
            existing_line = _prodigi_existing_dispatch_row(existing_dispatch_rows, row_id) or row
            defaults = prodigi_line_confirmation_defaults(existing_line)
            has_mapping = bool(row.get("prodigi_product_name") and row.get("prodigi_code") and row.get("prodigi_frame_colour"))
            with st.container(border=True):
                st.markdown(f"**{row.get('product_title') or '-'}**")
                st.caption(f"Shopify variant: {prodigi_shopify_variant_label(row) or '-'}")
                detail_columns = st.columns([2.4, 1, 1])
                detail_columns[0].write(f"Expected Prodigi variant: {row.get('prodigi_product_name') or '-'}")
                detail_columns[1].write(f"Prodigi code: {row.get('prodigi_code') or '-'}")
                detail_columns[2].write(f"Frame colour: {row.get('prodigi_frame_colour') or row.get('prodigi_frame') or '-'}")
                st.caption(prodigi_required_confirmation_question(row))
                confirmed = st.checkbox(
                    "Confirmed exact Prodigi variant selected",
                    value=bool(defaults["confirmed"] and has_mapping),
                    disabled=not has_mapping,
                    key=f"prodigi-dispatch-product-confirm-{row_key}",
                )
                confirmation_notes = defaults["notes"]
                if not confirmed:
                    confirmation_notes = st.text_input(
                        "Notes if not confirmed",
                        value=defaults["notes"],
                        key=f"prodigi-dispatch-product-notes-{row_key}",
                    )
                product_confirmations[row_id] = {
                    "confirmed": bool(confirmed),
                    "notes": confirmation_notes,
                    "has_mapping": has_mapping,
                }

    if selected_row:
        existing = _prodigi_existing_dispatch_row(existing_dispatch_rows, selected_row.get("row_id"))
        already_submitted = existing and _prodigi_dispatch_status(existing) == "Submitted"
        if already_submitted:
            st.info(f"Already submitted on {_prodigi_display_date(existing.get('date_sent_to_prodigi'))}.")

        with st.container(border=True):
            st.markdown("**Prodigi Details**")
            detail_columns = st.columns(2)
            details = [
                ("Shopify Order #", selected_row.get("shopify_order_name") or ""),
                ("Customer Name", selected_row.get("customer_name") or ""),
                ("Product", selected_row.get("product_title") or ""),
                ("Edition No.", _prodigi_edition_label(selected_row)),
                ("Frame", selected_row.get("frame") or ""),
                ("Shopify Size", selected_row.get("size") or ""),
                ("Prodigi Variant", selected_row.get("prodigi_product_name") or ""),
                ("Prodigi Code", selected_row.get("prodigi_code") or ""),
                ("Frame Colour", selected_row.get("prodigi_frame_colour") or selected_row.get("prodigi_frame") or ""),
                ("Shipping", selected_row.get("shipping_method") or ""),
            ]
            for index, (label, value) in enumerate(details):
                detail_columns[index % 2].write(f"**{label}:** {value or '-'}")

        st.markdown("**Dispatch QA**")
        default_answers = prodigi_default_qa_answers(existing or selected_row)
        selected_confirmation = product_confirmations.get(selected_row.get("row_id") or "", {})
        all_products_confirmed = bool(matches) and all(
            confirmation.get("confirmed") and confirmation.get("has_mapping")
            for confirmation in product_confirmations.values()
        )
        product_confirmation_notes = "; ".join(
            f"{next((line.get('product_title') for line in matches if line.get('row_id') == row_id), 'Line')}: {confirmation.get('notes')}"
            for row_id, confirmation in product_confirmations.items()
            if confirmation.get("notes")
        )
        qa_answers = {
            "product_option": "Yes" if all_products_confirmed else "No",
            "product_confirmation": "Yes" if selected_confirmation.get("confirmed") else "No",
            "product_confirmation_notes": product_confirmation_notes,
        }
        qa_specs = [
            ("certificate", "Certificate", "Has the certificate been generated and uploaded?"),
            ("artwork_upload", "Artwork upload", "Did you upload the correct artwork file to Prodigi in excellent quality?"),
            ("frame", "Frame", "Did you select the correct frame colour in Prodigi?"),
            ("size", "Prodigi Variant", "Did you select the correct Prodigi variant?"),
            ("edition_number", "Edition number", "Does the artwork/certificate match this edition number?"),
            ("shipping", "Shipping", "Did you select the correct shipping method?"),
            ("sent_to_production", "Sent to production", "Has this order been sent to production in Prodigi?"),
            ("final_check", "Final check", "Is this order fully checked with no errors?"),
        ]
        for field, title, question in qa_specs:
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.write(question)
                if field == "certificate" and not _prodigi_is_limited_edition(selected_row):
                    st.caption("Not Required")
                    qa_answers[field] = "Not Required"
                    continue
                if field == "certificate":
                    if _prodigi_certificate_uploaded(selected_row):
                        st.success("Certificate uploaded.")
                        qa_answers[field] = "Yes"
                    else:
                        st.warning("Certificate not uploaded.")
                        qa_answers[field] = st.radio(
                            "Certificate uploaded?",
                            ("Yes", "No"),
                            index=1,
                            horizontal=True,
                            key=f"prodigi-dispatch-qa-{field}-{safe_filename_part(selected_row.get('row_id') or '')}",
                        )
                    continue
                if field == "frame":
                    st.caption(f"Sports Cave frame: {selected_row.get('frame') or '-'}")
                    st.caption(f"Prodigi frame: {selected_row.get('prodigi_frame') or '-'}")
                elif field == "size":
                    st.caption(f"Shopify variant: {prodigi_shopify_variant_label(selected_row) or '-'}")
                    st.caption(f"Expected Prodigi variant: {selected_row.get('prodigi_product_name') or '-'}")
                    st.caption(f"Prodigi code: {selected_row.get('prodigi_code') or '-'}")
                    st.caption(f"Frame colour: {selected_row.get('prodigi_frame_colour') or selected_row.get('prodigi_frame') or '-'}")
                elif field == "edition_number":
                    if not _prodigi_is_limited_edition(selected_row):
                        st.caption("Not Required")
                        qa_answers[field] = "Not Required"
                        continue
                    st.caption(f"Edition {_prodigi_edition_label(selected_row)}")
                elif field == "shipping":
                    st.caption(f"Shipping method from Shopify: {selected_row.get('shipping_method') or '-'}")

                stored_answer = default_answers.get(field)
                index = None if stored_answer not in {"Yes", "No"} else ("Yes", "No").index(stored_answer)
                qa_answers[field] = st.radio(
                    title,
                    ("Yes", "No"),
                    index=index,
                    horizontal=True,
                    key=f"prodigi-dispatch-qa-{field}-{safe_filename_part(selected_row.get('row_id') or '')}",
                    label_visibility="collapsed",
                )

        issue_reasons = prodigi_dispatch_issue_reasons(selected_row, qa_answers)
        blockers = prodigi_dispatch_blockers(selected_row, qa_answers)
        line_blockers = []
        for row in matches:
            row_id = row.get("row_id") or ""
            line_confirmation = product_confirmations.get(row_id, {})
            if not line_confirmation.get("has_mapping"):
                line_blockers.append(f"{row.get('product_title') or 'Line'}: missing Prodigi mapping")
            if not line_confirmation.get("confirmed"):
                line_blockers.append(f"{row.get('product_title') or 'Line'}: exact Prodigi variant not confirmed")
            row_answers = dict(qa_answers)
            if not _prodigi_is_limited_edition(row):
                row_answers["certificate"] = "Not Required"
                row_answers["edition_number"] = "Not Required"
            elif _prodigi_certificate_uploaded(row):
                row_answers["certificate"] = "Yes"
            for blocker in prodigi_dispatch_blockers(row, row_answers):
                line_blockers.append(f"{row.get('product_title') or 'Line'}: {blocker}")
        completion_blockers = list(dict.fromkeys(blockers + line_blockers))
        notes = st.text_area(
            "Notes",
            value=(existing or {}).get("notes") or "",
            height=100,
            key=f"prodigi-dispatch-notes-{safe_filename_part(selected_row.get('row_id') or '')}",
        )
        if issue_reasons:
            st.warning("Needs Review: " + "; ".join(issue_reasons))
        if completion_blockers:
            for blocker in completion_blockers:
                st.warning(blocker)

        action_columns = st.columns([1, 1, 3])
        if action_columns[0].button("Save Issue", use_container_width=True, key="prodigi-dispatch-save-issue"):
            try:
                prodigi_save_dispatch_row(
                    selected_row,
                    status="Needs Review",
                    notes=notes,
                    qa_answers=qa_answers,
                )
                st.session_state["prodigi_dispatch_log_view"] = "Needs Review"
                st.success("Issue saved to dispatch log.")
                st.rerun()
            except Exception as error:
                supabase_backend.log_app_error("prodigi_dispatch_issue_save_failed", str(error), {"source": "prodigi_page"})
                st.error("Dispatch issue save failed. Check Supabase connection and Render logs.")
        if action_columns[1].button(
            "Complete Dispatch",
            type="primary",
            use_container_width=True,
            disabled=bool(completion_blockers) or bool(already_submitted),
            key="prodigi-dispatch-complete",
        ):
            try:
                for line in matches:
                    line_confirmation = product_confirmations.get(line.get("row_id") or "", {})
                    line_answers = dict(qa_answers)
                    line_answers["product_option"] = "Yes"
                    line_answers["product_confirmation"] = "Yes"
                    line_answers["product_confirmation_notes"] = line_confirmation.get("notes") or ""
                    if not _prodigi_is_limited_edition(line):
                        line_answers["certificate"] = "Not Required"
                        line_answers["edition_number"] = "Not Required"
                    elif _prodigi_certificate_uploaded(line):
                        line_answers["certificate"] = "Yes"
                    prodigi_save_dispatch_row(
                        line,
                        status="Submitted",
                        notes=notes if line.get("row_id") == selected_row.get("row_id") else line_confirmation.get("notes") or "",
                        qa_answers=line_answers,
                    )
                st.session_state["prodigi_dispatch_matches"] = []
                st.session_state["prodigi_dispatch_existing_rows"] = []
                st.session_state["prodigi_dispatch_selected_row_id"] = ""
                st.session_state["prodigi_dispatch_last_query"] = ""
                st.session_state["prodigi_dispatch_log_view"] = "Last 7 Days"
                st.success("Dispatch row saved")
                st.rerun()
            except Exception as error:
                supabase_backend.log_app_error("prodigi_dispatch_complete_save_failed", str(error), {"source": "prodigi_page"})
                st.error("Dispatch save failed. Check Supabase connection and Render logs.")

    st.divider()
    st.subheader("Submitted Dispatch Log")
    st.caption(f"Dispatch rows saved: {dispatch_summary.get('rows_saved', 0)}")
    st.caption(f"Last tracker save: {dispatch_summary.get('last_saved_at') or 'Not saved yet'}")
    log_search = st.text_input(
        "Search dispatch log",
        placeholder="Order, customer, product, edition, notes",
        key="prodigi-dispatch-log-search",
    )
    selected_log_view = st.radio(
        "Dispatch log view",
        ("Last 7 Days", "Needs Review", "Submitted", "History"),
        horizontal=True,
        key="prodigi_dispatch_log_view",
        label_visibility="collapsed",
    )
    log_started = time.perf_counter()
    table_rows = prodigi_load_dispatch_rows(selected_log_view, log_search, limit=50)
    records = prodigi_dispatch_table_records(table_rows)
    _prodigi_log_timing("dispatch table render", log_started, f"view={selected_log_view} rows={len(records)}")
    if records:
        st.dataframe(records, hide_index=True, use_container_width=True)
    elif dispatch_summary.get("rows_saved"):
        st.info("No dispatch rows in this view.")
    else:
        st.info("No dispatch rows saved yet.")
    _prodigi_log_timing("page render", page_started)


def fetch_latest_shopify_products(config):
    run_id = db.start_shopify_sync(config["store_domain"], config["api_version"])
    progress = st.progress(0, text="Fetching latest Shopify products...")
    products_seen = 0
    pages_synced = 0
    fetched_product_ids = []
    catalog_complete = False
    try:
        for page in shopify_sync.iter_catalog_pages(config=config):
            db.upsert_shopify_products(page["products"])
            fetched_product_ids.extend(product["shopify_product_id"] for product in page["products"])
            products_seen += len(page["products"])
            pages_synced += 1
            catalog_complete = not page.get("has_next_page")
            db.update_shopify_sync_run(
                run_id,
                products_seen=products_seen,
                pages_synced=pages_synced,
                api_version=page.get("api_version"),
            )
            percent = min(int(products_seen / max(config["max_products"], 1) * 100), 99)
            progress.progress(percent, text=f"Fetched {products_seen} Shopify products...")
            del page
            gc.collect()

        matched_count = db.auto_match_shopify_products()
        missing_count = db.mark_missing_shopify_products(fetched_product_ids) if catalog_complete else 0
        db.update_shopify_sync_run(
            run_id,
            status="Complete",
            products_seen=products_seen,
            pages_synced=pages_synced,
        )
        progress.progress(100, text="Shopify product fetch complete.")
        return {
            "products_seen": products_seen,
            "matched_count": matched_count,
            "missing_count": missing_count,
            "catalog_complete": catalog_complete,
        }
    except Exception as error:
        db.update_shopify_sync_run(
            run_id,
            status="Failed",
            products_seen=products_seen,
            pages_synced=pages_synced,
            error_message="Shopify product fetch failed. Check authentication, scopes, and API version.",
        )
        progress.empty()
        raise error


def apply_limited_edition_table_changes(products):
    updated_count = 0
    unchanged_count = 0
    errors = []
    for product in products:
        item_key = limited_edition_item_key(product)
        edition_limit = int(st.session_state.get(f"le-limit-{item_key}", product.get("edition_limit") or 100))
        next_available = int(
            st.session_state.get(f"le-next-{item_key}", product.get("next_available_edition") or 1)
        )
        editions_sold = int(st.session_state.get(f"le-sold-{item_key}", product.get("editions_sold") or 0))
        psd_file_url = str(st.session_state.get(f"le-psd-{item_key}", product.get("psd_file_url") or "") or "").strip()

        current_values = (
            int(product.get("edition_limit") or 100),
            int(product.get("next_available_edition") or 1),
            int(product.get("editions_sold") or 0),
            product.get("psd_file_url") or "",
        )
        new_values = (
            edition_limit,
            next_available,
            editions_sold,
            psd_file_url,
        )
        if current_values == new_values:
            unchanged_count += 1
            continue
        try:
            db.update_shopify_edition_product(
                product["shopify_product_id"],
                edition_limit=edition_limit,
                next_available_edition=next_available,
                editions_sold=editions_sold,
                psd_file_url=psd_file_url,
                prodigi_url=product.get("prodigi_url") or "",
                prodigi_product_id=product.get("prodigi_product_id") or "",
                notes=product.get("edition_notes") or "",
                allow_oversold=False,
            )
            updated_count += 1
        except Exception as error:
            errors.append(f"{product.get('product_title') or 'Product'}: {error}")

    return {"updated": updated_count, "unchanged": unchanged_count, "errors": errors[:10]}


def sync_changed_edition_widgets(config):
    products = db.list_shopify_products_needing_widget_sync(limit=500)
    synced_count = 0
    errors = []
    for product in products:
        try:
            shopify_sync.sync_edition_metafields(product, config=config)
            db.mark_shopify_edition_synced(product["shopify_product_id"])
            synced_count += 1
        except Exception as error:
            errors.append(f"{product.get('product_title') or 'Product'}: {error}")
    return {"attempted": len(products), "synced": synced_count, "errors": errors[:10]}


def parse_limited_edition_supabase_csv(uploaded_csv):
    text = uploaded_csv.getvalue().decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("The CSV has no header row.")
    return [dict(row) for row in reader]


def build_supabase_edition_editor_rows(products):
    rows = []
    for product in products:
        next_number = int(product.get("next_edition_number") or 1)
        total = int(product.get("edition_total") or 100)
        latest_sent = int(product.get("latest_sent") if product.get("latest_sent") is not None else max(next_number - 1, 0))
        rows.append(
            {
                "Product title": product.get("product_title") or "Untitled product",
                "Shopify handle": product.get("shopify_handle") or "",
                "Shopify product ID": product.get("shopify_product_id") or product.get("shopify_product_gid") or "",
                "Edition name": product.get("edition_name") or "Original Edition",
                "Latest sent": latest_sent,
                "Next edition number": next_number,
                "Total editions": total,
                "Remaining": max(total - latest_sent, 0),
                "Status": product.get("status") or ("sold_out" if product.get("sold_out") else "active"),
                "Last updated": format_updated_at(product.get("updated_at")),
            }
        )
    return rows


def apply_supabase_edition_editor_changes(products, edited_rows):
    products_by_handle = {item.get("shopify_handle"): item for item in products if item.get("shopify_handle")}
    updated = 0
    unchanged = 0
    errors = []
    for row in edited_rows or []:
        handle = str(row.get("Shopify handle") or "").strip()
        product = products_by_handle.get(handle)
        if not product:
            continue
        old_latest = int(product.get("latest_sent") if product.get("latest_sent") is not None else max(int(product.get("next_edition_number") or 1) - 1, 0))
        old_next = int(product.get("next_edition_number") or 1)
        old_total = int(product.get("edition_total") or 100)
        old_name = product.get("edition_name") or "Original Edition"
        old_status = product.get("status") or ("sold_out" if product.get("sold_out") else "active")

        new_latest = int(row.get("Latest sent") if row.get("Latest sent") is not None else old_latest)
        new_next_from_grid = int(row.get("Next edition number") if row.get("Next edition number") is not None else old_next)
        new_next = new_latest + 1 if new_latest != old_latest else new_next_from_grid
        new_total = int(row.get("Total editions") if row.get("Total editions") is not None else old_total)
        new_name = str(row.get("Edition name") or old_name).strip() or "Original Edition"
        new_status = str(row.get("Status") or old_status).strip().lower().replace(" ", "_")

        if (
            new_latest == old_latest
            and new_next == old_next
            and new_total == old_total
            and new_name == old_name
            and new_status == old_status
        ):
            unchanged += 1
            continue
        try:
            supabase_backend.update_edition_product(
                handle,
                edition_name=new_name,
                edition_total=new_total,
                next_edition_number=new_next,
                status=new_status,
                reason="Limited Editions tracker grid edit",
            )
            try:
                supabase_backend.sync_product_edition_metafields(handle)
            except Exception as sync_error:
                errors.append(f"{handle}: Shopify metafield sync failed: {sync_error}")
            updated += 1
        except Exception as error:
            errors.append(f"{handle}: {error}")
    return {"updated": updated, "unchanged": unchanged, "errors": errors}


def render_supabase_limited_edition_csv_import(uploaded_csv):
    if uploaded_csv is None:
        return
    st.markdown("**CSV import preview**")
    st.caption(
        "Matched rows update Supabase edition fields. Missing CSV products are not deleted."
    )
    try:
        csv_rows = parse_limited_edition_supabase_csv(uploaded_csv)
    except Exception as error:
        st.error("Could not read the CSV.")
        supabase_backend.log_app_error("limited_editions_csv_read_failed", str(error), {"source": "limited_editions_page"})
        return

    if not csv_rows:
        st.warning("The CSV has headers but no data rows.")
        return

    try:
        preview = supabase_backend.preview_limited_edition_import_rows(csv_rows)
    except Exception as error:
        st.error("Could not preview this CSV.")
        supabase_backend.log_app_error("limited_editions_csv_preview_failed", str(error), {"source": "limited_editions_page"})
        return

    preview_columns = st.columns(5)
    preview_columns[0].metric("Rows read", preview["rows_read"])
    preview_columns[1].metric("Matched", len(preview["matched"]))
    preview_columns[2].metric("Changes", len(preview["changes"]))
    preview_columns[3].metric("Createable", len(preview["createable"]))
    preview_columns[4].metric("Unmatched", len(preview["unmatched"]))

    if preview["changes"]:
        st.dataframe(
            [
                {
                    "Line": item["line"],
                    "Product": item["product_title"],
                    "Handle": item["shopify_handle"],
                    "Edition": f"{item['current_edition_name']} -> {item['new_edition_name']}",
                    "Next": f"{item['current_next']} -> {item['new_next']}",
                    "Total": f"{item['current_total']} -> {item['new_total']}",
                    "Status": f"{item['current_status']} -> {item['new_status']}",
                }
                for item in preview["changes"]
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No counter changes found in the matched CSV rows.")

    if preview["createable"]:
        st.markdown("**Products found in Shopify sync but not edition tracking yet**")
        st.dataframe(preview["createable"], use_container_width=True, hide_index=True)
    if preview["unmatched"]:
        st.markdown("**Unmatched rows**")
        st.dataframe(preview["unmatched"], use_container_width=True, hide_index=True)

    create_missing = st.checkbox(
        "Create missing edition products only when they already exist in Shopify sync",
        value=False,
        key="supabase-limited-csv-create-missing",
    )
    confirmed = st.checkbox(
        "I reviewed the preview and want to apply these edition tracker changes",
        key="supabase-limited-csv-confirm-apply",
    )
    if st.button(
        "Apply CSV Changes",
        type="primary",
        use_container_width=True,
        disabled=not confirmed,
    ):
        try:
            result = supabase_backend.apply_limited_edition_import_rows(
                csv_rows,
                create_missing_from_shopify=create_missing,
            )
            st.session_state.supabase_limited_notice = (
                f"CSV import complete. Rows read: {result['rows_read']}. "
                f"Matched: {result['rows_matched']}. Created: {result['rows_created']}. "
                f"Updated: {result['rows_updated']}. Skipped: {result['rows_skipped']}."
            )
            if result.get("errors"):
                st.session_state.supabase_limited_warning = "First CSV import issue: " + result["errors"][0]
            bump_supabase_cache_version("limited", "sync-state")
            st.rerun()
        except Exception as error:
            st.error("Limited Edition CSV import failed.")
            supabase_backend.log_app_error("limited_editions_csv_apply_failed", str(error), {"source": "limited_editions_page"})


def render_supabase_limited_editions_page():
    st.title("Limited Editions")
    st.caption("Supabase is the source of truth for edition numbers. Shopify remains the product/order source.")

    notice = st.session_state.pop("supabase_limited_notice", None)
    if notice:
        st.success(notice)
    warning = st.session_state.pop("supabase_limited_warning", None)
    if warning:
        st.warning(warning)

    config = shopify_sync.get_config()
    if not st.session_state.get("supabase-limited-defaults-v3-applied"):
        st.session_state["supabase-limited-defaults-v3-applied"] = True

    try:
        sync_state = cached_supabase_sync_state(supabase_cache_version("sync-state"))
        last_product_sync = sync_state.get("last_successful_product_sync_at")
    except Exception:
        sync_state = {}
        last_product_sync = ""
    initial_product_sync = not bool(last_product_sync)
    sync_button_label = "Load Product Catalogue" if initial_product_sync else "Sync Product Updates"
    sync_progress_label = "Importing Shopify product catalogue..." if initial_product_sync else "Checking Shopify product updates..."
    sync_complete_label = "Initial product sync complete." if initial_product_sync else "Shopify product sync complete."

    search = st.text_input(
        "Search products",
        placeholder="Search product title or Shopify handle",
        key="supabase-limited-search",
        label_visibility="collapsed",
    )
    actions = st.columns([1.05, 1.05, 1.1, 1.1])
    if actions[0].button(sync_button_label, type="primary", disabled=not config["configured"], use_container_width=True):
        progress = st.progress(0, text=sync_progress_label)
        sync_started = time.perf_counter()
        try:
            def update_product_progress(count):
                progress.progress(
                    min(count / 1000, 0.99),
                    text=f"Loaded {count} Shopify product records...",
                )

            result = supabase_backend.sync_shopify_products_to_supabase(
                config,
                progress_callback=update_product_progress,
                mode="full" if initial_product_sync else "incremental",
            )
            perf_log(
                f"PERF Shopify product fetch write time={(time.perf_counter() - sync_started):.3f}s "
                f"mode={result.get('mode') or ('full' if initial_product_sync else 'incremental')} "
                f"processed={int(result.get('products_processed', 0) or 0)}"
            )
            progress.progress(1.0, text=sync_complete_label)
            warning_suffix = ""
            if result.get("metafield_errors"):
                warning_suffix = f" Metafield sync warnings: {len(result['metafield_errors'])}."
            if result.get("mode") == "full":
                st.session_state.supabase_limited_notice = (
                    f"Imported {result['products_processed']} Shopify products into Supabase. "
                    f"Prepared the saved catalogue for instant screen loads and synced {result.get('metafields_synced', 0)} edition display records."
                    f"{warning_suffix}"
                )
            else:
                st.session_state.supabase_limited_notice = (
                    f"Synced {result['products_processed']} updated Shopify products into Supabase. "
                    f"Updated {result.get('metafields_synced', 0)} Shopify edition display records."
                    f"{warning_suffix}"
                )
            bump_supabase_cache_version("limited", "sync-state")
            st.rerun()
        except Exception as error:
            perf_log(f"PERF Shopify product fetch write time={(time.perf_counter() - sync_started):.3f}s status=failed")
            progress.empty()
            render_supabase_load_warning("Product sync", error, "limited-sync")
            supabase_backend.log_app_error(
                "limited_editions_product_sync_failed",
                str(error),
                {"source": "limited_editions_page"},
            )
    uploaded_csv = actions[1].file_uploader(
        "Import CSV",
        type=["csv"],
        key="supabase-limited-edition-csv-upload",
    )
    actions[2].caption("Saved products show automatically.")
    actions[3].caption("Sync only when Shopify has new updates.")

    render_supabase_limited_edition_csv_import(uploaded_csv)

    filter_signature = search.strip().lower()
    if st.session_state.get("supabase-limited-filter-signature") != filter_signature:
        st.session_state["supabase-limited-filter-signature"] = filter_signature
        st.session_state["supabase-limited-page"] = 0
    current_page = max(int(st.session_state.get("supabase-limited-page", 0) or 0), 0)
    page_size = DEFAULT_PAGE_SIZE
    offset = current_page * page_size
    page_started = time.perf_counter()
    db_started = time.perf_counter()
    try:
        with st.spinner("Loading edition products..."):
            cache_version = supabase_cache_version("limited")

            def load_limited_page():
                product_rows = cached_supabase_limited_products(
                    search,
                    page_size + 1,
                    offset,
                    cache_version,
                )
                visible_rows = product_rows[:page_size]
                handles = tuple(
                    product.get("shopify_handle")
                    for product in visible_rows
                    if product.get("shopify_handle")
                )
                return {
                    "products": visible_rows,
                    "has_next": len(product_rows) > page_size,
                    "asset_map": cached_supabase_product_asset_map(handles, cache_version),
                }

            snapshot_key = f"supabase-limited-screen-{current_page}-{filter_signature}"
            dataset, reused_saved_dataset, dataset_error = load_supabase_screen_snapshot(
                snapshot_key,
                cache_version,
                load_limited_page,
            )
            products = dataset.get("products") or []
            asset_map = dataset.get("asset_map") or {}
            has_next_page = bool(dataset.get("has_next"))
    except Exception as error:
        render_supabase_load_warning("Edition products", error, "limited-products")
        supabase_backend.log_app_error("limited_editions_load_failed", str(error), {"source": "limited_editions_page"})
        perf_log(
            f"PERF Limited Editions total={(time.perf_counter() - page_started):.3f}s "
            f"db={(time.perf_counter() - db_started):.3f}s render=0.000s rows=0"
        )
        return
    db_elapsed = time.perf_counter() - db_started
    if dataset_error:
        render_supabase_load_warning(
            "Edition products",
            dataset_error,
            "limited-products",
            using_saved_screen_data=True,
        )
        supabase_backend.log_app_error("limited_editions_load_failed", str(dataset_error), {"source": "limited_editions_page"})

    loaded_columns = st.columns([1.0, 0.75, 0.75, 1.0, 1.4])
    loaded_columns[0].download_button(
        "Export shown rows",
        data=build_supabase_products_csv(products, asset_map),
        file_name="sports-cave-supabase-limited-editions.csv",
        mime="text/csv",
        use_container_width=True,
    )
    if loaded_columns[1].button("Previous", disabled=current_page <= 0, use_container_width=True, key="supabase-limited-prev"):
        st.session_state["supabase-limited-page"] = max(current_page - 1, 0)
        st.rerun()
    if loaded_columns[2].button("Next", disabled=not has_next_page, use_container_width=True, key="supabase-limited-next"):
        st.session_state["supabase-limited-page"] = current_page + 1
        st.rerun()
    loaded_columns[3].caption(f"Page {current_page + 1} | {len(products)} products shown")
    loaded_columns[3].caption(
        "Last sync: " + (format_updated_at(last_product_sync) if last_product_sync else "Never")
    )
    if reused_saved_dataset:
        loaded_columns[4].caption("Showing the last saved screen snapshot while the live refresh retries.")
    else:
        loaded_columns[4].caption("Saved catalogue stays warm on screen until you manually sync again.")

    render_started = time.perf_counter()
    st.subheader("Edition Products")
    st.caption("Edit the live Supabase counters directly. If Latest sent is changed, Next is saved as Latest + 1.")
    if not products:
        st.info("No edition products match the current search yet.")
        perf_log(
            f"PERF Limited Editions total={(time.perf_counter() - page_started):.3f}s "
            f"db={db_elapsed:.3f}s render={(time.perf_counter() - render_started):.3f}s rows=0"
        )
        return

    st.markdown(
        """
        <style>
        .sc-product-thumb-empty {
            width: 46px;
            height: 46px;
            border-radius: 10px;
            border: 1px solid rgba(212, 165, 76, 0.36);
            background: rgba(245, 242, 234, 0.08);
            color: #D4A54C;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 0.72rem;
            font-weight: 800;
            letter-spacing: 0.04em;
        }
        .sc-limited-product-title {
            color: #F8FAFC;
            font-weight: 800;
            line-height: 1.2;
        }
        .sc-limited-handle {
            color: #A6A19A;
            font-size: 0.78rem;
            line-height: 1.25;
            word-break: break-word;
        }
        div[data-testid="stButton"] button,
        div[data-testid="stDownloadButton"] button,
        div[data-testid="stLinkButton"] a {
            white-space: nowrap !important;
        }
        div[data-testid="stNumberInput"] input,
        div[data-testid="stTextInput"] input {
            min-height: 2.45rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    header = st.columns([0.52, 2.0, 1.05, 0.62, 0.72, 0.62, 0.72, 0.78, 1.2, 1.2, 0.82, 0.7])
    for column, label in zip(
        header,
        ("Art", "Product", "Handle", "Total", "Latest", "Next", "Remaining", "Status", "PSD", "Prodigi", "Shopify", "Save"),
    ):
        column.markdown(f"**{label}**")
    status_options = {
        "active": "Active",
        "inactive": "Inactive",
        "sold_out": "Sold out",
    }
    for product_index, product in enumerate(products):
        product_handle = product.get("shopify_handle") or ""
        key_base = f"limited-row-{product_index}-{product_handle or 'missing'}"
        product_assets = asset_map.get(product_handle) or {}
        psd_url = product_assets.get("psd_master_file") or ""
        prodigi_url = product_assets.get("prodigi_link") or ""
        edition_total = max(int(product.get("edition_total") or 100), 1)
        next_number = max(int(product.get("next_edition_number") or 1), 1)
        latest_sent = max(int(product.get("latest_sent") if product.get("latest_sent") is not None else next_number - 1), 0)
        current_status = str(product.get("status") or ("sold_out" if product.get("sold_out") else "active")).lower()
        if current_status not in status_options:
            current_status = "active" if product.get("active") else "inactive"

        columns = st.columns([0.52, 2.0, 1.05, 0.62, 0.72, 0.62, 0.72, 0.78, 1.2, 1.2, 0.82, 0.7])
        with columns[0]:
            st.markdown('<div class="sc-product-thumb-empty">SC</div>', unsafe_allow_html=True)
        with columns[1]:
            st.markdown(
                f'<div class="sc-limited-product-title">{html.escape(product.get("product_title") or "Untitled product")}</div>',
                unsafe_allow_html=True,
            )
        columns[2].markdown(
            f'<div class="sc-limited-handle">{html.escape(product_handle or "-")}</div>',
            unsafe_allow_html=True,
        )
        total_value = columns[3].number_input(
            "Total",
            min_value=1,
            value=edition_total,
            step=1,
            key=f"{key_base}-total",
            label_visibility="collapsed",
        )
        latest_value = columns[4].number_input(
            "Latest sent",
            min_value=0,
            value=latest_sent,
            step=1,
            key=f"{key_base}-latest",
            label_visibility="collapsed",
        )
        next_value = columns[5].number_input(
            "Next edition",
            min_value=1,
            value=next_number,
            step=1,
            key=f"{key_base}-next",
            label_visibility="collapsed",
        )
        proposed_next = int(latest_value) + 1 if int(latest_value) != latest_sent else int(next_value)
        columns[6].markdown(f"**{max(int(total_value) - (proposed_next - 1), 0)}**")
        status_label = columns[7].selectbox(
            "Status",
            list(status_options.values()),
            index=select_index(list(status_options), current_status),
            key=f"{key_base}-status",
            label_visibility="collapsed",
        )
        selected_status = next(key for key, label in status_options.items() if label == status_label)
        psd_value = columns[8].text_input(
            "PSD URL",
            value=psd_url,
            placeholder="PSD link",
            key=f"{key_base}-psd",
            label_visibility="collapsed",
        )
        if psd_value.strip():
            columns[8].link_button("Open PSD", psd_value.strip(), use_container_width=True)
        prodigi_value = columns[9].text_input(
            "Prodigi URL",
            value=prodigi_url,
            placeholder="Prodigi link",
            key=f"{key_base}-prodigi",
            label_visibility="collapsed",
        )
        if prodigi_value.strip():
            columns[9].link_button("Open Prodigi", prodigi_value.strip(), use_container_width=True)
        with columns[10]:
            if product.get("admin_url"):
                st.link_button("Shopify", product["admin_url"], use_container_width=True)
            elif product.get("online_store_url"):
                st.link_button("Storefront", product["online_store_url"], use_container_width=True)
            else:
                st.caption("No link")
        if columns[11].button(
            "Save",
            key=f"{key_base}-save",
            type="primary",
            disabled=not product_handle,
            use_container_width=True,
        ):
            try:
                final_next = int(latest_value) + 1 if int(latest_value) != latest_sent else int(next_value)
                supabase_backend.update_edition_product(
                    product_handle,
                    edition_total=int(total_value),
                    next_edition_number=final_next,
                    status=selected_status,
                    reason="Limited Editions row edit",
                )
                sync_warning = ""
                try:
                    supabase_backend.sync_product_edition_metafields(product_handle)
                except Exception as sync_error:
                    sync_warning = f" Shopify metafield sync failed: {sync_error}"
                    supabase_backend.log_app_error(
                        "limited_editions_row_metafield_sync_failed",
                        str(sync_error),
                        {"source": "limited_editions_page", "handle": product_handle},
                    )
                if psd_value.strip():
                    supabase_backend.upsert_product_asset(
                        product_handle,
                        "psd_master_file",
                        psd_value.strip(),
                        "Limited Editions row edit",
                        asset_name=f"{product_handle}.psd",
                        is_primary=True,
                    )
                if prodigi_value.strip():
                    supabase_backend.upsert_product_asset(
                        product_handle,
                        "prodigi_link",
                        prodigi_value.strip(),
                        "Limited Editions row edit",
                        asset_name="Prodigi",
                        is_primary=True,
                    )
                bump_supabase_cache_version("limited")
                st.session_state.supabase_limited_notice = (
                    f"Saved edition settings for {product.get('product_title') or product_handle}.{sync_warning}"
                )
                st.rerun()
            except Exception as error:
                st.error("Could not save this edition row.")
                supabase_backend.log_app_error("limited_editions_row_save_failed", str(error), {"source": "limited_editions_page", "handle": product_handle})
        st.divider()
    render_elapsed = time.perf_counter() - render_started
    perf_log(
        f"PERF Limited Editions total={(time.perf_counter() - page_started):.3f}s "
        f"db={db_elapsed:.3f}s render={render_elapsed:.3f}s rows={len(products)}"
    )


def render_limited_editions_page(dispatch_log_renderer=None):
    if supabase_backend.is_configured():
        render_supabase_limited_editions_page()
        return
    if not allow_local_sqlite_fallback():
        render_supabase_required_notice("Limited Editions")
        return
    st.title("Limited Editions")
    render_local_cache_notice()
    st.caption("Track edition numbers and PSD files from saved product data.")
    st.markdown(
        """
        <style>
        .le-product-cell {
            display: flex;
            align-items: center;
            gap: 0.65rem;
            min-height: 44px;
        }
        .le-thumb {
            width: 38px;
            height: 38px;
            border-radius: 8px;
            object-fit: cover;
            background: #141416;
            border: 1px solid rgba(212, 165, 76, 0.28);
            flex: 0 0 auto;
        }
        .le-thumb-empty {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            color: #D4A54C;
            font-size: 0.75rem;
        }
        .le-title {
            color: #F5F2EA !important;
            font-weight: 700;
            text-decoration: none;
            line-height: 1.15;
        }
        .le-handle {
            color: #A6A19A;
            font-size: 0.78rem;
            margin-top: 0.18rem;
        }
        .le-row-rule {
            border-bottom: 1px solid rgba(245, 242, 234, 0.08);
            margin: 0.35rem 0 0.55rem;
        }
        .le-range {
            color: #A6A19A;
            text-align: center;
            padding-top: 0.35rem;
        }
        div[data-testid="stNumberInput"] input,
        div[data-testid="stTextInput"] input {
            min-height: 36px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    config = shopify_sync.get_config()
    summary = db.get_shopify_summary()
    edition_summary = db.get_shopify_edition_summary()
    notice = st.session_state.pop("limited_edition_notice", None)
    warning = st.session_state.pop("limited_edition_warning", None)
    if notice:
        st.success(notice)
    if warning:
        st.warning(warning)

    search = st.text_input(
        "Search products",
        placeholder="Search products by title, handle, sport, SKU, or keyword",
        key="limited-edition-search",
        label_visibility="collapsed",
    )

    actions = st.columns([1.25, 0.8, 0.8, 0.95, 1.05, 1.05])
    fetch_clicked = actions[0].button(
        "Sync Product Updates",
        type="primary",
        disabled=not config["configured"],
        use_container_width=True,
    )
    import_toggle_clicked = actions[1].button("Import CSV", use_container_width=True)
    actions[2].download_button(
        "Export CSV",
        data=build_limited_editions_csv(db.list_all_shopify_edition_products()),
        file_name="sports-cave-limited-editions.csv",
        mime="text/csv",
        use_container_width=True,
    )
    actions[3].download_button(
        "Download Template",
        data=build_limited_editions_template_csv(),
        file_name="sports-cave-limited-editions-template.csv",
        mime="text/csv",
        use_container_width=True,
    )
    sync_widget_clicked = actions[4].button(
        "Sync Edition Display",
        disabled=not config["configured"],
        use_container_width=True,
    )
    apply_clicked = actions[5].button("Apply Table Changes", use_container_width=True)

    if import_toggle_clicked:
        st.session_state.limited_edition_import_open = not st.session_state.get(
            "limited_edition_import_open",
            False,
        )

    if not config["configured"]:
        st.caption("Product sync is not configured. Saved products remain visible.")

    if fetch_clicked:
        try:
            result = fetch_latest_shopify_products(config)
            missing_note = (
                f" {result['missing_count']} cached products marked Missing."
                if result["catalog_complete"] and result["missing_count"]
                else ""
            )
            st.session_state.limited_edition_notice = (
                f"Fetched {result['products_seen']} Shopify products."
                f" {result['matched_count']} internal matches refreshed.{missing_note}"
            )
            st.rerun()
        except Exception as error:
            st.error("Could not fetch latest Shopify products.")
            st.error(str(error))

    if sync_widget_clicked:
        try:
            result = sync_changed_edition_widgets(config)
            if result["errors"]:
                st.session_state.limited_edition_warning = (
                    f"Updated {result['synced']} of {result['attempted']} edition display records. "
                    f"First issue: {result['errors'][0]}"
                )
            else:
                st.session_state.limited_edition_notice = (
                    f"Updated {result['synced']} edition display record"
                    f"{'s' if result['synced'] != 1 else ''}."
                )
            st.rerun()
        except Exception as error:
            st.error("Could not sync edition display to Shopify.")
            st.error(str(error))

    if st.session_state.get("limited_edition_import_open", False):
        with st.container(border=True):
            st.caption("Updates existing cached products only. Match order: Shopify product ID, handle, then product title.")
            import_columns = st.columns([2.5, 1])
            uploaded_csv = import_columns[0].file_uploader(
                "Limited Edition CSV",
                type=["csv"],
                key="limited-edition-import-csv",
                label_visibility="collapsed",
            )
            import_clicked = import_columns[1].button(
                "Import",
                disabled=uploaded_csv is None,
                use_container_width=True,
            )
            if import_clicked and uploaded_csv is not None:
                try:
                    result = import_limited_editions_csv(uploaded_csv)
                    st.session_state.limited_edition_notice = (
                        f"Imported {result['imported_rows']} rows. Updated {result['updated_rows']} products. "
                        f"Skipped {result['skipped_rows']} rows."
                    )
                    if result["errors"]:
                        st.session_state.limited_edition_warning = "First import issue: " + result["errors"][0]
                    st.session_state.limited_edition_import_open = False
                    st.rerun()
                except Exception as error:
                    st.error("Could not import the CSV.")
                    st.error(str(error))

    tracker_filter = st.selectbox(
        "Filter",
        ["All", "Active", "Draft", "Archived", "Missing Edition Setup", "Missing PSD", "Final Editions", "Sold Out"],
        key="le-tracker-filter",
    )

    st.caption(
        f"Last fetched: {format_updated_at(summary['last_synced_at']) if summary['last_synced_at'] else 'Never'} - "
        f"{summary['total']} products cached - {edition_summary['needs_widget_sync']} needing display update"
    )

    filter_signature = f"{search}|{tracker_filter}"
    if st.session_state.get("limited_editions_filter_signature") != filter_signature:
        st.session_state.limited_editions_filter_signature = filter_signature
        st.session_state.limited_editions_page = 1

    page_size = 50
    total_products = db.count_shopify_edition_products(search=search, tracker_filter=tracker_filter)
    max_page = max((total_products + page_size - 1) // page_size, 1)
    current_page = int(st.session_state.get("limited_editions_page", 1) or 1)
    current_page = min(max(current_page, 1), max_page)
    st.session_state.limited_editions_page = current_page
    offset = (current_page - 1) * page_size

    products = db.list_shopify_edition_products(
        search=search,
        tracker_filter=tracker_filter,
        limit=page_size,
        offset=offset,
    )

    if apply_clicked:
        result = apply_limited_edition_table_changes(products)
        if result["errors"]:
            st.session_state.limited_edition_warning = (
                f"Updated {result['updated']} products. First issue: {result['errors'][0]}"
            )
        else:
            st.session_state.limited_edition_notice = (
                f"Updated {result['updated']} products. {result['unchanged']} unchanged."
            )
        st.rerun()

    range_start = offset + 1 if total_products else 0
    range_end = min(offset + len(products), total_products)
    st.caption(f"{range_start}-{range_end} of {total_products} products")
    if not products:
        st.info("No saved products match this search or filter. Use Sync Product Updates if product updates are needed.")
        return

    header = st.columns([3.0, 0.75, 0.75, 0.75, 0.6, 0.7, 0.95, 1.65, 0.85])
    for column, label in zip(
        header,
        (
            "Product",
            "Status",
            "Edition Limit",
            "Next Edition",
            "Sold",
            "Remaining",
            "Edition Status",
            "PSD",
            "Updated",
        ),
    ):
        column.markdown(f"**{label}**")

    for product in products:
        item_key = limited_edition_item_key(product)
        row = st.columns([3.0, 0.75, 0.75, 0.75, 0.6, 0.7, 0.95, 1.65, 0.85])
        product_title = product.get("product_title") or "Untitled Shopify Product"
        safe_title = html.escape(product_title)
        safe_handle = html.escape(product.get("shopify_handle") or "Handle missing")
        thumbnail_url = product.get("thumbnail_url") or ""
        if thumbnail_url:
            thumb_html = f'<img class="le-thumb" src="{html.escape(thumbnail_url, quote=True)}" alt="">'
        else:
            thumb_html = '<span class="le-thumb le-thumb-empty">SC</span>'
        if product.get("online_store_url"):
            safe_url = html.escape(product["online_store_url"], quote=True)
            title_html = f'<a class="le-title" href="{safe_url}" target="_blank">{safe_title}</a>'
        else:
            title_html = f'<span class="le-title">{safe_title}</span>'
        row[0].markdown(
            f"""
            <div class="le-product-cell">
                {thumb_html}
                <div>
                    {title_html}
                    <div class="le-handle">{safe_handle}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        shopify_status_label = str(product.get("status") or "Missing").replace("_", " ").title()
        row[1].markdown(status_badge(shopify_status_label), unsafe_allow_html=True)
        edition_limit = row[2].number_input(
            "Edition limit",
            min_value=1,
            max_value=100000,
            value=int(product.get("edition_limit") or 100),
            step=1,
            key=f"le-limit-{item_key}",
            label_visibility="collapsed",
        )
        next_available = row[3].number_input(
            "Next edition",
            min_value=1,
            max_value=max(int(edition_limit) + 1, 2),
            value=min(max(int(product.get("next_available_edition") or 1), 1), max(int(edition_limit) + 1, 2)),
            step=1,
            key=f"le-next-{item_key}",
            label_visibility="collapsed",
        )
        editions_sold = row[4].number_input(
            "Sold",
            min_value=0,
            max_value=100000,
            value=int(product.get("editions_sold") or 0),
            step=1,
            key=f"le-sold-{item_key}",
            label_visibility="collapsed",
        )
        display_values = db.calculate_shopify_edition_values(
            edition_limit,
            next_available,
            editions_sold,
            allow_oversold=True,
        )
        row[5].write(format_optional_number(display_values["editions_remaining"]))
        row[6].markdown(status_badge(display_values["edition_status"]), unsafe_allow_html=True)
        psd_value = row[7].text_input(
            "PSD URL",
            value=product.get("psd_file_url") or "",
            key=f"le-psd-{item_key}",
            placeholder="PSD URL",
            label_visibility="collapsed",
        ).strip()
        if psd_value:
            row[7].link_button("Open PSD", psd_value, use_container_width=True)
        else:
            row[7].caption("Missing")
        last_updated = product.get("edition_updated_at") or product.get("updated_at") or product.get("last_shopify_sync_at")
        row[8].caption(format_updated_at(last_updated))
        if product.get("widget_sync_status") == "Needs Sync":
            row[8].markdown(status_badge("Needs Sync"), unsafe_allow_html=True)
        st.markdown('<div class="le-row-rule"></div>', unsafe_allow_html=True)

    pagination = st.columns([1, 2, 1])
    if pagination[0].button("Previous", disabled=current_page <= 1, use_container_width=True):
        st.session_state.limited_editions_page = max(current_page - 1, 1)
        st.rerun()
    pagination[1].markdown(
        f'<div class="le-range">Page {current_page} of {max_page} - {range_start}-{range_end} of {total_products}</div>',
        unsafe_allow_html=True,
    )
    if pagination[2].button("Next", disabled=current_page >= max_page, use_container_width=True):
        st.session_state.limited_editions_page = min(current_page + 1, max_page)
        st.rerun()


def _assignment_text(assignments):
    active = [
        item
        for item in assignments
        if item.get("assignment_status") not in {"Voided", "Refunded"}
    ]
    if not active:
        return "Needs Edition"
    numbers = sorted(int(item["edition_number"]) for item in active)
    limit = active[0].get("edition_limit") or active[0].get("edition_total") or 100
    if len(numbers) > 1 and numbers == list(range(numbers[0], numbers[-1] + 1)):
        return f"#{numbers[0]}-{numbers[-1]}/{limit}"
    return ", ".join(f"#{number}/{limit}" for number in numbers)


def _coerce_assignments(value):
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _order_assignment_summary(row):
    assignments = active_assignments(_coerce_assignments(row.get("assignments")))
    if assignments:
        count = len(assignments)
        assigned_at = assignments[-1].get("assigned_at")
        note = (
            f"{count} edition{'s' if count != 1 else ''} allocated"
            if count > 1
            else f"Assigned {format_updated_at(assigned_at)}" if assigned_at else "Edition allocated"
        )
        return {
            "assignments": assignments,
            "status": "Assigned",
            "label": _assignment_text(assignments),
            "note": note,
        }
    fallback_status = row.get("assignment_status") or "Needs Edition"
    fallback_note = row.get("last_error") or ""
    if fallback_status == supabase_backend.HISTORICAL_ORDER_STATUS and not fallback_note:
        fallback_note = supabase_backend.HISTORICAL_ORDER_NOTE
    return {
        "assignments": [],
        "status": fallback_status,
        "label": fallback_status,
        "note": fallback_note,
    }


def _clean_order_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _compact_text_list(values, *, empty="Not set", limit=2, separator=", "):
    unique_values = _unique_order_texts(values)
    if not unique_values:
        return empty
    if len(unique_values) <= limit:
        return separator.join(unique_values)
    return separator.join(unique_values[:limit]) + f" +{len(unique_values) - limit} more"


def _unique_order_texts(values):
    unique_values = []
    seen = set()
    for value in values or []:
        cleaned = _clean_order_text(value)
        if not cleaned:
            continue
        token = cleaned.casefold()
        if token in seen:
            continue
        seen.add(token)
        unique_values.append(cleaned)
    return unique_values


def _line_variant_summary(line_item):
    variant_text = _clean_order_text(line_item.get("variant_title"))
    if variant_text:
        return variant_text
    product_text = _clean_order_text(line_item.get("product_title"))
    return product_text or "Variant missing"


def _line_product_title(line_item):
    product_text = _clean_order_text(line_item.get("product_title"))
    if product_text:
        return product_text
    handle_text = _clean_order_text(line_item.get("shopify_handle"))
    if handle_text:
        return handle_text.replace("-", " ").title()
    return "Product missing"


def _line_product_title_with_quantity(line_item):
    product_text = _line_product_title(line_item)
    try:
        quantity = int(line_item.get("quantity") or 1)
    except (TypeError, ValueError):
        quantity = 1
    return f"{product_text} x{quantity}" if quantity > 1 else product_text


def _line_assignment_status(line_item):
    assignments = active_assignments(_coerce_assignments(line_item.get("assignments")))
    if assignments:
        return "Assigned"
    return _clean_order_text(line_item.get("assignment_status")) or "Needs Edition"


def _line_assignment_label(line_item):
    status = _line_assignment_status(line_item)
    if status == "Error":
        return "Needs Sync"
    if status == "Product Not Found":
        return "Product Not Found"
    if status == "Needs Edition Setup":
        return "Needs Edition"
    if status == "Sold Out":
        return "Sold Out Issue"
    if status == supabase_backend.HISTORICAL_ORDER_STATUS:
        return "Historical"
    return status


def _line_assignment_summary(line_item):
    assignments = active_assignments(_coerce_assignments(line_item.get("assignments")))
    if assignments:
        return _assignment_text(assignments)
    return _line_assignment_label(line_item)


def _line_edition_number_summary(line_item):
    assignments = active_assignments(_coerce_assignments(line_item.get("assignments")))
    if assignments:
        return _assignment_text(assignments)
    return _line_assignment_label(line_item)


def _order_psd_summary(line_items):
    urls = []
    seen = set()
    for line_item in line_items or []:
        url = _clean_order_text(line_item.get("psd_url") or line_item.get("psd_file_url"))
        if not url:
            continue
        token = url.casefold()
        if token in seen:
            continue
        seen.add(token)
        urls.append(url)
    if not urls:
        return {"url": "", "label": "No PSD", "title": "PSD folder missing"}
    if len(urls) == 1:
        return {"url": urls[0], "label": "Open PSD", "title": "Open PSD folder"}
    return {
        "url": urls[0],
        "label": f"PSD x{len(urls)}",
        "title": f"Open the first of {len(urls)} PSD links on this order",
    }


def _order_prodigi_summary(line_items):
    urls = []
    seen = set()
    for line_item in line_items or []:
        url = _clean_order_text(line_item.get("prodigi_url"))
        if not url:
            continue
        token = url.casefold()
        if token in seen:
            continue
        seen.add(token)
        urls.append(url)
    if not urls:
        return {"url": "", "label": "No Prodigi", "title": "Prodigi link missing"}
    if len(urls) == 1:
        return {"url": urls[0], "label": "Open Prodigi", "title": "Open Prodigi link"}
    return {
        "url": urls[0],
        "label": f"Prodigi x{len(urls)}",
        "title": f"Open the first of {len(urls)} Prodigi links on this order",
    }


def _jsonish(value):
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except Exception:
            return {}
    return {}


def _shipping_text_from_raw(raw_order):
    raw = _jsonish(raw_order)
    values = []

    def add(value):
        cleaned = _clean_order_text(value)
        if cleaned:
            values.append(cleaned)

    if isinstance(raw, dict):
        for key in ("shipping_title", "shipping_method", "shippingMethod", "shippingLine"):
            item = raw.get(key)
            if isinstance(item, dict):
                add(item.get("title") or item.get("code") or item.get("name"))
            else:
                add(item)
        shipping_lines = raw.get("shipping_lines") or raw.get("shippingLines") or raw.get("shippingRates")
        if not shipping_lines and isinstance(raw.get("raw_payload"), dict):
            nested_raw = raw["raw_payload"]
            add(nested_raw.get("shipping_title") or nested_raw.get("shipping_method"))
            shipping_lines = nested_raw.get("shipping_lines") or nested_raw.get("shippingLines")
        if isinstance(shipping_lines, dict):
            shipping_lines = shipping_lines.get("edges") or shipping_lines.get("nodes") or shipping_lines.get("items")
        if isinstance(shipping_lines, list):
            for item in shipping_lines:
                if isinstance(item, dict) and "node" in item and isinstance(item["node"], dict):
                    item = item["node"]
                if isinstance(item, dict):
                    add(item.get("title") or item.get("code") or item.get("name"))
                else:
                    add(item)
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                add(item.get("title") or item.get("code") or item.get("name"))
            else:
                add(item)
    return _compact_text_list(values, empty="", separator=" | ")


def _shipping_speed_label(order_row):
    raw_shipping = (
        order_row.get("shipping")
        or order_row.get("shipping_method")
        or order_row.get("shipping_title")
        or _shipping_text_from_raw(order_row.get("order_raw_json") or order_row.get("raw_json") or order_row.get("raw"))
    )
    shipping_text = _clean_order_text(raw_shipping)
    lowered = shipping_text.casefold()
    if "express" in lowered or "expedited" in lowered or "priority" in lowered:
        return "Express"
    if "standard" in lowered or "regular" in lowered or "economy" in lowered:
        return "Standard"
    return shipping_text or "-"


def _assignment_certificate_status(assignment):
    status = _clean_order_text(assignment.get("certificate_status"))
    has_r2 = bool(assignment.get("certificate_r2_bucket") and assignment.get("certificate_r2_key"))
    has_remote = bool(assignment.get("shopify_file_url"))
    local_path = _clean_order_text(assignment.get("local_file_path") or assignment.get("certificate_pdf_path"))
    if "error" in status.casefold():
        return "Error"
    if "regeneration" in status.casefold():
        return "Needs regeneration"
    if has_r2 or has_remote:
        return "Generated"
    if local_path:
        return "Generated" if Path(local_path).exists() else "Missing file"
    if status in {"Certificate Ready", "Generated"}:
        return "Missing file"
    return "Not generated"


def _order_financial_status(order_summary):
    line_items = order_summary.get("line_items") or []
    for line_item in line_items:
        if _line_assignment_status(line_item) in {"Error", "Product Not Found", "Needs Edition Setup", "Sold Out"}:
            return "Error"
    if _clean_order_text(order_summary.get("cancelled_at")):
        return "Cancelled / Refunded"
    financial_status = _clean_order_text(order_summary.get("financial_status") or "").upper()
    if "REFUND" in financial_status or "VOID" in financial_status:
        return "Cancelled / Refunded"
    fulfillment_status = _clean_order_text(order_summary.get("fulfillment_status") or "").upper()
    if "FULFILLED" in fulfillment_status and "UNFULFILLED" not in fulfillment_status:
        return "Fulfilled"
    if any(
        _line_assignment_status(item) in {"Needs Edition", "Product Not Found", "Needs Edition Setup"}
        for item in line_items
    ):
        return "Needs Sync"
    if any(active_assignments(_coerce_assignments(item.get("assignments"))) for item in line_items):
        return "Assigned"
    if financial_status in {"PAID", "PARTIALLY_PAID"} and fulfillment_status in {"UNFULFILLED", "PARTIALLY_FULFILLED", ""}:
        return "Paid / Unfulfilled"
    return "Saved"


def _r2_temporary_url(bucket, key):
    if not bucket or not key:
        return ""
    try:
        return r2_storage.generate_presigned_download_url(bucket, key) or ""
    except Exception:
        return ""


def _order_assignments_for_certificates(order_summary):
    assignments = []
    for line_item in order_summary.get("line_items") or []:
        for assignment in active_assignments(_coerce_assignments(line_item.get("assignments"))):
            if not assignment.get("edition_order_id") and not assignment.get("id"):
                continue
            merged = dict(assignment)
            merged.setdefault("product_title", line_item.get("product_title"))
            merged.setdefault("variant_title", line_item.get("variant_title"))
            merged.setdefault("shopify_handle", line_item.get("shopify_handle"))
            assignments.append(merged)
    return assignments


def _overall_order_status(line_items):
    statuses = [_line_assignment_status(item) for item in (line_items or [])]
    if not statuses:
        return "Needs Edition"
    has_assigned = "Assigned" in statuses
    for candidate in ("Error", "Product Not Found", "Needs Edition Setup", "Sold Out", "Needs Edition"):
        if candidate in statuses:
            return "Partially Assigned" if has_assigned else candidate
    if supabase_backend.HISTORICAL_ORDER_STATUS in statuses:
        return "Partially Assigned" if has_assigned else supabase_backend.HISTORICAL_ORDER_STATUS
    return "Assigned" if has_assigned else statuses[0]


def _build_compact_order_summary(order_row, line_items):
    normalized_items = []
    for item in line_items or []:
        line_copy = dict(item)
        line_copy["assignments"] = active_assignments(_coerce_assignments(line_copy.get("assignments")))
        normalized_items.append(line_copy)
    product_items = _unique_order_texts(_line_product_title_with_quantity(item) for item in normalized_items)
    edition_number_items = _unique_order_texts(_line_edition_number_summary(item) for item in normalized_items)
    assigned_numbers = sorted(
        int(assignment["edition_number"])
        for item in normalized_items
        for assignment in item.get("assignments") or []
        if assignment.get("edition_number") not in (None, "")
    )
    summary = {
        "order_key": str(order_row.get("shopify_order_id") or order_row.get("order_name") or ""),
        "order_label": order_row.get("order_name") or order_row.get("order_number") or "Order",
        "order_number": _clean_order_text(order_row.get("order_number")),
        "order_link": str(order_row.get("admin_url") or "").strip(),
        "customer_name": customer_display_name(order_row.get("customer_name")),
        "customer_email": _clean_order_text(order_row.get("customer_email")),
        "order_date": format_order_date(order_row.get("created_at") or order_row.get("processed_at")),
        "created_at": order_row.get("created_at") or "",
        "processed_at": order_row.get("processed_at") or "",
        "remote_updated_at": order_row.get("remote_updated_at") or "",
        "synced_at": order_row.get("synced_at") or "",
        "financial_status": _clean_order_text(order_row.get("financial_status")),
        "fulfillment_status": _clean_order_text(order_row.get("fulfillment_status")),
        "total_price": _clean_order_text(order_row.get("total_price")),
        "currency": _clean_order_text(order_row.get("currency")),
        "cancelled_at": order_row.get("cancelled_at") or "",
        "shipping_summary": _shipping_speed_label(order_row),
        "product_summary": _compact_text_list(
            product_items,
            empty="Product missing",
            separator=" | ",
        ),
        "product_items": product_items,
        "variant_summary": _compact_text_list(
            [_line_variant_summary(item) for item in normalized_items],
            empty="Variant missing",
            separator=" | ",
        ),
        "edition_summary": _compact_text_list(
            edition_number_items,
            empty="Needs Edition",
            separator=" | ",
        ),
        "edition_number_items": edition_number_items,
        "first_edition_number": assigned_numbers[0] if assigned_numbers else None,
        "status": _overall_order_status(normalized_items),
        "status_label": "",
        "psd": _order_psd_summary(normalized_items),
        "prodigi": _order_prodigi_summary(normalized_items),
        "line_items": normalized_items,
    }
    summary["status_label"] = _order_financial_status(summary)
    return summary


def _group_supabase_order_rows(rows):
    grouped_orders = {}
    for row in rows or []:
        order_id = str(row.get("shopify_order_id") or row.get("order_name") or len(grouped_orders))
        if order_id not in grouped_orders:
            grouped_orders[order_id] = {"order": dict(row), "line_items": []}
        if row.get("order_line_id") or row.get("shopify_line_item_id") or row.get("product_title"):
            grouped_orders[order_id]["line_items"].append(dict(row))
    return [
        _build_compact_order_summary(payload["order"], payload["line_items"])
        for payload in grouped_orders.values()
    ]


def _filter_limited_products(products, search):
    query = str(search or "").strip().casefold()
    if not query:
        return list(products or [])
    return [
        product
        for product in products or []
        if query in str(product.get("product_title") or "").casefold()
        or query in str(product.get("shopify_handle") or "").casefold()
    ]


def _parse_order_sort_datetime(value):
    raw = str(value or "").strip()
    if not raw:
        return datetime.min.replace(tzinfo=timezone.utc)
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _order_summary_matches_search(order_summary, search):
    query = str(search or "").strip().casefold()
    if not query:
        return True
    direct_values = (
        order_summary.get("order_label"),
        order_summary.get("order_number"),
        order_summary.get("customer_name"),
        order_summary.get("customer_email"),
        order_summary.get("product_summary"),
        order_summary.get("variant_summary"),
        order_summary.get("edition_summary"),
        order_summary.get("shipping_summary"),
    )
    for value in direct_values:
        if query in _clean_order_text(value).casefold():
            return True
    for line_item in order_summary.get("line_items") or []:
        line_values = (
            line_item.get("product_title"),
            line_item.get("variant_title"),
            line_item.get("sku"),
            line_item.get("shopify_handle"),
            line_item.get("assignment_status"),
            line_item.get("last_error"),
            _line_assignment_summary(line_item),
        )
        for value in line_values:
            if query in _clean_order_text(value).casefold():
                return True
        for assignment in active_assignments(_coerce_assignments(line_item.get("assignments"))):
            if query in _clean_order_text(assignment.get("edition_number")).casefold():
                return True
    return False


def _order_summary_is_paid_unfulfilled(order_summary):
    if _clean_order_text(order_summary.get("cancelled_at")):
        return False
    financial_status = _clean_order_text(order_summary.get("financial_status") or "").upper()
    fulfillment_status = _clean_order_text(order_summary.get("fulfillment_status") or "").upper()
    return financial_status in {"PAID", "PARTIALLY_PAID"} and fulfillment_status in {
        "UNFULFILLED",
        "PARTIALLY_FULFILLED",
        "",
    }


def _order_summary_has_line_status(order_summary, statuses):
    status_set = set(statuses or ())
    return any(_line_assignment_status(item) in status_set for item in order_summary.get("line_items") or [])


def _order_summary_certificate_needed(order_summary):
    assignments = _order_assignments_for_certificates(order_summary)
    if not assignments:
        return False
    return any(_assignment_certificate_status(assignment) != "Generated" for assignment in assignments)


def _order_summary_missing_asset(order_summary, asset_key):
    asset = order_summary.get(asset_key) or {}
    return not str(asset.get("url") or "").strip()


def _order_summary_needs_sports_cave_action(order_summary):
    if not _order_summary_is_paid_unfulfilled(order_summary):
        return False
    if _order_summary_has_line_status(
        order_summary,
        {"Needs Edition", "Product Not Found", "Needs Edition Setup", "Sold Out", "Error"},
    ):
        return True
    return (
        _order_summary_certificate_needed(order_summary)
        or _order_summary_missing_asset(order_summary, "psd")
        or _order_summary_missing_asset(order_summary, "prodigi")
    )


def _order_summary_matches_status(order_summary, status_filter):
    selected = str(status_filter or "Needs Action").strip()
    if selected == "All Saved Orders":
        return True
    if selected == "Needs Action":
        return _order_summary_needs_sports_cave_action(order_summary)
    if selected == "Paid + Unfulfilled":
        return _order_summary_is_paid_unfulfilled(order_summary)
    if selected == "Needs Edition":
        return _order_summary_is_paid_unfulfilled(order_summary) and _order_summary_has_line_status(
            order_summary,
            {"Needs Edition", "Needs Edition Setup", "Error"},
        )
    if selected == "Certificate Needed":
        return _order_summary_is_paid_unfulfilled(order_summary) and _order_summary_certificate_needed(order_summary)
    if selected == "Product Missing":
        return _order_summary_is_paid_unfulfilled(order_summary) and _order_summary_has_line_status(
            order_summary,
            {"Product Not Found", "Needs Edition Setup"},
        )
    if selected == "Sold Out Issue":
        return _order_summary_is_paid_unfulfilled(order_summary) and _order_summary_has_line_status(
            order_summary,
            {"Sold Out"},
        )
    if selected == "Assigned":
        return any(
            active_assignments(_coerce_assignments(line_item.get("assignments")))
            for line_item in order_summary.get("line_items") or []
        )
    if selected == "Fulfilled":
        fulfillment_status = _clean_order_text(order_summary.get("fulfillment_status")).casefold()
        return "fulfilled" in fulfillment_status and "unfulfilled" not in fulfillment_status
    if selected == "Cancelled / Refunded":
        return bool(order_summary.get("cancelled_at")) or any(
            token in _order_financial_status(order_summary).casefold()
            for token in ("refund", "refunded", "void", "cancel")
        )
    if selected == "Errors":
        return _order_summary_has_line_status(
            order_summary,
            {"Error", "Product Not Found", "Needs Edition Setup", "Sold Out"},
        )
    return True


def _sort_supabase_order_summaries(order_summaries, sort):
    selected = str(sort or "Date newest").strip()
    rows = list(order_summaries or [])
    if selected == "Date oldest":
        return sorted(
            rows,
            key=lambda item: (_parse_order_sort_datetime(item.get("created_at") or item.get("processed_at")), item.get("order_label") or ""),
        )
    if selected == "Shopify updated":
        return sorted(
            rows,
            key=lambda item: (_parse_order_sort_datetime(item.get("remote_updated_at") or item.get("created_at") or item.get("synced_at")), item.get("order_label") or ""),
            reverse=True,
        )
    if selected == "Customer":
        return sorted(
            rows,
            key=lambda item: (
                _clean_order_text(item.get("customer_name")).casefold() or "~",
                _parse_order_sort_datetime(item.get("created_at") or item.get("processed_at")),
            ),
        )
    if selected == "Edition number":
        return sorted(
            rows,
            key=lambda item: (
                item.get("first_edition_number") is None,
                item.get("first_edition_number") or 0,
                item.get("order_label") or "",
            ),
        )
    return sorted(
        rows,
        key=lambda item: (_parse_order_sort_datetime(item.get("created_at") or item.get("processed_at")), item.get("order_label") or ""),
        reverse=True,
    )


def _filter_supabase_order_summaries(order_summaries, *, search, sort, status_filter, page_size):
    filtered = [
        order_summary
        for order_summary in order_summaries or []
        if _order_summary_matches_search(order_summary, search)
        and _order_summary_matches_status(order_summary, status_filter)
    ]
    return _sort_supabase_order_summaries(filtered, sort)


def _build_local_order_summaries(orders):
    summaries = []
    for order in orders or []:
        summaries.append(_build_compact_order_summary(order, order.get("line_items") or []))
    return summaries


def _orders_page_styles():
    return """
    <style>
    .sc-orders-section-label {
        color: rgba(255, 255, 255, 0.72);
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        margin: 0.15rem 0 0.55rem;
        text-transform: uppercase;
    }
    .sc-order-feed-shell {
        background: #FFFFFF;
        border: 1px solid #D9DEE5;
        border-radius: 22px;
        box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
        overflow-x: auto;
        padding: 0.55rem 1rem 0.35rem;
    }
    .sc-order-feed-table {
        min-width: 1160px;
    }
    .sc-order-feed-head,
    .sc-order-feed-row {
        display: grid;
        grid-template-columns: minmax(110px, 0.72fr) minmax(165px, 1fr) minmax(300px, 1.7fr) minmax(180px, 0.95fr) minmax(230px, 1.2fr) minmax(92px, 0.5fr);
        gap: 0.7rem;
    }
    .sc-order-feed-head {
        margin-bottom: 0.35rem;
        padding: 0.2rem 0 0.55rem;
        border-bottom: 1px solid #E5E7EB;
    }
    .sc-order-feed-head div {
        color: #5B6472;
        font-size: 0.74rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }
    .sc-order-feed-row {
        align-items: center;
        border-bottom: 1px solid #ECEFF3;
        padding: 0.78rem 0;
    }
    .sc-order-feed-row:hover {
        background: #F8FAFC;
    }
    .sc-order-feed-row:last-child {
        border-bottom: 0;
    }
    .sc-order-feed-cell {
        min-width: 0;
    }
    .sc-order-feed-value {
        color: #111827;
        font-size: 0.93rem;
        font-weight: 660;
        line-height: 1.25;
        overflow-wrap: anywhere;
        white-space: normal;
    }
    .sc-order-feed-link {
        color: #0A66C2;
        font-weight: 800;
        text-decoration: none;
    }
    .sc-order-feed-link:hover {
        color: #084C92;
        text-decoration: none;
    }
    .sc-order-feed-product {
        color: #111827;
        font-weight: 760;
    }
    .sc-order-feed-edition-cell {
        display: flex;
        flex-wrap: wrap;
        gap: 0.36rem;
    }
    .sc-order-edition-chip {
        align-items: center;
        background: #EEF4FF;
        border: 1px solid #C9D8F4;
        border-radius: 999px;
        color: #163D73;
        display: inline-flex;
        font-size: 0.92rem;
        font-variant-numeric: tabular-nums;
        font-weight: 820;
        letter-spacing: 0.01em;
        line-height: 1.15;
        min-height: 34px;
        padding: 0.2rem 0.72rem;
        white-space: nowrap;
    }
    .sc-order-edition-chip-pending {
        background: #FFF5D6;
        border-color: #F0D27A;
        color: #6A4B00;
    }
    .sc-order-edition-chip-issue {
        background: #FFE8E8;
        border-color: #EAB4B4;
        color: #8B2323;
    }
    .sc-order-edition-chip-historical {
        background: #EEF2F6;
        border-color: #D5DCE3;
        color: #4B5563;
    }
    .sc-order-feed-action {
        align-items: center;
        background: #111827;
        border: 1px solid #111827;
        border-radius: 999px;
        color: #FFFFFF;
        display: inline-flex;
        font-size: 0.76rem;
        font-weight: 700;
        justify-content: center;
        min-height: 30px;
        padding: 0.05rem 0.72rem;
        text-decoration: none;
        white-space: nowrap;
    }
    .sc-order-feed-action:hover {
        background: #1F2937;
        color: #FFFFFF;
        text-decoration: none;
    }
    .sc-order-feed-action-disabled {
        background: #F3F4F6;
        border-color: #D1D5DB;
        color: #6B7280;
        opacity: 1;
        pointer-events: none;
    }
    @media (max-width: 900px) {
        .sc-order-feed-table {
            min-width: 1040px;
        }
        .sc-order-feed-head,
        .sc-order-feed-row {
            gap: 0.55rem;
        }
        .sc-order-feed-head div {
            font-size: 0.68rem;
        }
        .sc-order-feed-value {
            font-size: 0.88rem;
        }
    }
    @media (max-width: 560px) {
        .sc-order-feed-table {
            min-width: 980px;
        }
        .sc-order-feed-head,
        .sc-order-feed-row {
            gap: 0.45rem;
        }
        .sc-order-feed-row {
            padding: 0.55rem 0;
        }
        .sc-order-feed-value {
            font-size: 0.84rem;
        }
    }
    .sc-status {
        background: #F6F7F8;
        border-color: rgba(201, 204, 207, 0.95);
        color: #202223;
    }
    .sc-status-unfulfilled,
    .sc-status-partially-assigned {
        background: #FFF1B8;
        border-color: #E3C75F;
        color: #5E4A00;
    }
    .sc-status-assigned,
    .sc-status-paid {
        background: #E3F1DF;
        border-color: #95C99C;
        color: #166042;
    }
    .sc-status-needs-edition,
    .sc-status-product-not-found,
    .sc-status-sold-out,
    .sc-status-prodigi-missing,
    .sc-status-missing,
    .sc-status-historical-order,
    .sc-status-error,
    .sc-status-certificate-missing {
        background: #FFF1F1;
        border-color: #E2A8A8;
        color: #A53F3F;
    }
    </style>
    """


def _edition_chip_class(value):
    normalized = _clean_order_text(value).casefold()
    if normalized.startswith("#"):
        return "sc-order-edition-chip"
    if "historical" in normalized:
        return "sc-order-edition-chip sc-order-edition-chip-historical"
    if "needs edition" in normalized:
        return "sc-order-edition-chip sc-order-edition-chip-pending"
    return "sc-order-edition-chip sc-order-edition-chip-issue"


def _order_widget_token(value):
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "row")).strip("-") or "row"


def _certificate_row_label(assignments):
    if not assignments:
        return "Needs edition"
    statuses = [_assignment_certificate_status(assignment) for assignment in assignments]
    if all(status == "Generated" for status in statuses):
        return "Open cert" if len(assignments) == 1 else f"{len(assignments)} certs"
    if any(status == "Error" for status in statuses):
        return "Cert error"
    if any(status == "Missing file" for status in statuses):
        return "Missing file"
    return "Generate"


def _render_certificate_popover(order_summary, key_prefix):
    assignments = _order_assignments_for_certificates(order_summary)
    if not assignments:
        st.markdown('<span class="sc-order-muted-pill">Needs edition</span>', unsafe_allow_html=True)
        return

    with st.popover(_certificate_row_label(assignments), use_container_width=True):
        for index, assignment in enumerate(assignments, start=1):
            edition_order_id = assignment.get("edition_order_id") or assignment.get("id")
            key_id = _order_widget_token(edition_order_id)
            edition_label = f"#{assignment.get('edition_number')}/{assignment.get('edition_total') or 100}"
            product_label = assignment.get("product_title") or order_summary.get("product_summary") or "Product"
            st.markdown(f"**{edition_label}**")
            st.caption(product_label)
            status_label = _assignment_certificate_status(assignment)
            st.markdown(status_badge(status_label), unsafe_allow_html=True)

            button_columns = st.columns(2)
            generate_label = "Regenerate" if status_label == "Generated" else "Generate"
            if button_columns[0].button(
                generate_label,
                key=f"{key_prefix}-cert-generate-{key_id}-{index}",
                use_container_width=True,
            ):
                try:
                    if assignment.get("edition_order_id"):
                        supabase_backend.generate_certificate_for_edition_order(
                            assignment["edition_order_id"],
                            force=True,
                        )
                        st.session_state.supabase_orders_notice = f"Certificate generated for {edition_label}."
                    else:
                        generate_certificate_pdf(edition_order_id)
                        st.session_state.orders_notice = f"Certificate generated for {edition_label}."
                    st.rerun()
                except Exception as error:
                    st.error("Could not generate certificate.")
                    supabase_backend.log_app_error(
                        "orders_certificate_generate_failed",
                        str(error),
                        {"source": "orders_page", "edition_order_id": edition_order_id},
                    )

            preview_url = _r2_temporary_url(
                assignment.get("certificate_preview_r2_bucket"),
                assignment.get("certificate_preview_r2_key"),
            )
            if preview_url:
                button_columns[1].link_button("Preview", preview_url, use_container_width=True)

            pdf_url = (
                _r2_temporary_url(assignment.get("certificate_r2_bucket"), assignment.get("certificate_r2_key"))
                or str(assignment.get("shopify_file_url") or "").strip()
            )
            local_path_text = str(assignment.get("local_file_path") or assignment.get("certificate_pdf_path") or "").strip()
            local_path = Path(local_path_text) if local_path_text else None
            if pdf_url:
                st.link_button("Open Certificate", pdf_url, use_container_width=True)
            elif local_path and local_path.exists() and local_path.is_file():
                st.download_button(
                    "Download Certificate",
                    data=local_path.read_bytes(),
                    file_name=local_path.name,
                    mime="application/pdf",
                    key=f"{key_prefix}-cert-download-{key_id}-{index}",
                    use_container_width=True,
                )
            elif status_label == "Missing file":
                st.warning("Certificate row exists, but the file is missing.")


def _render_compact_orders_feed(order_summaries):
    st.markdown(
        """
        <style>
        div[data-testid="stHorizontalBlock"]:has(.sc-order-header-marker) {
            background: #FFFFFF;
            border: 1px solid #D9DEE5;
            border-bottom: 0;
            border-radius: 20px 20px 0 0;
            gap: 0.5rem !important;
            margin: 0 !important;
            padding: 0.56rem 0.78rem 0.42rem;
        }
        div[data-testid="stHorizontalBlock"]:has(.sc-order-row-marker) {
            background: #FFFFFF;
            border-left: 1px solid #D9DEE5;
            border-right: 1px solid #D9DEE5;
            border-bottom: 1px solid #E5E7EB;
            gap: 0.5rem !important;
            margin: 0 !important;
            min-height: 0 !important;
            padding: 0.42rem 0.78rem;
        }
        div[data-testid="stHorizontalBlock"]:has(.sc-order-header-marker) > div,
        div[data-testid="stHorizontalBlock"]:has(.sc-order-row-marker) > div {
            min-width: 0 !important;
        }
        div[data-testid="stElementContainer"]:has(.sc-order-header-marker),
        div[data-testid="stElementContainer"]:has(.sc-order-row-marker),
        div[data-testid="stElementContainer"]:has(.sc-order-stream-cell),
        div[data-testid="stElementContainer"]:has(.sc-order-edition-chip),
        div[data-testid="stElementContainer"]:has(.sc-order-link-pill),
        div[data-testid="stElementContainer"]:has(.sc-order-muted-pill) {
            margin-bottom: 0 !important;
        }
        div[data-testid="stHorizontalBlock"]:has(.sc-order-row-marker):last-of-type {
            border-radius: 0 0 20px 20px;
        }
        div[data-testid="stHorizontalBlock"]:has(.sc-order-row-marker) button,
        div[data-testid="stHorizontalBlock"]:has(.sc-order-row-marker) a {
            color: #111827 !important;
            font-weight: 800 !important;
            min-height: 2.05rem !important;
            padding: 0.18rem 0.55rem !important;
            white-space: nowrap !important;
        }
        div[data-testid="stHorizontalBlock"]:has(.sc-order-row-marker) button:disabled {
            color: #111827 !important;
            opacity: 1 !important;
        }
        div[data-testid="stHorizontalBlock"]:has(.sc-order-row-marker) a.sc-order-link-pill {
            color: #FFFFFF !important;
            min-height: 1.9rem !important;
            padding: 0.14rem 0.56rem !important;
        }
        .sc-order-stream-header {
            color: #5B6472;
            font-size: 0.68rem;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }
        .sc-order-stream-cell {
            color: #111827;
            font-size: 0.82rem;
            font-weight: 760;
            line-height: 1.18;
            overflow-wrap: anywhere;
        }
        .sc-order-status-pill {
            align-items: center;
            border-radius: 999px;
            display: inline-flex;
            font-size: 0.7rem;
            font-weight: 820;
            line-height: 1;
            min-height: 1.85rem;
            padding: 0.16rem 0.58rem;
            white-space: nowrap;
        }
        .sc-order-status-paid-unfulfilled {
            background: #FFF7E6;
            border: 1px solid #F2C66D;
            color: #8A5B00;
        }
        .sc-order-status-needs-edition {
            background: #FEF2F2;
            border: 1px solid #F5A8A8;
            color: #991B1B;
        }
        .sc-order-status-assigned {
            background: #ECFDF3;
            border: 1px solid #86E0A3;
            color: #166534;
        }
        .sc-order-status-fulfilled {
            background: #EFF6FF;
            border: 1px solid #93C5FD;
            color: #1D4ED8;
        }
        .sc-order-status-cancelled-refunded,
        .sc-order-status-saved {
            background: #F3F4F6;
            border: 1px solid #D1D5DB;
            color: #374151;
        }
        .sc-order-status-error {
            background: #111827;
            border: 1px solid #111827;
            color: #FFFFFF;
        }
        .sc-order-row-marker,
        .sc-order-header-marker {
            display: none;
        }
        .sc-order-link-pill,
        .sc-order-muted-pill {
            align-items: center;
            border-radius: 999px;
            display: inline-flex;
            font-size: 0.72rem;
            font-weight: 820;
            min-height: 1.9rem;
            padding: 0.14rem 0.56rem;
            text-decoration: none !important;
            white-space: nowrap;
        }
        .sc-order-link-pill {
            background: #111827;
            border: 1px solid #111827;
            color: #FFFFFF !important;
        }
        .sc-order-muted-pill {
            background: #F3F4F6;
            border: 1px solid #D1D5DB;
            color: #111827 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    header = st.columns([0.72, 0.74, 0.96, 1.44, 1.12, 0.82, 0.86, 0.62, 0.66, 0.82], gap="small")
    for column, label in zip(
        header,
        ("Order", "Date", "Customer", "Product", "Variant", "Edition", "Certificate", "PSD", "Prodigi", "Status"),
    ):
        marker = '<span class="sc-order-header-marker"></span>' if label == "Order" else ""
        column.markdown(f'{marker}<div class="sc-order-stream-header">{label}</div>', unsafe_allow_html=True)
    for index, item in enumerate(order_summaries or []):
        key_prefix = f"orders-row-{index}-{_order_widget_token(item.get('order_key') or index)}"
        columns = st.columns([0.72, 0.74, 0.96, 1.44, 1.12, 0.82, 0.86, 0.62, 0.66, 0.82], gap="small")
        order_label = html.escape(str(item.get("order_label") or "Order"))
        columns[0].markdown(
            f'<span class="sc-order-row-marker"></span><div class="sc-order-stream-cell">{order_label}</div>',
            unsafe_allow_html=True,
        )
        columns[1].markdown(
            f'<div class="sc-order-stream-cell">{html.escape(str(item.get("order_date") or "-"))}</div>',
            unsafe_allow_html=True,
        )
        columns[2].markdown(
            f'<div class="sc-order-stream-cell">{html.escape(str(item.get("customer_name") or "Customer missing"))}</div>',
            unsafe_allow_html=True,
        )
        columns[3].markdown(
            f'<div class="sc-order-stream-cell">{html.escape(str(item.get("product_summary") or "Product missing"))}</div>',
            unsafe_allow_html=True,
        )
        columns[4].markdown(
            f'<div class="sc-order-stream-cell">{html.escape(str(item.get("variant_summary") or "Variant missing"))}</div>',
            unsafe_allow_html=True,
        )
        with columns[5]:
            for edition_value in item.get("edition_number_items") or [item.get("edition_summary") or "Needs Edition"]:
                st.markdown(
                    f'<span class="{_edition_chip_class(edition_value)}">{html.escape(str(edition_value))}</span>',
                    unsafe_allow_html=True,
                )
        psd = item.get("psd") or {}
        psd_url = str(psd.get("url") or "").strip()
        prodigi = item.get("prodigi") or {}
        prodigi_url = str(prodigi.get("url") or "").strip()
        with columns[6]:
            _render_certificate_popover(item, key_prefix)
        if psd_url:
            columns[7].markdown(
                f'<a class="sc-order-link-pill" href="{html.escape(psd_url, quote=True)}" target="_blank" rel="noreferrer">{html.escape(str(psd.get("label") or "PSD"))}</a>',
                unsafe_allow_html=True,
            )
        else:
            columns[7].markdown('<span class="sc-order-muted-pill">No PSD</span>', unsafe_allow_html=True)
        if prodigi_url:
            columns[8].markdown(
                f'<a class="sc-order-link-pill" href="{html.escape(prodigi_url, quote=True)}" target="_blank" rel="noreferrer">{html.escape(str(prodigi.get("label") or "Prodigi"))}</a>',
                unsafe_allow_html=True,
            )
        else:
            columns[8].markdown('<span class="sc-order-muted-pill">No Prodigi</span>', unsafe_allow_html=True)
        status_label = str(item.get("status_label") or "Saved")
        status_class = re.sub(r"[^a-z0-9]+", "-", status_label.lower()).strip("-")
        columns[9].markdown(
            f'<span class="sc-order-status-pill sc-order-status-{status_class}">{html.escape(status_label)}</span>',
            unsafe_allow_html=True,
        )


def _cached_order_item_count(order_summary):
    total = 0
    for line_item in order_summary.get("line_items") or []:
        total += max(1, int(line_item.get("quantity") or 1))
    return total


def _cached_order_assignment_badge(order_summary):
    line_items = order_summary.get("line_items") or []
    assigned_count = sum(
        len(active_assignments(_coerce_assignments(line_item.get("assignments"))))
        for line_item in line_items
    )
    issue_statuses = {_line_assignment_status(line_item) for line_item in line_items}
    total_items = _cached_order_item_count(order_summary)
    pending_count = max(total_items - assigned_count, 0)
    if "Product Not Found" in issue_statuses:
        return {"label": "Product not found", "class_name": "product-not-found"}
    if "Sold Out" in issue_statuses:
        return {"label": "Sold out issue", "class_name": "sold-out-issue"}
    if assigned_count and pending_count == 0:
        return {"label": f"Editions assigned x{assigned_count}", "class_name": "assigned"}
    if "Error" in issue_statuses or "Needs Edition Setup" in issue_statuses:
        return {
            "label": f"Needs Sports Cave sync x{max(pending_count, 1)}",
            "class_name": "needs-sync",
        }
    if pending_count:
        return {
            "label": f"Needs Sports Cave sync x{pending_count}",
            "class_name": "needs-sync",
        }
    return {"label": "Needs Sports Cave sync", "class_name": "needs-sync"}


def _cached_order_delivery_label(order_summary):
    fulfillment = _humanize_shopify_status_text(order_summary.get("fulfillment_status"), "Unknown")
    normalized = str(order_summary.get("fulfillment_status") or "").upper()
    if "UNFULFILLED" in normalized:
        return "Unfulfilled"
    if "PARTIALLY" in normalized:
        return "Partial"
    if "FULFILLED" in normalized:
        return "Fulfilled"
    return fulfillment


def _cached_order_badge_slug(value):
    normalized = str(value or "").strip().lower()
    if "unfulfilled" in normalized:
        return "unfulfilled"
    if "partial" in normalized:
        return "partial"
    if "paid" == normalized:
        return "paid"
    if "pending" in normalized:
        return "pending"
    if "refund" in normalized or "void" in normalized or "cancel" in normalized:
        return "refunded"
    if "fulfilled" in normalized:
        return "fulfilled"
    return "unknown"


def _badge_color_for_status(value):
    slug = _cached_order_badge_slug(value)
    if slug == "unfulfilled":
        return "yellow"
    if slug in {"fulfilled", "paid"}:
        return "green"
    if slug == "partial":
        return "orange"
    if slug == "refunded":
        return "red"
    return "gray"


def _badge_color_for_assignment(class_name):
    value = str(class_name or "")
    if value == "assigned":
        return "green"
    if value in {"product-not-found", "sold-out-issue"}:
        return "red"
    return "yellow"


def _badge_color_for_edition(value):
    normalized = _clean_order_text(value).casefold()
    if normalized.startswith("#") or normalized.startswith("edition"):
        return "green"
    if "historical" in normalized:
        return "gray"
    if "sold out" in normalized or "error" in normalized or "not found" in normalized:
        return "red"
    return "yellow"


def _badge_color_for_certificate(label):
    normalized = _clean_order_text(label).casefold()
    if "open" in normalized or "cert" in normalized and "missing" not in normalized and "needs" not in normalized:
        return "green"
    if "missing" in normalized or "error" in normalized:
        return "red"
    return "yellow"


def _render_muted_text(value, fallback=""):
    cleaned = str(value or fallback or "").strip()
    if cleaned:
        st.caption(cleaned)


def _certificate_pdf_url(assignment):
    return (
        _r2_temporary_url(assignment.get("certificate_r2_bucket"), assignment.get("certificate_r2_key"))
        or str(assignment.get("shopify_file_url") or "").strip()
    )


def _render_certificate_action_cell(order_summary, key_prefix):
    assignments = _order_assignments_for_certificates(order_summary)
    if not assignments:
        st.badge("Needs Edition", color="yellow")
        return

    statuses = [_assignment_certificate_status(assignment) for assignment in assignments]
    pdf_url = next((_certificate_pdf_url(assignment) for assignment in assignments if _certificate_pdf_url(assignment)), "")
    if all(status == "Generated" for status in statuses):
        if pdf_url:
            st.link_button("Open PDF", pdf_url, use_container_width=True)
        else:
            st.badge("Open PDF", color="green")
            st.caption("Saved locally")
        return

    if any(status == "Error" for status in statuses):
        st.badge("Error", color="red")
        return

    if st.button("Generate PDF", key=f"{key_prefix}-generate-pdf", use_container_width=True):
        generated_count = 0
        try:
            for assignment in assignments:
                edition_order_id = assignment.get("edition_order_id") or assignment.get("id")
                if not edition_order_id:
                    continue
                supabase_backend.generate_certificate_for_edition_order(
                    edition_order_id,
                    force=_assignment_certificate_status(assignment) == "Missing file",
                )
                generated_count += 1
            if generated_count:
                st.session_state.supabase_orders_notice = (
                    f"Generated {generated_count} certificate PDF"
                    f"{'s' if generated_count != 1 else ''}."
                )
                bump_supabase_cache_version("orders", "order-summary")
                st.rerun()
            st.warning("No edition assignment was available for certificate generation.")
        except Exception as error:
            st.error("Could not generate PDF.")
            supabase_backend.log_app_error(
                "orders_certificate_generate_failed",
                str(error),
                {"source": "orders_page", "order": order_summary.get("order_label")},
            )


def _badge_color_for_helper_status(value):
    normalized = _clean_order_text(value).casefold()
    if "error" in normalized or "cancel" in normalized or "refund" in normalized:
        return "red"
    if "needs" in normalized or "unfulfilled" in normalized:
        return "yellow"
    if "assigned" in normalized or "fulfilled" in normalized or normalized == "paid":
        return "green"
    return "gray"


def _render_shopify_style_cached_orders_table(order_summaries):
    header_labels = (
        "Order",
        "Customer",
        "Product",
        "Variant",
        "Edition",
        "Certificate",
        "PSD",
        "Prodigi",
        "Shopify",
    )
    widths = [0.9, 1.15, 1.75, 1.15, 0.95, 0.95, 0.75, 0.85, 1.05]

    with st.container(border=True):
        header = st.columns(widths, gap="small", vertical_alignment="center")
        for column, label in zip(header, header_labels):
            column.caption(label)

        for index, order_summary in enumerate(order_summaries or []):
            key_prefix = f"cached-order-{index}-{_order_widget_token(order_summary.get('order_key') or index)}"
            columns = st.columns(widths, gap="small", vertical_alignment="center")

            order_link = str(order_summary.get("order_link") or "").strip()
            order_label = str(order_summary.get("order_label") or "Order").strip()
            with columns[0]:
                if order_link:
                    st.link_button(order_label, order_link, use_container_width=True)
                else:
                    st.write(f"**{order_label}**")
                _render_muted_text(order_summary.get("order_date"), "")

            with columns[1]:
                st.write(str(order_summary.get("customer_name") or "Customer missing"))
                _render_muted_text(order_summary.get("customer_email"), "Customer email hidden")

            with columns[2]:
                st.write(str(order_summary.get("product_summary") or "Product missing"))

            with columns[3]:
                st.write(str(order_summary.get("variant_summary") or "Variant missing"))

            with columns[4]:
                edition_values = order_summary.get("edition_number_items") or []
                if not edition_values:
                    assignment_badge = _cached_order_assignment_badge(order_summary)
                    st.badge(
                        assignment_badge["label"],
                        color=_badge_color_for_assignment(assignment_badge["class_name"]),
                    )
                else:
                    for edition_value in edition_values[:3]:
                        st.badge(str(edition_value), color=_badge_color_for_edition(edition_value))
                    if len(edition_values) > 3:
                        st.caption(f"+{len(edition_values) - 3} more")

            with columns[5]:
                _render_certificate_action_cell(order_summary, key_prefix)

            psd = order_summary.get("psd") or {}
            psd_url = str(psd.get("url") or "").strip()
            with columns[6]:
                if psd_url:
                    st.link_button("Open PSD", psd_url, use_container_width=True)
                else:
                    st.badge("Missing", color="gray")

            prodigi = order_summary.get("prodigi") or {}
            prodigi_url = str(prodigi.get("url") or "").strip()
            with columns[7]:
                if prodigi_url:
                    st.link_button("Open Prodigi", prodigi_url, use_container_width=True)
                else:
                    st.badge("Missing", color="gray")

            with columns[8]:
                if order_link:
                    st.link_button("Open Order", order_link, use_container_width=True)
                else:
                    st.badge("Missing link", color="gray")


def _shopify_orders_mirror_styles():
    return """
    <style>
    .sc-shopify-shell {
        background: linear-gradient(180deg, #f3f3f4 0%, #eeeeef 100%);
        border-radius: 22px;
        padding: 1rem;
        border: 1px solid rgba(12, 12, 13, 0.08);
    }
    .sc-shopify-metrics {
        display: grid;
        grid-template-columns: repeat(5, minmax(0, 1fr));
        gap: 0.85rem;
        margin-bottom: 1rem;
    }
    .sc-shopify-metric {
        background: #ffffff;
        border-radius: 18px;
        padding: 1rem 1.1rem;
        border: 1px solid rgba(12, 12, 13, 0.08);
        box-shadow: 0 8px 22px rgba(12, 12, 13, 0.06);
    }
    .sc-shopify-metric-label {
        color: #6d7175;
        font-size: 0.82rem;
        font-weight: 700;
        letter-spacing: 0.01em;
        margin-bottom: 0.35rem;
    }
    .sc-shopify-metric-value {
        color: #202223;
        font-size: 1.5rem;
        font-weight: 800;
        line-height: 1.1;
    }
    .sc-shopify-metric-subtle {
        color: #6d7175;
        font-size: 0.78rem;
        margin-top: 0.3rem;
    }
    .sc-shopify-table-card {
        background: #ffffff;
        border-radius: 18px;
        border: 1px solid rgba(12, 12, 13, 0.08);
        box-shadow: 0 8px 22px rgba(12, 12, 13, 0.06);
        overflow: hidden;
    }
    .sc-shopify-table-toolbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0.9rem 1rem;
        border-bottom: 1px solid rgba(12, 12, 13, 0.08);
        color: #202223;
        font-weight: 700;
    }
    .sc-shopify-batch-pill {
        display: inline-flex;
        align-items: center;
        border: 1px solid rgba(12, 12, 13, 0.1);
        border-radius: 999px;
        padding: 0.45rem 0.9rem;
        background: #ffffff;
        color: #202223;
        font-size: 0.9rem;
        font-weight: 700;
    }
    .sc-shopify-table-wrap {
        overflow-x: auto;
    }
    table.sc-shopify-table {
        width: 100%;
        min-width: 1180px;
        border-collapse: collapse;
        color: #202223;
    }
    table.sc-shopify-table thead th {
        text-align: left;
        padding: 0.9rem 1rem;
        color: #6d7175;
        font-size: 0.84rem;
        font-weight: 700;
        border-bottom: 1px solid rgba(12, 12, 13, 0.08);
        background: #ffffff;
        white-space: nowrap;
    }
    table.sc-shopify-table tbody td {
        padding: 0.95rem 1rem;
        border-bottom: 1px solid rgba(12, 12, 13, 0.08);
        vertical-align: top;
        font-size: 0.96rem;
    }
    table.sc-shopify-table tbody tr:hover {
        background: #f6f6f7;
    }
    .sc-shopify-cell-muted {
        color: #6d7175;
        font-size: 0.78rem;
        margin-top: 0.28rem;
        line-height: 1.35;
    }
    .sc-shopify-checkbox {
        width: 20px;
        height: 20px;
        border-radius: 6px;
        border: 1.5px solid #8c9196;
        display: inline-block;
        box-sizing: border-box;
        background: #ffffff;
    }
    .sc-shopify-order-link {
        color: #005bd3;
        text-decoration: none;
        font-weight: 800;
    }
    .sc-shopify-order-link:hover {
        text-decoration: underline;
    }
    .sc-shopify-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.38rem;
        border-radius: 999px;
        padding: 0.24rem 0.72rem;
        font-size: 0.84rem;
        font-weight: 800;
        white-space: nowrap;
    }
    .sc-shopify-badge::before {
        content: "";
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: currentColor;
        opacity: 0.7;
    }
    .sc-shopify-badge-fulfillment-unfulfilled,
    .sc-shopify-badge-delivery-unfulfilled {
        background: #ffe066;
        color: #6b5400;
    }
    .sc-shopify-badge-fulfillment-fulfilled,
    .sc-shopify-badge-delivery-delivered,
    .sc-shopify-badge-delivery-fulfilled {
        background: #d8f5d0;
        color: #0c5132;
    }
    .sc-shopify-badge-fulfillment-partially-fulfilled,
    .sc-shopify-badge-delivery-partially-fulfilled {
        background: #d9ecff;
        color: #0a4a8a;
    }
    .sc-shopify-badge-payment-paid {
        background: #ececec;
        color: #3f4449;
    }
    .sc-shopify-badge-payment-partially-paid {
        background: #d9ecff;
        color: #0a4a8a;
    }
    .sc-shopify-badge-payment-refunded,
    .sc-shopify-badge-payment-voided,
    .sc-shopify-badge-fulfillment-cancelled,
    .sc-shopify-badge-delivery-cancelled {
        background: #ffe0e0;
        color: #8a1f1f;
    }
    .sc-shopify-badge-fulfillment-open,
    .sc-shopify-badge-payment-pending,
    .sc-shopify-badge-delivery-open {
        background: #f1f2f3;
        color: #4a4f55;
    }
    .sc-shopify-badge-edition-assigned {
        background: #d8f5d0;
        color: #0c5132;
    }
    .sc-shopify-badge-edition-needs-attention,
    .sc-shopify-badge-edition-needs-sync {
        background: #fff0c2;
        color: #6b5400;
    }
    .sc-shopify-pagination-note {
        color: #6d7175;
        font-size: 0.82rem;
        text-align: center;
        padding-top: 0.4rem;
    }
    @media (max-width: 1100px) {
        .sc-shopify-metrics {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
    }
    </style>
    """


def _shopify_orders_mirror_query(search_text, quick_filter):
    tokens = []
    filter_token = {
        "All": "",
        "Unfulfilled": "fulfillment_status:unfulfilled",
        "Paid": "financial_status:paid",
        "Fulfilled": "fulfillment_status:fulfilled",
        "Cancelled": "status:cancelled",
    }.get(str(quick_filter or "All"), "")
    if filter_token:
        tokens.append(filter_token)
    cleaned_search = str(search_text or "").strip()
    if cleaned_search:
        tokens.append(cleaned_search)
    return " ".join(token for token in tokens if token).strip()


def _parse_iso_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _format_shopify_mirror_date(value):
    parsed = _parse_iso_datetime(value)
    if not parsed:
        return "-"
    local_value = parsed.astimezone()
    today = datetime.now().astimezone().date()
    if local_value.date() == today:
        prefix = "Today"
    elif local_value.date() == today - timedelta(days=1):
        prefix = "Yesterday"
    else:
        prefix = local_value.strftime("%d %b")
    return f"{prefix} at {local_value.strftime('%I:%M %p').lstrip('0').lower()}"


def _humanize_shopify_status_text(value, fallback="-"):
    cleaned = str(value or "").strip()
    if not cleaned:
        return fallback
    return cleaned.replace("_", " ").replace("-", " ").title()


def _status_slug(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-") or "open"


def _live_order_line_item_id(order, line_item, index):
    return str(
        line_item.get("shopify_line_item_id")
        or line_item.get("id")
        or f"{order.get('shopify_order_id') or 'order'}:line:{index}"
    ).strip()


def _live_order_item_count(order):
    total = 0
    for line_item in order.get("line_items") or []:
        total += max(1, int(line_item.get("quantity") or 1))
    return total


def _live_order_item_note(order):
    titles = []
    seen = set()
    for line_item in order.get("line_items") or []:
        title = str(line_item.get("product_title") or line_item.get("title") or "").strip()
        if not title:
            continue
        token = title.casefold()
        if token in seen:
            continue
        seen.add(token)
        titles.append(title)
    if not titles:
        return "No product titles"
    if len(titles) == 1:
        return titles[0]
    return f"{titles[0]} +{len(titles) - 1} more"


def _live_order_assignment_summary(order, assignment_snapshot):
    assigned = 0
    needs_attention = 0
    pending_sync = 0
    for index, line_item in enumerate(order.get("line_items") or [], start=1):
        line_item_id = _live_order_line_item_id(order, line_item, index)
        snapshot = assignment_snapshot.get(line_item_id) or {}
        assignments = snapshot.get("assignments") or []
        if assignments:
            assigned += len(assignments)
            continue
        status = str(snapshot.get("assignment_status") or "").strip()
        if status in {"Error", "Product Not Found", "Needs Edition Setup", "Sold Out"}:
            needs_attention += max(1, int(line_item.get("quantity") or 1))
        else:
            pending_sync += max(1, int(line_item.get("quantity") or 1))
    if assigned and not needs_attention and not pending_sync:
        return {
            "label": f"Editions assigned x{assigned}",
            "class_name": "assigned",
        }
    if needs_attention:
        return {
            "label": f"Needs attention x{needs_attention}",
            "class_name": "needs-attention",
        }
    if pending_sync:
        return {
            "label": f"Needs Sports Cave sync x{pending_sync}",
            "class_name": "needs-sync",
        }
    return {
        "label": "No edition checks yet",
        "class_name": "needs-sync",
    }


def _format_shopify_total(order):
    amount = str(order.get("total_price") or "").strip()
    if not amount:
        return "-"
    currency = str(order.get("currency") or "").strip().upper()
    symbol = "$" if currency in {"AUD", "USD", "CAD", "NZD", "SGD"} else f"{currency} "
    try:
        return f"{symbol}{float(amount):,.2f}"
    except ValueError:
        return f"{symbol}{amount}"


def _shopify_orders_visible_metrics(orders):
    orders_total = len(orders)
    items_total = sum(_live_order_item_count(order) for order in orders)
    refunded_total = sum(
        1
        for order in orders
        if any(token in str(order.get("financial_status") or "").upper() for token in ("REFUND", "VOID"))
    )
    fulfilled_total = sum(
        1 for order in orders if "FULFILLED" in str(order.get("fulfillment_status") or "").upper()
    )
    delivered_total = sum(
        1 for order in orders if "DELIVERED" in str(order.get("fulfillment_status") or "").upper()
    ) or fulfilled_total
    return {
        "orders": orders_total,
        "items": items_total,
        "returns": refunded_total,
        "fulfilled": fulfilled_total,
        "delivered": delivered_total,
    }


def _render_shopify_orders_metrics(orders):
    metrics = _shopify_orders_visible_metrics(orders)
    metric_cards = [
        ("Live window", "50 orders", "Direct from Shopify"),
        ("Orders", str(metrics["orders"]), "Visible on this page"),
        ("Items ordered", str(metrics["items"]), "Current page total"),
        ("Returns", str(metrics["returns"]), "Refunded / voided"),
        ("Orders fulfilled", str(metrics["fulfilled"]), f"Delivered {metrics['delivered']}"),
    ]
    cards_html = "".join(
        f"""
        <div class="sc-shopify-metric">
            <div class="sc-shopify-metric-label">{html.escape(label)}</div>
            <div class="sc-shopify-metric-value">{html.escape(value)}</div>
            <div class="sc-shopify-metric-subtle">{html.escape(subtle)}</div>
        </div>
        """
        for label, value, subtle in metric_cards
    )
    return textwrap.dedent(
        f"""
        <div class="sc-shopify-shell">
            <div class="sc-shopify-metrics">{cards_html}</div>
        </div>
        """
    ).strip()


def _render_shopify_orders_mirror_table(orders, assignment_snapshot):
    return ""


def _sync_visible_shopify_orders_into_sports_cave(orders):
    orders_checked = 0
    assignments_created = 0
    already_assigned = 0
    errors = []
    for order in orders or []:
        try:
            result = supabase_backend.process_shopify_order_for_editions(
                order,
                generate_certificates=False,
                sync_product_metafields=True,
            )
            orders_checked += 1
            assignments_created += int(result.get("assignments_created") or 0)
            already_assigned += int(result.get("existing_assignments_skipped") or 0)
            if result.get("errors"):
                errors.extend(result["errors"])
        except Exception as error:
            errors.append(str(error))
    return {
        "orders_checked": orders_checked,
        "assignments_created": assignments_created,
        "already_assigned": already_assigned,
        "errors": errors,
    }


def _order_fetch_message_from_error(error):
    message = str(error or "").strip()
    lowered = message.lower()
    if (
        "read_orders" in lowered
        or ("scope" in lowered and "order" in lowered)
        or "access denied" in lowered
        or "forbidden" in lowered
        or "not authorized" in lowered
    ):
        return (
            "warning",
            "Orders require read_orders scope. Add read_orders in Shopify Dev Dashboard, release the app version, approve permissions, then redeploy Render.",
    )
    return ("caption", "Showing saved orders. Latest Shopify refresh failed.")


def _log_orders_page_load(started, rows=0, db_seconds=0.0, render_seconds=0.0, shopify_seconds=0.0):
    total_seconds = time.perf_counter() - started
    perf_log(f"ACTION_BOARD_LOAD total={int(total_seconds * 1000)}ms rows={int(rows or 0)}")
    perf_log(
        f"PERF Orders load total={total_seconds:.3f}s "
        f"db={float(db_seconds or 0.0):.3f}s "
        f"render={float(render_seconds or 0.0):.3f}s "
        f"shopify={float(shopify_seconds or 0.0):.3f}s "
        f"rows={int(rows or 0)}"
    )


def render_shopify_orders_mirror_page():
    st.title("Orders")
    st.caption("Live mirror from Shopify. Sports Cave only overlays edition allocation state from Limited Editions.")
    st.markdown(_shopify_orders_mirror_styles(), unsafe_allow_html=True)

    config = shopify_sync.get_config()
    if not st.session_state.get("shopify-orders-mirror-defaults-v1"):
        st.session_state["shopify-orders-mirror-defaults-v1"] = True
        st.session_state["shopify-orders-mirror-search"] = ""
        st.session_state["shopify-orders-mirror-filter"] = "All"
        st.session_state["shopify-orders-mirror-cursor"] = ""
        st.session_state["shopify-orders-mirror-cursor-stack"] = []
        st.session_state["shopify-orders-mirror-refresh"] = 0
        st.session_state["shopify-orders-mirror-overlay-refresh"] = 0

    notice = st.session_state.pop("shopify_orders_mirror_notice", None)
    if notice:
        st.success(notice)
    warning = st.session_state.pop("shopify_orders_mirror_warning", None)
    if warning:
        st.warning(warning)

    if not config["configured"]:
        st.warning("Shopify Orders mirror is not configured yet.")
        render_shopify_scope_diagnostics(config, "orders-mirror")
        return

    admin_orders_url = shopify_sync.build_orders_admin_url(config.get("store_domain"))
    actions = st.columns([0.95, 1.1, 1.2, 1.6])
    refresh_clicked = actions[0].button("Refresh Shopify Mirror", type="primary", use_container_width=True)
    sync_visible_clicked = actions[1].button(
        "Sync Sports Cave Editions",
        disabled=not supabase_backend.is_configured(),
        use_container_width=True,
    )
    if admin_orders_url:
        actions[2].link_button("Open Real Shopify Orders", admin_orders_url, use_container_width=True)
    else:
        actions[2].caption("Shopify admin link unavailable.")
    actions[3].caption("Use the real Shopify admin button for the exact Shopify page. This screen mirrors it live inside Sports Cave OS.")

    filters = st.columns([0.7, 2.4])
    quick_filter = filters[0].selectbox(
        "View",
        ("All", "Unfulfilled", "Paid", "Fulfilled", "Cancelled"),
        key="shopify-orders-mirror-filter",
    )
    search_text = filters[1].text_input(
        "Search and filter",
        placeholder="Search and filter",
        key="shopify-orders-mirror-search",
    )

    filter_signature = json.dumps({"search": search_text.strip().lower(), "filter": quick_filter})
    if st.session_state.get("shopify-orders-mirror-filter-signature") != filter_signature:
        st.session_state["shopify-orders-mirror-filter-signature"] = filter_signature
        st.session_state["shopify-orders-mirror-cursor"] = ""
        st.session_state["shopify-orders-mirror-cursor-stack"] = []

    if refresh_clicked:
        st.session_state["shopify-orders-mirror-refresh"] = int(
            st.session_state.get("shopify-orders-mirror-refresh", 0)
        ) + 1
        st.session_state["shopify-orders-mirror-cursor"] = ""
        st.session_state["shopify-orders-mirror-cursor-stack"] = []

    current_cursor = st.session_state.get("shopify-orders-mirror-cursor") or ""
    search_query = _shopify_orders_mirror_query(search_text, quick_filter)
    try:
        with st.spinner("Loading live Shopify orders..."):
            live_page = cached_shopify_orders_mirror_page(
                search_query,
                current_cursor,
                int(st.session_state.get("shopify-orders-mirror-refresh", 0) or 0),
            )
            orders = live_page.get("orders") or []
    except Exception as error:
        level, text = _order_fetch_message_from_error(error)
        if level == "warning":
            st.warning(text)
        else:
            st.warning("Live Shopify orders could not be loaded right now.")
            st.caption(text)
        render_shopify_scope_diagnostics(config, "orders-mirror")
        return

    if sync_visible_clicked and orders:
        with st.spinner("Syncing visible Shopify orders into Sports Cave editions..."):
            result = _sync_visible_shopify_orders_into_sports_cave(orders)
        st.session_state["shopify-orders-mirror-overlay-refresh"] = int(
            st.session_state.get("shopify-orders-mirror-overlay-refresh", 0)
        ) + 1
        bump_supabase_cache_version("orders", "order-summary", "sync-state")
        st.session_state.shopify_orders_mirror_notice = (
            f"Checked {result['orders_checked']} live Shopify orders. "
            f"Created {result['assignments_created']} new edition assignments. "
            f"Skipped {result['already_assigned']} assignments that were already saved."
        )
        if result["errors"]:
            st.session_state.shopify_orders_mirror_warning = (
                f"Live mirror synced with warnings. First issue: {result['errors'][0]}"
            )
        st.rerun()

    if not orders:
        st.info("No Shopify orders matched the current live filters.")
        return

    line_item_ids = tuple(
        _live_order_line_item_id(order, line_item, index)
        for order in orders
        for index, line_item in enumerate(order.get("line_items") or [], start=1)
    )
    assignment_snapshot = {}
    if supabase_backend.is_configured() and line_item_ids:
        try:
            assignment_snapshot = cached_order_line_assignment_snapshot(
                line_item_ids,
                int(st.session_state.get("shopify-orders-mirror-overlay-refresh", 0) or 0),
            )
        except Exception:
            assignment_snapshot = {}

    st.markdown(_render_shopify_orders_metrics(orders), unsafe_allow_html=True)
    st.markdown(_render_shopify_orders_mirror_table(orders, assignment_snapshot), unsafe_allow_html=True)

    pager = st.columns([0.9, 0.9, 2.2])
    previous_clicked = pager[0].button(
        "Previous 50",
        disabled=not st.session_state.get("shopify-orders-mirror-cursor-stack"),
        use_container_width=True,
    )
    next_clicked = pager[1].button(
        "Next 50",
        disabled=not live_page.get("has_next_page"),
        use_container_width=True,
    )
    pager[2].caption(
        f"Showing {len(orders)} live Shopify orders from this page. "
        "Search and filter are sent straight to Shopify instead of loading saved order rows."
    )

    if previous_clicked:
        cursor_stack = list(st.session_state.get("shopify-orders-mirror-cursor-stack") or [])
        st.session_state["shopify-orders-mirror-cursor"] = cursor_stack.pop() if cursor_stack else ""
        st.session_state["shopify-orders-mirror-cursor-stack"] = cursor_stack
        st.rerun()
    if next_clicked:
        cursor_stack = list(st.session_state.get("shopify-orders-mirror-cursor-stack") or [])
        cursor_stack.append(current_cursor)
        st.session_state["shopify-orders-mirror-cursor-stack"] = cursor_stack
        st.session_state["shopify-orders-mirror-cursor"] = live_page.get("end_cursor") or ""
        st.rerun()


def render_supabase_orders_page():
    page_started = time.perf_counter()
    st.title("Orders")
    st.caption("Sports Cave fulfilment actions. Shopify remains the full order dashboard.")
    st.markdown(_orders_page_styles(), unsafe_allow_html=True)

    notice = st.session_state.pop("supabase_orders_notice", None)
    if notice:
        st.success(notice)
    status_message = st.session_state.pop("supabase_orders_status_message", None)
    if status_message:
        level, text = status_message
        if level == "warning":
            st.warning(text)
        else:
            st.caption(text)

    config = shopify_sync.get_config()
    action_board_filters = (
        "Needs Action",
        "Paid + Unfulfilled",
        "Needs Edition",
        "Certificate Needed",
        "Product Missing",
        "Sold Out Issue",
        "Assigned",
        "Fulfilled",
        "Cancelled / Refunded",
        "Errors",
        "All Saved Orders",
    )
    if (
        not st.session_state.get("supabase-orders-defaults-v4-applied")
        or st.session_state.get("supabase-orders-status-filter") not in action_board_filters
    ):
        st.session_state["supabase-orders-status-filter"] = "Needs Action"
        st.session_state["supabase-orders-visible-count"] = 50
        st.session_state["supabase-orders-defaults-v4-applied"] = True

    try:
        sync_state = cached_supabase_sync_state(supabase_cache_version("sync-state"))
        last_order_sync = sync_state.get("last_successful_order_fetch_at") or sync_state.get("last_successful_order_sync_at")
    except Exception:
        sync_state = {}
        last_order_sync = ""
    action_toolbar = st.columns([0.9, 0.9, 1.6])
    fetch_new_clicked = action_toolbar[0].button(
        "Fetch New Orders",
        disabled=not config["configured"],
        type="primary",
        use_container_width=True,
    )
    deep_refresh_clicked = action_toolbar[1].button(
        "Deep Refresh 60 Days",
        disabled=not config["configured"],
        use_container_width=True,
    )
    action_toolbar[2].caption(
        "Fetch uses Shopify only when clicked. Deep Refresh is slower and only for catch-up."
    )

    search = st.text_input(
        "Search orders",
        placeholder="Search order, customer, email, handle, SKU, or edition",
        key="supabase-orders-search",
    )

    filter_toolbar = st.columns([1.2, 1.8])
    status_filter = filter_toolbar[0].selectbox(
        "View",
        action_board_filters,
        key="supabase-orders-status-filter",
    )
    filter_toolbar[1].caption("Default shows paid unfulfilled orders needing Sports Cave action.")

    filter_signature = json.dumps({"search": search.strip().lower(), "status": status_filter})
    if st.session_state.get("supabase-orders-filter-signature") != filter_signature:
        st.session_state["supabase-orders-filter-signature"] = filter_signature
        st.session_state["supabase-orders-visible-count"] = 50
    visible_count = max(int(st.session_state.get("supabase-orders-visible-count", 50) or 50), 50)

    if not config["configured"]:
        st.caption("Shopify sync is not configured. Saved orders remain visible.")
    else:
        st.caption(
            "Last synced: "
            + (format_updated_at(last_order_sync) if last_order_sync else "Never")
        )

    if fetch_new_clicked or deep_refresh_clicked:
        sync_message = st.empty()
        sync_message.info("Fetching Shopify orders into the saved Sports Cave OS cache...")
        fetch_started = time.perf_counter()
        try:
            max_orders = 100 if fetch_new_clicked else 250
            query = None
            if deep_refresh_clicked:
                refresh_from = datetime.now(timezone.utc) - timedelta(days=60)
                query = (
                    "financial_status:paid fulfillment_status:unfulfilled "
                    f"updated_at:>='{refresh_from.isoformat(timespec='seconds').replace('+00:00', 'Z')}'"
                )
            result = supabase_backend.sync_shopify_orders_to_supabase(
                config,
                query=query,
                max_orders=max_orders,
                generate_certificates=False,
                sync_product_metafields=True,
            )
            perf_log(
                f"PERF FETCH_NEW_ORDERS total={(time.perf_counter() - fetch_started):.3f}s "
                f"orders_seen={int(result.get('orders_seen', 0) or 0)} "
                f"imported={int(result.get('orders_imported', 0) or 0)} "
                f"assigned={int(result.get('assignments_created', 0) or 0)}"
            )
            sync_message.empty()
            if result.get("orders_seen", 0) == 0:
                st.session_state.supabase_orders_notice = "No new paid unfulfilled orders found."
            else:
                st.session_state.supabase_orders_notice = (
                    f"Fetched {result.get('orders_seen', 0)} orders. "
                    f"Imported {result.get('orders_imported', 0)} new orders. "
                    f"Created {result.get('assignments_created', 0)} edition assignments."
                )
            if result.get("errors"):
                st.session_state.supabase_orders_status_message = (
                    "warning",
                    f"Showing saved orders. Shopify metafield/display sync warning: {result['errors'][0]}",
                )
            else:
                st.session_state.supabase_orders_status_message = ("caption", "Showing saved orders.")
            bump_supabase_cache_version("orders", "order-summary", "sync-state")
            st.rerun()
        except Exception as error:
            perf_log(f"PERF FETCH_NEW_ORDERS total={(time.perf_counter() - fetch_started):.3f}s status=failed")
            sync_message.empty()
            st.session_state.supabase_orders_status_message = _order_fetch_message_from_error(error)
            supabase_backend.log_app_error("orders_page_sync_failed", str(error), {"source": "orders_page"})
            st.rerun()

    db_started = time.perf_counter()
    try:
        with st.spinner("Loading orders..."):
            cache_version = supabase_cache_version("orders")
            snapshot_token = _order_widget_token(f"{status_filter}-{search}-{visible_count}")
            dataset, reused_saved_dataset, dataset_error = load_supabase_screen_snapshot(
                f"supabase-orders-screen-{snapshot_token}",
                cache_version,
                lambda: cached_supabase_orders_dataset(visible_count, cache_version, search, status_filter),
            )
            summary = dataset.get("summary") or {}
            filtered_order_summaries = dataset.get("order_summaries") or []
            db_elapsed = time.perf_counter() - db_started
    except Exception as error:
        db_elapsed = time.perf_counter() - db_started
        supabase_backend.log_app_error("orders_page_load_failed", str(error), {"source": "orders_page"})
        st.info("Orders are not available right now. Use Fetch New Orders to refresh the saved order list.")
        _log_orders_page_load(page_started, 0, db_seconds=db_elapsed)
        return
    if dataset_error:
        st.caption("Showing saved orders. Latest Shopify refresh failed.")
        supabase_backend.log_app_error("orders_page_load_failed", str(dataset_error), {"source": "orders_page"})

    if summary:
        st.caption(
            f"{summary.get('orders_synced', 0)} saved | "
            f"{summary.get('needs_edition', 0)} need editions | "
            f"{summary.get('historical_lines', 0)} historical | "
            f"{summary.get('assigned_today', 0)} assigned today"
        )

    order_summaries = filtered_order_summaries[:visible_count]

    if not order_summaries:
        if not summary.get("orders_synced"):
            st.info("No saved orders yet. Use Fetch New Orders or wait for Shopify webhook.")
        elif status_filter == "Needs Action":
            st.info("No paid unfulfilled orders need Sports Cave action right now.")
        else:
            st.info("No saved orders match the current filters yet.")
        _log_orders_page_load(page_started, 0, db_seconds=db_elapsed)
        return

    render_started = time.perf_counter()
    st.markdown('<div class="sc-orders-section-label">Order workspace</div>', unsafe_allow_html=True)
    if reused_saved_dataset:
        st.caption(f"Showing action rows from the last warm screen snapshot. {len(order_summaries)} currently visible.")
    else:
        st.caption("Showing fulfilment action rows from Supabase.")
    _render_shopify_style_cached_orders_table(order_summaries)
    render_elapsed = time.perf_counter() - render_started
    if dataset.get("has_more"):
        if st.button("Load 50 More", key="supabase-orders-load-more", use_container_width=True):
            st.session_state["supabase-orders-visible-count"] = visible_count + 50
            _log_orders_page_load(page_started, len(order_summaries), db_seconds=db_elapsed, render_seconds=render_elapsed)
            st.rerun()
    _log_orders_page_load(page_started, len(order_summaries), db_seconds=db_elapsed, render_seconds=render_elapsed)


def fetch_latest_orders(config):
    run_id = db.start_shopify_order_sync(config["store_domain"], config["api_version"])
    progress = st.progress(0, text="Fetching latest Shopify orders...")
    orders_seen = 0
    pages_synced = 0
    assignments_created = 0
    changed_product_ids = set()
    sync_warning = ""
    try:
        for page in shopify_sync.iter_order_pages(config=config):
            for order in page["orders"]:
                result = db.process_shopify_order_for_editions(order)
                assignments_created += result["assignments_created"]
                changed_product_ids.update(result["changed_product_ids"])
            orders_seen += len(page["orders"])
            pages_synced += 1
            db.update_shopify_order_sync_run(
                run_id,
                orders_seen=orders_seen,
                assignments_created=assignments_created,
                pages_synced=pages_synced,
                api_version=page.get("api_version"),
            )
            progress.progress(
                min(int(orders_seen / max(config["max_orders"], 1) * 100), 99),
                text=f"Fetched {orders_seen} Shopify orders...",
            )
            del page
            gc.collect()

        if os.getenv("SHOPIFY_AUTO_SYNC_EDITION_WIDGET", "true").lower() == "true":
            for product_id in changed_product_ids:
                try:
                    product = db.get_shopify_edition_product(product_id)
                    if product:
                        shopify_sync.sync_edition_metafields(product, config=config)
                        db.mark_shopify_edition_synced(product_id)
                except Exception:
                    sync_warning = "Edition assigned locally, but storefront display sync failed."

        db.update_shopify_order_sync_run(
            run_id,
            status="Complete",
            orders_seen=orders_seen,
            assignments_created=assignments_created,
            pages_synced=pages_synced,
        )
        progress.progress(100, text="Shopify order fetch complete.")
        return {
            "orders_seen": orders_seen,
            "assignments_created": assignments_created,
            "sync_warning": sync_warning,
        }
    except Exception as error:
        db.update_shopify_order_sync_run(
            run_id,
            status="Failed",
            orders_seen=orders_seen,
            assignments_created=assignments_created,
            pages_synced=pages_synced,
            error_message="Shopify order sync failed. Check read_orders scope and API version.",
        )
        progress.empty()
        raise error


def active_assignments(assignments):
    return [
        item
        for item in assignments
        if item.get("assignment_status") not in {"Voided", "Refunded"}
    ]


def certificate_path_exists(assignment):
    certificate_path = assignment.get("certificate_pdf_path")
    return bool(certificate_path and Path(certificate_path).exists())


def render_certificate_actions(assignments, key_prefix):
    active = active_assignments(assignments)
    if not active:
        st.button("Needs Edition", disabled=True, use_container_width=True, key=f"{key_prefix}-needs")
        return

    missing = [assignment for assignment in active if not certificate_path_exists(assignment)]
    if missing:
        if st.button("Generate PDF", key=f"{key_prefix}-generate", use_container_width=True):
            try:
                for assignment in missing:
                    generate_certificate_pdf(assignment["id"])
                st.session_state.orders_notice = (
                    f"Generated {len(missing)} certificate PDF"
                    f"{'s' if len(missing) != 1 else ''}."
                )
                st.rerun()
            except Exception as error:
                st.error("Could not generate the certificate PDF.")
                st.error(str(error))
        return

    if len(active) == 1:
        assignment = active[0]
        path = Path(assignment["certificate_pdf_path"])
        st.download_button(
            "Download PDF",
            data=path.read_bytes(),
            file_name=path.name,
            mime="application/pdf",
            key=f"{key_prefix}-download-{assignment['id']}",
            use_container_width=True,
        )
        return

    with st.expander("PDFs"):
        for assignment in active:
            path = Path(assignment["certificate_pdf_path"])
            st.download_button(
                f"#{assignment['edition_number']}",
                data=path.read_bytes(),
                file_name=path.name,
                mime="application/pdf",
                key=f"{key_prefix}-download-{assignment['id']}",
                use_container_width=True,
            )


def render_orders_page():
    render_supabase_orders_page()


def normalize_psd_handle_guess(value):
    cleaned = str(value or "").strip().lower()
    cleaned = re.sub(r"\.psd$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned)
    return cleaned.strip("-")


def parse_psd_csv(uploaded_csv):
    text = uploaded_csv.getvalue().decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        file_name = (row.get("File Name") or row.get("file_name") or "").strip()
        handle_guess = (
            row.get("Shopify Handle Guess")
            or row.get("shopify_handle")
            or row.get("Shopify Handle")
            or ""
        )
        normalized_handle = normalize_psd_handle_guess(handle_guess or file_name)
        asset_type = (row.get("Asset Type") or "psd_master_file").strip() or "psd_master_file"
        if asset_type not in supabase_backend.ASSET_TYPES:
            asset_type = "psd_master_file"
        rows.append(
            {
                "asset_name": file_name,
                "shopify_handle": normalized_handle,
                "google_drive_file_id": (row.get("Google Drive File ID") or "").strip(),
                "asset_url": (row.get("Google Drive URL") or row.get("google_drive_file_url") or "").strip(),
                "asset_type": asset_type,
                "notes": "PSD CSV import",
            }
        )
    return [row for row in rows if row["asset_url"] or row["google_drive_file_id"] or row["asset_name"]]


def get_product_by_handle(products, handle):
    normalized = normalize_psd_handle_guess(handle)
    for product in products:
        if normalize_psd_handle_guess(product.get("shopify_handle")) == normalized:
            return product
    return {}


def render_psd_storage_status():
    try:
        stats = supabase_backend.get_psd_link_stats()
    except Exception as error:
        st.warning("Could not load PSD storage counts.")
        st.exception(error)
        return
    columns = st.columns(5)
    columns[0].metric("Product asset rows", int(stats.get("product_assets_count") or 0))
    columns[1].metric("PSD rows", int(stats.get("psd_master_file_count") or 0))
    columns[2].metric("Matched PSDs", int(stats.get("matched_psd_count") or 0))
    columns[3].metric("Missing PSDs", int(stats.get("missing_psd_count") or 0))
    columns[4].metric("Products tracked", int(stats.get("products_count") or 0))
    st.caption(f"PSD links stored in Supabase: {int(stats.get('psd_master_file_count') or 0)}")


def render_psd_master_folder_controls(key_prefix="psd-master-folder"):
    try:
        setting = supabase_backend.ensure_psd_master_folder_setting()
    except Exception as error:
        st.warning("Could not save or load the PSD master folder setting.")
        st.exception(error)
        setting = supabase_backend.DEFAULT_PSD_MASTER_FOLDER_SETTING
    folder_url = (setting or {}).get("url") or supabase_backend.DEFAULT_PSD_MASTER_FOLDER_SETTING["url"]
    folder_name = (setting or {}).get("name") or "Sports Cave PSD Master Folder"
    with st.container(border=True):
        st.markdown("**PSD Master Folder**")
        st.caption(folder_name)
        st.code(folder_url, language="text")
        st.link_button("Open PSD Master Folder", folder_url, use_container_width=True)
        with st.expander("Update PSD master folder shortcut", expanded=False):
            new_name = st.text_input(
                "Folder name",
                value=folder_name,
                key=f"{key_prefix}-name",
            )
            new_url = st.text_input(
                "Folder URL",
                value=folder_url,
                key=f"{key_prefix}-url",
            )
            if st.button("Save PSD Master Folder", key=f"{key_prefix}-save", use_container_width=True):
                try:
                    supabase_backend.set_app_setting(
                        supabase_backend.PSD_MASTER_FOLDER_SETTING_KEY,
                        {"url": new_url.strip(), "name": new_name.strip() or "Sports Cave PSD Master Folder"},
                    )
                    st.success("PSD master folder saved.")
                except Exception as error:
                    st.error("Could not save PSD master folder.")
                    st.exception(error)


def render_psd_link_editor(
    shopify_handle,
    product_title="",
    *,
    existing_asset=None,
    key_prefix="psd-editor",
    expanded=True,
):
    handle = normalize_psd_handle_guess(shopify_handle)
    existing_asset = existing_asset or {}
    existing_url = existing_asset.get("asset_url") or existing_asset.get("google_drive_file_url") or ""
    default_asset_name = existing_asset.get("asset_name") or f"{handle}.psd"
    with st.expander(f"Edit PSD link - {product_title or handle}", expanded=expanded):
        st.caption("Supabase stores the Drive link only. The PSD file stays in Google Drive.")
        read_only_columns = st.columns(2)
        read_only_columns[0].text_input(
            "Shopify handle",
            value=handle,
            disabled=True,
            key=f"{key_prefix}-{handle}-handle",
        )
        read_only_columns[1].text_input(
            "Product title",
            value=product_title or "",
            disabled=True,
            key=f"{key_prefix}-{handle}-title",
        )
        psd_url = st.text_input(
            "PSD Drive URL",
            value=existing_url,
            placeholder="https://drive.google.com/file/d/FILE_ID/view",
            key=f"{key_prefix}-{handle}-url",
        )
        extracted_id = supabase_backend.extract_google_drive_file_id(psd_url)
        drive_id = st.text_input(
            "PSD file ID",
            value=existing_asset.get("google_drive_file_id") or extracted_id,
            placeholder="Auto-extracted where possible",
            key=f"{key_prefix}-{handle}-file-id",
        )
        edit_columns = st.columns([1.2, 0.8])
        asset_name = edit_columns[0].text_input(
            "Asset name",
            value=default_asset_name,
            key=f"{key_prefix}-{handle}-asset-name",
        )
        is_primary = edit_columns[1].checkbox(
            "Primary PSD",
            value=existing_asset.get("is_primary") is not False,
            key=f"{key_prefix}-{handle}-primary",
        )
        notes = st.text_input(
            "Notes",
            value=existing_asset.get("notes") or "Manual PSD link",
            key=f"{key_prefix}-{handle}-notes",
        )
        if existing_url:
            st.link_button("Open Current PSD", existing_url, use_container_width=True)
        master_setting = supabase_backend.get_psd_master_folder_setting()
        if master_setting.get("url"):
            st.link_button("Open PSD Master Folder", master_setting["url"], use_container_width=True)
        actions = st.columns(3)
        if actions[0].button("Save PSD Link", type="primary", key=f"{key_prefix}-{handle}-save", use_container_width=True):
            if not psd_url.strip() and not drive_id.strip():
                st.warning("Paste a PSD Drive URL or file ID before saving.")
            else:
                try:
                    supabase_backend.upsert_product_asset(
                        handle,
                        "psd_master_file",
                        psd_url.strip(),
                        notes.strip(),
                        asset_name=asset_name.strip() or f"{handle}.psd",
                        google_drive_file_id=drive_id.strip(),
                        is_primary=is_primary,
                    )
                    st.session_state.supabase_assets_notice = "PSD link saved."
                    st.rerun()
                except Exception as error:
                    st.error("Could not save PSD link.")
                    st.exception(error)
        if actions[1].button("Replace Existing Link", key=f"{key_prefix}-{handle}-replace", use_container_width=True):
            try:
                supabase_backend.upsert_product_asset(
                    handle,
                    "psd_master_file",
                    psd_url.strip(),
                    notes.strip() or "Manual PSD link replacement",
                    asset_name=asset_name.strip() or f"{handle}.psd",
                    google_drive_file_id=drive_id.strip(),
                    is_primary=True,
                )
                st.session_state.supabase_assets_notice = "PSD link replaced."
                st.rerun()
            except Exception as error:
                st.error("Could not replace PSD link.")
                st.exception(error)
        confirm_remove = st.checkbox(
            "Confirm remove stored PSD link only",
            key=f"{key_prefix}-{handle}-remove-confirm",
            help="This removes the Supabase shortcut only. It does not delete anything from Google Drive.",
        )
        if actions[2].button(
            "Remove PSD Link",
            disabled=not confirm_remove,
            key=f"{key_prefix}-{handle}-remove",
            use_container_width=True,
        ):
            try:
                supabase_backend.remove_product_asset(handle, "psd_master_file")
                st.session_state.supabase_assets_notice = "PSD link removed from Supabase."
                st.rerun()
            except Exception as error:
                st.error("Could not remove PSD link.")
                st.exception(error)


def render_psd_csv_import(products, *, expanded=False, key_prefix="supabase-psd", title="Import PSD CSV"):
    with st.expander(title, expanded=expanded):
        st.caption("Upload the Google Drive export CSV only when you are ready. The app stores Drive links only, not PSD files.")
        render_psd_master_folder_controls(f"{key_prefix}-master")
        render_psd_storage_status()
        uploaded_csv = st.file_uploader(
            "PSD CSV",
            type=["csv"],
            key=f"{key_prefix}-csv-upload",
            label_visibility="collapsed",
        )
        if uploaded_csv is None:
            return

        try:
            csv_rows = parse_psd_csv(uploaded_csv)
            asset_map = supabase_backend.get_product_asset_map()
            known_products = supabase_backend.list_known_product_handles()
        except Exception as error:
            st.error("Could not read the PSD CSV.")
            st.exception(error)
            return

        handle_lookup = {
            normalize_psd_handle_guess(item.get("shopify_handle")): item.get("shopify_handle")
            for item in known_products
            if item.get("shopify_handle")
        }
        for row in csv_rows:
            matched_handle = handle_lookup.get(row["shopify_handle"])
            if matched_handle:
                row["shopify_handle"] = matched_handle
        product_handles = set(handle_lookup.values())
        manually_linked_unmatched = set(st.session_state.get(f"{key_prefix}-linked-unmatched", []))
        product_options = {
            f"{item.get('product_title') or item.get('shopify_handle')} | {item.get('shopify_handle')}": item.get("shopify_handle")
            for item in known_products
            if item.get("shopify_handle")
        }

        matched = [row for row in csv_rows if row["shopify_handle"] in product_handles]
        unmatched = [
            row
            for row in csv_rows
            if row["shopify_handle"] not in product_handles
            and (row.get("google_drive_file_id") or row.get("asset_url") or row.get("asset_name")) not in manually_linked_unmatched
        ]
        linked_psd_handles = {
            handle
            for handle, assets in asset_map.items()
            if assets.get("psd_master_file")
        }
        missing = [item for item in products if item.get("shopify_handle") not in linked_psd_handles]

        match_columns = st.columns(4)
        match_columns[0].metric("Rows read", len(csv_rows))
        match_columns[1].metric("Matched PSDs", len(matched))
        match_columns[2].metric("Missing PSDs", len(missing))
        match_columns[3].metric("Unmatched PSDs", len(unmatched))

        if matched:
            st.markdown("**Matched PSDs**")
            overwrite_existing = st.checkbox(
                "Overwrite existing PSD links",
                value=False,
                help="Leave off to protect manually linked PSDs. Existing PSD links will be skipped.",
                key=f"{key_prefix}-overwrite-existing",
            )
            st.dataframe(
                [
                    {
                        "File Name": row["asset_name"],
                        "Shopify Handle": row["shopify_handle"],
                        "Drive URL": row["asset_url"],
                        "Existing PSD": "Yes" if (asset_map.get(row["shopify_handle"]) or {}).get("psd_master_file") else "No",
                    }
                    for row in matched[:200]
                ],
                use_container_width=True,
                hide_index=True,
            )
            if st.button("Import matched PSD links", type="primary", use_container_width=True):
                run_id = supabase_backend.start_sync_run("psd_csv_import")
                imported = 0
                skipped = 0
                errors = []
                try:
                    for row in matched:
                        try:
                            existing_url = (asset_map.get(row["shopify_handle"]) or {}).get("psd_master_file")
                            if existing_url and not overwrite_existing:
                                skipped += 1
                                continue
                            supabase_backend.upsert_product_asset(
                                row["shopify_handle"],
                                row["asset_type"] or "psd_master_file",
                                row["asset_url"],
                                row["notes"] or "PSD CSV import",
                                asset_name=row["asset_name"],
                                google_drive_file_id=row["google_drive_file_id"],
                                is_primary=True,
                            )
                            imported += 1
                        except Exception as row_error:
                            errors.append(f"{row.get('asset_name') or row.get('shopify_handle')}: {row_error}")
                    supabase_backend.finish_sync_run(
                        run_id,
                        "Complete" if not errors else "Complete With Warnings",
                        records_seen=len(csv_rows),
                        records_processed=imported,
                        error_message="; ".join(errors[:3]) if errors else "",
                    )
                    st.session_state.supabase_assets_notice = (
                        f"PSD import complete. Rows read: {len(csv_rows)}. Matched: {len(matched)}. "
                        f"Imported/updated: {imported}. Skipped existing: {skipped}. "
                        f"Unmatched: {len(unmatched)}. Missing PSDs after import may need refresh. "
                        f"Errors: {len(errors)}."
                    )
                    st.rerun()
                except Exception as error:
                    supabase_backend.finish_sync_run(
                        run_id,
                        "Failed",
                        records_seen=len(csv_rows),
                        records_processed=imported,
                        error_message="PSD CSV import failed.",
                    )
                    supabase_backend.log_app_error(
                        "psd_csv_import_failed",
                        str(error),
                        {"imported": imported, "matched": len(matched)},
                    )
                    st.error("PSD CSV import failed.")
                    st.exception(error)

        if missing:
            st.markdown("**Missing PSDs**")
            for item in missing[:50]:
                columns = st.columns([2.2, 1.3, 1, 1])
                columns[0].write(item.get("product_title") or item.get("shopify_handle"))
                columns[1].caption(item.get("shopify_handle"))
                if item.get("admin_url"):
                    columns[2].link_button("Shopify", item["admin_url"], use_container_width=True)
                else:
                    columns[2].caption("No Shopify link")
                if columns[3].button("Add PSD Link", key=f"{key_prefix}-missing-add-{item.get('shopify_handle')}", use_container_width=True):
                    st.session_state.psd_editor_context = {
                        "handle": item.get("shopify_handle"),
                        "title": item.get("product_title"),
                        "source": key_prefix,
                    }
            editor_context = st.session_state.get("psd_editor_context") or {}
            if editor_context.get("source") == key_prefix:
                handle = editor_context.get("handle")
                product = get_product_by_handle(products, handle)
                psd_assets = supabase_backend.get_primary_psd_assets([handle])
                render_psd_link_editor(
                    handle,
                    product.get("product_title") or editor_context.get("title") or "",
                    existing_asset=psd_assets.get(handle),
                    key_prefix=f"{key_prefix}-missing-editor",
                )

        if unmatched:
            st.markdown("**Unmatched PSDs**")
            st.dataframe(
                [
                    {
                        "File Name": row["asset_name"],
                        "Handle Guess": row["shopify_handle"],
                        "Drive URL": row["asset_url"],
                    }
                    for row in unmatched[:200]
                ],
                use_container_width=True,
                hide_index=True,
            )
            if not product_options:
                st.warning("No Shopify handles are available for manual linking yet. Sync Shopify products first.")
                return
            manual_columns = st.columns([1.4, 1.6, 1])
            unmatched_options = [
                f"{row['asset_name'] or row['shopify_handle']} | {index}"
                for index, row in enumerate(unmatched)
            ]
            selected_unmatched = manual_columns[0].selectbox("Unmatched PSD", unmatched_options)
            selected_index = int(selected_unmatched.rsplit("|", 1)[-1].strip())
            selected_product_label = manual_columns[1].selectbox("Link to Shopify product", list(product_options.keys()))
            overwrite_manual = st.checkbox(
                "Overwrite this product's existing PSD link",
                value=False,
                key=f"{key_prefix}-manual-overwrite",
            )
            if manual_columns[2].button("Save manual link", use_container_width=True):
                row = unmatched[selected_index]
                handle = product_options[selected_product_label]
                existing_url = (asset_map.get(handle) or {}).get("psd_master_file")
                if existing_url and not overwrite_manual:
                    st.warning("This product already has a PSD link. Tick overwrite if you want to replace it.")
                    return
                supabase_backend.upsert_product_asset(
                    handle,
                    row["asset_type"] or "psd_master_file",
                    row["asset_url"],
                    row["notes"] or "PSD CSV import",
                    asset_name=row["asset_name"],
                    google_drive_file_id=row["google_drive_file_id"],
                    is_primary=True,
                )
                linked_key = row.get("google_drive_file_id") or row.get("asset_url") or row.get("asset_name")
                st.session_state[f"{key_prefix}-linked-unmatched"] = list(
                    set(st.session_state.get(f"{key_prefix}-linked-unmatched", [])) | {linked_key}
                )
                st.session_state.supabase_assets_notice = f"Linked {row['asset_name']} to {handle}."
                st.rerun()


def _certificate_r2_download_url(row):
    bucket = row.get("certificate_r2_bucket") or row.get("certificate_pdf_r2_bucket")
    key = row.get("certificate_r2_key") or row.get("certificate_pdf_r2_key")
    if not bucket or not key:
        return ""
    return r2_storage.generate_presigned_download_url(bucket, key)


def render_r2_storage_panel():
    with st.expander("Cloudflare R2 Storage", expanded=False):
        status = r2_storage.get_r2_status()
        status_columns = st.columns(2)
        status_columns[0].metric("R2 configured", "Yes" if status["configured"] else "No")
        status_columns[1].metric("R2 endpoint configured", "Yes" if status["endpoint_configured"] else "No")

        bucket_columns = st.columns(4)
        bucket_columns[0].caption("Certificates bucket")
        bucket_columns[0].write(status["certificates_bucket"] or "Missing")
        bucket_columns[1].caption("Assets bucket")
        bucket_columns[1].write(status["assets_bucket"] or "Missing")
        bucket_columns[2].caption("Backups bucket")
        bucket_columns[2].write(status["backups_bucket"] or "Missing")
        bucket_columns[3].caption("PSD archive bucket")
        bucket_columns[3].write(status["psd_archive_bucket"] or "Missing")

        test_columns = st.columns(2)
        if test_columns[0].button("Test R2 connection", disabled=not status["configured"], use_container_width=True):
            result = r2_storage.test_r2_connection()
            if result.get("ok"):
                st.success(f"R2 connection OK: {result.get('bucket')}")
            else:
                st.error(result.get("error") or "R2 connection failed.")

        if test_columns[1].button("Test R2 upload", disabled=not status["configured"], use_container_width=True):
            result = r2_storage.test_upload_backup_file()
            if result.get("ok"):
                st.success("R2 test upload complete.")
                st.caption(f"{result.get('bucket')}/{result.get('key')}")
                if result.get("download_url"):
                    st.link_button("Open temporary download", result["download_url"], use_container_width=True)
                metadata_result = supabase_backend.upsert_file_asset(
                    {
                        "asset_type": "backup_test",
                        "bucket": result.get("bucket"),
                        "object_key": result.get("key"),
                        "filename": "sports-cave-os-r2-test.txt",
                        "mime_type": result.get("content_type") or "text/plain; charset=utf-8",
                        "size_bytes": result.get("size_bytes"),
                        "source": "r2",
                        "status": "active",
                    }
                )
                if metadata_result.get("ok"):
                    st.caption("Supabase file metadata saved.")
                else:
                    st.warning(metadata_result.get("warning") or "Upload worked, but metadata was not saved.")
            else:
                st.error(result.get("error") or "R2 test upload failed.")


def render_product_assets_page():
    st.title("Product Assets")
    st.caption("Store Google Drive, PSD, certificate, mockup, Shopify CDN, and Prodigi links by Shopify handle.")
    if not supabase_backend.is_configured():
        st.warning("Shared product asset storage is not connected right now. Existing saved asset links are not changed.")
        return
    try:
        supabase_backend.ensure_schema()
    except Exception as error:
        st.error("Product assets could not be refreshed. Existing saved asset links are not changed.")
        supabase_backend.log_app_error("product_assets_schema_check_failed", str(error), {"source": "product_assets_page"})
        return

    notice = st.session_state.pop("supabase_assets_notice", None)
    if notice:
        st.success(notice)

    render_psd_master_folder_controls("product-assets-master-folder")
    render_psd_storage_status()

    search = st.text_input(
        "Search products",
        placeholder="Search product title or Shopify handle",
        key="supabase-assets-search",
        label_visibility="collapsed",
    )
    filter_columns = st.columns([1, 1, 2])
    asset_type_filter = filter_columns[0].selectbox(
        "Asset type filter",
        ["All", *list(supabase_backend.ASSET_TYPES)],
        format_func=lambda value: "All asset types" if value == "All" else supabase_backend.ASSET_LABELS.get(value, value),
        key="supabase-assets-type-filter",
    )
    link_filter = filter_columns[1].selectbox(
        "Link status",
        ["All", "Linked", "Missing"],
        key="supabase-assets-link-filter",
    )
    products = supabase_backend.list_edition_products(search=search, limit=1000)
    if not products:
        st.info("No products found yet. Open Limited Editions and click Sync Shopify Products first.")
        return

    render_psd_csv_import(products)

    with st.container(border=True):
        st.subheader("Add or Update Asset Link")
        product_options = [
            f"{item.get('product_title') or item.get('shopify_handle')} | {item.get('shopify_handle')}"
            for item in products
        ]
        selected = st.selectbox("Product", product_options, key="supabase-asset-product")
        selected_handle = selected.rsplit("|", 1)[-1].strip()
        asset_type = st.selectbox(
            "Asset type",
            list(supabase_backend.ASSET_TYPES),
            format_func=lambda value: supabase_backend.ASSET_LABELS.get(value, value),
            key="supabase-asset-type",
        )
        asset_name = st.text_input("Asset name", placeholder="Optional file/folder name")
        asset_url = st.text_input("Asset URL", placeholder="Paste the Google Drive, Shopify CDN, or Prodigi link")
        google_drive_file_id = st.text_input("Google Drive file ID", placeholder="Optional Drive file/folder ID")
        notes = st.text_input("Notes", placeholder="Optional VA notes")
        if st.button("Save Asset Link", type="primary", use_container_width=True):
            try:
                supabase_backend.upsert_product_asset(
                    selected_handle,
                    asset_type,
                    asset_url,
                    notes,
                    asset_name=asset_name,
                    google_drive_file_id=google_drive_file_id,
                    is_primary=True,
                )
                st.session_state.supabase_assets_notice = "Asset link saved."
                st.rerun()
            except Exception as error:
                st.error("Could not save asset link.")
                st.exception(error)

    rows = supabase_backend.list_product_assets(search=search)
    if asset_type_filter != "All":
        rows = [row for row in rows if row.get("asset_type") == asset_type_filter]
    if link_filter == "Linked":
        rows = [row for row in rows if row.get("asset_url") or row.get("google_drive_file_url")]
    elif link_filter == "Missing":
        rows = [row for row in rows if not (row.get("asset_url") or row.get("google_drive_file_url"))]

    st.subheader("Stored Asset Rows")
    if rows:
        st.dataframe(
            [
                {
                    "shopify_handle": row.get("shopify_handle"),
                    "asset_type": row.get("asset_type") or "Missing",
                    "asset_name": row.get("asset_name") or "",
                    "google_drive_file_url": row.get("google_drive_file_url") or row.get("asset_url") or "",
                    "is_primary": row.get("is_primary"),
                    "notes": row.get("notes") or "",
                    "created_at": format_updated_at(row.get("created_at")) if row.get("created_at") else "",
                    "updated_at": format_updated_at(row.get("updated_at")) if row.get("updated_at") else "",
                }
                for row in rows
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No product asset rows match the current filters.")

    asset_map = {}
    for row in rows:
        handle = row.get("shopify_handle")
        if not handle:
            continue
        entry = asset_map.setdefault(
            handle,
            {
                "product_title": row.get("product_title"),
                "assets": {},
            },
        )
        if row.get("asset_type"):
            entry["assets"][row["asset_type"]] = row

    st.subheader("Asset Control")
    for product in products:
        handle = product.get("shopify_handle")
        entry = asset_map.get(handle) or {"product_title": product.get("product_title"), "assets": {}}
        with st.expander(f"{entry.get('product_title') or handle} | {handle}", expanded=False):
            columns = st.columns(3)
            for index, asset_type in enumerate(supabase_backend.ASSET_TYPES):
                asset = entry["assets"].get(asset_type) or {}
                with columns[index % 3]:
                    with st.container(border=True):
                        st.markdown(f"**{supabase_backend.ASSET_LABELS.get(asset_type, asset_type)}**")
                        asset_link = asset.get("asset_url") or asset.get("google_drive_file_url")
                        if asset_link:
                            st.markdown(status_badge("Connected"), unsafe_allow_html=True)
                            st.link_button("Open", asset_link, use_container_width=True)
                            st.caption(format_updated_at(asset.get("updated_at")))
                        else:
                            st.markdown(status_badge("Missing"), unsafe_allow_html=True)


def render_edition_orders_page():
    st.title("Edition Orders")
    st.caption("Every allocated edition number from paid Shopify orders.")
    if not supabase_backend.is_configured():
        st.warning("Shared order storage is not connected right now. Existing edition allocations are not changed.")
        return
    search = st.text_input(
        "Search edition orders",
        placeholder="Search order, product, handle, or customer",
        key="supabase-edition-orders-search",
        label_visibility="collapsed",
    )
    try:
        rows = supabase_backend.list_edition_orders(search=search, limit=500)
    except Exception as error:
        st.error("Edition orders could not be refreshed. Existing edition allocations are not changed.")
        supabase_backend.log_app_error("edition_orders_page_load_failed", str(error), {"source": "edition_orders_page"})
        return
    if not rows:
        st.info("No edition allocations found yet.")
        return
    header = st.columns([0.9, 2.2, 0.9, 1.3, 1.1, 1.2, 1])
    for column, label in zip(header, ("Order", "Product", "Edition", "Customer", "Assigned", "Certificate", "Shopify")):
        column.markdown(f"**{label}**")
    for row in rows:
        columns = st.columns([0.9, 2.2, 0.9, 1.3, 1.1, 1.2, 1])
        columns[0].write(row.get("order_name") or row.get("shopify_order_id") or "Order")
        columns[1].write(row.get("product_title") or row.get("shopify_handle"))
        columns[1].caption(row.get("variant_title") or "")
        columns[2].markdown(status_badge(f"#{row.get('edition_number')}/{row.get('edition_total')}"), unsafe_allow_html=True)
        columns[3].write(row.get("customer_name") or row.get("customer_email") or "Customer")
        columns[4].caption(format_updated_at(row.get("assigned_at")))
        r2_download_url = _certificate_r2_download_url(row)
        if row.get("shopify_file_url"):
            columns[5].link_button("Open PDF", row["shopify_file_url"], use_container_width=True)
        elif r2_download_url:
            columns[5].link_button("Open R2 PDF", r2_download_url, use_container_width=True)
        elif row.get("local_file_path") and Path(row["local_file_path"]).exists():
            path = Path(row["local_file_path"])
            columns[5].download_button(
                "PDF",
                data=path.read_bytes(),
                file_name=path.name,
                mime="application/pdf",
                key=f"edition-order-pdf-{row['id']}",
                use_container_width=True,
            )
        else:
            if columns[5].button("Generate", key=f"edition-order-generate-{row['id']}", use_container_width=True):
                try:
                    supabase_backend.generate_certificate_for_edition_order(row["id"])
                    st.rerun()
                except Exception as error:
                    st.error("Could not generate certificate.")
                    st.exception(error)
        if row.get("admin_url"):
            columns[6].link_button("Open", row["admin_url"], use_container_width=True)
        else:
            columns[6].caption("Missing")
        st.divider()


def render_supabase_certificates_page():
    st.title("Certificates")
    st.caption("Certificate PDFs generated from Supabase edition allocations.")
    if not supabase_backend.is_configured():
        st.warning("Shared certificate storage is not connected right now. Existing certificate records are not changed.")
        return
    search = st.text_input(
        "Search certificates",
        placeholder="Search product, customer, or order",
        key="supabase-certificates-search",
        label_visibility="collapsed",
    )
    try:
        rows = supabase_backend.list_certificates(search=search, limit=500)
    except Exception as error:
        st.error("Certificates could not be refreshed. Existing certificate records are not changed.")
        supabase_backend.log_app_error("certificates_page_load_failed", str(error), {"source": "certificates_page"})
        return
    if not rows:
        st.info("No certificates generated yet.")
        return
    header = st.columns([1, 2.1, 0.9, 1.2, 1.1, 1])
    for column, label in zip(header, ("Order", "Product", "Edition", "Collector", "Generated", "PDF")):
        column.markdown(f"**{label}**")
    for row in rows:
        columns = st.columns([1, 2.1, 0.9, 1.2, 1.1, 1])
        columns[0].write(row.get("order_name") or row.get("shopify_order_id") or "Order")
        columns[1].write(row.get("product_title") or row.get("shopify_handle") or "Sports Cave Artwork")
        columns[2].write(f"#{row.get('edition_number')}/{row.get('edition_total')}")
        columns[3].caption(row.get("customer_name") or "Collector")
        columns[4].caption(format_updated_at(row.get("generated_at")))
        r2_download_url = _certificate_r2_download_url(row)
        if row.get("shopify_file_url"):
            columns[5].link_button("Open PDF", row["shopify_file_url"], use_container_width=True)
        elif r2_download_url:
            columns[5].link_button("Open R2 PDF", r2_download_url, use_container_width=True)
        elif row.get("local_file_path") and Path(row["local_file_path"]).exists():
            path = Path(row["local_file_path"])
            columns[5].download_button(
                "PDF",
                data=path.read_bytes(),
                file_name=path.name,
                mime="application/pdf",
                key=f"supabase-certificate-download-{row['id']}",
                use_container_width=True,
            )
        else:
            columns[5].caption("Missing")


def render_webhook_events_page():
    st.title("Webhook Events")
    st.caption("Shopify webhook IDs and processing results. Duplicates are safely ignored.")
    if not supabase_backend.is_configured():
        st.warning("Webhook Events requires DATABASE_URL.")
        return
    try:
        rows = supabase_backend.list_webhook_events(limit=300)
    except Exception as error:
        st.error("Could not load webhook events.")
        st.exception(error)
        return
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_sync_runs_page():
    st.title("Sync Runs")
    st.caption("Product and order sync history.")
    if not supabase_backend.is_configured():
        st.warning("Sync Runs requires DATABASE_URL.")
        return
    try:
        rows = supabase_backend.list_sync_runs(limit=300)
    except Exception as error:
        st.error("Could not load sync runs.")
        st.exception(error)
        return
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_app_errors_page():
    st.title("App Errors")
    st.caption("Production-safe error log. Secrets are never stored here.")
    if not supabase_backend.is_configured():
        st.warning("App Errors requires DATABASE_URL.")
        return
    try:
        rows = supabase_backend.list_app_errors(limit=300)
    except Exception as error:
        st.error("Could not load app errors.")
        st.exception(error)
        return
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_persistence_check_page():
    st.title("Persistence Check")
    st.caption("Manual Supabase persistence check. Nothing runs until this page is opened or you press refresh.")
    if not supabase_backend.is_configured():
        st.warning("DATABASE_URL is missing. Supabase persistence is not connected.")
        return

    if st.button("Refresh Persistence Check", type="primary", use_container_width=True):
        st.cache_data.clear()

    try:
        counts = supabase_backend.persistence_counts()
    except Exception as error:
        st.error("Could not connect to Supabase using DATABASE_URL.")
        st.exception(error)
        return

    st.success("Supabase connection works.")
    rows = [{"table": table_name, "rows": count} for table_name, count in counts.items()]
    st.dataframe(rows, use_container_width=True, hide_index=True)

    zero_tables = [table_name for table_name, count in counts.items() if int(count or 0) == 0]
    if zero_tables:
        st.warning("These tables currently have 0 rows: " + ", ".join(zero_tables))
    else:
        st.success("All tracked persistence tables contain rows.")

    st.subheader("Quick Actions")
    actions = st.columns(3)
    if actions[0].button("Check Product Assets", use_container_width=True):
        st.session_state.pending_page = "Product Assets"
        st.rerun()
    if actions[1].button("Check Edition Tables", use_container_width=True):
        st.session_state.pending_page = "Limited Editions"
        st.rerun()
    if actions[2].button("Run Integrity Check", use_container_width=True):
        st.session_state.pending_page = "Edition Integrity Check"
        st.rerun()


def render_edition_integrity_check_page():
    st.title("Edition Integrity Check")
    st.caption("Read-only safety checks for duplicate editions, skipped numbers, counters, failed webhooks, and missing PSDs.")
    if not supabase_backend.is_configured():
        st.warning("Edition Integrity Check requires DATABASE_URL.")
        return
    st.warning("This tool does not auto-fix edition numbers. Review results before making any protected repair.")
    if not st.button("Run Integrity Check", type="primary", use_container_width=True):
        st.info("Click Run Integrity Check when you want to audit Supabase edition data.")
        return
    try:
        with st.spinner("Checking edition integrity..."):
            results = supabase_backend.run_integrity_check()
    except Exception as error:
        st.error("Could not run the integrity check.")
        st.exception(error)
        return

    total_issues = sum(len(rows) for rows in results.values())
    if total_issues == 0:
        st.success("No integrity issues found.")
        return
    st.error(f"{total_issues} integrity issue groups/rows found. Review before sending further limited edition orders.")
    labels = {
        "duplicate_edition_numbers": "Duplicate edition numbers per product",
        "skipped_edition_numbers": "Skipped edition numbers",
        "missing_product_handle": "Edition orders missing product handle",
        "counter_lower_than_expected": "next_edition_number lower than max assigned + 1",
        "sold_out_not_marked": "Products sold out but not marked sold out",
        "negative_remaining": "Products with negative remaining editions",
        "failed_webhooks": "Failed webhook events",
        "certificate_failures": "Certificate generation failures",
        "missing_psd_links": "Product handles with missing PSD links",
    }
    for key, rows in results.items():
        with st.expander(f"{labels.get(key, key)} ({len(rows)})", expanded=bool(rows)):
            if rows:
                st.dataframe(rows, use_container_width=True, hide_index=True)
                st.caption("Repair suggestion: inspect the affected product/order records before any protected manual change.")
            else:
                st.success("No issues.")


def render_certificates_page():
    if supabase_backend.is_configured():
        render_supabase_certificates_page()
        return
    st.title("Certificates")
    st.caption("Rough generated Sports Cave limited edition PDFs. Customer vault and emails come later.")
    certificates = db.list_generated_certificates(limit=100)
    summary = db.get_certificate_summary()
    st.metric("Certificate PDFs generated", summary["generated"])
    if not certificates:
        st.info("No certificate PDFs have been generated yet. Generate them from the Orders page after editions are assigned.")
        return

    header = st.columns([1.1, 2.2, 0.9, 1.1, 1.4, 1])
    for column, label in zip(header, ("Order", "Product", "Edition", "Collector", "Generated", "PDF")):
        column.markdown(f"**{label}**")
    for certificate in certificates:
        columns = st.columns([1.1, 2.2, 0.9, 1.1, 1.4, 1])
        columns[0].write(certificate.get("order_name") or "Order")
        columns[1].write(certificate.get("product_title") or "Sports Cave Artwork")
        columns[2].write(f"#{certificate['edition_number']}/{certificate['edition_limit']}")
        columns[3].caption(certificate.get("customer_name") or "Collector")
        columns[4].caption(format_updated_at(certificate.get("certificate_generated_at")))
        path = Path(certificate.get("certificate_pdf_path") or "")
        if path.exists():
            columns[5].download_button(
                "Download PDF",
                data=path.read_bytes(),
                file_name=path.name,
                mime="application/pdf",
                key=f"certificate-download-{certificate['id']}",
                use_container_width=True,
            )
        else:
            columns[5].caption("Missing file")


def _prompt_edit_id(namespace, key):
    return f"{namespace}::{key}"


def render_prompt_edit_button(prompt_id, *, label="✎"):
    button_key = f"prompt-edit-button::{prompt_id}"
    panel_key = f"prompt-edit-open::{prompt_id}"
    if st.button(label, key=button_key, help="Developer password required.", use_container_width=True):
        st.session_state[panel_key] = True


def render_prompt_edit_panel(title, prompt_id, prompt_text, *, height=360):
    panel_key = f"prompt-edit-open::{prompt_id}"
    if not st.session_state.get(panel_key):
        return prompt_text

    with st.container(border=True):
        st.caption("Developer only. Saved changes replace this prompt everywhere it is used.")
        edited_text = st.text_area(
            "Prompt text",
            value=prompt_text,
            height=height,
            key=f"prompt-edit-text::{prompt_id}",
        )
        password = st.text_input(
            "Developer password",
            type="password",
            key=f"prompt-edit-password::{prompt_id}",
        )
        cols = st.columns([1, 1, 3])
        if cols[0].button("Save prompt", key=f"prompt-edit-save::{prompt_id}", use_container_width=True):
            if password != DEVELOPER_PAGE_PASSWORD:
                st.error("Developer password is incorrect.")
            else:
                prompt_store.save_prompt(prompt_id, title, edited_text)
                st.session_state[panel_key] = False
                st.success("Prompt saved to backend.")
                st.rerun()
        if cols[1].button("Cancel", key=f"prompt-edit-cancel::{prompt_id}", use_container_width=True):
            st.session_state[panel_key] = False
            st.rerun()
    return prompt_text


def render_prompt_edit_controls(title, prompt_id, prompt_text, *, height=360, label="✎"):
    render_prompt_edit_button(prompt_id, label=label)
    return render_prompt_edit_panel(title, prompt_id, prompt_text, height=height)


def render_prompt_block(title, prompt, key, when_to_use=None, height=220):
    prompt_id = _prompt_edit_id("marketing", key)
    prompt_text = prompt_store.get_prompt(prompt_id, prompt).strip()
    with st.expander(title, expanded=False):
        if when_to_use:
            st.caption(f"When to use this: {when_to_use}")
        st.caption("Copy this prompt into ChatGPT.")
        st.text_area(
            f"{title} prompt",
            value=prompt_text,
            height=height,
            key=f"prompt-text-{key}",
            label_visibility="collapsed",
        )
        action_cols = st.columns([1.2, 0.35, 4.45])
        with action_cols[0]:
            render_copy_text_button(prompt_text, f"marketing-{key}", "Copy Prompt")
        with action_cols[1]:
            render_prompt_edit_button(prompt_id)
        render_prompt_edit_panel(title, prompt_id, prompt_text)


def render_marketing_card(title, body, *, key=None, copy_label=None):
    st.markdown(
        f"""
        <div class="marketing-card">
          <div class="marketing-card-title">{html.escape(title)}</div>
          <div class="marketing-card-body">{html.escape(body).replace(chr(10), "<br>")}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if key and copy_label:
        render_copy_text_button(body.strip(), f"marketing-card-{key}", copy_label)


META_URL_PARAMETERS = "utm_source=facebook&utm_medium=paid_social&utm_campaign={{campaign.name}}&utm_content={{ad.name}}&utm_term={{adset.name}}&placement={{placement}}"


def render_meta_url_parameters_block():
    st.markdown("#### Meta tracking URL parameters")
    st.caption("Paste this into Meta Ads Manager under Tracking -> URL parameters.")
    st.text_input(
        "URL parameters",
        value=META_URL_PARAMETERS,
        key="meta-usa-url-parameters",
        help="Copy this exact line into the Meta URL parameters field.",
    )
    render_copy_text_button(
        META_URL_PARAMETERS,
        "meta-usa-url-parameters",
        "Copy URL Parameters",
    )


def render_prompt_collection(prompts, key_prefix):
    for title, prompt in prompts:
        render_prompt_block(title, prompt, f"{key_prefix}-{safe_filename_part(title)}", height=230)


def inject_marketing_factory_styles():
    st.markdown(
        """
        <style>
        .marketing-card {
            border: 1px solid rgba(212, 165, 76, 0.28);
            border-radius: 16px;
            background: linear-gradient(135deg, rgba(17, 17, 17, 0.98), rgba(26, 22, 17, 0.92));
            padding: 18px 20px;
            margin: 0 0 14px 0;
        }
        .marketing-card-title {
            color: #F5F2EA;
            font-weight: 800;
            font-size: 1.02rem;
            margin-bottom: 8px;
        }
        .marketing-card-body {
            color: #C9C2B8;
            line-height: 1.48;
            font-size: 0.94rem;
        }
        div[data-testid="stTextArea"] textarea {
            background: #F5F2EA !important;
            color: #0B0B0D !important;
            -webkit-text-fill-color: #0B0B0D !important;
            border: 1px solid rgba(212, 165, 76, 0.55) !important;
            border-radius: 10px !important;
            padding: 14px 16px !important;
            font-size: 0.95rem !important;
            line-height: 1.45 !important;
            caret-color: #0B0B0D !important;
        }
        div[data-testid="stTextArea"] textarea::placeholder {
            color: #4B4B4D !important;
            -webkit-text-fill-color: #4B4B4D !important;
            opacity: 1 !important;
        }
        div[data-testid="stExpander"] {
            background: rgba(17, 17, 17, 0.98) !important;
            border: 1px solid rgba(212, 165, 76, 0.18) !important;
            border-radius: 12px !important;
        }
        div[data-testid="stExpander"] summary,
        div[data-testid="stExpander"] summary:hover,
        div[data-testid="stExpander"] summary:focus,
        div[data-testid="stExpander"] summary p,
        div[data-testid="stExpander"] summary span {
            background: #111111 !important;
            color: #F5F2EA !important;
        }
        div[data-testid="stExpander"] p,
        div[data-testid="stExpander"] li,
        div[data-testid="stExpander"] label,
        div[data-testid="stExpander"] span {
            color: #F5F2EA !important;
        }
        div[data-testid="stExpander"] div[data-testid="stTextArea"] textarea,
        div[data-testid="stExpander"] div[data-testid="stTextArea"] textarea:focus,
        div[data-testid="stExpander"] div[data-testid="stTextArea"] textarea:hover {
            background: #F5F2EA !important;
            color: #0B0B0D !important;
            -webkit-text-fill-color: #0B0B0D !important;
            caret-color: #0B0B0D !important;
        }
        div[data-testid="stExpander"] div[data-testid="stButton"] button,
        div[data-testid="stExpander"] div[data-testid="stButton"] button:hover,
        div[data-testid="stExpander"] div[data-testid="stButton"] button:focus {
            background: #F5F2EA !important;
            color: #0B0B0D !important;
            -webkit-text-fill-color: #0B0B0D !important;
            border-color: rgba(212, 165, 76, 0.55) !important;
            filter: none !important;
            transform: none !important;
        }
        div[data-testid="stExpander"] div[data-testid="stButton"] button *,
        div[data-testid="stExpander"] div[data-testid="stButton"] button span,
        div[data-testid="stExpander"] div[data-testid="stButton"] button p {
            color: #0B0B0D !important;
            -webkit-text-fill-color: #0B0B0D !important;
            fill: #0B0B0D !important;
            stroke: #0B0B0D !important;
        }
        div[data-testid="stTabs"] button,
        div[data-testid="stTabs"] button:hover,
        div[data-testid="stTabs"] button:focus {
            color: #F5F2EA !important;
            background: #111111 !important;
            border-color: rgba(212, 165, 76, 0.25) !important;
        }
        div[data-testid="stTabs"] button[aria-selected="true"],
        div[data-testid="stTabs"] button[aria-selected="true"]:hover,
        div[data-testid="stTabs"] button[aria-selected="true"]:focus {
            background: #D4A54C !important;
            color: #0B0B0D !important;
        }
        div[data-testid="stButton"] button,
        div[data-testid="stDownloadButton"] button,
        a[data-testid="stLinkButton"] {
            transition: none !important;
        }
        div[data-testid="stButton"] button:hover,
        div[data-testid="stDownloadButton"] button:hover,
        a[data-testid="stLinkButton"]:hover {
            color: inherit !important;
            filter: none !important;
        }
        pre, code {
            background: #F5F2EA !important;
            color: #0B0B0D !important;
            border-color: rgba(212, 165, 76, 0.45) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


class LazyPromptLibrary:
    def __init__(self, loader):
        self._loader = loader
        self._prompts = None

    def _load(self):
        if self._prompts is None:
            self._prompts = self._loader()
        return self._prompts

    def __getitem__(self, key):
        return self._load()[key]

    def items(self):
        return self._load().items()


META_PROMPTS = LazyPromptLibrary(lambda: {
    "au_carousel": """
You are my Sports Cave Australian Meta Ads copywriter.

I will upload:
- A screenshot of the product artwork
- The carousel images being used
- The product/theme/fan base
- Any context such as athlete, rivalry, team, moment, championship, location or historical meaning

Write the best possible Meta carousel card text for an Australian audience.

Use the Sports Cave Australian carousel style:
- premium
- nostalgic
- collector-focused
- man cave ready
- Australian
- emotionally driven
- scarcity based
- simple and punchy

Do not write long headlines. Do not use generic sales copy. Do not over-explain the product.
Do not sound like a normal poster ad. Do not use cheap discount language. Do not use emojis.

Each carousel card:
Headline: 1-2 words preferred, maximum 3 short words
Description: 1-2 words preferred, maximum 3 short words

Structure:
Card 1: Main emotional hook
Card 2: Fan identity
Card 3: Wall/display desire
Card 4: Collector/premium quality
Card 5: Scarcity/FOMO

For each card, write 3 options, choose the strongest final version, then give final clean version only in a table.
""",
    "au_primary": """
You are my Sports Cave Australian Meta ads copywriter.

Write 3 primary text variations for this product.

Audience:
Australian sports fans, men 25-55, collectors, man cave owners, gift buyers.

Tone:
Nostalgic, direct, masculine, emotional, collector-driven, and urgent.

Use memory, rivalry, old-school greatness, Aussie sporting pride, man cave ownership, and numbered scarcity.

Avoid generic poster language, over-explaining, discount language, polished AI phrasing, elevate, transform, and ultimate.

Structure:
Hook
Short emotional setup
Collector/scarcity line
Clear CTA

Write 3 variants. Each variant should be 3-5 short sentences.
End with one of:
Secure yours.
Own the moment.
Do not miss this drop.

Also provide:
- 5 headline options, max 4 words
- 5 description options, max 6 words
""",
    "au_motorsport": """
You are my Sports Cave Australian motorsport Meta ads copywriter.

Write ad copy for a limited-edition motorsport wall art drop.

Audience:
Australian men 25-55 who grew up on V8s, Bathurst, Holden vs Ford rivalry, old-school touring cars, and garage/man cave culture.

Tone:
Raw, nostalgic, gritty, collector-driven, proudly Australian.

Use themes:
- when racing was raw
- roaring engines
- mountain memories
- true rivalry
- Holden/Ford tribal identity
- old-school Bathurst energy
- man cave ownership
- limited numbered release

Do not name specific drivers unless I provide the name. Do not sound polished or corporate. Do not write long paragraphs.

Write:
1. Three primary text variants
2. Five short headlines
3. Five description lines
4. Five carousel card headline/description pairs
""",
    "usa_carousel": """
You are my Sports Cave USA Meta Ads copywriter.

I will upload product artwork, carousel images, the product name, sport, fan base, and any story/context.

Write Meta carousel card copy for a USA audience.

The copy must feel:
- identity-based
- legacy-driven
- greatness-focused
- collector exclusive
- fan cave ready
- gift friendly
- short, human, and urgent

Use angles like legacy debate, greatest era, rivalry, championship memory, fan cave ownership, numbered collector drop, only 100 made, no reprints, final editions.

Avoid Australian slang, generic poster wording, long card text, cheap discounts, and corporate phrasing.

USA carousel formula:
Card 1: Greatness hook
Card 2: Fan identity or legacy
Card 3: Wall ownership or fan cave
Card 4: Collector value
Card 5: Scarcity or final chance

For each card provide 3 options, then the strongest final version in a table.
""",
    "usa_primary": """
You are my Sports Cave USA Meta Ads copywriter.

Write 3 primary text variations for this limited-edition sports wall art product.

Audience:
USA sports fans, collectors, fan cave owners, nostalgia buyers, and gift buyers.

Tone:
Sharp, emotional, legacy-driven, collector-focused, and urgent.

Structure:
Hook
Short emotional setup
Collector/scarcity line
CTA

Each variant should be 3-5 short sentences.

Then provide:
- 6 headlines, max 4 words
- 6 descriptions, max 6 words
""",
    "usa_nba": """
You are my Sports Cave USA NBA Meta Ads copywriter.

Write ad copy for a limited-edition NBA wall art product built around rivalry, greatness, mentality, or legacy.

Audience:
USA NBA fans, collectors, Lakers/Bulls/Warriors/Knicks/Celtics-type fan bases, basketball nostalgia fans, fan cave owners, gift buyers.

Tone:
Sharp, emotional, legacy-driven, intense, collector-focused.

Use:
- built different
- no debate
- greatness recognizes greatness
- mentality
- the era fans still talk about
- legacy on the wall
- numbered collector drop
- only 100 made
- once gone, gone

Do not write like a normal poster ad. Do not over-explain. Do not sound corporate. Do not use emojis.

Write:
1. Three primary text variants
2. Five headlines
3. Five descriptions
4. Five carousel card headline/description pairs
""",
    "usa_master": """
SPORTS CAVE USA - GENERIC MASTER PROMPT FOR ALL PRODUCTS

Create a high-converting Meta Instant Experience concept for Sports Cave USA using the supplied product image as the core reference.

This must work for any Sports Cave product - not just baseball, not just one athlete, and not just one sport.

The final output must adapt to the specific artwork provided.

Brand Context

Sports Cave sells premium framed and unframed sports wall art for collectors, fans, man caves, home bars, garages, home offices, and gift buyers.

The brand feel is:
- premium
- nostalgic
- masculine
- emotional
- collector-driven
- limited-edition
- warm and cinematic
- built for real fans, not casuals

The goal is to make the viewer feel:
"This belongs on my wall."

Target Audience

Primary audience: USA sports fans aged roughly 25-55, especially men who care about iconic moments, rivalries, legends, nostalgia, and identity.

Secondary audience: gift buyers shopping for sports fans.

The tone should feel premium and emotional, not corporate, generic, or overly polished.

Core Rule

The supplied product image decides everything:
- sport
- room style
- props
- emotional angle
- wording
- supporting details
- image mood
- carousel direction
- CTA phrasing

Do not default to baseball, Babe Ruth, The Called Shot, NBA, or any other single theme unless that exact product is what is supplied.

Product Accuracy Rule

The artwork in the generated concepts must stay as close as possible to the supplied product image.

Preserve:
- artwork title
- layout
- colours
- frame style
- names
- signatures
- edition details
- central image
- overall design identity

Do not turn the artwork into a different product.
Do not invent a new artwork.
Do not swap the sport.
Do not add unrelated teams, athletes, leagues, or moments.

Visual Style Rule

Every image should feel like a premium Sports Cave collector release for USA buyers.

Use:
- black frame
- dark premium interiors
- warm lighting
- realistic shadows
- cinematic atmosphere
- masculine styling
- subtle collector-room details
- believable upscale environments

Avoid:
- clutter
- cheap poster-shop feel
- bright showroom feel
- fake-looking CGI rooms
- warped frames
- distorted artwork
- excessive text overlays
- generic stock-style interiors

USA Positioning Rule

The overall feel should be tailored for USA buyers.

Use room environments that fit American fan culture, such as:
- fan caves
- home bars
- sports dens
- garages
- basement lounges
- collector offices
- trophy rooms
- home offices
- premium rec rooms

Subtle USA trust/value cues can be supported in copy such as:
- fast USA delivery
- secure checkout
- 30-day returns
- limited collector release
- framed or unframed options

Do not overload the image with trust badges or promo clutter.

COPY STYLE RULES

Write all copy in a short, emotional, collector-focused tone.

It should feel like:
- nostalgia
- pride
- identity
- scarcity
- premium ownership

Not like:
- generic ecommerce copy
- technical product descriptions
- over-explained sales language
- cheesy ad-speak

Use short lines.
Fragments are fine.
Emotion first.
Clarity second.

Copy Themes to Lean On

Use the product to identify the strongest angle:
- iconic moment
- rivalry
- legend
- greatness
- nostalgia
- collector pride
- man cave identity
- gift-worthy tribute
- limited availability

Scarcity Rule

Where suitable, reinforce limited-edition positioning with language like:
- Only 100 editions made
- Numbered collector release
- Limited run
- Once it sells out, it's gone
- No reprints after sellout

Do not sound pushy or fake.

GENERIC INSTANT EXPERIENCE STRUCTURE

Create the Instant Experience around these core sections.

1. Feed Hero Image

Purpose: stop the scroll and make the product feel premium.

Requirements:
- vertical 4:5
- supplied artwork shown clearly
- black frame
- dark premium room
- warm lighting
- artwork readable
- strong hero composition
- collector atmosphere
- optional small overlay text

Keep overlay text minimal.

Possible examples:
- Limited Collector Release
- Only 100 Made
- Numbered Edition
- Built For Real Fans

Do not overcrowd the image.

2. IA Opening Photo

Purpose: first image inside the Instant Experience.

Use the cleanest, most premium room mockup.

Requirements:
- dark fan cave / sports room / office / collector den
- large black-framed artwork on wall
- artwork must be readable
- no CTA button
- no heavy overlay text
- let the image breathe

Text under it:

[ARTWORK TITLE / MOMENT / RIVALRY / LEGEND] LIVES
One moment.
One memory.
A story real fans never forgot.

Examples:
- THE RIVALRY LIVES
- THE LEGEND LIVES
- THE MOMENT LIVES
- THE DYNASTY LIVES
- THE GLORY LIVES

Use what fits the product best.

3. Mid Story / Desire Image

Purpose: deepen emotional connection before a CTA.

Use a second room angle or a more dramatic placement of the artwork.

Requirements:
- same artwork
- same black frame
- similar premium environment
- slightly different angle or room
- stronger emotional feel
- product still readable
- optional supporting text nearby

Use short emotional copy such as:
- For the fans who remember.
- For the wall that means something.
- For the ones who know this moment mattered.

4. Collector Detail Close-Up

Purpose: prove this is a premium collector piece.

Show details like:
- limited edition number
- title detail
- signature detail
- gold accents
- print texture
- frame depth
- premium finish

This should feel tactile and valuable.

Supporting copy:

Only 100 Editions Made
A numbered collector release for fans who know what this means.

5. Emotional Artwork Detail Close-Up

Purpose: sell the story inside the artwork.

Zoom in on the most emotional or recognizable part of the design.

That could be:
- the athlete's face
- a defining gesture
- the rivalry interaction
- the car
- the jersey
- the celebration
- the track
- the stadium
- the fight pose
- the horse
- the signature moment
- the title area

Supporting copy:

The moment.
The rivalry.
The memory that never left.

Adapt to the product.

6. Product Set Section

Purpose: cross-sell related pieces without killing the story.

Only include products that belong in the same emotional world.

Rules:
- show up to 4 products
- use carousel layout if possible
- hero product first
- then 2-3 closely related products
- same sport or same collector vibe
- do not mix random unrelated sports

Good product set logic:
- same athlete series
- same rivalry theme
- same sport
- same era
- same legend-based collector appeal

This should feel curated, not random.

7. Frame / Finish Image

Purpose: answer practical objections while keeping the premium feel.

Show:
- black framed version as hero
- unframed version if relevant
- frame depth
- premium finish
- clean styling
- minimal clutter

Supporting copy:

Premium Collector Finish
Available framed or unframed.
Built for fan caves, offices, garages, home bars, and collector walls.

8. Final CTA Hero Image

Purpose: close the sale.

Use the strongest room mockup again, or a tighter, darker, more dramatic version of it.

Requirements:
- artwork large
- black frame
- dark premium room
- cinematic lighting
- emotional and clean
- no clutter

Final Copy:

Own The Moment
Only 100 made. Once this edition sells out, it's gone.

CTA Button:
Secure Yours

GENERIC IMAGE ENVIRONMENT RULES BY SPORT

Use the supplied artwork to choose the right room feel and props.

Only use props that naturally support the product.

Motorsport:
- premium garage
- racing lounge
- dark office
- workshop-inspired collector space
- helmet
- shelf details
- subtle motorsport memorabilia
- leather seating
- track-inspired mood

Basketball:
- man cave
- sports lounge
- loft office
- trophy shelf
- basketball accents
- premium urban atmosphere
- dark walls
- collector-room energy

Football / NFL:
- home bar
- game-day lounge
- sports den
- football helmet or ball as subtle props
- leather couch
- warm masculine atmosphere

Baseball:
- vintage American den
- old-school office
- premium sports room
- glove, bat, ball, or scorecard only when relevant

Hockey:
- darker sports bar feel
- collector room
- rink nostalgia
- stick or puck only when relevant
- old-school fan cave mood

Soccer / Football:
- collector lounge
- premium football room
- scarf or boots only if subtle
- dark modern sports den
- stadium-memory atmosphere

Combat Sports:
- gym office
- fight-night collector wall
- gloves or robe only if subtle
- dramatic moody lighting
- bold, powerful atmosphere

Horse Racing:
- heritage lounge
- refined timber room
- racing-club mood
- trophies
- leather
- classic sporting atmosphere

Generic fallback:

If the sport is unclear, keep the environment simple, dark, warm, premium, and collector-focused.

Do not force props.

HARD RULES
- Every output must adapt to the supplied product image.
- Do not default to Babe Ruth, baseball, The Called Shot, or any specific existing example unless that is the product provided.
- Do not introduce unrelated athletes, teams, or sports.
- Do not use official league or sponsor branding unless it already appears in the supplied artwork.
- Keep the supplied artwork recognizable and faithful.
- Prioritize premium collector emotion over busy ad design.
- The artwork is always the hero.

The viewer should instantly feel:
"This is not just wall art. This is a piece of sports history for my wall."

GENERIC COPY BLOCKS TO USE THROUGHOUT

Use and adapt these as needed.

Opening:

[ARTWORK TITLE / MOMENT / RIVALRY / LEGEND] LIVES
One moment.
One memory.
A story real fans never forgot.

Collector block:

Only 100 Editions Made
A numbered collector release built for fans who know what this means.

Identity block:

For The Fans Who Remember
The rivalry.
The glory.
The era that never left.

Trust block:

Premium Collector Finish
Available framed or unframed.
Fast USA delivery.
Secure checkout.
30-day returns.

Final CTA:

Own The Moment
Only 100 made. Once this edition sells out, it's gone.

Button:
Secure Yours

FINAL GOAL

The final Instant Experience should feel like a premium collector campaign for USA sports fans.

It should make a buyer think:
"I remember this."
"I want this on my wall."
"If I wait too long, I'll miss it."
""",
    "full_meta": """
You are my Sports Cave Meta Ads strategist and copywriter.

I will upload:
- Product artwork
- Product name
- Sport
- Country target
- Fan base
- Any story/context behind the piece

Create a full Meta ad copy pack.

Use Sports Cave tone:
- nostalgic
- collector-driven
- emotional
- premium
- urgent
- short and human
- not corporate
- not over-explained

Output:
1. Campaign angle
2. Target audience
3. Primary text - 3 variants
4. Headlines - 8 options, max 4 words
5. Descriptions - 8 options, max 6 words
6. Carousel card copy - 5 cards
7. Retargeting version - 2 variants
8. Final scarcity version - 2 variants

Rules:
- no generic poster language
- no cheap discount language
- no elevate
- no transform
- no ultimate
- short lines
- collector urgency
- clear CTA
""",
})

SEO_PROMPTS = LazyPromptLibrary(lambda: {
    "site_qualification": """
You are an SEO editor reviewing a website for brand-safe backlinks.

Website: [PASTE URL]

Assess:
- Content quality
- Brand safety
- Whether a premium sports wall art brand belongs here

Return:
1. Approve or Reject
2. Short reason
3. Any red flags

If rejected, do not proceed.
""",
    "outreach": """
Hi [Name],

I came across your article on [topic] and really enjoyed it - especially the section on [specific part].

I am with Sports Cave, a sports wall art brand used by collectors and man cave owners globally.

I noticed you mention sports decor in the article and thought our framed sports art could be a useful example for readers looking for real products.

If helpful, I am happy to suggest a short line that fits naturally into the post.

Either way, great article.

Best,
[Your Name]
""",
    "keyword_mapping": """
You are an expert SEO strategist for a premium sports wall art brand called Sports Cave.

Analyse Google Search Console keyword data and extract ONLY high-intent buyer keywords.

IMPORTANT RULES:
- We ONLY want keywords that indicate someone is looking to BUY wall art
- DO NOT include informational or research-based keywords
- DO NOT include irrelevant or low-intent keywords

BUYER INTENT KEYWORDS MUST:
- Include wall art, poster, print, framed, decor
OR
- Include player name plus wall art intent
OR
- Include man cave or best buyer intent modifiers

REJECT:
- who is michael jordan
- jordan stats
- nba history
- anything informational

TASK:
1. Analyse keyword data
2. Filter low-intent keywords
3. Select only best keywords for Sports Cave
4. Categorise into Product, Collection, Blog

OUTPUT:
Category | Keyword | Type | Priority | Notes

Only include keywords that could realistically lead to purchase. Do not explain. Only return the table.
""",
    "product_meta": """
Rewrite the following product meta title and meta description for SEO.

Requirements:
- Include this keyword naturally: [PASTE KEYWORD]
- Keep it premium, emotional, and nostalgic
- Do NOT sound robotic or keyword stuffed
- Make it feel like a collector piece
- Focus on curiosity and desire

Current Meta Title:
[PASTE]

Current Meta Description:
[PASTE]
""",
    "product_description": """
Take the product description below and subtly integrate the following keyword:

Keyword: [PASTE KEYWORD]

Rules:
- Keep original emotional tone and storytelling exactly the same
- Do NOT rewrite or change structure
- Only add keyword naturally where it fits
- Do NOT force it
- Maintain nostalgic, premium collector feel
- Still sound human

Product Description:
[PASTE]
""",
    "collection_description": """
Rewrite the following collection description to include this keyword:

Keyword: [PASTE]

Rules:
- Keep premium and minimal
- Maintain emotional and collector tone
- Do NOT keyword stuff
- Make it flow naturally
- Keep it clean and high-end

Current Collection Description:
[PASTE]
""",
    "blog_optimisation": """
Rewrite the blog post below to naturally include the following keyword:

Keyword: [PASTE]

Rules:
- Maintain storytelling tone like a sports documentary
- Do NOT make it sound SEO-focused
- Keep emotional and engaging
- Add keyword naturally 2-3 times max
- Do NOT force placement
- Keep readability and flow perfect

Blog Post:
[PASTE]
""",
    "blog_topic": """
You are a senior SEO strategist for Sports Cave.

Given this product or collection, suggest 10 blog topics that could attract sports fans and lead them naturally toward Sports Cave products.

Product or collection:
[PASTE]

Rules:
- Prioritise buyer intent
- Use nostalgia, legacy, rivalry, greatness, and man cave culture
- Avoid generic thin topics
- Include the recommended primary keyword

Output:
Topic | Primary keyword | Search intent | Why it fits Sports Cave
""",
    "blog_writing": """
You are a senior sports journalist writing for Sports Cave.

Write a premium SEO blog article that feels like Sports Illustrated, ESPN, or The Athletic - not generic AI content.

Topic:
[PASTE]

Primary keyword:
[PASTE]

Requirements:
- 1100-1700 words
- H1 title
- Strong intro
- 5-7 H2 sections
- Optional H3s
- One useful bullet list
- Natural internal reference to Sports Cave near the final third
- Final conclusion on legacy and why the moment matters
- Emotional, nostalgic, human, and collector-aware
- No keyword stuffing
""",
    "blog_html": """
Convert this blog post into Shopify-ready HTML.

Rules:
- Preserve the tone and meaning
- Use clean H1, H2, H3, p, ul, li tags
- Add internal links only inside the blog body
- Do not add links to product pages unless clearly relevant
- Add image placeholders where useful
- Keep the article premium and easy to read

Internal link options:
Homepage: https://www.sportscaveshop.com
Soccer: https://www.sportscaveshop.com/collections/soccer
NBA: https://www.sportscaveshop.com/collections/nba
Cricket: https://www.sportscaveshop.com/collections/cricket
Motor Racing: https://www.sportscaveshop.com/collections/motor-racing-wall-art
Combat Sports: https://www.sportscaveshop.com/collections/combat-art
Horse Racing: https://www.sportscaveshop.com/collections/horse-racing-wall-art
Tennis: https://www.sportscaveshop.com/collections/tennis-wall-art

Blog:
[PASTE]
""",
    "image_optimisation": """
Create SEO image file names and alt text for this Sports Cave blog.

Blog topic:
[PASTE]

Images:
[PASTE IMAGE DESCRIPTIONS]

Output:
Image number | File name | Alt text

Rules:
- File names lowercase with hyphens
- Alt text natural and descriptive
- Include keyword only if natural
- No stuffing
""",
    "blog_meta": """
Create SEO meta tags for this Sports Cave blog.

Blog title:
[PASTE]

Primary keyword:
[PASTE]

Requirements:
- Meta title under 60 characters where possible
- Meta description under 155 characters where possible
- Premium, emotional, click-worthy
- Natural keyword use
- No clickbait

Output:
Meta title:
Meta description:
URL handle:
""",
    "blog_tags": """
Generate Shopify blog tags for this Sports Cave article.

Blog topic:
[PASTE]

Rules:
- 8-12 tags
- Include sport, athlete/team if provided, country focus, content type, and theme
- Keep tags clean and useful

Output a comma-separated list only.
""",
    "alt_text": """
Create Shopify image alt text for this Sports Cave product.

Product name:
[PASTE]

Artwork/image notes:
[PASTE]

Rules:
- Natural and descriptive
- Include sport/player/team only when true
- Include wall art intent only once
- No keyword stuffing
- No fake claims

Output 5 alt text options.
""",
    "internal_linking": """
Suggest internal links for this Sports Cave product or blog.

Page/product:
[PASTE]

Relevant collections/products:
[PASTE]

Rules:
- Only suggest links that genuinely help the shopper
- Use natural anchor text
- Keep collector/man cave tone
- No spammy exact-match anchor stuffing

Output:
Anchor text | Destination | Where to place it | Reason
""",
})


SOCIAL_PROMPTS = LazyPromptLibrary(lambda: {
    "Instagram caption prompt": """
Write Instagram captions for this Sports Cave product.

Product:
[PASTE]

Fan base / sport / story:
[PASTE]

Tone:
- premium
- nostalgic
- collector-driven
- short and human
- not generic poster copy

Output:
1. Launch caption
2. Scarcity caption
3. Fan pride caption
4. Man cave caption
5. Final editions caption
""",
    "Story prompt": """
Create a 5-frame Instagram Story sequence for this Sports Cave product.

Product:
[PASTE]

Use:
- short frame text
- collector urgency
- swipe/tap CTA
- no overexplaining

Output:
Frame 1 text:
Frame 2 text:
Frame 3 text:
Frame 4 text:
Frame 5 text:
""",
    "Reel cover prompt": """
Write Reel cover text options for a Sports Cave product video.

Product:
[PASTE]

Rules:
- maximum 5 words
- bold fan emotion
- collector feel
- no clickbait

Output 12 options.
""",
    "Launch post prompt": """
Create a launch post for this new Sports Cave limited edition.

Product:
[PASTE]

Details:
[PASTE edition limit, sport, fan base]

Output:
- short caption
- longer caption
- 8 hashtags
- CTA
""",
    "Final editions post prompt": """
Write a final editions social post.

Product:
[PASTE]

Remaining editions:
[PASTE]

Rules:
- urgent but premium
- no fake panic
- collector tone
- clear CTA

Output 3 variants.
""",
})


EMAIL_PROMPTS = LazyPromptLibrary(lambda: {
    "Product launch email prompt": """
Write a product launch email for Sports Cave.

Product:
[PASTE]

Audience:
[PASTE]

Output:
Subject lines: 5
Preview text: 3
Email body:
CTA:
""",
    "Abandoned cart email prompt": """
Write an abandoned cart email for a Sports Cave shopper.

Product/cart context:
[PASTE]

Tone:
- helpful
- collector-focused
- no cheap discount pressure

Output:
Subject lines: 5
Preview text: 3
Email body:
CTA:
""",
    "Browse abandonment prompt": """
Write a browse abandonment email for someone who viewed Sports Cave wall art.

Collection/product viewed:
[PASTE]

Output:
Subject lines: 5
Preview text: 3
Email body:
CTA:
""",
    "Collector drop email prompt": """
Write a collector drop email announcing a numbered Sports Cave release.

Drop:
[PASTE]

Edition limit:
[PASTE]

Output:
Subject lines: 5
Preview text: 3
Email body:
CTA:
""",
    "Father's Day/gift email prompt": """
Write a Sports Cave gift email for Father's Day or gift season.

Products/collection:
[PASTE]

Rules:
- premium gift feel
- man cave angle
- not cheesy

Output:
Subject lines: 8
Preview text: 4
Email body:
CTA:
""",
})


def render_meta_ads_section():
    st.subheader("Meta Ads")
    st.caption("Copy/paste prompt library only. No live AI calls.")
    au_tab, usa_tab, universal_tab, checklist_tab = st.tabs(
        ["Australia", "USA", "Universal Ad Copy", "Quality Checklist"]
    )

    with au_tab:
        st.markdown("### Australian Meta Ads SOP")
        st.caption("Nostalgia, rivalry, man cave, Aussie pride, and numbered collector drops.")
        render_marketing_card(
            "Goal",
            "Make the fan feel: 'That belongs on my wall.' Keep the copy short, nostalgic, Australian, and collector-led.",
        )
        with st.expander("Winning AU themes", expanded=True):
            st.write("Nostalgia: History, Framed; Captured Forever; Final Bow; Centre Court Silence.")
            st.write("Identity: Gooner Pride; Built for Real Man Caves; For The Fans; Real Fans Remember.")
            st.write("Collector value: Limited Edition; 100 Numbered Editions; Numbered Run; Collector Piece.")
            st.write("Australian/man cave: Man Cave Ready; Clubroom Ready; Aussie Icon; Aussie-Made; Built Proper.")
            st.write("Scarcity: Once They're Gone; Only 100 Made; Strictly Limited; Final Editions.")
            st.warning("Avoid Premium Display, High Quality Art, Best Poster, Shop Now, Great Gift, too clever, too American, or too polished.")
        render_prompt_block("AU Carousel Card Copy Prompt", META_PROMPTS["au_carousel"], "au-carousel")
        render_prompt_block("AU Primary Text Prompt", META_PROMPTS["au_primary"], "au-primary")
        render_prompt_block("AU Motorsport Nostalgia Prompt", META_PROMPTS["au_motorsport"], "au-motorsport")

    with usa_tab:
        st.markdown("### USA Meta Ads SOP")
        st.caption("Identity, legacy debates, collector exclusivity, fan cave culture, and sports hero obsession.")
        render_marketing_card(
            "Goal",
            "Make the product feel like legacy on the wall, not a normal poster. Use fan identity, rivalry, and collector scarcity.",
        )
        with st.expander("Best USA angles", expanded=True):
            st.write("Gift for Sports Fans Who Have Everything")
            st.write("Limited Edition Collector Series")
            st.write("Man Cave Upgrade / Fan Cave Ready")
            st.write("Legacy Debate / Mentality / Rivalry / Greatest Era")
            st.write("Championship Memory / Numbered Collector Drop")
            st.warning("Avoid Australian slang, generic sports poster wording, long card text, and corporate phrasing.")
        render_meta_url_parameters_block()
        render_prompt_block(
            "USA Generic Instant Experience Master Prompt",
            META_PROMPTS["usa_master"],
            "usa-master-instant-experience",
            when_to_use="Use this for any USA Meta Instant Experience creative brief. Upload the product image first, then paste this prompt.",
            height=360,
        )
        render_prompt_block("USA Carousel Card Copy Prompt", META_PROMPTS["usa_carousel"], "usa-carousel")
        render_prompt_block("USA Primary Text Prompt", META_PROMPTS["usa_primary"], "usa-primary")
        render_prompt_block("USA NBA Rivalry / Mentality Prompt", META_PROMPTS["usa_nba"], "usa-nba")

    with universal_tab:
        render_prompt_block("Full Meta Ad Pack Prompt", META_PROMPTS["full_meta"], "full-meta", height=260)

    with checklist_tab:
        st.markdown("### Meta Ads Quality Checklist")
        checks = (
            "Does every carousel headline fit on mobile?",
            "Does every description fit on mobile?",
            "Does each card create a different buying reason?",
            "Does copy feel like collector art, not a poster?",
            "Is nostalgia or identity clear early?",
            "Is scarcity clear by final card?",
            "Would the target country understand the tone?",
            "Is anything too generic, too long, too polished, or AI-sounding?",
            "Is there a clear CTA?",
            "Does it match the true fan base?",
        )
        render_copy_text_button("\n".join(f"- {item}" for item in checks), "meta-quality-checklist", "Copy Checklist")
        for item in checks:
            st.checkbox(item, key=f"meta-check-{safe_filename_part(item)}")
        st.info("Carousel cards are micro-hooks. Primary text and landing pages do the deeper selling.")


def render_seo_section():
    st.subheader("SEO")
    st.caption("Practical operating manual for commercial intent, authority, and long-term organic sales.")
    tabs = st.tabs(
        [
            "SEO Overview",
            "Citations",
            "Backlinks",
            "Keyword Mapping",
            "SEO Execution",
            "Blog Creation",
            "Blog Editing",
            "Prompt Library",
            "Daily / Weekly Checklist",
        ]
    )

    with tabs[0]:
        st.markdown("### SEO Overview")
        st.write("Primary goal: drive organic sales to Sports Cave products and collections.")
        st.write("Secondary goals: build authority, support paid ads with trust, and rank for high-intent sports keywords globally.")
        st.info("Primary markets: Australia, United States, United Kingdom. Secondary: Canada and New Zealand.")
        with st.expander("Non-negotiables", expanded=True):
            for item in (
                "Quality beats quantity",
                "Relevance beats volume",
                "Consistency beats speed",
                "Structure beats creativity",
                "Authority compounds over time",
                "No vanity traffic",
                "One primary keyword per page",
                "No keyword stuffing",
                "Write for sports fans, not Google",
                "Human edit is mandatory",
            ):
                st.write(f"- {item}")
        st.warning("If the task is not covered by the SEO SOP, stop and ask.")

    with tabs[1]:
        st.markdown("### Citations and Business Listings")
        st.caption("Build trust by getting Sports Cave listed on reputable platforms with the website URL visible.")
        st.code(
            "Business name: Sports Cave\nWebsite: https://www.sportscaveshop.com\n"
            "Description: Sports Cave creates premium sports wall art for fans, collectors, and man caves world-wide. "
            "Featuring iconic sporting moments from basketball, cricket, motorsports, and more.",
            language=None,
        )
        with st.expander("Workflow", expanded=True):
            st.write("1. Open SEO Citation Tracker")
            st.write("2. Go to Citations TO DO")
            st.write("3. Pick next platform")
            st.write("4. Create profile/listing")
            st.write("5. Add website URL")
            st.write("6. Upload logo if available")
            st.write("7. Update tracker")
            st.write("8. Move completed row to Completed Citations")
        st.warning("No shortened links, paid links, spam directories, or unsafe platforms. If not logged, it does not count.")
        st.write("Weekly target: 10-15 citations per week.")

    with tabs[2]:
        st.markdown("### Backlink Acquisition")
        st.caption("Authority-only link building for Sports Cave.")
        st.info("One strong link is better than fifty weak ones.")
        with st.expander("Allowed and banned opportunities", expanded=True):
            st.write("Allowed: sports blogs, motorsport blogs, cricket blogs, soccer blogs, NBA fan blogs, man cave blogs, home decor blogs, gift guides, collectibles and memorabilia blogs.")
            st.write("Secondary: relevant forums and communities where links are allowed and natural.")
            st.warning("Hard ban: PBNs, Fiverr links, paid marketplaces, blog comment spam, signatures, auto-generated sites, and SEO-only sites.")
        st.write("Anchor mix: 70% brand/naked, 20% descriptive, max 10% exact keyword.")
        render_prompt_block("Site Qualification Prompt", SEO_PROMPTS["site_qualification"], "seo-site-qualification")
        render_prompt_block("Backlink Outreach Template", SEO_PROMPTS["outreach"], "seo-outreach")

    with tabs[3]:
        st.markdown("### Keyword Extraction and Mapping")
        st.caption("Use GSC exports to find buyer-intent keywords and map them to products, collections, or blogs.")
        st.warning("We are not brainstorming keywords. We extract real data and reject informational searches.")
        render_prompt_block("Keyword Mapping Prompt", SEO_PROMPTS["keyword_mapping"], "seo-keyword-mapping", height=260)

    with tabs[4]:
        st.markdown("### SEO Execution System")
        st.caption("Apply selected keywords without ruining Sports Cave's emotional premium tone.")
        st.info("Weekly flow: 3 product optimisations, 2 collection optimisations, 2 blog optimisations/creations, 3 distribution actions.")
        render_prompt_block("Product Meta Tags Prompt", SEO_PROMPTS["product_meta"], "seo-product-meta")
        render_prompt_block("Product Description Keyword Prompt", SEO_PROMPTS["product_description"], "seo-product-description")
        render_prompt_block("Collection Description Prompt", SEO_PROMPTS["collection_description"], "seo-collection-description")
        render_prompt_block("Blog Optimisation Prompt", SEO_PROMPTS["blog_optimisation"], "seo-blog-optimisation")
        st.caption("Distribution: Pinterest title uses the keyword; Reddit/forums should read like a fan; YouTube Shorts title includes the keyword.")

    with tabs[5]:
        st.markdown("### Blog Content Creation")
        st.caption("Create premium sports journal-style articles that attract traffic and funnel readers to Sports Cave.")
        with st.expander("Workflow", expanded=True):
            st.write("1. Select product or collection")
            st.write("2. Find best blog topic using ChatGPT")
            st.write("3. Generate SEO blog article")
            st.write("4. Human quality check")
            st.write("5. Embed video if available")
            st.write("6. Send to Blog Editing SOP")
        render_prompt_block("Blog Topic Research Prompt", SEO_PROMPTS["blog_topic"], "seo-blog-topic")
        render_prompt_block("SEO Blog Writing Prompt", SEO_PROMPTS["blog_writing"], "seo-blog-writing", height=280)

    with tabs[6]:
        st.markdown("### Blog Editing and Internal Linking")
        st.caption("Upgrade blog posts into Shopify-ready HTML with internal links, image placeholders, and meta tags.")
        st.warning("Internal linking is only done inside blog posts unless Nathan instructs otherwise.")
        render_prompt_block("Blog Editing HTML Master Prompt", SEO_PROMPTS["blog_html"], "seo-blog-html", height=300)
        render_prompt_block("Blog Image Optimisation Prompt", SEO_PROMPTS["image_optimisation"], "seo-image-optimisation")
        render_prompt_block("Blog Meta Tag Prompt", SEO_PROMPTS["blog_meta"], "seo-blog-meta")
        render_prompt_block("Blog Tag Generation Prompt", SEO_PROMPTS["blog_tags"], "seo-blog-tags")

    with tabs[7]:
        st.markdown("### SEO Prompt Library")
        groups = (
            ("Keyword Research", (("Keyword Mapping", "keyword_mapping"),)),
            ("Product SEO", (("Product Meta Tags", "product_meta"), ("Product Description Keyword", "product_description"))),
            ("Collection SEO", (("Collection Description", "collection_description"),)),
            ("Blog Creation", (("Blog Topic Research", "blog_topic"), ("SEO Blog Writing", "blog_writing"))),
            ("Blog Editing", (("Blog Editing HTML", "blog_html"), ("Image Optimisation", "image_optimisation"), ("Meta Tags", "blog_meta"), ("Blog Tags", "blog_tags"))),
            ("Backlinks", (("Site Qualification", "site_qualification"), ("Outreach", "outreach"))),
        )
        for group_name, prompts in groups:
            with st.expander(group_name, expanded=False):
                for prompt_title, prompt_key in prompts:
                    render_prompt_block(prompt_title, SEO_PROMPTS[prompt_key], f"library-{prompt_key}")

    with tabs[8]:
        st.markdown("### Daily / Weekly Checklist")
        checklist_columns = st.columns(3)
        daily = ("Citation work", "Backlink prospecting", "Outreach", "Pinterest/Reddit/YouTube distribution", "Tracker updates")
        weekly = ("Export GSC keywords", "Run keyword mapping", "Optimise 3 products", "Optimise 2 collections", "Create/improve 2 blogs", "Complete 10-15 outreach emails", "Publish/report progress")
        monthly = ("Technical SEO check", "Page speed review", "Blog/internal link review", "Reporting")
        for item in daily:
            checklist_columns[0].checkbox(item, key=f"seo-daily-{safe_filename_part(item)}")
        for item in weekly:
            checklist_columns[1].checkbox(item, key=f"seo-weekly-{safe_filename_part(item)}")
        for item in monthly:
            checklist_columns[2].checkbox(item, key=f"seo-monthly-{safe_filename_part(item)}")
        st.info("End-of-day report: work completed, links updated, citations completed, outreach sent, live links earned, blockers.")
        st.warning("If not tracked, it does not count.")


def render_simple_seo_section():
    st.subheader("SEO")
    st.caption("Manual prompt library for product SEO, metadata, image alt text, blogs, and internal links. No SEO APIs run here.")
    render_marketing_card(
        "SEO workflow",
        "Paste the product/page context into one prompt at a time. Keep the final copy premium, human, and buyer-intent focused.",
    )
    prompt_pairs = (
        ("Product SEO Prompt", SEO_PROMPTS["product_description"]),
        ("Meta Title / Description Prompt", SEO_PROMPTS["product_meta"]),
        ("Alt Text Prompt", SEO_PROMPTS["alt_text"]),
        ("Blog Idea Prompt", SEO_PROMPTS["blog_topic"]),
        ("Internal Linking Prompt", SEO_PROMPTS["internal_linking"]),
    )
    render_prompt_collection(prompt_pairs, "seo-simple")


def render_social_media_section():
    st.subheader("Social Media")
    st.caption("Copy-ready social prompts for launch posts, captions, stories, reels, and final-edition urgency.")
    render_marketing_card(
        "Social rule",
        "Lead with fan emotion, legacy, scarcity, or man cave pride. Keep every line shorter than it feels in the draft.",
    )
    render_prompt_collection(tuple(SOCIAL_PROMPTS.items()), "social")


def render_email_marketing_section():
    st.subheader("Email Marketing")
    st.caption("Manual email prompt library for Sports Cave launches, carts, browse recovery, collector drops, and gifting.")
    render_marketing_card(
        "Email rule",
        "Make the collector feel seen first, then sell. Avoid cheap discount pressure unless Nathan specifically asks for a promotion.",
    )
    render_prompt_collection(tuple(EMAIL_PROMPTS.items()), "email")


def render_marketing_factory_page():
    started = time.perf_counter()
    inject_marketing_factory_styles()
    st.title("Marketing Factory")
    st.caption("Prompt and SOP hub for Sports Cave operators. No live AI generation.")
    meta_tab, seo_tab, social_tab, email_tab = st.tabs(
        ["Meta Ads", "SEO", "Social Media", "Email Marketing"]
    )
    with meta_tab:
        render_meta_ads_section()
    with seo_tab:
        render_simple_seo_section()
    with social_tab:
        render_social_media_section()
    with email_tab:
        render_email_marketing_section()
    perf_log(f"PERF MarketingFactory total={(time.perf_counter() - started):.3f}s prompt_load=rendered")


def render_developer_widget_status(shopify_config):
    st.markdown("**Widget Status**")
    st.caption("Shopify widgets read product metafields only. Supabase remains the source of truth for edition counters.")
    if not supabase_backend.is_configured():
        st.warning("DATABASE_URL is required before loading widget status.")
        return

    controls = st.columns([1.1, 0.85, 0.85])
    widget_search = controls[0].text_input(
        "Widget status search",
        placeholder="Search product or handle",
        key="dev-widget-status-search",
        label_visibility="collapsed",
    )
    widget_limit = controls[1].selectbox(
        "Rows",
        [50, 100, 200],
        index=1,
        key="dev-widget-status-limit",
        label_visibility="collapsed",
    )
    if controls[2].button(
        "Sync Edition Display",
        disabled=not shopify_config["configured"],
        key="dev-widget-sync-all",
        use_container_width=True,
    ):
        progress = st.progress(0, text="Syncing Shopify edition display metafields...")
        try:
            def update_widget_progress(count):
                progress.progress(min(count / max(int(widget_limit), 1), 0.99), text=f"Synced {count} products...")

            result = supabase_backend.sync_all_product_edition_metafields(
                shopify_config,
                search=widget_search,
                limit=int(widget_limit),
                progress_callback=update_widget_progress,
            )
            progress.progress(1.0, text="Shopify edition display sync complete.")
            if result.get("errors"):
                st.warning(
                    f"Synced {result.get('synced', 0)} of {result.get('attempted', 0)} products. "
                    f"First issue: {result['errors'][0]}"
                )
            else:
                st.success(f"Synced {result.get('synced', 0)} product display records.")
        except Exception as error:
            progress.empty()
            st.error("Widget display sync failed.")
            st.exception(error)

    try:
        products = supabase_backend.list_edition_products(search=widget_search, limit=int(widget_limit))
    except Exception as error:
        st.error("Could not load widget status from Supabase.")
        st.exception(error)
        return

    if not products:
        st.info("No products found for this widget status view.")
        return

    rows = []
    for product in products:
        payload = supabase_backend.calculate_product_edition_metafield_values(product)
        rows.append(
            {
                "Product": product.get("product_title") or "Untitled product",
                "Handle": product.get("shopify_handle") or "",
                "Next": supabase_backend.format_edition_display_number(
                    payload.get("next_edition_number"),
                    payload.get("edition_total"),
                ),
                "Remaining": payload.get("remaining_count"),
                "Widget text": payload.get("edition_display_text") or "",
                "Metafields": product.get("metafields_sync_status") or "Never Synced",
                "Last sync": format_updated_at(product.get("metafields_synced_at")),
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_settings_page(app_version, database_path, password_status):
    st.title("Developer")
    st.caption("Diagnostics, connection checks, imports, and admin tools for Sports Cave OS.")
    assets_notice = st.session_state.pop("supabase_assets_notice", None)
    if assets_notice:
        st.success(assets_notice)
    shopify_config = shopify_sync.get_config()
    shopify_token_status = shopify_sync.get_token_status(shopify_config)
    shopify_summary = db.get_shopify_summary()
    order_summary = db.get_shopify_order_summary()
    certificate_summary = db.get_certificate_summary()
    latest_shopify_run = db.get_latest_shopify_sync_run()
    latest_order_run = db.get_latest_shopify_order_sync_run()
    supabase_enabled = supabase_backend.is_configured()
    database_health = supabase_backend.database_status(run_schema_check=supabase_enabled)
    supabase_counts = {}
    supabase_sync_state = {}
    if supabase_enabled:
        try:
            supabase_counts = supabase_backend.persistence_counts()
            supabase_sync_state = supabase_backend.get_sync_state()
        except Exception:
            supabase_counts = {}
            supabase_sync_state = {}
    products_saved_count = supabase_counts.get("shopify_products", shopify_summary["total"])
    orders_saved_count = supabase_counts.get("shopify_orders", order_summary["total"])
    edition_assignments_saved_count = supabase_counts.get("edition_orders", 0)
    certificates_saved_count = supabase_counts.get("certificates", certificate_summary["generated"])
    order_fetch_duration_ms = int(supabase_sync_state.get("last_order_fetch_duration_ms") or 0)
    orders_imported_count = int(supabase_sync_state.get("last_orders_imported_count") or 0)
    assignments_created_count = int(supabase_sync_state.get("last_assignments_created_count") or 0)
    last_product_fetch = (
        format_updated_at(supabase_sync_state.get("last_successful_product_sync_at"))
        if supabase_sync_state.get("last_successful_product_sync_at")
        else format_updated_at(shopify_summary["last_synced_at"]) if shopify_summary["last_synced_at"] else "Never"
    )
    last_order_fetch = (
        format_updated_at(supabase_sync_state.get("last_successful_order_fetch_at") or supabase_sync_state.get("last_successful_order_sync_at"))
        if (supabase_sync_state.get("last_successful_order_fetch_at") or supabase_sync_state.get("last_successful_order_sync_at"))
        else format_updated_at(order_summary["last_synced_at"]) if order_summary["last_synced_at"] else "Never"
    )
    last_sync_status = "Never"
    if latest_shopify_run:
        last_sync_status = (
            "Success"
            if latest_shopify_run["status"] == "Complete"
            else latest_shopify_run["status"]
        )
    order_sync_status = "Never"
    if latest_order_run:
        order_sync_status = "Success" if latest_order_run["status"] == "Complete" else latest_order_run["status"]
    order_fetch_status = supabase_sync_state.get("last_order_fetch_status") or order_sync_status or "Never"
    if not order_fetch_status:
        order_fetch_status = order_sync_status
    settings = (
        ("Database mode", database_health.get("mode") or ("Supabase/Postgres" if supabase_enabled else "SQLite fallback")),
        ("Database connected", "Yes" if database_health.get("connected") else "No"),
        ("Database host/project", database_health.get("host_reference") or "Not configured"),
        ("Database tables ready", "Yes" if database_health.get("tables_ready") else "No"),
        ("Last database check", format_updated_at(database_health.get("checked_at")) if database_health.get("checked_at") else "Never"),
        ("DATABASE_URL source", database_health.get("url_source") or "Missing"),
        ("Shopify connection", "Configured" if shopify_config["configured"] else "Not configured"),
        ("Shopify store domain", "Configured" if shopify_config["store_domain"] else "Missing"),
        ("Shopify API version", "Configured" if shopify_config["api_version"] else "Missing"),
        ("Shopify auth mode", shopify_config["auth_mode"]),
        ("Products saved", str(products_saved_count)),
        ("Orders cached", str(orders_saved_count)),
        ("Edition assignments saved", str(edition_assignments_saved_count)),
        ("Certificates saved", str(certificates_saved_count)),
        ("Missing index warnings", "None detected; safe indexes are created on schema check"),
        ("Last product sync status", last_sync_status),
        ("Last order fetch status", order_fetch_status),
        ("Last product fetch", last_product_fetch),
        ("Last order fetch", last_order_fetch),
        ("Last fetch duration", f"{order_fetch_duration_ms} ms" if order_fetch_duration_ms else "Never"),
        ("Last imported count", str(orders_imported_count)),
        ("Last assignments created", str(assignments_created_count)),
        ("Certificate PDFs generated", str(certificate_summary["generated"])),
        (
            "Limited edition backend",
            "Supabase/Postgres active" if supabase_enabled else "Local cache fallback",
        ),
        ("Shopify webhook endpoint", "/webhooks/shopify/orders-paid"),
        (
            "Last token refresh",
            format_updated_at(shopify_token_status["last_refresh"])
            if shopify_token_status["last_refresh"]
            else "Never",
        ),
        ("Google Drive mode", "Link-based file hub"),
        ("Full Google Drive API sync", "Coming later"),
        ("Drive Picker", "Coming later"),
        ("Certificate system", "Rough local PDF generation active"),
    )
    columns = st.columns(2)
    for index, (label, value) in enumerate(settings):
        with columns[index % 2]:
            with st.container(border=True):
                st.markdown(f"**{label}**")
                st.caption(value)

    if database_health.get("warning"):
        st.warning(database_health["warning"])
    if supabase_enabled and (shopify_summary.get("total") or order_summary.get("total")) and not (products_saved_count or orders_saved_count):
        st.warning("Postgres is active but existing SQLite data has not been imported. Local SQLite data was left untouched.")
    if database_health.get("error_type"):
        st.caption(f"Database diagnostic error type: {database_health['error_type']}. No connection string or secret was displayed.")

    st.info(
        "Sports Cave OS reads Shopify products and orders only when a worker clicks Sync. "
        "Client credentials are exchanged for a temporary in-memory token only at that time. "
        "Edition numbers and certificates come from Sports Cave OS; Shopify metafields are display only."
    )
    st.write(f"**Local database:** `{database_path}`")
    st.write(f"**Password protection:** {password_status}")
    st.write(f"**App version:** {app_version}")

    render_r2_storage_panel()

    with st.expander("Admin test tools", expanded=False):
        test_columns = st.columns(3)
        if test_columns[0].button("Test Supabase connection", disabled=not supabase_backend.is_configured(), use_container_width=True):
            try:
                result = supabase_backend.test_connection()
                st.success("Supabase connection OK.")
                st.caption(f"Server time: {result.get('server_time')}")
            except Exception as error:
                st.error("Supabase connection failed.")
                st.caption(f"Error type: {error.__class__.__name__}. Check Render DATABASE_URL, SSL mode, and Supabase network settings.")
        if test_columns[1].button("Test Shopify connection", disabled=not shopify_config["configured"], use_container_width=True):
            try:
                result = shopify_sync.test_connection(config=shopify_config)
                st.success(f"Shopify connection OK: {result.get('name')}")
            except Exception as error:
                st.error("Shopify connection failed.")
                st.exception(error)
        if test_columns[2].button(
            "Test product update sync",
            disabled=not (shopify_config["configured"] and supabase_backend.is_configured()),
            use_container_width=True,
        ):
            try:
                result = supabase_backend.sync_shopify_products_to_supabase(shopify_config, mode="incremental")
                if result.get("skipped"):
                    st.warning(result.get("message"))
                else:
                    st.success(f"Synced {result['products_processed']} updated Shopify products.")
            except Exception as error:
                st.error("Product sync test failed.")
                st.exception(error)
        if supabase_backend.is_configured():
            try:
                edition_orders = supabase_backend.list_edition_orders(limit=100)
            except Exception:
                edition_orders = []
            if edition_orders:
                options = [
                    f"{item.get('order_name') or item.get('shopify_order_id')} | "
                    f"{item.get('product_title')} | #{item.get('edition_number')} | {item.get('id')}"
                    for item in edition_orders
                ]
                selected = st.selectbox("Certificate test edition order", options)
                selected_id = selected.rsplit("|", 1)[-1].strip()
                if st.button("Test certificate generation", use_container_width=True):
                    try:
                        path = supabase_backend.generate_certificate_for_edition_order(selected_id)
                        st.success("Certificate generated.")
                        st.caption(path)
                    except Exception as error:
                        st.error("Certificate generation failed.")
                        st.exception(error)
            else:
                st.caption("No edition orders are available for certificate generation testing yet.")

    with st.expander("Developer Tools", expanded=False):
        dev_tabs = st.tabs([
            "Shopify Diagnostics",
            "Shopify Limited Edition Setup",
            "Sync Tools",
            "Metafield Bridge",
            "Product Assets / PSD Links",
            "Certificates",
        ])
        with dev_tabs[0]:
            st.caption("Manual Shopify connection check. This only runs a token/API test when you click the button.")
            render_shopify_scope_diagnostics(shopify_config, "settings-dev")
        with dev_tabs[1]:
            st.subheader("Shopify Limited Edition Setup")
            st.caption("Developer-only setup for the Shopify product metafields used by Edition Ops.")
            setup_cols = st.columns([1, 1, 2])
            if setup_cols[0].button(
                "Check Product Metafield Definitions",
                key="settings-edition-ops-check-definitions",
                disabled=not shopify_config["configured"],
                use_container_width=True,
            ):
                try:
                    st.session_state.settings_edition_ops_definitions = (
                        shopify_sync.list_edition_ops_metafield_definitions(config=shopify_config)
                    )
                except Exception as error:
                    st.error("Could not check Edition Ops definitions.")
                    st.exception(error)
            if setup_cols[1].button(
                "Create Missing Product Metafield Definitions",
                key="settings-edition-ops-create-definitions",
                disabled=not shopify_config["configured"],
                use_container_width=True,
            ):
                try:
                    st.session_state.settings_edition_ops_definitions = (
                        shopify_sync.create_missing_edition_ops_metafield_definitions(config=shopify_config)
                    )
                except Exception as error:
                    st.error("Could not create Edition Ops definitions.")
                    st.exception(error)
            setup_cols[2].caption("Run this only when setting up a new Shopify store or repairing missing product fields.")

            definition_status = st.session_state.get("settings_edition_ops_definitions")
            if definition_status:
                rows = []
                for definition in definition_status.get("definitions") or []:
                    rows.append(
                        {
                            "Name": definition.get("name"),
                            "Namespace / key": f"{definition.get('namespace')}.{definition.get('key')}",
                            "Owner": definition.get("ownerType"),
                            "Type": definition.get("type"),
                            "Status": definition.get("status"),
                        }
                    )
                if rows:
                    st.dataframe(rows, hide_index=True, use_container_width=True)
                for error in definition_status.get("errors") or []:
                    st.error(f"{error.get('namespace')}.{error.get('key')}: {error.get('message')}")

        with dev_tabs[2]:
            st.caption("Protected sync tools. These are not part of the normal VA workflow.")
            if not supabase_backend.is_configured():
                st.warning("DATABASE_URL is required before running sync tools.")
            else:
                try:
                    sync_state = supabase_backend.get_sync_state()
                except Exception:
                    sync_state = {}
                state_columns = st.columns(3)
                state_columns[0].metric(
                    "Last order sync",
                    format_updated_at(sync_state.get("last_successful_order_sync_at"))
                    if sync_state.get("last_successful_order_sync_at")
                    else "Never",
                )
                state_columns[1].metric(
                    "Edition tracking start",
                    format_updated_at(sync_state.get("edition_tracking_start_at"))
                    if sync_state.get("edition_tracking_start_at")
                    else "Not set",
                )
                state_columns[2].metric(
                    "Last product sync",
                    format_updated_at(sync_state.get("last_successful_product_sync_at"))
                    if sync_state.get("last_successful_product_sync_at")
                    else "Never",
                )

                st.markdown("**Initial Full Product Sync**")
                st.caption("Use this once when Supabase has no products. It upserts products and creates missing edition records without resetting edition counters.")
                full_confirm = st.checkbox(
                    "I understand this fetches the Shopify product library but does not reset edition numbers.",
                    key="dev-confirm-full-product-sync",
                )
                if st.button(
                    "Run Initial Full Product Sync",
                    disabled=not (shopify_config["configured"] and full_confirm),
                    key="dev-full-product-sync",
                    use_container_width=True,
                ):
                    progress = st.progress(0, text="Running initial full product sync...")
                    try:
                        def update_full_product_progress(count):
                            progress.progress(min(count / 1000, 0.99), text=f"Loaded {count} products...")

                        result = supabase_backend.sync_shopify_products_to_supabase(
                            shopify_config,
                            progress_callback=update_full_product_progress,
                            mode="full",
                        )
                        progress.progress(1.0, text="Initial full product sync complete.")
                        st.success(f"Synced {result.get('products_processed', 0)} products.")
                    except Exception as error:
                        progress.empty()
                        st.error("Initial full product sync failed.")
                        st.exception(error)

                st.markdown("**Historical Order Backfill**")
                st.caption("Only use this if you intentionally want previous paid Shopify orders assigned edition records.")
                backfill_confirm = st.checkbox(
                    "This will assign edition numbers to previous paid Shopify orders that do not already have edition records. Continue?",
                    key="dev-confirm-historical-backfill",
                )
                if st.button(
                    "Run Historical Order Backfill",
                    disabled=not (shopify_config["configured"] and backfill_confirm),
                    key="dev-historical-order-backfill",
                    use_container_width=True,
                ):
                    try:
                        result = supabase_backend.sync_shopify_orders_to_supabase(
                            shopify_config,
                            historical_backfill=True,
                            query="financial_status:paid",
                            max_orders=500,
                        )
                        st.success(
                            f"Backfill checked {result.get('orders_seen', 0)} orders and assigned "
                            f"{result.get('assignments_created', 0)} edition records."
                        )
                    except Exception as error:
                        st.error("Historical order backfill failed.")
                        st.exception(error)

                st.markdown("**Reset Sync Timestamps**")
                reset_confirm = st.checkbox(
                    "Reset incremental sync timestamps and restart edition tracking from now.",
                    key="dev-confirm-reset-sync-timestamps",
                )
                if st.button(
                    "Reset Sync Timestamps",
                    disabled=not reset_confirm,
                    key="dev-reset-sync-timestamps",
                    use_container_width=True,
                ):
                    try:
                        supabase_backend.reset_incremental_sync_timestamps()
                        st.success("Sync timestamps reset. Normal order sync will start from now with the lookback buffer.")
                    except Exception as error:
                        st.error("Could not reset sync timestamps.")
                        st.exception(error)

                st.markdown("**Reset all edition counters to 0 sold**")
                st.caption(
                    "Sets every active product/run to Next #1 and Latest sent 0. "
                    "Historical orders, certificates, totals, PSD links, and Prodigi links are kept."
                )
                edition_reset_confirm = st.text_input(
                    "Type RESET EDITIONS to enable this reset",
                    key="dev-reset-editions-confirm",
                    placeholder="RESET EDITIONS",
                )
                if st.button(
                    "Reset all edition counters to 0 sold",
                    disabled=edition_reset_confirm.strip() != "RESET EDITIONS",
                    key="dev-reset-all-editions-zero-sold",
                    use_container_width=True,
                ):
                    try:
                        result = supabase_backend.reset_active_edition_counters_to_zero_sold()
                        st.success(
                            f"Reset {result.get('active_runs_reset', 0)} active edition counters to 0 sold."
                        )
                    except Exception as error:
                        st.error("Could not reset edition counters.")
                        st.exception(error)
        with dev_tabs[3]:
            st.caption("Product metafields are the display source for these storefront snippets. The snippets do not call Sports Cave OS, stock, or variant inventory.")
            bridge_columns = st.columns(3)
            bridge_columns[0].markdown("**Sports Cave Remaining Pill**")
            bridge_columns[0].caption("Reads edition_remaining and edition_total.")
            bridge_columns[1].markdown("**Sports Cave Numbered Edition Bar**")
            bridge_columns[1].caption("Reads edition_next_number and edition_total.")
            bridge_columns[2].markdown("**Safe install path**")
            bridge_columns[2].caption("Copy into a product page custom-liquid block or convert into app blocks later.")
            st.info(
                "No live theme edits are made from this page. App blocks are not scaffolded in this repo yet, so these are paste-ready fallback snippets."
            )
            for snippet in load_edition_widget_liquid_snippets():
                st.markdown(f"**{snippet['label']}**")
                if snippet["code"]:
                    st.caption(str(snippet["path"]))
                    st.text_area(
                        snippet["label"],
                        value=snippet["code"],
                        height=snippet["height"],
                        label_visibility="collapsed",
                    )
                    render_copy_text_button(
                        snippet["code"],
                        f"settings-{safe_filename_part(snippet['label'])}-snippet",
                        f"Copy {snippet['label']}",
                    )
                else:
                    st.warning(f"{snippet['label']} snippet file is missing from the repo.")
            widget_code, snippet_path = load_edition_widget_liquid()
            if widget_code and snippet_path.exists():
                st.caption("Wrapper render line for themes where both snippet files are installed.")
                st.text_area(
                    "sports-cave-edition-widget.liquid",
                    value=widget_code,
                    height=90,
                    label_visibility="collapsed",
                )
                render_copy_text_button(
                    widget_code,
                    "settings-metafield-widget-snippet",
                    "Copy Both Widgets Wrapper",
                )
            st.divider()
            render_developer_widget_status(shopify_config)
        with dev_tabs[4]:
            st.caption("Import and manage Google Drive PSD links in Supabase product_assets. No PSD files are uploaded or stored.")
            if not supabase_backend.is_configured():
                st.warning("DATABASE_URL is required before importing PSD links.")
            else:
                try:
                    render_psd_master_folder_controls("settings-dev-psd-master")
                    render_psd_storage_status()
                except Exception as error:
                    st.warning("Could not load PSD link status.")
                    st.exception(error)
                if st.button("Load PSD CSV Import Tool", key="settings-load-psd-import", use_container_width=True):
                    st.session_state.settings_psd_import_loaded = True
            if supabase_backend.is_configured() and st.session_state.get("settings_psd_import_loaded"):
                try:
                    products = supabase_backend.list_edition_products(limit=1000)
                    render_psd_csv_import(
                        products,
                        expanded=True,
                        key_prefix="settings-psd",
                        title="Import PSD CSV",
                    )
                except Exception as error:
                    st.error("Could not load products for PSD import.")
                    st.exception(error)
        with dev_tabs[5]:
            st.caption("Certificate tools live here now; Orders remains the daily certificate workflow.")
            if not supabase_backend.is_configured():
                st.warning("DATABASE_URL is required before loading certificate tools.")
            elif st.button("Load Certificate Tools", key="settings-load-certificates", use_container_width=True):
                st.session_state.settings_certificates_loaded = True
            if supabase_backend.is_configured() and st.session_state.get("settings_certificates_loaded"):
                render_supabase_certificates_page()


def render_placeholder_page(title):
    render_page_intro(
        title,
        "Coming in a later phase.",
        "Use Dashboard, Files, Product Uploads, Mockups, Orders, or Limited Editions for current workflows.",
    )
