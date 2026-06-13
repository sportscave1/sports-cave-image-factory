import csv
import gc
import html
import io
import json
import os
import re
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components

import db
import shopify_sync


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
    "prodigi_url",
    "prodigi_product_id",
    "notes",
    "last_shopify_sync_at",
    "updated_at",
)

PRODIGI_DASHBOARD_URL = "https://dashboard.prodigi.com/dashboard"
PRODIGI_SIZE_OPTIONS = (
    {
        "shopify_size": "XL",
        "prodigi_size": "A1",
        "dimensions": "62 × 87 cm (24.4 × 34.3 in)",
        "framed_name": 'Classic Frame, EMA 200gsm Fine Art Print, No Mount / No Mat, Perspex Glaze, 59.4x84.1cm / 23.4x33.1" (A1)',
        "framed_code": "GLOBAL-CFP-A1",
        "unframed_name": 'EMA, Enhanced Matte Art Paper, 200gsm, 59.4x84.1cm / 23.4x33.1" (A1)',
        "unframed_code": "GLOBAL-FAP-A1",
    },
    {
        "shopify_size": "L",
        "prodigi_size": "A2",
        "dimensions": "45 × 62 cm (17.7 × 24.4 in)",
        "framed_name": 'Classic Frame, EMA 200gsm Fine Art Print, No Mount / No Mat, Perspex Glaze, 42x59.4cm / 16.5x23.4" (A2)',
        "framed_code": "GLOBAL-CFP-A2",
        "unframed_name": 'EMA, Enhanced Matte Art Paper, 200gsm, 42x59.4cm / 16.5x23.4" (A2)',
        "unframed_code": "GLOBAL-FAP-A2",
    },
    {
        "shopify_size": "M",
        "prodigi_size": "A3",
        "dimensions": "30 × 45 cm (11.8 × 17.7 in)",
        "framed_name": 'Classic Frame, EMA 200gsm Fine Art Print, No Mount / No Mat, Perspex Glaze, 29.7x42cm / 11.7x16.5" (A3)',
        "framed_code": "GLOBAL-CFP-A3",
        "unframed_name": 'EMA, Enhanced Matte Art Paper, 200gsm, 29.7x42cm / 11.7x16.5" (A3)',
        "unframed_code": "GLOBAL-FAP-A3",
    },
    {
        "shopify_size": "S",
        "prodigi_size": "A4",
        "dimensions": "21 × 30 cm (8.3 × 11.8 in)",
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
                "prodigi_url": product.get("prodigi_url") or "",
                "prodigi_product_id": product.get("prodigi_product_id") or "",
                "notes": product.get("edition_notes") or "",
                "last_shopify_sync_at": product.get("last_shopify_sync_at") or "",
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
                prodigi_url=csv_value(row, "prodigi_url", current.get("prodigi_url") or ""),
                prodigi_product_id=csv_value(
                    row,
                    "prodigi_product_id",
                    current.get("prodigi_product_id") or "",
                ),
                notes=csv_value(row, "notes", current.get("edition_notes") or ""),
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


def render_dashboard_page():
    render_page_intro(
        "Sports Cave OS",
        "Internal backend for product creation, mockups, limited editions, files, and VA workflows.",
        "Start with Today's Focus, then open the products that need attention.",
        "Finish missing product data before moving a product to Live.",
    )

    st.subheader("Dashboard")
    st.caption("The daily command screen for product readiness, missing files, and edition priorities.")
    metrics, focus = db.get_dashboard_data()
    metric_specs = (
        ("Shopify products synced", metrics["shopify_products_synced"]),
        ("Orders synced", metrics["orders_synced"]),
        ("Orders needing editions", metrics["orders_needing_assignment"]),
        ("Orders assigned today", metrics["orders_assigned_today"]),
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
        if st.button("Back to Products"):
            st.session_state.selected_product_id = None
            st.rerun()
        return

    detail_actions = st.columns([1, 1, 1, 3])
    with detail_actions[0]:
        if st.button("Back to Products", use_container_width=True):
            st.session_state.selected_product_id = None
            st.session_state.editing_product_id = None
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


def render_prodigi_page():
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
        prodigi_url = str(
            st.session_state.get(f"le-prodigi-url-{item_key}", product.get("prodigi_url") or "") or ""
        ).strip()
        prodigi_product_id = str(
            st.session_state.get(f"le-prodigi-id-{item_key}", product.get("prodigi_product_id") or "") or ""
        ).strip()
        notes = str(st.session_state.get(f"le-notes-{item_key}", product.get("edition_notes") or "") or "").strip()

        current_values = (
            int(product.get("edition_limit") or 100),
            int(product.get("next_available_edition") or 1),
            int(product.get("editions_sold") or 0),
            product.get("psd_file_url") or "",
            product.get("prodigi_url") or "",
            product.get("prodigi_product_id") or "",
            product.get("edition_notes") or "",
        )
        new_values = (
            edition_limit,
            next_available,
            editions_sold,
            psd_file_url,
            prodigi_url,
            prodigi_product_id,
            notes,
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
                prodigi_url=prodigi_url,
                prodigi_product_id=prodigi_product_id,
                notes=notes,
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


def render_limited_editions_page(dispatch_log_renderer=None):
    st.title("Limited Editions")
    st.caption("Track edition numbers, PSD files, Prodigi links, and storefront edition display.")

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
        "Search limited editions",
        placeholder="Search by product name, handle, order product, or SKU",
        key="limited-edition-search",
        label_visibility="collapsed",
    )

    actions = st.columns([1.25, 0.9, 1.05, 1.35, 1.15])
    fetch_clicked = actions[0].button(
        "Fetch Latest Shopify Products",
        type="primary",
        disabled=not config["configured"],
        use_container_width=True,
    )
    actions[1].download_button(
        "Export CSV",
        data=build_limited_editions_csv(db.list_all_shopify_edition_products()),
        file_name="sports-cave-limited-editions.csv",
        mime="text/csv",
        use_container_width=True,
    )
    actions[2].download_button(
        "CSV Template",
        data=build_limited_editions_template_csv(),
        file_name="sports-cave-limited-editions-template.csv",
        mime="text/csv",
        use_container_width=True,
    )
    sync_widget_clicked = actions[3].button(
        "Sync Edition Display to Shopify",
        disabled=not config["configured"],
        use_container_width=True,
    )
    apply_clicked = actions[4].button("Apply Table Changes", use_container_width=True)

    if not config["configured"]:
        st.caption("Shopify connection is not configured. Cached products still remain visible from Sports Cave OS.")

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
                    f"Synced {result['synced']} of {result['attempted']} widget records. "
                    f"First issue: {result['errors'][0]}"
                )
            else:
                st.session_state.limited_edition_notice = (
                    f"Synced {result['synced']} storefront edition display record"
                    f"{'s' if result['synced'] != 1 else ''}."
                )
            st.rerun()
        except Exception as error:
            st.error("Could not sync edition display to Shopify.")
            st.error(str(error))

    with st.expander("Import CSV", expanded=False):
        st.caption("Updates existing cached products only. Match order: Shopify product ID, handle, then product title.")
        import_columns = st.columns([2.5, 1])
        uploaded_csv = import_columns[0].file_uploader(
            "Limited Edition CSV",
            type=["csv"],
            key="limited-edition-import-csv",
            label_visibility="collapsed",
        )
        import_clicked = import_columns[1].button("Import CSV", disabled=uploaded_csv is None, use_container_width=True)
        if import_clicked and uploaded_csv is not None:
            try:
                result = import_limited_editions_csv(uploaded_csv)
                st.session_state.limited_edition_notice = (
                    f"Imported {result['imported_rows']} rows. Updated {result['updated_rows']} products. "
                    f"Skipped {result['skipped_rows']} rows."
                )
                if result["errors"]:
                    st.session_state.limited_edition_warning = "First import issue: " + result["errors"][0]
                st.rerun()
            except Exception as error:
                st.error("Could not import the CSV.")
                st.error(str(error))

    filters = st.columns([1, 1.1, 0.8, 0.9, 0.75])
    shopify_status = filters[0].selectbox(
        "Shopify status",
        ["All", "Active", "Draft", "Archived", "Missing"],
        key="le-shopify-status",
    )
    edition_filter = filters[1].selectbox(
        "Edition status",
        ["All", "Not Set", "Available", "Count", "Low", "Final Editions", "Sold Out"],
        key="le-edition-status",
    )
    missing_psd_only = filters[2].checkbox("Missing PSD", key="le-missing-psd")
    missing_prodigi_only = filters[3].checkbox("Missing Prodigi", key="le-missing-prodigi")
    show_limit = filters[4].selectbox("Show", [25, 50, 100, 500], index=0, key="le-show-limit")

    st.caption(
        f"Last fetched: {format_updated_at(summary['last_synced_at']) if summary['last_synced_at'] else 'Never'} - "
        f"{summary['total']} products cached - {edition_summary['needs_widget_sync']} needing widget sync"
    )

    products = db.list_shopify_edition_products(
        search=search,
        shopify_status=shopify_status,
        edition_filter=edition_filter,
        limit=show_limit,
    )
    if missing_psd_only:
        products = [product for product in products if not product.get("psd_file_url")]
    if missing_prodigi_only:
        products = [product for product in products if not product.get("prodigi_url")]

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

    st.caption(f"{len(products)} product{'s' if len(products) != 1 else ''} shown")
    if not products:
        st.info("No cached Shopify products match these filters. Use Fetch Latest Shopify Products if the cache is empty.")
        return

    header = st.columns([2.5, 0.75, 0.8, 0.8, 0.7, 0.75, 1.05, 0.75, 0.85, 1.05])
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
            "Prodigi",
            "Last Updated",
        ),
    ):
        column.markdown(f"**{label}**")

    for product in products:
        item_key = limited_edition_item_key(product)
        row = st.columns([2.5, 0.75, 0.8, 0.8, 0.7, 0.75, 1.05, 0.75, 0.85, 1.05])
        product_title = product.get("product_title") or "Untitled Shopify Product"
        if product.get("online_store_url"):
            safe_title = html.escape(product_title)
            safe_url = html.escape(product["online_store_url"], quote=True)
            row[0].markdown(
                f'<a href="{safe_url}" target="_blank" style="color:#F5F2EA;font-weight:700;text-decoration:none;">{safe_title}</a>',
                unsafe_allow_html=True,
            )
        else:
            row[0].markdown(f"**{product_title}**")
        row[0].caption(product.get("shopify_handle") or "Handle missing")

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
        if product.get("psd_file_url"):
            row[7].link_button("Open PSD", product["psd_file_url"], use_container_width=True)
        else:
            row[7].caption("Missing")
        if product.get("prodigi_url"):
            row[8].link_button("Open Prodigi", product["prodigi_url"], use_container_width=True)
        else:
            row[8].caption("Missing")
        last_updated = product.get("edition_updated_at") or product.get("updated_at") or product.get("last_shopify_sync_at")
        row[9].caption(format_updated_at(last_updated))
        if product.get("widget_sync_status") == "Needs Sync":
            row[9].markdown(status_badge("Needs Sync"), unsafe_allow_html=True)

        with st.expander(f"Edit links and notes - {product.get('shopify_handle') or product_title}", expanded=False):
            detail_columns = st.columns([1.6, 1.6, 1, 1.2])
            detail_columns[0].text_input(
                "PSD file URL",
                value=product.get("psd_file_url") or "",
                key=f"le-psd-{item_key}",
            )
            detail_columns[1].text_input(
                "Prodigi URL",
                value=product.get("prodigi_url") or "",
                key=f"le-prodigi-url-{item_key}",
            )
            detail_columns[2].text_input(
                "Prodigi Product ID",
                value=product.get("prodigi_product_id") or "",
                key=f"le-prodigi-id-{item_key}",
            )
            detail_columns[3].caption(f"Shopify ID: {product.get('shopify_product_id') or 'Missing'}")
            detail_columns[3].caption(
                f"Metafield sync: {format_updated_at(product.get('last_edition_sync_at')) if product.get('last_edition_sync_at') else 'Never'}"
            )
            st.text_area(
                "Notes",
                value=product.get("edition_notes") or "",
                height=72,
                key=f"le-notes-{item_key}",
            )
        st.divider()


def _assignment_text(assignments):
    if not assignments:
        return "No edition assigned"
    return ", ".join(
        f"#{item['edition_number']}/{item['edition_limit']}"
        for item in assignments
        if item.get("assignment_status") not in {"Voided", "Refunded"}
    ) or "Edition locked but voided/refunded"


def render_orders_page():
    st.title("Orders")
    st.caption("Edition numbers are assigned from Sports Cave OS, not Shopify stock.")
    config = shopify_sync.get_config()
    order_summary = db.get_shopify_order_summary()
    notice = st.session_state.pop("orders_notice", None)
    warning = st.session_state.pop("orders_warning", None)
    if notice:
        st.success(notice)
    if warning:
        st.warning(warning)

    toolbar = st.columns([2.4, 1, 1, 1])
    search = toolbar[0].text_input("Search order/customer/product", placeholder="Order, customer, product")
    sync_clicked = toolbar[1].button(
        "Sync Shopify Orders",
        type="primary",
        disabled=not config["configured"],
        use_container_width=True,
    )
    status_filter = toolbar[2].selectbox(
        "Filter",
        ["All", "Needs Edition", "Assigned", "Paid", "Unfulfilled", "Error", "Sold Out Issue"],
    )
    show_limit = toolbar[3].selectbox("Show", [25, 50, 100, 500], index=1)

    if not config["configured"]:
        st.warning("Shopify is not connected yet. Configure Shopify credentials in Render environment variables.")

    if sync_clicked:
        run_id = db.start_shopify_order_sync(config["store_domain"], config["api_version"])
        progress = st.progress(0, text="Starting Shopify order sync...")
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
                )
                progress.progress(
                    min(int(orders_seen / config["max_orders"] * 100), 99),
                    text=f"Synced {orders_seen} Shopify orders...",
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
            progress.progress(100, text="Shopify order sync complete.")
            st.session_state.orders_notice = (
                f"Synced {orders_seen} Shopify orders. Assigned {assignments_created} edition number"
                f"{'s' if assignments_created != 1 else ''}."
            )
            if sync_warning:
                st.session_state.orders_warning = sync_warning
            st.rerun()
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
            st.error("Shopify order sync failed. Check read_orders scope and API version.")
            st.error(str(error))

    metrics = st.columns(3)
    metrics[0].metric("Orders synced", order_summary["total"])
    metrics[1].metric("Needs edition", order_summary["needs_assignment"])
    metrics[2].metric("Assigned today", order_summary["assigned_today"])
    st.caption(
        "Last order sync: "
        + (format_updated_at(order_summary["last_synced_at"]) if order_summary["last_synced_at"] else "Never")
    )

    orders = db.list_shopify_orders(search=search, status_filter=status_filter, limit=show_limit)
    if not orders:
        st.info("No synced Shopify orders match these filters. Run Sync Shopify Orders when you are ready.")
        return

    for order in orders:
        with st.container(border=True):
            header = st.columns([1.3, 1.8, 1.2, 1.1, 1.2, 1])
            header[0].markdown(f"**{order.get('order_name') or order.get('order_number') or 'Order'}**")
            header[1].write(order.get("customer_name") or "Customer not shown")
            header[2].write(format_updated_at(order.get("created_at")))
            header[3].markdown(status_badge(order.get("financial_status") or "Unknown"), unsafe_allow_html=True)
            header[4].markdown(status_badge(order.get("fulfillment_status") or "Unknown"), unsafe_allow_html=True)
            if order.get("admin_url"):
                header[5].link_button("Open Shopify Order", order["admin_url"], use_container_width=True)

            for line in order["line_items"]:
                line_columns = st.columns([2.6, 1.2, 1.6, 1.2, 1, 1, 1.4])
                product_label = line.get("product_title") or "Unknown product"
                if line_columns[0].button(product_label, key=f"order-track-product-{line['id']}", use_container_width=True):
                    st.session_state["limited-edition-search"] = line.get("product_handle") or product_label
                    st.session_state.pending_page = "Limited Editions"
                    st.rerun()
                line_columns[0].caption(line.get("variant_title") or "Variant not shown")
                line_columns[1].write(f"Qty {line.get('quantity') or 1}")
                line_columns[2].write(_assignment_text(line.get("assignments") or []))
                line_columns[3].markdown(status_badge(line.get("assignment_status")), unsafe_allow_html=True)
                if line.get("psd_file_url"):
                    line_columns[4].link_button("Open PSD", line["psd_file_url"], use_container_width=True)
                if line.get("prodigi_url"):
                    line_columns[5].link_button("Open Prodigi", line["prodigi_url"], use_container_width=True)
                with line_columns[6].expander("Manual override"):
                    st.warning("Manual edition changes can affect collector records.")
                    override_number = st.number_input(
                        "Edition number",
                        min_value=1,
                        step=1,
                        key=f"override-number-{line['id']}",
                    )
                    override_notes = st.text_input("Notes", key=f"override-notes-{line['id']}")
                    if st.button("Save Override", key=f"override-save-{line['id']}", use_container_width=True):
                        try:
                            db.manual_override_edition_assignment(
                                line["id"],
                                override_number,
                                notes=override_notes,
                                force=False,
                            )
                            st.session_state.orders_notice = "Manual edition override saved."
                            st.rerun()
                        except Exception as error:
                            st.error(str(error))


def render_settings_page(app_version, database_path, password_status):
    st.title("Settings")
    st.caption("Safe connection status and file workflow settings for Sports Cave OS.")
    shopify_config = shopify_sync.get_config()
    shopify_token_status = shopify_sync.get_token_status(shopify_config)
    shopify_summary = db.get_shopify_summary()
    order_summary = db.get_shopify_order_summary()
    latest_shopify_run = db.get_latest_shopify_sync_run()
    latest_order_run = db.get_latest_shopify_order_sync_run()
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
        ("Order sync count", str(order_summary["total"])),
        ("Last product sync status", last_sync_status),
        ("Last order sync status", order_sync_status),
        ("Last product fetch", format_updated_at(shopify_summary["last_synced_at"]) if shopify_summary["last_synced_at"] else "Never"),
        ("Last order fetch", format_updated_at(order_summary["last_synced_at"]) if order_summary["last_synced_at"] else "Never"),
        (
            "Last token refresh",
            format_updated_at(shopify_token_status["last_refresh"])
            if shopify_token_status["last_refresh"]
            else "Never",
        ),
        ("Google Drive mode", "Link-based file hub"),
        ("Full Google Drive API sync", "Coming later"),
        ("Drive Picker", "Coming later"),
        ("Certificate system", "Not active yet"),
    )
    columns = st.columns(2)
    for index, (label, value) in enumerate(settings):
        with columns[index % 2]:
            with st.container(border=True):
                st.markdown(f"**{label}**")
                st.caption(value)

    st.info(
        "Phase 5B reads Shopify products and orders only when a worker clicks Sync. "
        "Client credentials are exchanged for a temporary in-memory token only at that time. "
        "Edition numbers come from Sports Cave OS; Shopify metafields are display only."
    )
    st.write(f"**Local database:** `{database_path}`")
    st.write(f"**Password protection:** {password_status}")
    st.write(f"**App version:** {app_version}")


def render_placeholder_page(title):
    render_page_intro(
        title,
        "Coming in a later phase.",
        "Use Dashboard, Products, Files, Product Uploads, Mockups, or Limited Editions for the current Phase 3 workflows.",
    )
