"""Google-only rendering within the existing New Ads form and Files save workflow."""

import hashlib
from copy import deepcopy

import streamlit as st

import ads_google_demand_gen as google


PLATFORM_KEY = "ads_platform"
PENDING_KEY = "ads_google_pending_record"


def beta():
    st.markdown('<span style="color:#D4A54C;font-size:0.75rem;font-weight:600">BETA</span>', unsafe_allow_html=True)


def form_keys():
    import ads_page as ads
    return (ads.ADS_PRODUCT_NAME_KEY, ads.ADS_PRODUCT_SELECTOR_KEY, "ads_category", "ads_country",
            "ads_campaign_type", *ads.CAMPAIGN_MOMENT_SESSION_KEYS,
            ads.ADS_PRODUCT_URL_KEY, ads.ADS_PRODUCT_URL_AUTOFILL_PRODUCT_KEY,
            ads.ADS_PRODUCT_URL_AUTOFILL_SELECTION_KEY, ads.ADS_PRODUCT_URL_PREVIOUS_PRODUCT_KEY,
            ads.ADS_PRODUCT_URL_LAST_AUTO_VALUE_KEY, ads.ADS_PRODUCT_URL_MANUALLY_EDITED_KEY,
            ads.ADS_PRODUCT_URL_INITIALIZED_KEY)


def platform_changed():
    """Keep drafts and form values separate without renaming any legacy Meta widget key."""
    state = st.session_state
    previous = state.get("ads_previous_platform", "Meta")
    state[f"ads_form_snapshot_{previous}"] = {key: deepcopy(state[key]) for key in form_keys() if key in state}
    selected = state.get(PLATFORM_KEY, "Meta")
    snapshot = state.get(f"ads_form_snapshot_{selected}")
    if snapshot is not None:
        for key in form_keys():
            state.pop(key, None)
        state.update(deepcopy(snapshot))
    state["ads_previous_platform"] = selected


def apply_pending(product_rows):
    import ads_page as ads
    pending = st.session_state.pop(PENDING_KEY, None)
    if not pending:
        return
    result, workflow = pending
    st.session_state[google.RESULT_KEY] = result
    st.session_state[google.WORKFLOW_KEY] = workflow
    selection = ads.resolve_edition_ops_product_selection(result["product_name"], rows=product_rows,
                                                         product_id=result.get("product_id"))
    selector = ads._edition_ops_product_selector_identity(selection["row"]) if selection.get("row") else result["product_name"]
    st.session_state[ads.ADS_PRODUCT_SELECTOR_KEY] = selector
    st.session_state[ads.ADS_PRODUCT_NAME_KEY] = result["product_name"]
    resolved = ads.resolve_ads_product_selector_value(selector, rows=product_rows)
    ads._synchronise_ads_product_url_state(resolved)
    st.session_state[ads.ADS_PRODUCT_URL_KEY] = result["product_url"]
    st.session_state[ads.ADS_PRODUCT_URL_MANUALLY_EDITED_KEY] = True
    for field in ("category", "country"):
        st.session_state[f"ads_{field}"] = result[field]
    moment = result["campaign_moment"]
    for field in ("type", "name", "market", "promotion", "strength"):
        st.session_state[f"ads_campaign_moment_{field}"] = moment.get(field, "")
    st.session_state["ads_campaign_moment_date"] = ads._parse_campaign_moment_date(moment.get("date"))
    st.session_state["ads_campaign_moment_include_images"] = moment.get("include_in_image_prompts", False)


def how_to():
    st.markdown(
        "**GOOGLE DEMAND GEN BETA**\n\n"
        "1. Select product, category and country.\n"
        "2. Copy the generated ChatGPT prompt and download the blank Google CSV template from CSV.\n"
        "3. Upload the exact Sports Cave product image and CSV template in ChatGPT with that prompt.\n"
        "4. ChatGPT returns the Google Demand Gen setup, 5 headlines, 5 descriptions, 9 complete image-generation prompts and the completed CSV.\n"
        "5. Upload the completed Google CSV, then generate the 9 creatives.\n"
        "6. Upload the finished creatives into the matching Sports Cave OS image slots.\n"
        "7. Save the campaign.\n"
        "8. Post Now is unavailable for Google while the Google Ads connection is still in Beta."
    )


def render_reopen():
    import ads_page as ads
    with st.expander("Open saved Google campaign", expanded=False):
        st.caption("Choose the Google campaign folder saved through Files.")
        if st.button("Browse saved campaigns", key="ads-google-browse-open"):
            st.session_state["ads_google_browse"] = True
        if not st.session_state.get("ads_google_browse"):
            return
        if not ads.os_accounts.can_access_page(ads.current_ads_user(), "Files"):
            st.info("Files access is not approved for this account.")
            return
        try:
            token, root = ads._ads_dropbox_connection()
            picker = st.session_state.setdefault("ads_google_load_picker", {})
            folder = ads._render_ads_folder_picker(token, root, {"context_key": "google-load"}, picker,
                state_key="ads_google_load_picker", key_prefix="google-load-picker", container_key="google-load-picker")
            if st.button("Open this Google campaign", key="ads-google-load-confirm"):
                path = ads.dropbox_integration.join_upload_path(folder, google.MANIFEST_FILENAME)
                st.session_state[PENDING_KEY] = google.load_campaign(token, root, path)
                st.session_state["ads_google_browse"] = False
                st.rerun()
        except Exception as error:
            st.error(f"Could not open the Google campaign: {error}")


def render_result(result, *, product_rows=(), source_matches=True):
    import ads_page as ads
    workflow = st.session_state.get(google.WORKFLOW_KEY)
    if not workflow or workflow.get("context_key") != result["context_key"]:
        workflow = google.new_workflow(result)
        st.session_state[google.WORKFLOW_KEY] = workflow
    context = result["context_key"]
    st.subheader("1. Copy this ChatGPT prompt")
    ads.render_prompt_copy_button(result["master_prompt"], f"google-prompt::{context}")
    if not source_matches:
        st.info("The form has changed. Select Submit to build the Google campaign for these values.")

    # Same CSV popover pattern as Meta; process imports before displaying shared copy.
    heading, control = st.columns([5, 1], vertical_alignment="center")
    heading.subheader("GOOGLE AD COPY")
    with control:
        with st.popover("CSV", icon=":material/table_view:"):
            st.download_button("Download Google CSV Template", data=google.build_csv(template=True),
                file_name=google.TEMPLATE_FILENAME, mime="text/csv", key=f"google-template::{context}")
            uploaded = st.file_uploader("Upload Completed Google CSV", type=["csv"], key=f"google-csv::{context}")
            if uploaded is not None:
                digest = hashlib.sha256(uploaded.getvalue()).hexdigest()
                if digest != workflow.get("csv_upload_hash"):
                    try:
                        record, imported = google.import_csv(uploaded.getvalue(), current=result,
                                                             workflow=workflow, product_rows=product_rows)
                        imported["csv_upload_hash"] = digest
                        imported.pop("csv_error", None)
                        st.session_state[PENDING_KEY] = (record, imported)
                        st.rerun()
                    except google.GoogleCampaignError as error:
                        workflow["csv_upload_hash"] = digest
                        workflow["csv_error"] = str(error)
            if workflow.get("csv_error"):
                st.error(workflow["csv_error"])
            st.download_button("Download Filled Google CSV", data=google.build_csv(result, workflow),
                file_name=google.FILLED_FILENAME, mime="text/csv", key=f"google-filled::{context}")
    config = result["google_config"]
    if result.get("copy_loaded"):
        st.success("Google Copy Loaded ✓")
        st.caption("Headlines: 5 / 5 · Descriptions: 5 / 5 · Image Prompts: 9 / 9")
        st.caption(f"Generated Assets: {google.asset_count(workflow)} / 9")
    else:
        st.caption("Download the blank CSV template, have ChatGPT complete it, then upload the completed CSV here.")
    left, right = st.columns(2)
    for column, label, key in ((left, "Headlines", "headlines"), (right, "Descriptions", "descriptions")):
        column.markdown(f"**{label}**")
        for index, value in enumerate(config[key], 1):
            column.text(f"{index}. {value}")
    st.text(f"Business Name: {config['business_name']}\nCTA: {config['cta']}")
    if result.get("copy_loaded"):
        with st.expander("Google Demand Gen setup", expanded=False):
            for key in ("campaign_name", "ad_group_name", "ad_name", "campaign_goal", "bidding_strategy",
                        "conversion_goal", "product_feed_mode", "product_feed_guidance", "channels", "display_network",
                        "audience_name", "demographic_signal", "optimised_targeting", "final_url_suffix"):
                st.text(f"{key.replace('_', ' ').title()}: {config.get(key, '')}")
            st.text("Custom Search Segment: " + "; ".join(config.get("search_terms", [])))

    st.subheader("Generated Ad Images")
    st.caption("Nine assets for ONE Google Demand Gen Image + Products ad.")
    for group_index, (_, group) in enumerate(google.GROUPS):
        st.markdown(f"**GROUP {group_index + 1} — {group}**")
        for column, spec in zip(st.columns(3), google.IMAGE_SLOTS[group_index * 3:group_index * 3 + 3]):
            with column, st.container(border=True):
                slot_id = spec["id"]
                st.markdown(f"**{spec['label']}**")
                st.caption(f"{spec['width']} × {spec['height']} · {spec['ratio']}")
                slot = workflow["slots"].get(slot_id) or {}
                version = workflow["upload_versions"].get(slot_id, 0)
                uploaded = st.file_uploader("Replace image" if slot else "Upload image", type=["png", "jpg", "jpeg", "webp"],
                    key=f"google-image::{context}::{slot_id}::{version}")
                if uploaded is not None:
                    digest = hashlib.sha256(uploaded.getvalue()).hexdigest()
                    if digest != workflow.setdefault("upload_hashes", {}).get(slot_id):
                        workflow["upload_hashes"][slot_id] = digest
                        try:
                            workflow["slots"][slot_id] = google.process_image(uploaded.getvalue(), spec, original_name=uploaded.name)
                            workflow["outcomes"].pop(slot_id, None)
                            workflow.setdefault("upload_errors", {}).pop(slot_id, None)
                            result["google_config"]["image_slots"][slot_id].pop("saved_path", None)
                            slot = workflow["slots"][slot_id]
                        except (google.GoogleCampaignError, google.images.AdsImageValidationError) as error:
                            workflow.setdefault("upload_errors", {})[slot_id] = str(error)
                if workflow.get("upload_errors", {}).get(slot_id):
                    st.error(workflow["upload_errors"][slot_id])
                if slot.get("valid"):
                    st.image(slot["data"], width="stretch")
                    receipt = workflow["outcomes"].get(slot_id) or {}
                    st.caption(f"Saved filename: {spec['filename']}" if receipt else f"Filename on save: {spec['filename']}")
                    st.caption("Saved ✓" if receipt else "Ready to save ✓")
                else:
                    st.caption("Image needed")
                if st.button("Remove", key=f"google-remove::{context}::{slot_id}", disabled=not slot):
                    workflow["slots"].pop(slot_id, None)
                    workflow["outcomes"].pop(slot_id, None)
                    workflow.get("upload_hashes", {}).pop(slot_id, None)
                    workflow.get("upload_errors", {}).pop(slot_id, None)
                    workflow["upload_versions"][slot_id] = version + 1
                    result["google_config"]["image_slots"][slot_id].pop("saved_path", None)
                    st.rerun()
                prompt = config["image_slots"][slot_id].get("prompt")
                if prompt:
                    with st.expander("Image generation prompt"):
                        st.text(prompt)
                        ads.render_prompt_copy_button(prompt, f"google-slot-prompt::{context}::{slot_id}", label="Copy Image Prompt")
    st.caption(f"Google Assets: {google.asset_count(workflow)} / 9")
    st.caption(google.completion_label(workflow))
    render_save(result, workflow, source_matches=source_matches)
    st.subheader("Post Now")
    beta()
    st.button("Post Now", disabled=True, help=google.POSTING_HELP, key=f"google-post-now::{context}")
    st.caption(google.POSTING_HELP)


def render_save(result, workflow, *, source_matches):
    import ads_page as ads
    context = result["context_key"]
    if st.button("Save campaign", type="primary", icon=":material/save:",
                 key=f"google-save::{context}", disabled=not source_matches, use_container_width=True):
        workflow["save_open"] = True
    if workflow.get("save_open"):
        user = ads.current_ads_user()
        if not ads.os_accounts.can_access_page(user, "Files"):
            st.info("Files access is not approved for this account.")
            return
        try:
            token, root = ads._ads_dropbox_connection()
            destination = workflow.get("saved_folder_path") or ads._render_ads_folder_picker(
                token, root, result, workflow, state_key=google.WORKFLOW_KEY,
                key_prefix="google-save-picker", container_key="google-save-picker")
            st.caption(f"Destination: {destination}")
            save, cancel = st.columns(2)
            if save.button("Save campaign here", key=f"google-save-confirm::{context}", disabled=not source_matches):
                with st.spinner("Saving Google campaign..."):
                    ads.save_ads_images_to_dropbox(token, root, destination, result, workflow)
                    ads._ads_clear_directory_cache(destination, workflow["saved_folder_path"])
                st.rerun()
            if cancel.button("Cancel", key=f"google-save-cancel::{context}"):
                workflow["save_open"] = False
                st.rerun()
        except Exception as error:
            st.error(f"The Google campaign could not be saved: {error}")
    if workflow.get("saved_folder_path"):
        st.caption(f"Last saved: {result['updated_at']} · {workflow['saved_folder_path']}")
        if st.button("Open folder", icon=":material/folder_open:", key=f"google-folder::{context}"):
            ads._open_ads_files_folder(workflow["saved_folder_path"])
