import csv
import gc
import html
import io
import json
import os
import re
from datetime import date, datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

import db
import shopify_sync
import supabase_backend


CERTIFICATE_OUTPUT_DIR = db.BASE_DIR / "output" / "certificates"
ORDER_FETCH_ERROR_MESSAGE = (
    "Orders require a Shopify access token with the read_orders scope. For Shopify Dev Dashboard "
    "apps, Sports Cave OS requests this token from SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET."
)

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

PRODIGI_DASHBOARD_URL = "https://dashboard.prodigi.com/dashboard"
PRODIGI_SIZE_OPTIONS = (
    {
        "shopify_size": "XL",
        "prodigi_size": "A1",
        "dimensions": "62 x 87 cm (24.4 x 34.3 in)",
        "framed_name": 'Classic Frame, EMA 200gsm Fine Art Print, No Mount / No Mat, Perspex Glaze, 59.4x84.1cm / 23.4x33.1" (A1)',
        "framed_code": "GLOBAL-CFP-A1",
        "unframed_name": 'EMA, Enhanced Matte Art Paper, 200gsm, 59.4x84.1cm / 23.4x33.1" (A1)',
        "unframed_code": "GLOBAL-FAP-A1",
    },
    {
        "shopify_size": "L",
        "prodigi_size": "A2",
        "dimensions": "45 x 62 cm (17.7 x 24.4 in)",
        "framed_name": 'Classic Frame, EMA 200gsm Fine Art Print, No Mount / No Mat, Perspex Glaze, 42x59.4cm / 16.5x23.4" (A2)',
        "framed_code": "GLOBAL-CFP-A2",
        "unframed_name": 'EMA, Enhanced Matte Art Paper, 200gsm, 42x59.4cm / 16.5x23.4" (A2)',
        "unframed_code": "GLOBAL-FAP-A2",
    },
    {
        "shopify_size": "M",
        "prodigi_size": "A3",
        "dimensions": "30 x 45 cm (11.8 x 17.7 in)",
        "framed_name": 'Classic Frame, EMA 200gsm Fine Art Print, No Mount / No Mat, Perspex Glaze, 29.7x42cm / 11.7x16.5" (A3)',
        "framed_code": "GLOBAL-CFP-A3",
        "unframed_name": 'EMA, Enhanced Matte Art Paper, 200gsm, 29.7x42cm / 11.7x16.5" (A3)',
        "unframed_code": "GLOBAL-FAP-A3",
    },
    {
        "shopify_size": "S",
        "prodigi_size": "A4",
        "dimensions": "21 x 30 cm (8.3 x 11.8 in)",
        "framed_name": 'Classic Frame, EMA 200gsm Fine Art Print, No Mount / No Mat, Perspex Glaze, 21x29.7cm / 8.3x11.7" (A4)',
        "framed_code": "GLOBAL-CFP-A4",
        "unframed_name": 'EMA, Enhanced Matte Art Paper, 200gsm, 21x29.7cm / 8.3x11.7" (A4)',
        "unframed_code": "GLOBAL-FAP-A4",
    },
)
PRODIGI_FRAME_OPTIONS = (
    ("Black", "Black", "Sports Cave Black Frame"),
    ("Oak", "Natural", "Sports Cave Oak Frame"),
    ("White", "White", "Sports Cave White Frame"),
    ("Unframed", "No frame / Fine Art Paper", "Sports Cave Unframed"),
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


def status_badge(status):
    status_class = re.sub(r"[^a-z0-9]+", "-", str(status or "").lower()).strip("-")
    return f'<span class="sc-status sc-status-{status_class}">{status or "Not Set"}</span>'


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
    st.error("Supabase is not connected, so this page cannot save or load persistent records.")
    st.info(
        "Set DATABASE_URL, SUPABASE_DATABASE_URL, or POSTGRES_URL in Render environment variables. "
        "Sports Cave OS can still run locally, but edition numbers are only safely preserved when "
        "Supabase is connected."
    )
    st.caption(
        "If you need to force Supabase-only mode, set ENABLE_LOCAL_SQLITE_FALLBACK=false."
    )


def render_local_cache_notice():
    st.warning(
        "Supabase is not connected. Showing the local Sports Cave cache so the app keeps working, "
        "but edition counters will not be safely stored in Supabase until the Render database URL is connected."
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
                scope_columns = st.columns(4)
                for index, scope_name in enumerate(("read_orders", "read_products", "read_customers", "write_files")):
                    if scope_status.get(scope_name):
                        scope_columns[index].success(scope_name)
                    else:
                        scope_columns[index].warning(f"{scope_name} missing")
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
    st.subheader("System Status")
    st.caption("The app shell loaded. Live integrations are checked only when you click a button.")
    status_columns = st.columns(3)
    status_columns[0].success("App loaded")
    status_columns[1].info("Supabase URL: " + ("Found" if supabase_backend.is_configured() else "Missing"))
    shopify_config = shopify_sync.get_config()
    status_columns[2].info("Shopify config: " + ("Found" if shopify_config["configured"] else "Missing"))

    action_columns = st.columns([1, 1, 1, 1])
    test_supabase = action_columns[0].button(
        "Test Supabase",
        disabled=not supabase_backend.is_configured(),
        use_container_width=True,
    )
    test_shopify = action_columns[1].button(
        "Test Shopify",
        disabled=not shopify_config["configured"],
        use_container_width=True,
    )
    open_orders = action_columns[2].button("Open Orders", use_container_width=True)
    open_limited = action_columns[3].button("Open Limited Editions", use_container_width=True)
    st.caption("No Supabase or Shopify queries run during initial Dashboard render.")

    if open_orders:
        st.session_state.pending_page = "Orders"
        st.rerun()
    if open_limited:
        st.session_state.pending_page = "Limited Editions"
        st.rerun()

    if test_supabase:
        try:
            with st.spinner("Testing Supabase connection..."):
                result = supabase_backend.test_connection()
            st.success("Supabase connection OK.")
            st.caption(f"Server time: {result.get('server_time')}")
        except Exception as error:
            st.error("Supabase connection failed, but the app is still running.")
            st.exception(error)

    if test_shopify:
        try:
            with st.spinner("Testing Shopify connection..."):
                result = shopify_sync.test_connection(config=shopify_config)
            st.success(f"Shopify connection OK: {result.get('name')}")
        except Exception as error:
            st.error("Shopify connection failed, but the app is still running.")
            st.exception(error)

    st.subheader("Today's Focus")
    st.caption("Start by syncing Shopify products, then clear missing PSD links, certificates, and order issues.")
    focus_columns = st.columns(3)
    focus_columns[0].info("Open Limited Editions to sync products and confirm edition totals.")
    focus_columns[1].info("Open Orders to sync paid orders and check edition assignments.")
    focus_columns[2].info("Open Product Assets to import PSD CSV links and connect Drive/CDN assets.")


def render_dashboard_page():
    render_page_intro(
        "Sports Cave OS",
        "Internal backend for product creation, mockups, limited editions, files, and VA workflows.",
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


def render_products_page():
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
    products = db.list_file_hub_products(file_filter)
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


def render_prodigi_page():
    st.title("Prodigi")
    st.caption("Compact Prodigi matching for Shopify order variants.")
    st.link_button("Open Prodigi Dashboard", PRODIGI_DASHBOARD_URL, use_container_width=False)
    st.info("XL=A1 - L=A2 - M=A3 - S=A4. Oak in Sports Cave = Natural in Prodigi. Framed = Classic Frame. Unframed = Fine Art Paper.")

    st.subheader("Size map")
    size_columns = st.columns(4)
    for column, size_option in zip(size_columns, PRODIGI_SIZE_OPTIONS):
        with column:
            st.markdown(f"**{size_option['shopify_size']} = {size_option['prodigi_size']}**")
            st.caption(size_option["dimensions"])

    st.subheader("Frame map")
    frame_columns = st.columns(4)
    for column, (shopify_frame, prodigi_frame, prodigi_note) in zip(frame_columns, PRODIGI_FRAME_OPTIONS):
        with column:
            st.markdown(f"**{shopify_frame}**")
            st.caption(f"Select: {prodigi_frame}")
            st.caption(prodigi_note)

    st.subheader("Product codes")
    header = st.columns([0.8, 0.55, 0.7, 2.9, 0.9, 0.9])
    for column, label in zip(header, ("Frame", "Size", "Prodigi", "Product name / code", "Copy name", "Copy code")):
        column.markdown(f"**{label}**")

    frame_rows = (
        ("Black", "Black", False),
        ("Oak", "Natural", False),
        ("White", "White", False),
        ("Unframed", "No frame", True),
    )
    for frame_label, frame_colour, is_unframed in frame_rows:
        for size_option in PRODIGI_SIZE_OPTIONS:
            product_name = size_option["unframed_name"] if is_unframed else size_option["framed_name"]
            product_code = size_option["unframed_code"] if is_unframed else size_option["framed_code"]
            columns = st.columns([0.8, 0.55, 0.7, 2.9, 0.9, 0.9])
            columns[0].write(frame_label)
            columns[0].caption(f"Select {frame_colour}")
            columns[1].write(size_option["shopify_size"])
            columns[2].write(size_option["prodigi_size"])
            columns[3].write(product_name)
            columns[3].code(product_code, language=None)
            key_base = f"prodigi-{frame_label.lower()}-{size_option['shopify_size'].lower()}"
            with columns[4]:
                render_copy_text_button(product_name, f"{key_base}-name", "Copy Name")
            with columns[5]:
                render_copy_text_button(product_code, f"{key_base}-code", "Copy Code")

    st.warning("Before sending to production: confirm XL=A1, L=A2, M=A3, S=A4, Classic Frame or Fine Art Paper, and the exact frame colour.")


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


def render_supabase_limited_editions_page():
    st.title("Limited Editions")
    st.caption("Supabase is the source of truth for edition numbers. Shopify remains the product/order source.")
    try:
        supabase_backend.ensure_schema()
    except Exception as error:
        st.error("Could not connect to Supabase using DATABASE_URL.")
        st.exception(error)
        return

    notice = st.session_state.pop("supabase_limited_notice", None)
    if notice:
        st.success(notice)
    warning = st.session_state.pop("supabase_limited_warning", None)
    if warning:
        st.warning(warning)

    config = shopify_sync.get_config()
    search = st.text_input(
        "Search products",
        placeholder="Search product title or Shopify handle",
        key="supabase-limited-search",
        label_visibility="collapsed",
    )
    actions = st.columns([1.2, 1, 1, 2])
    if actions[0].button("Sync Shopify Products", type="primary", disabled=not config["configured"], use_container_width=True):
        try:
            result = supabase_backend.sync_shopify_products_to_supabase(config)
            st.session_state.supabase_limited_notice = (
                f"Synced {result['products_processed']} active Shopify products into Supabase."
            )
            st.rerun()
        except Exception as error:
            st.error("Shopify product sync failed.")
            st.exception(error)
    actions[1].caption("Shopify connection: " + ("Configured" if config["configured"] else "Missing"))
    with st.expander("Shopify connection diagnostics", expanded=False):
        render_shopify_scope_diagnostics(config, "limited-editions")

    try:
        products = supabase_backend.list_edition_products(search=search, limit=1000)
        asset_map = supabase_backend.get_product_asset_map()
    except Exception as error:
        st.error("Could not load edition products from Supabase.")
        st.exception(error)
        return

    actions[2].download_button(
        "Export CSV",
        data=supabase_backend.export_products_csv(products),
        file_name="sports-cave-supabase-limited-editions.csv",
        mime="text/csv",
        use_container_width=True,
    )
    actions[3].caption(f"{len(products)} products shown")

    with st.expander("Import Limited Edition CSV", expanded=False):
        st.caption(
            "Imports save permanently into Supabase. Product-level counters update edition_products; "
            "rows with edition numbers also create edition_orders without duplicating existing editions."
        )
        import_columns = st.columns([2.4, 1.2, 1])
        uploaded_csv = import_columns[0].file_uploader(
            "Limited Edition CSV",
            type=["csv"],
            key="supabase-limited-edition-import-csv",
            label_visibility="collapsed",
        )
        overwrite_orders = import_columns[1].checkbox(
            "Overwrite existing assigned edition rows",
            value=False,
            key="supabase-limited-overwrite-orders",
            help="Leave off to protect existing assigned edition records.",
        )
        if import_columns[2].button(
            "Import CSV",
            disabled=uploaded_csv is None,
            type="primary",
            use_container_width=True,
            key="supabase-limited-import-button",
        ):
            try:
                csv_text = uploaded_csv.getvalue().decode("utf-8-sig", errors="replace")
                csv_rows = list(csv.DictReader(io.StringIO(csv_text)))
                result = supabase_backend.import_limited_edition_rows(
                    csv_rows,
                    overwrite_existing_orders=overwrite_orders,
                )
                st.session_state.supabase_limited_notice = (
                    f"Import complete: {result['rows_read']} rows read, "
                    f"{result['rows_matched']} matched, {result['rows_inserted']} inserted, "
                    f"{result['rows_updated']} updated, {result['rows_skipped']} skipped."
                )
                if result["errors"]:
                    st.session_state.supabase_limited_warning = "First import issue: " + result["errors"][0]
                st.rerun()
            except Exception as error:
                supabase_backend.log_app_error(
                    "limited_edition_import_ui_failed",
                    str(error),
                    {"file_name": getattr(uploaded_csv, "name", "")},
                )
                st.error("Could not import the Limited Edition CSV into Supabase.")
                st.exception(error)

    metrics = st.columns(4)
    metrics[0].metric("Products", len(products))
    metrics[1].metric("Active", sum(1 for item in products if item.get("active")))
    metrics[2].metric("Sold out", sum(1 for item in products if item.get("sold_out")))
    metrics[3].metric("Remaining total", sum(int(item.get("remaining_editions") or 0) for item in products))

    with st.expander("Edit edition total or active status", expanded=False):
        if products:
            options = [f"{item.get('product_title') or item.get('shopify_handle')} | {item.get('shopify_handle')}" for item in products]
            selected = st.selectbox("Product", options, key="supabase-edition-edit-product")
            selected_handle = selected.rsplit("|", 1)[-1].strip()
            selected_product = next(item for item in products if item.get("shopify_handle") == selected_handle)
            new_total = st.number_input(
                "Edition total",
                min_value=1,
                max_value=100000,
                value=int(selected_product.get("edition_total") or 100),
                step=1,
                key="supabase-edition-total-edit",
            )
            new_active = st.checkbox(
                "Active",
                value=bool(selected_product.get("active")),
                key="supabase-edition-active-edit",
            )
            if st.button("Save Edition Settings", use_container_width=True):
                supabase_backend.update_edition_product(
                    selected_handle,
                    edition_total=new_total,
                    active=new_active,
                )
                st.session_state.supabase_limited_notice = "Edition settings saved."
                st.rerun()
        else:
            st.caption("Sync Shopify products first.")

    st.subheader("Edition Products")
    if not products:
        st.info("No edition products found yet. Click Sync Shopify Products.")
        return

    header = st.columns([2.2, 1.25, 0.65, 0.65, 0.8, 0.75, 0.75, 0.75, 0.9, 1.0])
    for column, label in zip(
        header,
        ("Product", "Handle", "Total", "Next", "Last", "Remaining", "Active", "Sold Out", "PSD", "Links"),
    ):
        column.markdown(f"**{label}**")
    for product in products:
        columns = st.columns([2.2, 1.25, 0.65, 0.65, 0.8, 0.75, 0.75, 0.75, 0.9, 1.0])
        columns[0].write(product.get("product_title") or "Untitled product")
        columns[1].caption(product.get("shopify_handle") or "")
        columns[2].write(product.get("edition_total") or 100)
        columns[3].write(product.get("next_edition_number") or 1)
        last_assigned = product.get("last_assigned_edition")
        columns[4].write(f"{last_assigned}/{product.get('edition_total') or 100}" if last_assigned else "None")
        columns[5].write(product.get("remaining_editions") or 0)
        columns[6].markdown(status_badge("Active" if product.get("active") else "Inactive"), unsafe_allow_html=True)
        columns[7].markdown(status_badge("Sold Out" if product.get("sold_out") else "Available"), unsafe_allow_html=True)
        psd_url = (asset_map.get(product.get("shopify_handle")) or {}).get("psd_master_file")
        with columns[8]:
            if psd_url:
                st.link_button("Open PSD", psd_url, use_container_width=True)
            else:
                st.markdown(status_badge("PSD Missing"), unsafe_allow_html=True)
        with columns[9]:
            if product.get("admin_url"):
                st.link_button("Shopify", product["admin_url"], use_container_width=True)
            elif product.get("online_store_url"):
                st.link_button("Storefront", product["online_store_url"], use_container_width=True)
            else:
                st.caption("No link")
        st.divider()


def render_limited_editions_page(dispatch_log_renderer=None):
    if supabase_backend.is_configured():
        render_supabase_limited_editions_page()
        return
    if not allow_local_sqlite_fallback():
        render_supabase_required_notice("Limited Editions")
        return
    st.title("Limited Editions")
    render_local_cache_notice()
    st.caption("Track edition numbers and PSD files from the local product cache.")
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
        "Fetch Latest Shopify Products",
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
        st.caption("Connection is not configured. Cached products still remain visible from Sports Cave OS.")

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
        st.info("No cached products match this search or filter. Use Fetch Latest Shopify Products if the cache is empty.")
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
    limit = active[0].get("edition_limit")
    if len(numbers) > 1 and numbers == list(range(numbers[0], numbers[-1] + 1)):
        return f"#{numbers[0]}-{numbers[-1]}/{limit}"
    return ", ".join(f"#{number}/{limit}" for number in numbers)


def render_supabase_orders_page():
    st.title("Orders")
    st.caption("Orders load from Supabase first. Shopify refreshes only when you click a sync button.")
    try:
        supabase_backend.ensure_schema()
    except Exception as error:
        st.error("Could not connect to Supabase using DATABASE_URL.")
        st.exception(error)
        return

    notice = st.session_state.pop("supabase_orders_notice", None)
    if notice:
        st.success(notice)

    config = shopify_sync.get_config()
    controls = st.columns([1, 1, 1.2, 1.2, 1.4])
    if controls[0].button("Fetch latest 50", disabled=not config["configured"], use_container_width=True):
        try:
            result = supabase_backend.sync_shopify_orders_to_supabase(
                config,
                query="financial_status:paid",
                max_orders=50,
            )
            st.session_state.supabase_orders_notice = (
                f"Synced {result['orders_seen']} paid Shopify orders. "
                f"Assigned {result['assignments_created']} edition numbers."
            )
            st.rerun()
        except Exception as error:
            st.error("Could not sync latest Shopify orders.")
            st.exception(error)
    if controls[1].button("Fetch latest 250", disabled=not config["configured"], use_container_width=True):
        try:
            result = supabase_backend.sync_shopify_orders_to_supabase(
                config,
                query="financial_status:paid",
                max_orders=250,
            )
            st.session_state.supabase_orders_notice = (
                f"Synced {result['orders_seen']} paid Shopify orders. "
                f"Assigned {result['assignments_created']} edition numbers."
            )
            st.rerun()
        except Exception as error:
            st.error("Could not sync latest Shopify orders.")
            st.exception(error)
    if controls[2].button("Sync unfulfilled paid", disabled=not config["configured"], use_container_width=True):
        try:
            result = supabase_backend.sync_shopify_orders_to_supabase(
                config,
                query="financial_status:paid fulfillment_status:unfulfilled",
                max_orders=1000,
            )
            st.session_state.supabase_orders_notice = (
                f"Synced {result['orders_seen']} unfulfilled paid orders. "
                f"Assigned {result['assignments_created']} edition numbers."
            )
            st.rerun()
        except Exception as error:
            st.error("Could not sync unfulfilled paid Shopify orders.")
            st.exception(error)
    since_date = controls[3].date_input("Since", value=date.today(), key="supabase-orders-since")
    if controls[4].button("Sync since date", disabled=not config["configured"], use_container_width=True):
        try:
            result = supabase_backend.sync_shopify_orders_to_supabase(
                config,
                query=f"financial_status:paid created_at:>={since_date.isoformat()}",
                max_orders=1000,
            )
            st.session_state.supabase_orders_notice = (
                f"Synced {result['orders_seen']} paid orders since {since_date.isoformat()}. "
                f"Assigned {result['assignments_created']} edition numbers."
            )
            st.rerun()
        except Exception as error:
            st.error("Could not sync Shopify orders since the selected date.")
            st.exception(error)

    with st.expander("Shopify connection diagnostics", expanded=False):
        render_shopify_scope_diagnostics(config, "orders")

    summary = supabase_backend.get_order_summary()
    metrics = st.columns(6)
    metric_specs = (
        ("Orders synced", summary.get("orders_synced", 0)),
        ("Needs edition", summary.get("needs_edition", 0)),
        ("Assigned today", summary.get("assigned_today", 0)),
        ("Certificates missing", summary.get("certificates_missing", 0)),
        ("PSD links missing", summary.get("psd_links_missing", 0)),
        ("Prodigi links missing", summary.get("prodigi_links_missing", 0)),
    )
    for index, (label, value) in enumerate(metric_specs):
        metrics[index].metric(label, value)

    tools = st.columns([2.5, 1.2, 1.2])
    search = tools[0].text_input(
        "Search orders",
        placeholder="Search order, customer, email, product, SKU, or edition",
        label_visibility="collapsed",
        key="supabase-orders-search",
    )
    sort = tools[1].selectbox(
        "Sort",
        ["Date newest", "Date oldest", "Order number", "Customer", "Edition number", "Certificate status", "PSD status"],
        key="supabase-orders-sort",
    )
    limit = tools[2].selectbox("Rows", [100, 250, 500, 1000], index=1, key="supabase-orders-limit")

    try:
        rows = supabase_backend.list_orders(search=search, sort=sort, limit=limit)
    except Exception as error:
        st.error("Could not load orders from Supabase.")
        st.exception(error)
        return

    selected = []
    bulk = st.columns([1, 1, 1, 1.4])
    generate_bulk = bulk[0].button("Generate certificates", use_container_width=True)
    mark_checked = bulk[1].button("Mark certificate checked", use_container_width=True)
    export_clicked = bulk[2].button("Export selected CSV", use_container_width=True)
    with bulk[3]:
        st.caption("Select rows below for bulk actions.")

    if not rows:
        st.info("No orders found yet. Use a Shopify sync button above.")
        return

    header = st.columns([0.35, 0.9, 0.8, 1.25, 0.85, 0.95, 0.75, 0.75, 1.7, 1.1, 0.8, 1.0, 0.75, 0.75, 1.0])
    for column, label in zip(
        header,
        (
            "",
            "Order",
            "Date",
            "Customer",
            "Payment",
            "Fulfillment",
            "Total",
            "Items",
            "Product",
            "Variant",
            "Edition",
            "Certificate",
            "PSD",
            "Prodigi",
            "Actions",
        ),
    ):
        column.markdown(f"**{label}**")

    for row_index, row in enumerate(rows):
        row_key = row.get("edition_order_id") or row.get("shopify_order_id") or row_index
        columns = st.columns([0.35, 0.9, 0.8, 1.25, 0.85, 0.95, 0.75, 0.75, 1.7, 1.1, 0.8, 1.0, 0.75, 0.75, 1.0])
        checked = columns[0].checkbox("Select", key=f"supabase-order-select-{row_key}", label_visibility="collapsed")
        if checked:
            selected.append(row)
        order_label = row.get("order_name") or row.get("order_number") or "Order"
        if row.get("admin_url"):
            columns[1].markdown(
                f'<a href="{html.escape(row["admin_url"], quote=True)}" target="_blank" style="color:#F5F2EA;font-weight:700;text-decoration:none;">{html.escape(order_label)}</a>',
                unsafe_allow_html=True,
            )
        else:
            columns[1].write(order_label)
        columns[2].caption(format_updated_at(row.get("created_at")))
        columns[3].write(row.get("customer_name") or row.get("customer_email") or "Customer not shown")
        if row.get("customer_email"):
            columns[3].caption(row["customer_email"])
        columns[4].markdown(status_badge(row.get("financial_status") or "Unknown"), unsafe_allow_html=True)
        columns[5].markdown(status_badge(row.get("fulfillment_status") or "Unknown"), unsafe_allow_html=True)
        columns[6].write((row.get("currency") or "") + " " + str(row.get("total_price") or ""))
        columns[7].write("1")
        columns[8].write(row.get("product_title") or "Needs edition")
        if row.get("sku"):
            columns[8].caption(f"SKU {row['sku']}")
        columns[9].caption(row.get("variant_title") or "Variant not shown")
        if row.get("edition_number"):
            columns[10].markdown(
                status_badge(f"#{row['edition_number']}/{row.get('edition_total') or 100}"),
                unsafe_allow_html=True,
            )
        else:
            columns[10].markdown(status_badge("Needs Edition"), unsafe_allow_html=True)
        with columns[11]:
            if row.get("shopify_file_url"):
                st.link_button("Open PDF", row["shopify_file_url"], use_container_width=True)
            elif row.get("local_file_path") and Path(row["local_file_path"]).exists():
                path = Path(row["local_file_path"])
                st.download_button(
                    "PDF",
                    data=path.read_bytes(),
                    file_name=path.name,
                    mime="application/pdf",
                    key=f"supabase-cert-download-{row_key}",
                    use_container_width=True,
                )
            elif row.get("edition_order_id"):
                if st.button("Generate", key=f"supabase-cert-generate-{row_key}", use_container_width=True):
                    try:
                        supabase_backend.generate_certificate_for_edition_order(row["edition_order_id"])
                        st.session_state.supabase_orders_notice = "Certificate generated."
                        st.rerun()
                    except Exception as error:
                        st.error("Could not generate certificate.")
                        st.exception(error)
            else:
                st.caption("Missing")
        if row.get("psd_url"):
            columns[12].link_button("PSD", row["psd_url"], use_container_width=True)
        else:
            columns[12].markdown(status_badge("PSD Missing"), unsafe_allow_html=True)
        if row.get("prodigi_url"):
            columns[13].link_button("Prodigi", row["prodigi_url"], use_container_width=True)
        else:
            columns[13].markdown(status_badge("Prodigi Missing"), unsafe_allow_html=True)
        with columns[14]:
            if row.get("edition_order_id"):
                if st.button("View", key=f"supabase-order-view-{row_key}", use_container_width=True):
                    st.session_state["supabase-edition-orders-search"] = str(row.get("order_name") or "")
                    st.session_state.pending_page = "Edition Orders"
                    st.rerun()
            else:
                st.caption("No edition")
        st.divider()

    if selected:
        with st.expander("Selected Shopify order links", expanded=False):
            shown = set()
            for row in selected:
                if row.get("admin_url") and row["admin_url"] not in shown:
                    shown.add(row["admin_url"])
                    st.link_button(
                        row.get("order_name") or "Open Shopify order",
                        row["admin_url"],
                        use_container_width=True,
                    )
            if not shown:
                st.caption("No Shopify order links are available for the selected rows.")

    if generate_bulk and selected:
        generated = 0
        for row in selected:
            if row.get("edition_order_id"):
                supabase_backend.generate_certificate_for_edition_order(row["edition_order_id"])
                generated += 1
        st.session_state.supabase_orders_notice = f"Generated {generated} certificate PDF files."
        st.rerun()
    if mark_checked and selected:
        checked_ids = [row.get("edition_order_id") for row in selected if row.get("edition_order_id")]
        updated = supabase_backend.mark_certificates_checked(checked_ids)
        st.session_state.supabase_orders_notice = f"Marked {updated} certificate records as checked."
        st.rerun()
    if export_clicked and selected:
        st.download_button(
            "Download selected CSV",
            data=supabase_backend.export_orders_csv(selected),
            file_name="sports-cave-selected-orders.csv",
            mime="text/csv",
            use_container_width=True,
        )


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
    if supabase_backend.is_configured():
        render_supabase_orders_page()
        return
    if not allow_local_sqlite_fallback():
        render_supabase_required_notice("Orders")
        return
    st.title("Orders")
    render_local_cache_notice()
    st.caption("Edition numbers are assigned from Sports Cave OS, not Shopify stock.")
    config = shopify_sync.get_config()
    order_summary = db.get_shopify_order_summary()
    notice = st.session_state.pop("orders_notice", None)
    warning = st.session_state.pop("orders_warning", None)
    if notice:
        st.success(notice)
    if warning:
        st.warning(warning)

    search = st.text_input(
        "Search orders",
        placeholder="Search order, customer, product, SKU, or edition number",
        key="orders-search",
        label_visibility="collapsed",
    )

    toolbar = st.columns([1, 1.2, 3])
    fetch_clicked = toolbar[0].button(
        "Fetch Latest Orders",
        type="primary",
        disabled=not config["configured"],
        use_container_width=True,
    )
    status_filter = toolbar[1].selectbox(
        "Filter",
        ["All", "Needs Edition", "Assigned", "Paid", "Unfulfilled", "Error", "Sold Out Issue"],
    )
    toolbar[2].caption(
        "Last fetched: "
        + (format_updated_at(order_summary["last_synced_at"]) if order_summary["last_synced_at"] else "Never")
        + f" - {order_summary['total']} orders cached"
    )

    if not config["configured"]:
        st.caption("Shopify connection is not configured. Cached orders still remain visible from Sports Cave OS.")

    if fetch_clicked:
        try:
            result = fetch_latest_orders(config)
            st.session_state.orders_notice = (
                f"Fetched {result['orders_seen']} Shopify orders. Cached orders remain available offline. Assigned "
                f"{result['assignments_created']} edition number"
                f"{'s' if result['assignments_created'] != 1 else ''}."
            )
            if result["sync_warning"]:
                st.session_state.orders_warning = result["sync_warning"]
            st.rerun()
        except Exception:
            if order_summary["total"]:
                st.warning("Latest Shopify fetch failed. Showing cached orders.")
            else:
                st.warning("Shopify order sync failed. Check read_orders scope and API version.")
            st.caption(ORDER_FETCH_ERROR_MESSAGE)

    metrics = st.columns(3)
    metrics[0].metric("Orders cached", order_summary["total"])
    metrics[1].metric("Needs edition", order_summary["needs_assignment"])
    metrics[2].metric("Assigned today", order_summary["assigned_today"])

    if "orders_visible_count" not in st.session_state:
        st.session_state.orders_visible_count = 50
    orders = db.list_shopify_orders(
        search=search,
        status_filter=status_filter,
        limit=st.session_state.orders_visible_count,
    )
    if not orders:
        if not order_summary["last_synced_at"]:
            st.info("No orders fetched yet. Click Fetch Latest Orders to import recent Shopify orders.")
        else:
            st.info("No cached Shopify orders match these filters. Use Fetch Latest Orders when you are ready.")
        return

    header = st.columns([0.9, 0.9, 1.25, 0.9, 0.95, 2.1, 1.05, 1.1, 0.85, 0.95])
    for column, label in zip(
        header,
        ("Order", "Date", "Customer", "Payment", "Fulfillment", "Product", "Edition", "Certificate", "PSD", "Prodigi"),
    ):
        column.markdown(f"**{label}**")

    for order in orders:
        for line_index, line in enumerate(order["line_items"]):
            columns = st.columns([0.9, 0.9, 1.25, 0.9, 0.95, 2.1, 1.05, 1.1, 0.85, 0.95])
            order_name = order.get("order_name") or order.get("order_number") or "Order"
            if line_index == 0:
                if order.get("admin_url"):
                    safe_url = html.escape(order["admin_url"], quote=True)
                    columns[0].markdown(
                        f'<a href="{safe_url}" target="_blank" style="color:#F5F2EA;font-weight:700;text-decoration:none;">{html.escape(order_name)}</a>',
                        unsafe_allow_html=True,
                    )
                else:
                    columns[0].markdown(f"**{order_name}**")
                columns[1].caption(format_updated_at(order.get("created_at")))
                columns[2].write(order.get("customer_name") or "Customer not shown")
                if order.get("customer_email"):
                    columns[2].caption(order["customer_email"])
                columns[3].markdown(status_badge(order.get("financial_status") or "Unknown"), unsafe_allow_html=True)
                columns[4].markdown(status_badge(order.get("fulfillment_status") or "Unknown"), unsafe_allow_html=True)
            else:
                columns[0].caption(order_name)

            product_label = line.get("product_title") or "Unknown product"
            if columns[5].button(product_label, key=f"order-track-product-{line['id']}", use_container_width=True):
                st.session_state["limited-edition-search"] = line.get("product_handle") or product_label
                st.session_state.pending_page = "Limited Editions"
                st.rerun()
            details = []
            if line.get("variant_title"):
                details.append(line["variant_title"])
            if line.get("sku"):
                details.append(f"SKU {line['sku']}")
            if int(line.get("quantity") or 1) > 1:
                details.append(f"Qty {line['quantity']}")
            if line.get("assignment_status") == "Product Not Found":
                details.append("Fetch Latest Shopify Products or check product ID")
            columns[5].caption(" - ".join(details) if details else "Variant not shown")
            columns[6].write(_assignment_text(line.get("assignments") or []))
            columns[6].markdown(status_badge(line.get("assignment_status")), unsafe_allow_html=True)
            with columns[7]:
                render_certificate_actions(line.get("assignments") or [], f"cert-line-{line['id']}")
            if line.get("psd_file_url"):
                columns[8].link_button("Open PSD", line["psd_file_url"], use_container_width=True)
            else:
                columns[8].caption("Missing")
            if line.get("prodigi_url"):
                columns[9].link_button("Open Prodigi", line["prodigi_url"], use_container_width=True)
            else:
                columns[9].caption("Missing")
            st.divider()

    if len(orders) >= st.session_state.orders_visible_count:
        if st.button("Load 50 More", use_container_width=True):
            st.session_state.orders_visible_count = min(st.session_state.orders_visible_count + 50, 500)
            st.rerun()


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
                "notes": (row.get("Parent Folder") or row.get("Parent Folder, if available") or "").strip(),
            }
        )
    return [row for row in rows if row["asset_url"] or row["google_drive_file_id"] or row["asset_name"]]


def render_psd_csv_import(products):
    with st.expander("Import PSD CSV", expanded=False):
        st.caption("Upload the Google Drive export CSV only when you are ready. The app stores Drive links only, not PSD files.")
        uploaded_csv = st.file_uploader(
            "PSD CSV",
            type=["csv"],
            key="supabase-psd-csv-upload",
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

        product_handles = {item.get("shopify_handle") for item in known_products if item.get("shopify_handle")}
        product_options = {
            f"{item.get('product_title') or item.get('shopify_handle')} | {item.get('shopify_handle')}": item.get("shopify_handle")
            for item in known_products
            if item.get("shopify_handle")
        }

        matched = [row for row in csv_rows if row["shopify_handle"] in product_handles]
        unmatched = [row for row in csv_rows if row["shopify_handle"] not in product_handles]
        linked_psd_handles = {
            handle
            for handle, assets in asset_map.items()
            if assets.get("psd_master_file")
        }
        missing = [item for item in products if item.get("shopify_handle") not in linked_psd_handles]

        match_columns = st.columns(3)
        match_columns[0].metric("Matched PSDs", len(matched))
        match_columns[1].metric("Missing PSDs", len(missing))
        match_columns[2].metric("Unmatched PSDs", len(unmatched))

        if matched:
            st.markdown("**Matched PSDs**")
            overwrite_existing = st.checkbox(
                "Overwrite existing PSD links",
                value=False,
                help="Leave off to protect manually linked PSDs. Existing PSD links will be skipped.",
                key="supabase-psd-overwrite-existing",
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
                try:
                    for row in matched:
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
                    supabase_backend.finish_sync_run(
                        run_id,
                        "Complete",
                        records_seen=len(matched),
                        records_processed=imported,
                    )
                    st.session_state.supabase_assets_notice = (
                        f"Imported {imported} matched PSD links. Skipped {skipped} existing links."
                    )
                    st.rerun()
                except Exception as error:
                    supabase_backend.finish_sync_run(
                        run_id,
                        "Failed",
                        records_seen=len(matched),
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
            st.dataframe(
                [
                    {
                        "Product": item.get("product_title"),
                        "Shopify Handle": item.get("shopify_handle"),
                    }
                    for item in missing[:200]
                ],
                use_container_width=True,
                hide_index=True,
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
                key="supabase-psd-manual-overwrite",
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
                    row["notes"],
                    asset_name=row["asset_name"],
                    google_drive_file_id=row["google_drive_file_id"],
                    is_primary=True,
                )
                st.session_state.supabase_assets_notice = f"Linked {row['asset_name']} to {handle}."
                st.rerun()


def render_product_assets_page():
    st.title("Product Assets")
    st.caption("Store Google Drive, PSD, certificate, mockup, Shopify CDN, and Prodigi links by Shopify handle.")
    if not supabase_backend.is_configured():
        st.warning("Product Assets requires DATABASE_URL. Configure Supabase on Render to use this page.")
        return
    try:
        supabase_backend.ensure_schema()
    except Exception as error:
        st.error("Could not connect to Supabase.")
        st.exception(error)
        return

    notice = st.session_state.pop("supabase_assets_notice", None)
    if notice:
        st.success(notice)

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
                        if asset.get("asset_url"):
                            st.markdown(status_badge("Connected"), unsafe_allow_html=True)
                            st.link_button("Open", asset["asset_url"], use_container_width=True)
                            st.caption(format_updated_at(asset.get("updated_at")))
                        else:
                            st.markdown(status_badge("Missing"), unsafe_allow_html=True)


def render_edition_orders_page():
    st.title("Edition Orders")
    st.caption("Every allocated edition number from paid Shopify orders.")
    if not supabase_backend.is_configured():
        st.warning("Edition Orders requires DATABASE_URL.")
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
        st.error("Could not load edition orders.")
        st.exception(error)
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
        if row.get("shopify_file_url"):
            columns[5].link_button("Open PDF", row["shopify_file_url"], use_container_width=True)
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
        st.warning("Certificates requires DATABASE_URL.")
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
        st.error("Could not load certificates.")
        st.exception(error)
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
        if row.get("shopify_file_url"):
            columns[5].link_button("Open PDF", row["shopify_file_url"], use_container_width=True)
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


def render_prompt_block(title, prompt, key, when_to_use=None, height=220):
    with st.expander(title, expanded=False):
        if when_to_use:
            st.caption(f"When to use this: {when_to_use}")
        st.caption("Copy this prompt into ChatGPT.")
        st.text_area(
            f"{title} prompt",
            value=prompt.strip(),
            height=height,
            key=f"prompt-text-{key}",
            label_visibility="collapsed",
        )
        render_copy_text_button(prompt.strip(), f"marketing-{key}", "Copy Prompt")


def inject_marketing_factory_styles():
    st.markdown(
        """
        <style>
        div[data-testid="stTextArea"] textarea {
            background: #F5F2EA !important;
            color: #0B0B0D !important;
            border: 1px solid rgba(212, 165, 76, 0.55) !important;
            border-radius: 10px !important;
            padding: 14px 16px !important;
            font-size: 0.95rem !important;
            line-height: 1.45 !important;
            caret-color: #0B0B0D !important;
        }
        div[data-testid="stTextArea"] textarea::placeholder {
            color: #4B4B4D !important;
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


META_PROMPTS = {
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
}

SEO_PROMPTS = {
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
}


def render_meta_ads_section():
    st.subheader("Meta Ads")
    st.caption("Copy/paste prompt library only. No live AI calls.")
    au_tab, usa_tab, universal_tab, checklist_tab = st.tabs(
        ["Australia", "USA", "Universal Ad Copy", "Quality Checklist"]
    )

    with au_tab:
        st.markdown("### Australian Meta Ads SOP")
        st.caption("Nostalgia, rivalry, man cave, Aussie pride, and numbered collector drops.")
        st.write("Goal: make the fan feel, 'That belongs on my wall.'")
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
        with st.expander("Best USA angles", expanded=True):
            st.write("Gift for Sports Fans Who Have Everything")
            st.write("Limited Edition Collector Series")
            st.write("Man Cave Upgrade / Fan Cave Ready")
            st.write("Legacy Debate / Mentality / Rivalry / Greatest Era")
            st.write("Championship Memory / Numbered Collector Drop")
            st.warning("Avoid Australian slang, generic sports poster wording, long card text, and corporate phrasing.")
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


def render_marketing_factory_page():
    inject_marketing_factory_styles()
    st.title("Marketing Factory")
    st.caption("Meta Ads and SEO SOP hub for Sports Cave operators. No live AI generation.")
    meta_tab, seo_tab, social_tab, email_tab = st.tabs(
        ["Meta Ads", "SEO", "Social Media", "Email Marketing"]
    )
    with meta_tab:
        render_meta_ads_section()
    with seo_tab:
        render_seo_section()
    with social_tab:
        st.info("Social Media workflows are coming soon.")
    with email_tab:
        st.info("Email Marketing workflows are coming soon.")


def render_settings_page(app_version, database_path, password_status):
    st.title("Settings")
    st.caption("Safe connection status and file workflow settings for Sports Cave OS.")
    shopify_config = shopify_sync.get_config()
    shopify_token_status = shopify_sync.get_token_status(shopify_config)
    shopify_summary = db.get_shopify_summary()
    order_summary = db.get_shopify_order_summary()
    certificate_summary = db.get_certificate_summary()
    latest_shopify_run = db.get_latest_shopify_sync_run()
    latest_order_run = db.get_latest_shopify_order_sync_run()
    supabase_status = "Configured" if supabase_backend.is_configured() else "Missing"
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
    settings = (
        ("Shopify connection", "Configured" if shopify_config["configured"] else "Not configured"),
        ("Shopify store domain", "Configured" if shopify_config["store_domain"] else "Missing"),
        ("Shopify API version", "Configured" if shopify_config["api_version"] else "Missing"),
        ("Shopify auth mode", shopify_config["auth_mode"]),
        ("Products cached", str(shopify_summary["total"])),
        ("Orders cached", str(order_summary["total"])),
        ("Last product sync status", last_sync_status),
        ("Last order sync status", order_sync_status),
        ("Last product fetch", format_updated_at(shopify_summary["last_synced_at"]) if shopify_summary["last_synced_at"] else "Never"),
        ("Last order fetch", format_updated_at(order_summary["last_synced_at"]) if order_summary["last_synced_at"] else "Never"),
        ("Certificate PDFs generated", str(certificate_summary["generated"])),
        ("Supabase DATABASE_URL", supabase_status),
        (
            "Limited edition backend",
            "Supabase/Postgres active" if supabase_backend.is_configured() else "Local cache fallback",
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

    st.info(
        "Sports Cave OS reads Shopify products and orders only when a worker clicks Fetch. "
        "Client credentials are exchanged for a temporary in-memory token only at that time. "
        "Edition numbers and certificates come from Sports Cave OS; Shopify metafields are display only."
    )
    st.write(f"**Local database:** `{database_path}`")
    st.write(f"**Password protection:** {password_status}")
    st.write(f"**App version:** {app_version}")

    with st.expander("Admin test tools", expanded=False):
        test_columns = st.columns(3)
        if test_columns[0].button("Test Supabase connection", disabled=not supabase_backend.is_configured(), use_container_width=True):
            try:
                result = supabase_backend.test_connection()
                st.success("Supabase connection OK.")
                st.caption(f"Server time: {result.get('server_time')}")
            except Exception as error:
                st.error("Supabase connection failed.")
                st.exception(error)
        if test_columns[1].button("Test Shopify connection", disabled=not shopify_config["configured"], use_container_width=True):
            try:
                result = shopify_sync.test_connection(config=shopify_config)
                st.success(f"Shopify connection OK: {result.get('name')}")
            except Exception as error:
                st.error("Shopify connection failed.")
                st.exception(error)
        if test_columns[2].button(
            "Test product sync",
            disabled=not (shopify_config["configured"] and supabase_backend.is_configured()),
            use_container_width=True,
        ):
            try:
                result = supabase_backend.sync_shopify_products_to_supabase(shopify_config)
                st.success(f"Synced {result['products_processed']} Shopify products.")
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
                selected_id = int(selected.rsplit("|", 1)[-1].strip())
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


def render_placeholder_page(title):
    render_page_intro(
        title,
        "Coming in a later phase.",
        "Use Dashboard, Files, Product Uploads, Mockups, Orders, or Limited Editions for current workflows.",
    )
