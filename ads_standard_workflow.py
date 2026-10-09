"""Shared standard three-ad CSV editor using the existing Ads parser and image workflow."""
import hashlib


def apply_csv(ads, result, workflow, data):
    rows = ads.parse_standard_ads_csv(data, product_name=result['product_name'])
    # Validate the entire import before replacing the current draft.
    workflow['standard_ads'] = [dict(row) for row in rows]
    workflow.pop(ads.posting_handoff.SAVED_PACKAGE_KEY, None)
    for key in list(ads.st.session_state):
        if str(key).startswith(f"ads-single-copy::{result['context_key']}::"):
            ads.st.session_state.pop(key, None)
    return rows


def csv_bytes(ads, result, workflow):
    return ads.build_standard_ads_csv(workflow.get('standard_ads') or None, product_name=result['product_name'])


def render(ads, result, workflow, *, source_matches=True):
    st = ads.st
    with st.popover('CSV', icon=':material/table_view:'):
        upload = st.file_uploader('Import CSV', type=['csv'], key=f"ads-single-import::{result['context_key']}")
        if upload is not None:
            data = upload.getvalue()
            digest = hashlib.sha256(data).hexdigest()
            if digest != workflow.get('standard_csv_upload_hash'):
                try:
                    apply_csv(ads, result, workflow, data)
                    workflow['standard_csv_status'] = (True, 'CSV imported — ad copy applied.')
                except ads.StandardAdsCSVError as error:
                    workflow['standard_csv_status'] = (False, str(error))
                workflow['standard_csv_upload_hash'] = digest
        st.download_button('Export CSV', csv_bytes(ads, result, workflow), file_name=ads.STANDARD_ADS_CSV_FILENAME,
                           mime='text/csv', key=f"ads-single-export::{result['context_key']}")
        status = workflow.get('standard_csv_status')
        if status:
            (st.success if status[0] else st.error)(status[1])
    rows = workflow.get('standard_ads') or []
    if not rows:
        st.caption('Import the completed CSV to populate the ad copy and show three image slots.')
        if result.get('workflow_mode') == 'creative_refresh':
            ads._render_ads_final_actions(result, workflow, source_matches=source_matches)
        return
    for row in rows:
        number = row['ad_number']
        label = 'CREATIVE REFRESH' if result.get('workflow_mode') == 'creative_refresh' else 'AD'
        with st.expander(f'{label} {number} — copy', expanded=False):
            for field, title in ads.STANDARD_ADS_OUTPUT_FIELDS:
                row[field] = st.text_area(title, value=str(row.get(field) or ''),
                    key=f"ads-single-copy::{result['context_key']}::{number}::{field}")
    try:
        ads.parse_standard_ads_csv(csv_bytes(ads, result, workflow), product_name=result['product_name'])
    except ads.StandardAdsCSVError as error:
        if result.get('workflow_mode') != 'creative_refresh':
            st.error(str(error))
            return
        st.caption(f'Draft copy needs completion before publishing: {error}')
    ads._render_ads_image_slots(result, workflow)
    if result.get('workflow_mode') == 'creative_refresh':
        ads._render_ads_final_actions(result, workflow, source_matches=source_matches)
        return
    ads._render_ads_image_save(result, workflow)
    st.caption("POST NOW opens the saved package in Posting for review. Standard single-image publishing is not yet supported there.")
    ads._render_saved_ad_post_now(result, workflow, source_matches=source_matches)
