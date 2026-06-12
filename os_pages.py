import re

import streamlit as st

import db


QUICK_LINKS = (
    ("shopify_admin_url", "Open Shopify Admin"),
    ("live_product_url", "Open Live Product Page"),
    ("psd_file_url", "Open PSD File"),
    ("jpg_file_url", "Open JPG File"),
    ("webp_folder_url", "Open WebP Folder"),
    ("mockup_folder_url", "Open Mockup Folder"),
    ("certificate_folder_url", "Open Certificate Folder"),
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


def select_index(options, value, default=0):
    try:
        return options.index(value)
    except ValueError:
        return default


def go_to_product(product_id):
    st.session_state.selected_product_id = int(product_id)
    st.session_state.selected_page = "Products"
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
        ("Total products", metrics["total_products"]),
        ("Live products", metrics["live_products"]),
        ("Needs review", metrics["needs_review"]),
        ("Missing edition limits", metrics["missing_edition_limits"]),
        ("Final editions", metrics["final_editions"]),
        ("Sold out", metrics["sold_out"]),
    )
    metric_columns = st.columns(3)
    for index, (label, value) in enumerate(metric_specs):
        metric_columns[index % 3].metric(label, value)

    st.subheader("Today's Focus")
    st.caption("These lists are generated from the product database, so the next useful task is always visible.")
    focus_columns = st.columns(2)
    with focus_columns[0]:
        render_focus_list("Missing PSD links", focus["missing_psd"], "Every product has a PSD link.")
        render_focus_list("Missing edition limits", focus["missing_edition_limit"], "Every product has an edition limit.")
    with focus_columns[1]:
        render_focus_list("Missing Prodigi IDs", focus["missing_prodigi"], "Every product has a Prodigi ID.")
        render_focus_list("Products not live", focus["not_live"], "All products are live.")


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
            index=select_index(list(db.PRODUCT_STATUSES), product.get("status", "Draft")),
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
        jpg_file_url = st.text_input("JPG file URL", value=product.get("jpg_file_url", ""), key=f"{prefix}-jpg")
        webp_folder_url = st.text_input(
            "WebP folder URL", value=product.get("webp_folder_url", ""), key=f"{prefix}-webp"
        )
        mockup_folder_url = st.text_input(
            "Mockup folder URL", value=product.get("mockup_folder_url", ""), key=f"{prefix}-mockup"
        )
        certificate_folder_url = st.text_input(
            "Certificate folder URL",
            value=product.get("certificate_folder_url", ""),
            key=f"{prefix}-certificate",
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
        "psd_file_url": psd_file_url,
        "jpg_file_url": jpg_file_url,
        "webp_folder_url": webp_folder_url,
        "mockup_folder_url": mockup_folder_url,
        "certificate_folder_url": certificate_folder_url,
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
        columns = st.columns([3.2, 1.3, 1.3, 1.2, 1.1, 0.9, 0.9, 0.8])
        columns[0].markdown(f"**{product['product_name']}**")
        columns[0].caption(product.get("handle") or "No handle")
        columns[1].write(product.get("sport_category") or "Other")
        columns[2].write(product.get("country_focus") or "Global")
        columns[3].markdown(status_badge(product.get("status")), unsafe_allow_html=True)
        columns[4].write(format_optional_number(product.get("editions_remaining")))
        with columns[5]:
            if product.get("shopify_admin_url"):
                st.link_button("Shopify", product["shopify_admin_url"], use_container_width=True)
            else:
                st.caption("No link")
        with columns[6]:
            if product.get("live_product_url"):
                st.link_button("Live", product["live_product_url"], use_container_width=True)
            else:
                st.caption("No link")
        with columns[7]:
            if st.button("Open", key=f"open-product-{product['id']}", use_container_width=True):
                go_to_product(product["id"])


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

    actions = st.columns([1, 3])
    with actions[0]:
        if st.button("Add New Product", type="primary", use_container_width=True):
            st.session_state.show_add_product = not st.session_state.get("show_add_product", False)
    if st.session_state.get("show_add_product"):
        render_add_product_form()

    filter_columns = st.columns([2.2, 1.2, 1.2])
    search = filter_columns[0].text_input("Search products", placeholder="Product name or handle")
    sport_filter = filter_columns[1].selectbox("Sport category", ["All", *db.SPORT_CATEGORIES])
    status_filter = filter_columns[2].selectbox("Status", ["All", *db.PRODUCT_STATUSES])

    products = db.list_products(search=search, sport_category=sport_filter, status=status_filter)
    st.caption(f"{len(products)} product{'s' if len(products) != 1 else ''} found")
    if not products:
        st.info("No products match these filters yet.")
        return

    header = st.columns([3.2, 1.3, 1.3, 1.2, 1.1, 0.9, 0.9, 0.8])
    for column, label in zip(
        header,
        ("Product", "Sport", "Country", "Status", "Edition left", "Shopify", "Live", "Detail"),
    ):
        column.caption(label)
    for product in products:
        render_product_row(product)


def render_product_overview(product):
    st.subheader("Product Overview")
    overview_columns = st.columns(4)
    overview_columns[0].metric("Sport", product.get("sport_category") or "Other")
    overview_columns[1].metric("Country", product.get("country_focus") or "Global")
    overview_columns[2].markdown("**Status**")
    overview_columns[2].markdown(status_badge(product.get("status")), unsafe_allow_html=True)
    overview_columns[3].metric("Handle", product.get("handle") or "Missing")
    if product.get("notes"):
        st.write(product["notes"])
    else:
        st.caption("No VA notes added yet.")

    with st.expander("Edit Product Overview"):
        with st.form(f"edit-product-{product['id']}"):
            payload = product_form_fields(f"edit-{product['id']}", product)
            submitted = st.form_submit_button("Save Product Changes", type="primary")
        if submitted:
            db.update_product(product["id"], payload)
            st.success("Product updated.")
            st.rerun()


def render_quick_links(product):
    st.subheader("Quick Links")
    available_links = [(field, label) for field, label in QUICK_LINKS if product.get(field)]
    if not available_links:
        st.info("No file or product links have been added yet.")
        return

    columns = st.columns(3)
    for index, (field, label) in enumerate(available_links):
        with columns[index % 3]:
            st.link_button(label, product[field], use_container_width=True)


def render_prodigi_mapping(product):
    st.subheader("Prodigi Mapping")
    with st.form(f"prodigi-form-{product['id']}"):
        prodigi_id = st.text_input("Prodigi Product ID", value=product.get("prodigi_product_id") or "")
        submitted = st.form_submit_button("Save Prodigi ID")
    if submitted:
        db.update_product_fields(product["id"], prodigi_product_id=prodigi_id)
        st.success("Prodigi mapping saved.")
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
    return (
        ("Product name exists", bool(product.get("product_name"))),
        ("Handle exists", bool(product.get("handle"))),
        ("PSD link added", bool(product.get("psd_file_url"))),
        ("JPG link added", bool(product.get("jpg_file_url"))),
        ("WebP folder added", bool(product.get("webp_folder_url"))),
        ("Mockup folder added", bool(product.get("mockup_folder_url"))),
        ("Prodigi ID added", bool(product.get("prodigi_product_id"))),
        ("Edition limit set", product.get("edition_limit") is not None),
        ("Shopify admin URL added", bool(product.get("shopify_admin_url"))),
        ("Live product URL added", bool(product.get("live_product_url"))),
    )


def render_readiness_checklist(product):
    st.subheader("Product Readiness Checklist")
    items = readiness_items(product)
    completed = sum(is_ready for _, is_ready in items)
    st.progress(completed / len(items), text=f"{completed} of {len(items)} readiness checks complete")
    columns = st.columns(2)
    for index, (label, is_ready) in enumerate(items):
        marker = "READY" if is_ready else "MISSING"
        columns[index % 2].markdown(
            f'<div class="sc-check sc-check-{"ready" if is_ready else "missing"}"><strong>{marker}</strong> {label}</div>',
            unsafe_allow_html=True,
        )


def render_product_detail_page(product_id):
    product = db.get_product(product_id)
    if not product:
        st.error("This product record could not be found.")
        if st.button("Back to Products"):
            st.session_state.selected_product_id = None
            st.rerun()
        return

    if st.button("Back to Products"):
        st.session_state.selected_product_id = None
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
    detail_columns = st.columns(2)
    with detail_columns[0]:
        render_prodigi_mapping(product)
    with detail_columns[1]:
        render_va_notes(product)
    st.divider()
    render_edition_tracking(product)
    st.divider()
    render_readiness_checklist(product)


def render_local_limited_editions():
    status_filter = st.selectbox("Edition status", ["All", *db.EDITION_STATUSES[:-1]])
    editions = db.list_limited_editions(status_filter)
    st.caption(f"{len(editions)} product{'s' if len(editions) != 1 else ''} shown")

    if not editions:
        st.info("No products match this edition status yet.")
        return

    header = st.columns([3, 1, 1, 1, 1, 1.4, 1.3, 0.8])
    for column, label in zip(
        header,
        ("Product", "Limit", "Sold", "Remaining", "Next", "Edition status", "Last synced", "Detail"),
    ):
        column.caption(label)

    for item in editions:
        with st.container(border=True):
            columns = st.columns([3, 1, 1, 1, 1, 1.4, 1.3, 0.8])
            columns[0].markdown(f"**{item['product_name']}**")
            columns[0].caption(item.get("sport_category") or "Other")
            columns[1].write(format_optional_number(item.get("edition_limit")))
            columns[2].write(item.get("editions_sold") or 0)
            columns[3].write(format_optional_number(item.get("editions_remaining")))
            columns[4].write(format_optional_number(item.get("next_edition_number")))
            columns[5].markdown(status_badge(item.get("edition_status")), unsafe_allow_html=True)
            columns[6].write(item.get("last_synced_at") or "Local only")
            with columns[7]:
                if st.button("Open", key=f"edition-open-{item['product_id']}", use_container_width=True):
                    go_to_product(item["product_id"])


def render_limited_editions_page(dispatch_log_renderer=None):
    render_page_intro(
        "Limited Editions",
        "Local edition limits and remaining numbers for every product in Sports Cave OS.",
        "Open a product to set its edition limit and editions sold.",
        "Edition status is calculated automatically; do not type it manually.",
    )
    render_local_limited_editions()

    if dispatch_log_renderer:
        st.divider()
        show_dispatch_log = st.toggle(
            "Show Edition Dispatch Log",
            value=False,
            help="Loads the existing Google Sheet dispatch view only when you choose to open it.",
        )
        if show_dispatch_log:
            dispatch_log_renderer(embedded=True)


def render_settings_page(app_version, database_path, password_status):
    render_page_intro(
        "Settings",
        "Connection status and future system settings for Sports Cave OS.",
        "No external service connection is required in Phase 1.",
    )
    settings = (
        ("Shopify connection", "Not connected yet"),
        ("Google Drive / file storage", "Not connected yet"),
        ("Certificate system", "Not active yet"),
        ("Marketing Factory", "Not active yet"),
    )
    columns = st.columns(2)
    for index, (label, value) in enumerate(settings):
        with columns[index % 2]:
            with st.container(border=True):
                st.markdown(f"**{label}**")
                st.caption(value)

    st.info(
        "These systems will be connected in later phases. Current phase focuses on product database, "
        "file shortcuts, and limited edition structure."
    )
    st.write(f"**Local database:** `{database_path}`")
    st.write(f"**Password protection:** {password_status}")
    st.write(f"**App version:** {app_version}")


def render_placeholder_page(title):
    render_page_intro(
        title,
        "Coming in a later phase.",
        "Use Dashboard, Products, Mockups, or Limited Editions for the current Phase 1 workflows.",
    )
