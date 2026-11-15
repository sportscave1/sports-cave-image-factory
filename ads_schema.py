"""Read-only Ads readiness. DDL belongs to the explicit migration workflow."""
from threading import Lock
from time import monotonic

TABLES = frozenset('ads_action_log ads_analysis_exports ads_copy_pack_versions ads_copy_packs ads_product_mapping ads_sync_logs meta_ad_accounts meta_ad_insights_age_gender_daily meta_ad_insights_country_daily meta_ad_insights_daily meta_ad_insights_platform_daily meta_ads meta_adsets meta_campaigns meta_creative_tags meta_creatives meta_posting_submissions'.split())
POSTING_COLUMNS = frozenset('submission_id request_fingerprint created_at updated_at completed_at status campaign_id campaign_name adset_id adset_name ad_name destination_url image_checksum meta_image_hash meta_creative_id meta_ad_id meta_status safe_error lease_token lease_expires_at product_id product_title product_handle country sport catalog_id catalog_name product_set_id product_set_name audience_type audience_id audience_name pixel_id pixel_name account_currency meta_page_photo_id meta_canvas_photo_element_id meta_canvas_product_element_id meta_canvas_button_element_id meta_canvas_footer_element_id meta_instant_experience_id ad_results posting_mode campaign_ownership adset_ownership campaign_configured_status adset_configured_status requested_lifecycle_strategy verified_lifecycle_strategy lifecycle_verification_source ad_type'.split())
_lock = Lock()
_verified = None


class AdsSchemaUnavailable(RuntimeError):
    pass


def ensure(backend):
    global _verified
    # One target only; bounded positive cache. Failures are never cached.
    target = backend.get_database_url()
    with _lock:
        if _verified and _verified[0] == target and monotonic() < _verified[1]:
            return
        with backend.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=ANY(%s)", (list(TABLES),))
                rows = cur.fetchall()
        tables = {r['table_name'] for r in rows}
        columns = {r['column_name'] for r in rows if r['table_name'] == 'meta_posting_submissions'}
        if TABLES - tables or POSTING_COLUMNS - columns:
            raise AdsSchemaUnavailable('Ads database schema is incomplete. An administrator must apply the reviewed Ads migrations before posting. No migration or Meta write was attempted.')
        _verified = (target, monotonic() + 60)


def reset():
    global _verified
    with _lock:
        _verified = None
