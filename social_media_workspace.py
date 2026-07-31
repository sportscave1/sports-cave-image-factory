import hashlib
import html
import io
import json
import logging
import time
from datetime import date, timedelta
from pathlib import PurePosixPath

import streamlit as st
import streamlit.components.v1 as components

from activity_log import record_activity_log
import dropbox_integration
import os_accounts
import social_media
import social_media_branding
import social_media_catalog
import social_media_creator
import social_media_store


CREATOR_RESULT_KEY = "social_creator_result"
CREATOR_PREFILL_KEY = "social_creator_prefill"
SOCIAL_UPLOAD_TYPES = (
    "jpg",
    "jpeg",
    "png",
    "webp",
    "gif",
    "mp4",
    "mov",
    "m4v",
    "webm",
)

FIELD_KEYS = {
    "content_focus": "social-create-focus",
    "collection": "social-create-collection",
    "product_choice": "social-create-product-choice",
    "manual_product": "social-create-manual-product",
    "product_url": "social-create-product-url",
    "event": "social-create-event",
    "market": "social-create-market",
    "sport": "social-create-sport",
    "format": "social-create-format",
    "series": "social-create-series",
    "platforms": "social-create-platforms",
    "production_method": "social-create-production-method",
    "objective": "social-create-objective",
    "funnel_stage": "social-create-funnel",
    "hook": "social-create-hook",
    "cta": "social-create-cta",
    "offer": "social-create-offer",
    "offer_end_date": "social-create-offer-end",
}


def inject_workspace_styles():
    st.markdown(
        """
        <style>
        .sc-social-header {
            padding: 0.75rem 1rem !important;
            margin-bottom: 0.55rem !important;
        }
        .sc-social-header h1 {
            font-size: 1.4rem !important;
        }
        .sc-social-header p {
            font-size: 0.78rem !important;
            margin-top: 0.2rem !important;
        }
        .sc-social-profiles {
            gap: 0.35rem !important;
            margin-bottom: 0.7rem !important;
        }
        .sc-social-profile {
            min-height: 2.35rem !important;
            padding: 0.4rem 0.55rem !important;
        }
        .sc-social-profile svg {
            height: 1.05rem !important;
            width: 1.05rem !important;
        }
        .sc-social-profile-name {
            font-size: 0.74rem !important;
        }
        .sc-social-profile-open {
            display: none !important;
        }
        .sc-social-assignment {
            align-items: center;
            background: #111214;
            border-left: 3px solid #d6a83d;
            border-radius: 6px;
            color: #f5f2ea;
            display: grid;
            gap: 0.25rem 0.9rem;
            grid-template-columns: minmax(0, 1.35fr) repeat(3, minmax(0, 1fr));
            margin: 0.45rem 0 0.75rem;
            padding: 0.75rem 0.9rem;
        }
        .sc-social-assignment strong {
            color: #ffffff;
        }
        .sc-social-assignment-label {
            color: #d6a83d;
            font-size: 0.68rem;
            font-weight: 750;
            text-transform: uppercase;
        }
        .sc-social-assignment-value {
            font-size: 0.83rem;
            line-height: 1.25;
        }
        .sc-social-stage {
            border-top: 1px solid #e5e1d8;
            margin-top: 0.5rem;
            padding-top: 0.55rem;
        }
        .sc-social-stage-title {
            color: #171717;
            font-size: 0.93rem;
            font-weight: 760;
            margin-bottom: 0.2rem;
        }
        .sc-social-selected-product {
            background: #f7f5ef;
            border: 1px solid #ded9cd;
            border-radius: 6px;
            min-height: 4.5rem;
            padding: 0.65rem 0.75rem;
        }
        .sc-social-selected-product strong {
            display: block;
            font-size: 0.86rem;
        }
        .sc-social-selected-product span {
            color: #706a60;
            font-size: 0.72rem;
        }
        .sc-social-plan-row {
            border-top: 1px solid #e6e1d7;
            padding: 0.55rem 0 0.1rem;
        }
        .sc-social-plan-title {
            font-size: 0.86rem;
            font-weight: 730;
        }
        .sc-social-plan-meta {
            color: #736e65;
            font-size: 0.72rem;
        }
        .sc-social-reference {
            background: #111214;
            border-left: 3px solid #d6a83d;
            border-radius: 6px;
            color: #f5f2ea;
            padding: 0.75rem 0.9rem;
        }
        .sc-social-reference strong {
            color: #f1c65b;
        }
        @media (max-width: 760px) {
            .sc-social-assignment {
                grid-template-columns: 1fr 1fr;
            }
            .sc-social-profiles {
                grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _store_activity(result):
    activity = (result or {}).get("activity")
    if not activity:
        return
    record_activity_log(
        activity["action_type"],
        activity["page"],
        activity["message"],
        entity_type=activity["entity_type"],
        entity_id=activity["entity_id"],
        metadata=activity["metadata"],
        event_key=activity["event_key"],
    )


def copy_button(text, *, key, label="Copy"):
    button_id = "social-copy-" + hashlib.sha1(str(key).encode("utf-8")).hexdigest()[:12]
    payload = json.dumps(str(text or ""))
    safe_label = html.escape(label)
    components.html(
        f"""
        <button id="{button_id}" type="button"
          style="width:100%;border:1px solid #252525;border-radius:6px;padding:9px 12px;background:#fff;color:#111;font-weight:700;cursor:pointer;">
          {safe_label}
        </button>
        <script>
        (() => {{
          const button = document.getElementById("{button_id}");
          const value = {payload};
          button.addEventListener("click", async () => {{
            const original = button.innerText;
            try {{
              if (navigator.clipboard && window.isSecureContext) {{
                await navigator.clipboard.writeText(value);
              }} else {{
                const field = document.createElement("textarea");
                field.value = value;
                field.style.position = "fixed";
                field.style.opacity = "0";
                document.body.appendChild(field);
                field.select();
                document.execCommand("copy");
                field.remove();
              }}
              button.innerText = "Copied";
            }} catch (error) {{
              button.innerText = "Copy failed";
            }}
            setTimeout(() => button.innerText = original, 1200);
          }});
        }})();
        </script>
        """,
        height=45,
    )


def _select_index(options, value, default=0):
    try:
        return list(options).index(value)
    except ValueError:
        return default


def _editable_selectbox(label, suggestions, *, key, placeholder):
    current = str(st.session_state.get(key) or "").strip()
    options = list(suggestions)
    if current and current not in options:
        options.insert(0, current)
    value = st.selectbox(
        label,
        options,
        index=_select_index(options, current) if current else None,
        placeholder=placeholder,
        accept_new_options=True,
        filter_mode="fuzzy",
        key=key,
    )
    return str(value or "").strip()


def _product_option_id(product):
    return str(product.get("id") or product.get("handle") or product.get("title") or "")


def _find_product(products, identity):
    return next(
        (
            product
            for product in products
            if _product_option_id(product) == str(identity or "")
        ),
        {},
    )


def _set_prefill(prefill):
    st.session_state[CREATOR_PREFILL_KEY] = dict(prefill or {})
    st.session_state.pop(CREATOR_RESULT_KEY, None)
    st.session_state.pop("social-output-saved-path", None)


def _consume_prefill(products):
    prefill = st.session_state.pop(CREATOR_PREFILL_KEY, None)
    if not prefill:
        return
    offer_end_date = prefill.get("offer_end_date")
    if isinstance(offer_end_date, str) and offer_end_date:
        try:
            offer_end_date = date.fromisoformat(offer_end_date)
        except ValueError:
            offer_end_date = None
    product_match = next(
        (
            product
            for product in products
            if (
                prefill.get("product_handle")
                and str(product.get("handle") or "").casefold()
                == str(prefill.get("product_handle") or "").casefold()
            )
            or (
                prefill.get("product_title")
                and str(product.get("title") or "").casefold()
                == str(prefill.get("product_title") or "").casefold()
            )
        ),
        {},
    )
    mappings = {
        "content_focus": prefill.get("content_focus"),
        "collection": prefill.get("collection"),
        "product_choice": _product_option_id(product_match),
        "manual_product": "" if product_match else prefill.get("product_title"),
        "product_url": prefill.get("product_url") or product_match.get("url"),
        "event": prefill.get("event"),
        "market": prefill.get("market"),
        "sport": prefill.get("sport"),
        "format": prefill.get("format"),
        "series": prefill.get("series"),
        "platforms": list(prefill.get("platforms") or ()),
        "production_method": prefill.get("production_method"),
        "objective": prefill.get("objective"),
        "funnel_stage": prefill.get("funnel_stage"),
        "hook": prefill.get("hook"),
        "cta": prefill.get("cta"),
        "offer": prefill.get("offer"),
        "offer_end_date": offer_end_date,
    }
    for field, value in mappings.items():
        if value not in (None, "", []):
            st.session_state[FIELD_KEYS[field]] = value


def _sync_selected_product(products):
    selected = _find_product(
        products,
        st.session_state.get(FIELD_KEYS["product_choice"]),
    )
    if selected:
        st.session_state[FIELD_KEYS["product_url"]] = selected.get("url") or ""
        st.session_state[FIELD_KEYS["manual_product"]] = ""


def _assignment_from_store(user, target, store, account_store):
    selected_date = social_media.sydney_today()
    assignment = {}
    getter = getattr(store, "get_current_assignment", None)
    if getter:
        try:
            job = getter(
                user,
                target_user_id=target["id"],
                assignment_date=selected_date,
                account_store=account_store,
            )
            assignment = dict((job or {}).get("payload") or {})
            if assignment:
                assignment.update(
                    {
                        "status": job.get("status") or assignment.get("status"),
                        "job_id": job.get("id") or "",
                        "date": job.get("scheduled_date") or selected_date,
                    }
                )
        except Exception:
            assignment = {}
    if assignment:
        return assignment
    strategy = social_media_creator.strategy_assignment_for_date(selected_date)
    priority_getter = getattr(store, "get_weekly_priority", None)
    if priority_getter:
        try:
            priority = priority_getter(user, week_start=selected_date)
        except Exception:
            priority = {}
        if priority:
            strategy["market"] = priority.get("priority_market") or "Global"
            hero_products = priority.get("hero_products") or []
            if hero_products:
                strategy["product_title"] = hero_products[0]
            if priority.get("event_drop"):
                strategy["event"] = priority["event_drop"]
            strategy["offer"] = priority.get("approved_offer") or ""
    return strategy


def _render_assignment(assignment):
    selected_date = assignment.get("scheduled_date") or assignment.get("date")
    if isinstance(selected_date, str):
        try:
            selected_date = date.fromisoformat(selected_date)
        except ValueError:
            selected_date = None
    day_label = assignment.get("day") or (
        selected_date.strftime("%A") if selected_date else "Today"
    )
    subject = (
        assignment.get("product_title")
        or assignment.get("collection")
        or assignment.get("event")
        or "Choose the approved priority"
    )
    platforms = ", ".join(assignment.get("platforms") or ()) or "Recommended platforms"
    st.markdown(
        f"""
        <div class="sc-social-assignment">
          <div>
            <div class="sc-social-assignment-label">Today's assignment</div>
            <div class="sc-social-assignment-value"><strong>{html.escape(str(day_label))}</strong><br>{html.escape(str(assignment.get("series") or "Content"))}</div>
          </div>
          <div>
            <div class="sc-social-assignment-label">Priority</div>
            <div class="sc-social-assignment-value">{html.escape(str(subject))}</div>
          </div>
          <div>
            <div class="sc-social-assignment-label">Objective / status</div>
            <div class="sc-social-assignment-value">{html.escape(str(assignment.get("objective") or "Not set"))}<br>{html.escape(str(assignment.get("status") or "Draft"))}</div>
          </div>
          <div>
            <div class="sc-social-assignment-label">Format / market</div>
            <div class="sc-social-assignment-value">{html.escape(str(assignment.get("format") or ""))}<br>{html.escape(str(assignment.get("market") or "Global"))}<br>{html.escape(platforms)}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _creator_payload_from_form(values, selected_product):
    return {
        **values,
        "scheduled_date": social_media.sydney_today(),
        "product_id": selected_product.get("id") or "",
        "product_title": (
            selected_product.get("title")
            or values.get("manual_product")
            or ""
        ),
        "product_handle": selected_product.get("handle") or "",
        "product_image_url": selected_product.get("image_url") or "",
        "edition_limit": selected_product.get("edition_limit"),
        "edition_limit_verified": bool(
            selected_product.get("edition_limit_verified")
        ),
        "edition_limit_source": selected_product.get("edition_limit_source") or "",
        "status": "Draft",
    }


def _render_creator_form(products):
    product_by_id = {
        _product_option_id(product): product
        for product in products
        if _product_option_id(product)
    }
    product_options = ("",) + tuple(product_by_id)
    collections = ("",) + social_media_catalog.collection_options(products)

    with st.container(border=True):
        st.markdown('<div class="sc-social-stage"><div class="sc-social-stage-title">1. What are we promoting?</div></div>', unsafe_allow_html=True)
        focus = st.segmented_control(
            "Content focus",
            social_media_creator.CONTENT_FOCUS_OPTIONS,
            default=st.session_state.get(FIELD_KEYS["content_focus"], "Product"),
            key=FIELD_KEYS["content_focus"],
        )
        row = st.columns(2)
        collection = row[0].selectbox(
            "Collection",
            collections,
            index=_select_index(
                collections,
                st.session_state.get(FIELD_KEYS["collection"], ""),
            ),
            format_func=lambda value: value or "Select a collection",
            key=FIELD_KEYS["collection"],
        )
        product_choice = row[1].selectbox(
            "Product",
            product_options,
            index=_select_index(
                product_options,
                st.session_state.get(FIELD_KEYS["product_choice"], ""),
            ),
            format_func=lambda identity: (
                product_by_id[identity]["title"]
                if identity
                else "Select a product"
            ),
            key=FIELD_KEYS["product_choice"],
            on_change=_sync_selected_product,
            args=(products,),
        )
        selected_product = product_by_id.get(product_choice, {})
        manual_product = ""
        if not selected_product and focus == "Product":
            manual_product = st.text_input(
                "Product name (if it is not in the catalogue)",
                placeholder="Enter the exact verified product name",
                key=FIELD_KEYS["manual_product"],
            )
        product_url = st.text_input(
            "Product URL",
            value=st.session_state.get(
                FIELD_KEYS["product_url"],
                selected_product.get("url") or "",
            ),
            placeholder="https://sportscaveshop.com/products/...",
            key=FIELD_KEYS["product_url"],
        )
        if selected_product or manual_product:
            preview_title = selected_product.get("title") or manual_product
            preview_meta = " / ".join(
                value
                for value in (
                    selected_product.get("product_type"),
                    selected_product.get("handle"),
                )
                if value
            )
            st.markdown(
                f'<div class="sc-social-selected-product"><strong>{html.escape(preview_title)}</strong>'
                f'<span>{html.escape(preview_meta or "Exact protected product selection")}</span></div>',
                unsafe_allow_html=True,
            )
        event = ""
        if focus == "Launch/event":
            event = st.text_input(
                "Event or sporting moment",
                placeholder="Enter the exact approved event, launch or sporting moment",
                key=FIELD_KEYS["event"],
            )
        row = st.columns(2)
        market = row[0].selectbox(
            "Market",
            social_media_creator.MARKET_OPTIONS,
            index=_select_index(
                social_media_creator.MARKET_OPTIONS,
                st.session_state.get(FIELD_KEYS["market"], "Global"),
            ),
            key=FIELD_KEYS["market"],
        )
        sport = row[1].selectbox(
            "Sport",
            social_media_creator.SPORT_OPTIONS,
            index=_select_index(
                social_media_creator.SPORT_OPTIONS,
                st.session_state.get(FIELD_KEYS["sport"], "Other"),
                default=len(social_media_creator.SPORT_OPTIONS) - 1,
            ),
            key=FIELD_KEYS["sport"],
        )

        st.markdown('<div class="sc-social-stage"><div class="sc-social-stage-title">2. What are we making?</div></div>', unsafe_allow_html=True)
        row = st.columns(2)
        content_format = row[0].selectbox(
            "Format",
            social_media_creator.FORMAT_OPTIONS,
            index=_select_index(
                social_media_creator.FORMAT_OPTIONS,
                st.session_state.get(FIELD_KEYS["format"], "Reel"),
            ),
            key=FIELD_KEYS["format"],
        )
        series = row[1].selectbox(
            "Sports Cave series",
            social_media_creator.SERIES_OPTIONS,
            index=_select_index(
                social_media_creator.SERIES_OPTIONS,
                st.session_state.get(FIELD_KEYS["series"], "THE MOMENT"),
                default=1,
            ),
            key=FIELD_KEYS["series"],
        )
        platforms = st.multiselect(
            "Platforms",
            social_media_creator.PLATFORM_OPTIONS,
            default=st.session_state.get(
                FIELD_KEYS["platforms"],
                ["All suitable platforms"],
            ),
            key=FIELD_KEYS["platforms"],
        )
        production_method = ""
        if content_format == "Reel":
            production_method = st.selectbox(
                "Production method",
                social_media_creator.PRODUCTION_METHOD_OPTIONS,
                index=_select_index(
                    social_media_creator.PRODUCTION_METHOD_OPTIONS,
                    st.session_state.get(
                        FIELD_KEYS["production_method"],
                        "AI Reels Studio",
                    ),
                ),
                key=FIELD_KEYS["production_method"],
            )

        st.markdown('<div class="sc-social-stage"><div class="sc-social-stage-title">3. Brief details</div></div>', unsafe_allow_html=True)
        row = st.columns(2)
        objective = row[0].selectbox(
            "Objective",
            social_media_creator.OBJECTIVE_OPTIONS,
            index=_select_index(
                social_media_creator.OBJECTIVE_OPTIONS,
                st.session_state.get(FIELD_KEYS["objective"], "Reach"),
            ),
            key=FIELD_KEYS["objective"],
        )
        funnel_stage = row[1].selectbox(
            "Funnel stage",
            social_media_creator.FUNNEL_OPTIONS,
            index=_select_index(
                social_media_creator.FUNNEL_OPTIONS,
                st.session_state.get(FIELD_KEYS["funnel_stage"], "Cold"),
            ),
            key=FIELD_KEYS["funnel_stage"],
        )
        hook = _editable_selectbox(
            "Hook or content angle",
            social_media_creator.recommended_hook_options(
                objective=objective,
                funnel_stage=funnel_stage,
                series=series,
                content_format=content_format,
            ),
            key=FIELD_KEYS["hook"],
            placeholder="Choose or type a content angle",
        )
        cta = _editable_selectbox(
            "One CTA",
            social_media_creator.recommended_cta_options(
                objective=objective,
                funnel_stage=funnel_stage,
                series=series,
            ),
            key=FIELD_KEYS["cta"],
            placeholder="Choose or type one CTA",
        )
        row = st.columns(2)
        offer = row[0].text_input(
            "Offer (optional)",
            key=FIELD_KEYS["offer"],
        )
        offer_end_date = row[1].date_input(
            "Offer end date (optional)",
            value=None,
            key=FIELD_KEYS["offer_end_date"],
        )
        submitted = st.button(
            "Build Content Prompt",
            type="primary",
            icon=":material/auto_awesome:",
            key="social-build-content-prompt",
            width="stretch",
        )

    values = {
        "content_focus": focus,
        "collection": collection,
        "manual_product": manual_product,
        "product_url": product_url,
        "event": event,
        "market": market,
        "sport": sport,
        "format": content_format,
        "series": series,
        "platforms": platforms,
        "production_method": production_method,
        "objective": objective,
        "funnel_stage": funnel_stage,
        "hook": hook,
        "cta": cta,
        "offer": offer,
        "offer_end_date": offer_end_date.isoformat() if offer_end_date else "",
    }
    return _creator_payload_from_form(values, selected_product), submitted


def _social_dropbox_connection():
    cached = st.session_state.get("files_access_token") or {}
    if cached.get("token") and float(cached.get("expires_at") or 0) > time.monotonic():
        access_token = cached["token"]
    else:
        auth = dropbox_integration.resolve_server_auth()
        access_token = auth["access_token"]
        source = auth.get("source") or "refresh_token"
        st.session_state["files_access_token"] = {
            "token": access_token,
            "source": source,
            "expires_at": time.monotonic() + (25 * 60 if source == "refresh_token" else 5 * 60),
        }
    root_cache = st.session_state.get("files_team_root") or {}
    if (
        root_cache.get("path")
        and float(root_cache.get("loaded_at") or 0) + 15 * 60 > time.monotonic()
    ):
        root_path = str(root_cache["path"])
    else:
        root_path = dropbox_integration.find_team_folder(access_token)
        st.session_state["files_team_root"] = {
            "path": root_path,
            "loaded_at": time.monotonic(),
        }
    return access_token, root_path


def save_social_output(access_token, root_path, package, uploads=()):
    relative_folder = social_media_creator.validate_relative_output_path(
        social_media_creator.output_relative_folder(package["input"])
    )
    destination = dropbox_integration.normalize_dropbox_path(
        f"{root_path}/{relative_folder}"
    )
    if not dropbox_integration.path_is_within_root(destination, root_path):
        raise ValueError("The Social Media output folder is outside the approved Files root.")
    dropbox_integration.ensure_folder_path(
        access_token,
        destination,
        root_path=root_path,
    )
    text_items = (
        ("Brief.txt", social_media_creator.build_brief_text(package).encode("utf-8")),
        ("Social Copy.txt", social_media_creator.build_social_copy_text(package).encode("utf-8")),
    )
    outcomes = []
    skipped = []
    for filename, data in text_items:
        metadata = dropbox_integration.upload_stream(
            access_token,
            f"{destination}/{filename}",
            io.BytesIO(data),
            size=len(data),
            conflict="replace",
        )
        outcomes.append(
            {"filename": filename, "metadata": metadata, "kind": "text"}
        )
    for index, uploaded in enumerate(uploads or (), start=1):
        original_name = str(getattr(uploaded, "name", "") or "asset.bin")
        extension = PurePosixPath(original_name.replace("\\", "/")).suffix.lstrip(".")
        original_data = uploaded.getvalue()
        branding_plan = social_media_creator.branding_plan_for_upload(
            package,
            index=index,
            extension=extension,
        )
        clean_data = original_data
        clean_extension = extension
        clean_error = ""
        try:
            clean_data, clean_extension = social_media_branding.prepare_clean_asset(
                original_data,
                extension,
                branding_plan,
            )
        except Exception as error:
            logging.exception("Social Media clean-master normalization failed")
            clean_error = str(error)
        clean_filename = social_media_creator.asset_filename(
            package["input"],
            index=index,
            extension=clean_extension,
            platform="clean-master",
        )
        metadata = dropbox_integration.upload_stream(
            access_token,
            f"{destination}/{clean_filename}",
            io.BytesIO(clean_data),
            size=len(clean_data),
            conflict="replace",
        )
        outcomes.append(
            {
                "filename": clean_filename,
                "metadata": metadata,
                "kind": "clean_master",
            }
        )
        if clean_error:
            skipped.append(
                {
                    "index": index,
                    "kind": "branded_final",
                    "reason": (
                        "The clean master was saved in its original format, but the "
                        f"branded final could not be created: {clean_error}"
                    ),
                }
            )
            continue
        try:
            branded_data, branded_extension = (
                social_media_branding.compose_branded_asset(
                    clean_data,
                    clean_extension,
                    branding_plan,
                )
            )
        except (
            social_media_branding.SocialBrandAssetError,
            social_media_branding.SocialBrandClaimError,
        ) as error:
            skipped.append(
                {
                    "index": index,
                    "kind": "branded_final",
                    "reason": str(error),
                }
            )
            continue
        branded_filename = social_media_creator.asset_filename(
            package["input"],
            index=index,
            extension=branded_extension,
            platform="branded-final",
        )
        branded_metadata = dropbox_integration.upload_stream(
            access_token,
            f"{destination}/{branded_filename}",
            io.BytesIO(branded_data),
            size=len(branded_data),
            conflict="replace",
        )
        outcomes.append(
            {
                "filename": branded_filename,
                "metadata": branded_metadata,
                "kind": "branded_final",
            }
        )
    cache = st.session_state.setdefault("files_directory_cache", {})
    cache.pop(destination, None)
    cache.pop(dropbox_integration.normalize_dropbox_path(str(PurePosixPath(destination).parent)), None)
    return {
        "path": destination,
        "relative_folder": relative_folder,
        "outcomes": outcomes,
        "skipped": skipped,
    }


def _open_files_folder(path):
    clean_path = dropbox_integration.normalize_dropbox_path(path)
    st.session_state["files_browser_path"] = clean_path
    st.session_state.pop("files_preview_path", None)
    st.session_state["current_page"] = "Files"
    st.session_state["selected_page"] = "Files"
    st.session_state["current_page_source"] = "social-media-output"
    try:
        st.query_params["page"] = "files"
        st.query_params["files_path"] = clean_path
    except Exception:
        pass
    st.rerun()


def _open_ai_reels(payload):
    st.session_state["smrs_final_product_handle"] = social_media_creator.product_handle_from_input(payload)
    st.session_state["smrs_final_product_title"] = payload.get("product_title") or ""
    st.session_state["smrs_final_athlete_product_name"] = (
        payload.get("product_title")
        or payload.get("event")
        or payload.get("collection")
        or ""
    )
    st.session_state["smrs_final_sport_category"] = payload.get("sport") or ""
    st.session_state["current_page"] = social_media.AI_REELS_ROUTE
    st.session_state["selected_page"] = social_media.AI_REELS_ROUTE
    st.session_state["current_page_source"] = "social-media-create"
    try:
        st.query_params["page"] = social_media.AI_REELS_PAGE_KEY
    except Exception:
        pass
    st.rerun()


def _save_job(user, target, store, account_store, package, relative_folder, status):
    saver = getattr(store, "save_content_job", None)
    if not saver:
        return None
    payload = {**package["input"], "status": status}
    key = social_media_store.request_key(
        "content-job-save",
        user.get("id"),
        f"{target['id']}:{package['input_signature']}:{relative_folder}:{status}",
        payload,
    )
    result = saver(
        user,
        target_user_id=target["id"],
        payload=payload,
        generated_output=package,
        destination_path=relative_folder,
        request_key_value=key,
        account_store=account_store,
    )
    _store_activity(result)
    return result


def _render_result(user, target, store, account_store, package):
    st.markdown("### Content package")
    tabs = st.tabs(
        (
            "Today's Brief",
            "ChatGPT Creative Prompt",
            "Caption and Posting Copy",
            "Platform Adaptations",
            "Asset and Approval Checklist",
            "Save Output",
        )
    )
    with tabs[0]:
        for label, value in package["brief"]:
            st.markdown(f"**{label}:** {value}")
        copy_button(
            "\n".join(f"{label}: {value}" for label, value in package["brief"]),
            key="social-brief",
            label="Copy Brief",
        )
    with tabs[1]:
        st.caption(f"Prompt contract: {package['contract_version']}")
        copy_button(
            package["creative_prompt"],
            key="social-creative-prompt",
            label="Copy Complete Prompt",
        )
        st.text_area(
            "Complete creative prompt",
            value=package["creative_prompt"],
            height=360,
            disabled=True,
            key=f"social-creative-preview::{package['input_signature']}",
        )
        for index, prompt in enumerate(package["visual_prompts"], start=1):
            with st.expander(prompt["label"], expanded=index == 1):
                copy_button(
                    prompt["prompt"],
                    key=f"social-visual-prompt::{package['input_signature']}::{index}",
                    label=f"Copy {prompt['label']}",
                )
                st.text_area(
                    f"{prompt['label']} prompt",
                    value=prompt["prompt"],
                    height=280,
                    disabled=True,
                    key=f"social-visual-preview::{package['input_signature']}::{index}",
                )
        for index, prompt in enumerate(package["video_prompts"], start=1):
            with st.expander(prompt["label"], expanded=False):
                copy_button(
                    prompt["prompt"],
                    key=f"social-video-prompt::{package['input_signature']}::{index}",
                    label=f"Copy {prompt['label']}",
                )
                st.text_area(
                    f"{prompt['label']} prompt",
                    value=prompt["prompt"],
                    height=220,
                    disabled=True,
                    key=f"social-video-preview::{package['input_signature']}::{index}",
                )
        if (
            package["input"]["format"] == "Reel"
            and package["input"]["production_method"] == "AI Reels Studio"
        ):
            st.info("Create the stills in ChatGPT, then open AI Reels Studio in Sports Cave OS.")
            if st.button(
                "Open AI Reels",
                icon=":material/movie_edit:",
                key=f"social-open-ai-reels::{package['input_signature']}",
            ):
                _open_ai_reels(package["input"])
    with tabs[2]:
        for index, caption in enumerate(package["caption_variations"], start=1):
            with st.expander(f"Caption {index}", expanded=index == 1):
                st.write(caption)
                copy_button(
                    caption,
                    key=f"social-caption::{package['input_signature']}::{index}",
                    label=f"Copy Caption {index}",
                )
        st.markdown(f"**Cover hook:** {package['cover_hook']}")
        st.markdown(f"**CTA:** {package['cta']}")
        if package["warnings"]:
            st.warning(" ".join(package["warnings"]))
    with tabs[3]:
        platform_copy = "\n\n".join(
            f"{platform}\n{values['guidance']}\n{values['tracked_url'] or '[not supplied]'}"
            for platform, values in package["platform_adaptations"].items()
        )
        copy_button(
            platform_copy,
            key=f"social-platforms::{package['input_signature']}",
            label="Copy Platform Adaptations",
        )
        for platform, values in package["platform_adaptations"].items():
            with st.expander(platform, expanded=False):
                st.write(values["guidance"])
                st.code(values["tracked_url"] or "[not supplied]", language=None)
                copy_button(
                    values["tracked_url"],
                    key=f"social-url::{package['input_signature']}::{platform}",
                    label=f"Copy {platform} URL",
                )
    with tabs[4]:
        copy_button(
            "\n".join(package["checklist"]),
            key=f"social-checklist::{package['input_signature']}",
            label="Copy Checklist",
        )
        for item in package["checklist"]:
            st.checkbox(
                item,
                value=False,
                key=f"social-check::{package['input_signature']}::{item}",
            )
    with tabs[5]:
        st.caption(
            f"Recommended: {package['recommended_asset_count']} ordered asset"
            f"{'s' if package['recommended_asset_count'] != 1 else ''}. "
            "Each uploaded asset saves as a Clean Master and, when verification passes, "
            "a Branded Final. Partial saves are allowed."
        )
        if not package.get("publish_ready", True):
            st.warning(
                "The clean master can be saved, but the branded final is blocked until "
                + " ".join(package.get("warnings") or ())
            )
        uploads = st.file_uploader(
            "Finished images or videos",
            type=list(SOCIAL_UPLOAD_TYPES),
            accept_multiple_files=True,
            key=f"social-output-assets::{package['input_signature']}",
        )
        status_options = social_media_creator.WORK_STATUS_OPTIONS
        allowed_statuses = (
            status_options
            if os_accounts.is_admin(user)
            else tuple(
                status
                for status in status_options
                if status not in {"Approved", "Changes requested"}
            )
        )
        status = st.selectbox(
            "Tracking status",
            allowed_statuses,
            index=_select_index(allowed_statuses, "Draft"),
            key=f"social-output-status::{package['input_signature']}",
        )
        relative_folder = social_media_creator.output_relative_folder(package["input"])
        st.caption(f"Destination: `{relative_folder}`")
        if st.button(
            "Save Output",
            type="primary",
            icon=":material/save:",
            key=f"social-output-save::{package['input_signature']}",
            width="stretch",
        ):
            if not os_accounts.can_access_page(user, "Files"):
                st.warning("Files access is not approved for this account.")
            else:
                try:
                    access_token, root_path = _social_dropbox_connection()
                    saved = save_social_output(
                        access_token,
                        root_path,
                        package,
                        uploads,
                    )
                    try:
                        _save_job(
                            user,
                            target,
                            store,
                            account_store,
                            package,
                            saved["relative_folder"],
                            status,
                        )
                    except Exception:
                        logging.exception("Social Media job tracking save failed")
                        st.warning(
                            "The files were saved, but the tracking record could not be updated."
                        )
                    st.session_state["social-output-saved-path"] = saved["path"]
                    st.success(
                        f"Saved {len(saved['outcomes'])} file"
                        f"{'s' if len(saved['outcomes']) != 1 else ''}."
                    )
                    for skipped in saved.get("skipped") or ():
                        st.warning(skipped.get("reason") or "A branded final was skipped.")
                    record_activity_log(
                        "social_media_output_saved",
                        social_media.SOCIAL_MEDIA_ROUTE,
                        f"Social Media output saved: {relative_folder}",
                        entity_type="dropbox_folder",
                        entity_id=saved["path"],
                        metadata={
                            "relative_folder": relative_folder,
                            "asset_count": len(uploads or ()),
                            "prompt_version": package["contract_version"],
                            "status": "success",
                            "result": "success",
                        },
                        event_key=(
                            f"social-output/{package['input_signature']}/"
                            f"{hashlib.sha1(relative_folder.encode('utf-8')).hexdigest()[:12]}"
                        ),
                    )
                except Exception:
                    logging.exception("Social Media output save failed")
                    st.warning("This Social Media output could not be saved right now.")
        saved_path = st.session_state.get("social-output-saved-path")
        if saved_path:
            st.caption(f"Saved folder: `{saved_path}`")
            if st.button(
                "Open folder in Files",
                icon=":material/folder_open:",
                key=f"social-open-files::{package['input_signature']}",
            ):
                _open_files_folder(saved_path)


def render_create(user, target, store, account_store=None):
    products = social_media_catalog.load_social_product_catalog()
    _consume_prefill(products)
    assignment = _assignment_from_store(user, target, store, account_store)
    _render_assignment(assignment)
    if st.button(
        "Create this",
        type="primary",
        icon=":material/edit_square:",
        key="social-create-assignment",
    ):
        _set_prefill(social_media_creator.prefill_from_assignment(assignment))
        st.rerun()
    payload, submitted = _render_creator_form(products)
    existing = st.session_state.get(CREATOR_RESULT_KEY)
    try:
        current_signature = social_media_creator.input_signature(payload)
    except Exception:
        current_signature = ""
    if existing and current_signature and existing.get("input_signature") != current_signature:
        st.session_state.pop(CREATOR_RESULT_KEY, None)
        st.session_state.pop("social-output-saved-path", None)
        existing = None
        st.caption("Selections changed. Build a fresh prompt for the current brief.")
    if submitted:
        try:
            existing = social_media_creator.build_content_package(payload)
        except social_media_creator.SocialCreatorValidationError as error:
            st.warning(str(error))
        else:
            st.session_state.pop("social-output-saved-path", None)
            st.session_state[CREATOR_RESULT_KEY] = existing
            st.rerun()
    if existing:
        _render_result(user, target, store, account_store, existing)


def _plan_prefill(series, content_format, hook, priority=None):
    priority = dict(priority or {})
    product = (priority.get("hero_products") or [""])[0]
    return {
        "content_focus": "Product" if product else "Launch/event" if priority.get("event_drop") else "Community/fan conversation",
        "product_title": product,
        "event": priority.get("event_drop") or "",
        "market": priority.get("priority_market") or "Global",
        "format": content_format,
        "series": series,
        "platforms": ("All suitable platforms",),
        "production_method": "AI Reels Studio",
        "objective": "Reach",
        "funnel_stage": "Cold",
        "hook": hook,
        "cta": "See the complete edition.",
        "offer": priority.get("approved_offer") or "",
    }


def render_plan(user, target, store, account_store=None):
    week_start, week_end = social_media.sydney_week_bounds()
    priority_getter = getattr(store, "get_weekly_priority", None)
    try:
        priority = priority_getter(user, week_start=week_start) if priority_getter else {}
    except Exception:
        priority = {}
    campaign_mode = priority.get("campaign_mode") or "Normal month"
    st.markdown(
        '<div class="sc-social-reference"><strong>North Star</strong><br>'
        "Sport creates the emotion. The edition becomes the payoff. "
        "Proof removes doubt. Scarcity creates action.</div>",
        unsafe_allow_html=True,
    )
    balance = (
        "35% reach / 35% trust and consideration / 30% conversion"
        if campaign_mode == "Product drop"
        else "50% reach / 30% trust and consideration / 20% conversion"
    )
    st.caption(f"{campaign_mode}: {balance}")

    if os_accounts.is_admin(user):
        products = social_media_catalog.load_social_product_catalog()
        product_titles = tuple(product["title"] for product in products)
        with st.expander("Set this week's priorities", expanded=not bool(priority)):
            with st.form("social-weekly-priority-form"):
                row = st.columns(2)
                priority_market = row[0].selectbox(
                    "Priority market",
                    social_media_creator.MARKET_OPTIONS,
                    index=_select_index(
                        social_media_creator.MARKET_OPTIONS,
                        priority.get("priority_market") or "Global",
                    ),
                )
                selected_mode = row[1].selectbox(
                    "Campaign mode",
                    ("Normal month", "Product drop"),
                    index=0 if campaign_mode == "Normal month" else 1,
                )
                hero_products = st.multiselect(
                    "Hero products or collections",
                    product_titles,
                    default=[
                        item
                        for item in priority.get("hero_products") or ()
                        if item in product_titles
                    ],
                )
                event_drop = st.text_input(
                    "Event or drop",
                    value=priority.get("event_drop") or "",
                )
                approved_offer = st.text_input(
                    "Approved offer",
                    value=priority.get("approved_offer") or "",
                )
                restrictions = st.text_area(
                    "Restrictions",
                    value=priority.get("restrictions") or "",
                    height=75,
                )
                save_priority = st.form_submit_button(
                    "Save weekly priorities",
                    type="primary",
                    width="stretch",
                )
            if save_priority:
                payload = {
                    "week_start": week_start,
                    "priority_market": priority_market,
                    "hero_products": hero_products,
                    "event_drop": event_drop,
                    "approved_offer": approved_offer,
                    "restrictions": restrictions,
                    "campaign_mode": selected_mode,
                }
                key = social_media_store.request_key(
                    "weekly-priority",
                    user.get("id"),
                    str(week_start),
                    payload,
                )
                try:
                    result = store.save_weekly_priority(
                        user,
                        payload=payload,
                        request_key_value=key,
                    )
                    _store_activity(result)
                except Exception:
                    st.warning("This week's Social Media priorities could not be saved.")
                else:
                    st.success("Weekly priorities saved.")
                    st.rerun()

    st.markdown(f"### This Week")
    st.caption(f"{week_start.strftime('%d %b')} to {week_end.strftime('%d %b %Y')}")
    weekly_items = (
        ("Monday", "THE MOMENT", "Reel", "Reach"),
        ("Tuesday", "CAVE DEBATE", "Story sequence", "Engagement"),
        ("Wednesday", "WALL WORTHY", "Reel", "Desire"),
        ("Thursday", "REAL COLLECTORS", "UGC/collector proof", "Trust"),
        ("Friday", "ONLY 100", "Feed carousel", "Conversion"),
    )
    for day_label, series, content_format, job in weekly_items:
        columns = st.columns([1, 2.5, 1.5, 1])
        columns[0].markdown(f"**{day_label}**")
        columns[1].markdown(
            f'<div class="sc-social-plan-title">{series}</div>'
            f'<div class="sc-social-plan-meta">{content_format} - {job}</div>',
            unsafe_allow_html=True,
        )
        columns[2].caption(
            "Approved priority"
            if priority
            else "Strategy template"
        )
        if columns[3].button(
            "Use in Create",
            key=f"social-week-use::{day_label}",
        ):
            prefill = _plan_prefill(
                series,
                content_format,
                next(
                    item["hook"]
                    for item in social_media_creator.WEEKLY_ASSIGNMENTS
                    if item["day"] == day_label
                ),
                priority,
            )
            _set_prefill(prefill)
            st.session_state["social-media-workspace-view"] = "Create"
            st.rerun()

    jobs_loader = getattr(store, "list_content_jobs", None)
    if jobs_loader:
        try:
            jobs = jobs_loader(
                user,
                target_user_id=target["id"],
                start_date=week_start,
                end_date=week_end,
                account_store=account_store,
            )
        except Exception:
            jobs = []
        if jobs:
            with st.expander("Approval and production status", expanded=False):
                st.dataframe(
                    [
                        {
                            "Date": row.get("scheduled_date"),
                            "Content": row.get("title"),
                            "Series": row.get("series"),
                            "Format": row.get("content_format"),
                            "Status": row.get("status"),
                        }
                        for row in jobs
                    ],
                    hide_index=True,
                    width="stretch",
                )
                by_id = {row["id"]: row for row in jobs}
                with st.form("social-plan-status-form"):
                    selected_job_id = st.selectbox(
                        "Work item",
                        tuple(by_id),
                        format_func=lambda job_id: (
                            f"{by_id[job_id].get('title')} - "
                            f"{by_id[job_id].get('status')}"
                        ),
                    )
                    allowed_statuses = (
                        social_media_creator.WORK_STATUS_OPTIONS
                        if os_accounts.is_admin(user)
                        else tuple(
                            status
                            for status in social_media_creator.WORK_STATUS_OPTIONS
                            if status not in {"Approved", "Changes requested"}
                        )
                    )
                    selected_job = by_id[selected_job_id]
                    selected_status = st.selectbox(
                        "Status",
                        allowed_statuses,
                        index=_select_index(
                            allowed_statuses,
                            selected_job.get("status") or "Draft",
                        ),
                    )
                    update_status = st.form_submit_button(
                        "Update status",
                        type="primary",
                        width="stretch",
                    )
                if update_status:
                    payload = {
                        **(selected_job.get("payload") or {}),
                        "status": selected_status,
                    }
                    key = social_media_store.request_key(
                        "content-job-status",
                        user.get("id"),
                        f"{selected_job_id}:{selected_status}:{selected_job.get('updated_at')}",
                        payload,
                    )
                    try:
                        result = store.save_content_job(
                            user,
                            target_user_id=target["id"],
                            job_id=selected_job_id,
                            payload=payload,
                            generated_output=selected_job.get("generated_output") or {},
                            destination_path=selected_job.get("destination_path") or "",
                            source_kind=selected_job.get("source_kind") or "create",
                            request_key_value=key,
                            account_store=account_store,
                        )
                        _store_activity(result)
                    except Exception:
                        st.warning("This content status could not be updated.")
                    else:
                        st.success("Content status updated.")
                        st.rerun()

    with st.expander("Weekly operating rhythm and starting windows", expanded=False):
        for assignment in social_media_creator.WEEKLY_ASSIGNMENTS:
            st.markdown(
                f"**{assignment['day']}:** {assignment['series']} - "
                f"{assignment['objective'].casefold()}."
            )
        st.caption(
            "Starting tests: Australia/New Zealand 6:30-8:30 pm Sydney; "
            "UK 6:00-8:00 pm London; USA/Canada 6:00-9:00 pm target time zone. "
            "Replace these with account data after four weeks."
        )

    st.markdown("### First 30 days")
    for week_title, items in social_media_creator.FIRST_30_DAYS:
        with st.expander(week_title, expanded=False):
            for index, (series, content_format, hook) in enumerate(items):
                columns = st.columns([2, 3, 1.2])
                columns[0].markdown(f"**{series}**")
                columns[1].caption(f"{content_format} - {hook}")
                if columns[2].button(
                    "Use in Create",
                    key=f"social-30-day::{week_title}::{index}",
                ):
                    _set_prefill(
                        _plan_prefill(
                            series,
                            content_format,
                            hook,
                            priority,
                        )
                    )
                    st.session_state["social-media-workspace-view"] = "Create"
                    st.rerun()

    with st.expander("Reusable launch sequence", expanded=False):
        for timing, instruction in social_media_creator.LAUNCH_SEQUENCE:
            st.markdown(f"**{timing}:** {instruction}")


def render_playbook():
    st.markdown(
        '<div class="sc-social-reference"><strong>Positioning</strong><br>'
        "Premium limited-edition sports wall art built around the moments, heroes and "
        "rivalries fans never forget.</div>",
        unsafe_allow_html=True,
    )
    with st.expander("Positioning and content mix", expanded=True):
        st.markdown(
            """
- Trust comes from real frames, real homes, real collectors, craftsmanship and reviews.
- Use "Only 100", live tracking and retired forever only where factually applicable.
- Social is not a sports-news page or a repetitive product catalogue.
- 75-80% connects to a product, collection or future release; 20-25% may be collector-relevant fan conversation.
- Mix: 25% moments/rivalries, 20% product desire, 20% collector proof, 15% behind the edition, 10% community, 10% drops/scarcity.
            """
        )
    with st.expander("Visual system", expanded=False):
        st.markdown(
            """
- Black `#070708`; charcoal `#111214`; warm gold `#D6A83D`; highlight gold `#F1C65B`; off-white `#F5F2EA`.
- Headline: League Spartan or Montserrat ExtraBold. Supporting text: Inter or Montserrat.
- One hero image, one 3-5 word hook, one small gold series label and a restrained logo.
- Team colours stay inside the artwork. The surrounding system stays black, gold and off-white.
- Use slow push-ins, light sweeps, hand reveals, room transitions or detail pans.
- Avoid template-heavy effects and nine-tile puzzle grids.
            """
        )
    with st.expander("Story system", expanded=False):
        st.markdown(
            """
1. Hook.
2. Native interaction: poll, quiz, slider or question box.
3. Product bridge.
4. Proof.
5. One CTA and exact link sticker.

Use 3-6 frames normally and 6-10 only for launches/events. Add platform stickers natively, never render them into generated photography. Use direct links on 3-4 days, not every sequence.
            """
        )
    with st.expander("Platform guide", expanded=False):
        st.markdown(
            """
**Instagram:** Flagship discovery, brand, community and shopping. Reels/Stories 1080 x 1920; feed 1080 x 1350.

**Facebook:** Older fans, trust and product traffic. Add context, proof and direct product links.

**TikTok:** Discovery, personality and debate. Faster hook, original human voice and no cross-platform watermark.

**YouTube Shorts:** Searchable short-form. Use searchable titles and a longer story cut where justified.

**Pinterest:** Evergreen room inspiration and shopping search. Use 1000 x 1500, keyword titles and exact product URLs.
            """
        )
    with st.expander("Approval gates and ownership", expanded=False):
        st.markdown(
            """
- Artwork and frame unchanged.
- Counts, prices, offers and delivery claims verified on scheduling day.
- Rights confirmed.
- Cover survives the profile crop.
- One job and one CTA.
- Exact destination URL opens the correct product and market experience.

Nathan owns goals, markets, hero products, launches, offers, brand decisions, approvals and paid-ad decisions. The VA owns approved production, editing, scheduling, captions, Stories, community triage, UGC requests and reporting. Creative reviews, usage permissions, emerging moments and learning from winners are shared.
            """
        )
    with st.expander("Measurement", expanded=False):
        st.markdown(
            """
- Reels: 3-second hold, average watch time, completion, non-follower reach, shares per reach.
- Carousels: reach, swipe depth, saves, shares, profile visits.
- Stories: completion, exits, sticker taps, replies, link CTR.
- Profile: visits, follows, website taps, product-tag taps.
- Commerce: sessions, product views, add-to-carts, checkouts, purchases, revenue, conversion rate.
- Community: meaningful comments, UGC permissions, DM questions, response time.

Compare each series with its own four-week rolling median after the baseline period. Review organic work after about 72 hours for early signals and seven days for a fuller result before handing winners to Ads.
            """
        )
