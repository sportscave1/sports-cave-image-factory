from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
import uuid
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo

from ads_image_workflow import AdsImageValidationError, prepare_meta_posting_image
from ads_meta_contract import META_AD_URL_PARAMETERS, META_DEFAULT_CTA
from meta_ads_client import (
    MetaAdsAmbiguousResultError,
    MetaAdsApiError,
    MetaPostingClient,
    sanitize_meta_error,
)


SUCCESS_MESSAGE = "Paused in Meta — ready for review"
POSTING_PERMISSION = "ads_management"
POSTING_STATUSES = (
    "VALIDATING",
    "IMAGE_UPLOADED",
    "CREATIVE_CREATED",
    "AD_CREATED",
    "COMPLETE",
    "FAILED",
    "AMBIGUOUS",
)
class PostingError(RuntimeError):
    pass


class PostingValidationError(PostingError):
    pass


class PostingBusyError(PostingError):
    pass


class PostingAmbiguousError(PostingError):
    pass


@dataclass(frozen=True)
class PostingRequest:
    submission_id: str
    campaign_id: str
    adset_id: str
    destination_url: str
    image_bytes: bytes
    image_name: str
    primary_text: str
    headline: str
    ad_name: str
    description: str = ""


def normalize_account_id(value):
    return re.sub(r"^act_", "", str(value or "").strip(), flags=re.IGNORECASE)


def validate_destination_url(value):
    clean = str(value or "").strip()
    parsed = urlparse(clean)
    if parsed.scheme.casefold() != "https" or not parsed.netloc:
        raise PostingValidationError("Enter a valid https:// product URL.")
    return clean


def default_ad_name(destination_url, *, now=None):
    clean_url = str(destination_url or "").strip()
    path_parts = [unquote(part).strip() for part in urlparse(clean_url).path.split("/") if part.strip()]
    handle = path_parts[-1] if path_parts else "product"
    handle = re.sub(r"[^a-zA-Z0-9-]+", "-", handle).strip("-").casefold() or "product"
    timestamp = now or datetime.now(ZoneInfo("Australia/Sydney"))
    return f"SC | {handle} | {timestamp.date().isoformat()}"


def posting_submission_id():
    return str(uuid.uuid4())


def ads_manager_url(*, account_id, campaign_id, adset_id, ad_id):
    account = normalize_account_id(account_id)
    return (
        "https://www.facebook.com/adsmanager/manage/ads"
        f"?act={account}&selected_campaign_ids={campaign_id}"
        f"&selected_adset_ids={adset_id}&selected_ad_ids={ad_id}"
    )


def _request_fingerprint(request, *, image_checksum, destination_url):
    payload = {
        "campaign_id": str(request.campaign_id or "").strip(),
        "adset_id": str(request.adset_id or "").strip(),
        "destination_url": destination_url,
        "image_checksum": image_checksum,
        "primary_text": str(request.primary_text or ""),
        "headline": str(request.headline or ""),
        "description": str(request.description or ""),
        "ad_name": str(request.ad_name or "").strip(),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def validate_posting_request(request):
    try:
        uuid.UUID(str(request.submission_id or ""))
    except (ValueError, TypeError, AttributeError) as error:
        raise PostingValidationError("Start a new Posting submission and try again.") from error
    campaign_id = str(request.campaign_id or "").strip()
    adset_id = str(request.adset_id or "").strip()
    if not campaign_id:
        raise PostingValidationError("Select a Meta campaign.")
    if not adset_id:
        raise PostingValidationError("Select a Meta ad set.")
    destination_url = validate_destination_url(request.destination_url)
    if not bytes(request.image_bytes or b""):
        raise PostingValidationError("Upload the finished ad image.")
    try:
        image = prepare_meta_posting_image(
            request.image_bytes,
            original_name=request.image_name,
        )
    except AdsImageValidationError as error:
        raise PostingValidationError(str(error)) from error
    primary_text = str(request.primary_text or "")
    headline = str(request.headline or "")
    ad_name = str(request.ad_name or "").strip()
    if not primary_text.strip():
        raise PostingValidationError("Enter the final primary text.")
    if not headline.strip():
        raise PostingValidationError("Enter the final headline.")
    if not ad_name:
        raise PostingValidationError("Enter an ad name.")
    return {
        "campaign_id": campaign_id,
        "adset_id": adset_id,
        "destination_url": destination_url,
        "image": image,
        "primary_text": primary_text,
        "headline": headline,
        "description": str(request.description or ""),
        "ad_name": ad_name,
        "image_checksum": str(image["source_hash"]),
    }


class SupabasePostingStore:
    """Small persistent ledger providing leases and resumable Meta IDs."""

    def _backend(self):
        import supabase_backend

        return supabase_backend

    def claim(self, request_data, *, lease_token):
        backend = self._backend()
        backend.ensure_ads_schema()
        with backend.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO meta_posting_submissions(
                        submission_id, request_fingerprint, status,
                        campaign_id, campaign_name, adset_id, adset_name,
                        ad_name, destination_url, image_checksum
                    ) VALUES (%s::uuid, %s, 'VALIDATING', %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (submission_id) DO NOTHING
                    """,
                    (
                        request_data["submission_id"],
                        request_data["request_fingerprint"],
                        request_data["campaign_id"],
                        request_data["campaign_name"],
                        request_data["adset_id"],
                        request_data["adset_name"],
                        request_data["ad_name"],
                        request_data["destination_url"],
                        request_data["image_checksum"],
                    ),
                )
                cur.execute(
                    "SELECT * FROM meta_posting_submissions WHERE submission_id=%s::uuid",
                    (request_data["submission_id"],),
                )
                existing = dict(cur.fetchone() or {})
                if str(existing.get("request_fingerprint") or "") != request_data["request_fingerprint"]:
                    raise PostingValidationError(
                        "This submission changed after posting began. Reset and create a new submission."
                    )
                if str(existing.get("status") or "") in {"COMPLETE", "AMBIGUOUS"}:
                    conn.commit()
                    return {"claimed": False, "record": existing}
                cur.execute(
                    """
                    UPDATE meta_posting_submissions
                    SET lease_token=%s::uuid,
                        lease_expires_at=now() + interval '2 minutes',
                        updated_at=now(),
                        safe_error=NULL
                    WHERE submission_id=%s::uuid
                      AND (lease_expires_at IS NULL OR lease_expires_at < now())
                    RETURNING *
                    """,
                    (lease_token, request_data["submission_id"]),
                )
                claimed = dict(cur.fetchone() or {})
                if not claimed:
                    cur.execute(
                        "SELECT * FROM meta_posting_submissions WHERE submission_id=%s::uuid",
                        (request_data["submission_id"],),
                    )
                    existing = dict(cur.fetchone() or {})
                conn.commit()
                return {"claimed": bool(claimed), "record": claimed or existing}

    def update_stage(self, submission_id, status, **fields):
        if status not in POSTING_STATUSES:
            raise ValueError("Unknown Posting status.")
        allowed = {
            "meta_image_hash",
            "meta_creative_id",
            "meta_ad_id",
            "meta_status",
            "safe_error",
        }
        values = {key: fields[key] for key in fields if key in allowed}
        assignments = ["status=%s", "updated_at=now()"]
        params = [status]
        for key, value in values.items():
            assignments.append(f"{key}=%s")
            params.append(value)
        if status in {"COMPLETE", "FAILED", "AMBIGUOUS"}:
            assignments.extend(["lease_token=NULL", "lease_expires_at=NULL"])
        if status == "COMPLETE":
            assignments.append("completed_at=now()")
        params.append(str(submission_id))
        backend = self._backend()
        backend.ensure_ads_schema()
        with backend.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE meta_posting_submissions SET {', '.join(assignments)} "
                    "WHERE submission_id=%s::uuid RETURNING *",
                    tuple(params),
                )
                row = dict(cur.fetchone() or {})
            conn.commit()
        return row

    def recent(self, limit=20):
        backend = self._backend()
        if not backend.is_configured():
            return []
        backend.ensure_ads_schema()
        with backend.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT submission_id, created_at, completed_at, status,
                           campaign_id, campaign_name, adset_id, adset_name,
                           ad_name, meta_ad_id, meta_creative_id, meta_status
                    FROM meta_posting_submissions
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (max(1, min(int(limit or 20), 100)),),
                )
                return [dict(row) for row in cur.fetchall()]


class MetaPostingService:
    def __init__(self, *, client=None, store=None, url_tags=META_AD_URL_PARAMETERS):
        self.client = client or MetaPostingClient()
        self.store = store or SupabasePostingStore()
        self.url_tags = str(url_tags or "")

    def _validate_destination(self, clean):
        permissions = set(self.client.permissions())
        if POSTING_PERMISSION not in permissions:
            raise PostingValidationError("Meta posting permission is unavailable.")
        if not str(self.client.page_id or "").strip():
            raise PostingValidationError("Sports Cave Facebook Page identity is not configured.")
        if not str(self.client.instagram_actor_id or "").strip():
            raise PostingValidationError("Sports Cave Instagram identity is not configured.")

        campaign = dict(self.client.campaign(clean["campaign_id"]) or {})
        adset = dict(self.client.adset(clean["adset_id"]) or {})
        account = normalize_account_id(self.client.ad_account_id)
        if not campaign.get("id") or normalize_account_id(campaign.get("account_id")) != account:
            raise PostingValidationError("The selected campaign is no longer available.")
        if (
            not adset.get("id")
            or str(adset.get("campaign_id") or "") != str(campaign.get("id") or "")
            or normalize_account_id(adset.get("account_id")) != account
        ):
            raise PostingValidationError("The selected ad set is no longer available in that campaign.")
        return campaign, adset

    def _ambiguous(self, submission_id, message):
        safe_error = sanitize_meta_error(message)
        self.store.update_stage(submission_id, "AMBIGUOUS", safe_error=safe_error)
        raise PostingAmbiguousError(safe_error)

    def create_paused_ad(self, request):
        clean = validate_posting_request(request)
        try:
            campaign, adset = self._validate_destination(clean)
        except MetaAdsApiError as error:
            raise PostingError(sanitize_meta_error(error)) from error

        fingerprint = _request_fingerprint(
            request,
            image_checksum=clean["image_checksum"],
            destination_url=clean["destination_url"],
        )
        lease_token = str(uuid.uuid4())
        claim = self.store.claim(
            {
                "submission_id": str(request.submission_id),
                "request_fingerprint": fingerprint,
                "campaign_id": clean["campaign_id"],
                "campaign_name": str(campaign.get("name") or ""),
                "adset_id": clean["adset_id"],
                "adset_name": str(adset.get("name") or ""),
                "ad_name": clean["ad_name"],
                "destination_url": clean["destination_url"],
                "image_checksum": clean["image_checksum"],
            },
            lease_token=lease_token,
        )
        record = dict(claim.get("record") or {})
        if not claim.get("claimed"):
            if str(record.get("status") or "") == "COMPLETE":
                return record
            if str(record.get("status") or "") == "AMBIGUOUS":
                raise PostingAmbiguousError(
                    str(record.get("safe_error") or "Meta did not confirm the earlier result. Review it before retrying.")
                )
            raise PostingBusyError("This ad is already being created. Wait for the current request to finish.")

        submission_id = str(request.submission_id)
        try:
            image_hash = str(record.get("meta_image_hash") or "")
            if not image_hash:
                try:
                    image_hash = self.client.upload_image(
                        clean["image"]["data"],
                        filename=clean["image"]["upload_name"],
                        content_type=clean["image"]["content_type"],
                    )
                except MetaAdsAmbiguousResultError as error:
                    self._ambiguous(submission_id, error)
                record = self.store.update_stage(
                    submission_id,
                    "IMAGE_UPLOADED",
                    meta_image_hash=image_hash,
                )

            creative_name = f"{clean['ad_name']} | Sports Cave Posting {submission_id[:8]}"
            creative_id = str(record.get("meta_creative_id") or "")
            if not creative_id:
                existing_creative = self.client.find_creative_by_name(creative_name)
                creative_id = str((existing_creative or {}).get("id") or "")
            if not creative_id:
                try:
                    creative_id = self.client.create_creative(
                        creative_name=creative_name,
                        image_hash=image_hash,
                        primary_text=clean["primary_text"],
                        headline=clean["headline"],
                        description=clean["description"],
                        destination_url=clean["destination_url"],
                        cta_type=META_DEFAULT_CTA,
                        url_tags=self.url_tags,
                    )
                except MetaAdsAmbiguousResultError as error:
                    try:
                        existing_creative = self.client.find_creative_by_name(creative_name)
                    except MetaAdsApiError:
                        existing_creative = None
                    creative_id = str((existing_creative or {}).get("id") or "")
                    if not creative_id:
                        self._ambiguous(submission_id, error)
            record = self.store.update_stage(
                submission_id,
                "CREATIVE_CREATED",
                meta_creative_id=creative_id,
            )

            ad_id = str(record.get("meta_ad_id") or "")
            if not ad_id:
                existing_ad = self.client.find_ad_by_creative(clean["adset_id"], creative_id)
                ad_id = str((existing_ad or {}).get("id") or "")
            if not ad_id:
                try:
                    ad_id = self.client.create_paused_ad(
                        ad_name=clean["ad_name"],
                        adset_id=clean["adset_id"],
                        creative_id=creative_id,
                    )
                except MetaAdsAmbiguousResultError as error:
                    try:
                        existing_ad = self.client.find_ad_by_creative(clean["adset_id"], creative_id)
                    except MetaAdsApiError:
                        existing_ad = None
                    ad_id = str((existing_ad or {}).get("id") or "")
                    if not ad_id:
                        self._ambiguous(submission_id, error)
            record = self.store.update_stage(submission_id, "AD_CREATED", meta_ad_id=ad_id)

            confirmed = dict(self.client.ad(ad_id) or {})
            configured_status = str(
                confirmed.get("configured_status") or confirmed.get("status") or ""
            ).upper()
            if configured_status != "PAUSED":
                self._ambiguous(
                    submission_id,
                    "Meta created the ad but did not confirm that it is paused. Review it in Ads Manager.",
                )
            return self.store.update_stage(
                submission_id,
                "COMPLETE",
                meta_ad_id=ad_id,
                meta_creative_id=creative_id,
                meta_image_hash=image_hash,
                meta_status="PAUSED",
                safe_error="",
            )
        except (PostingAmbiguousError, PostingBusyError, PostingValidationError):
            raise
        except MetaAdsApiError as error:
            safe_error = sanitize_meta_error(error)
            self.store.update_stage(submission_id, "FAILED", safe_error=safe_error)
            raise PostingError(safe_error) from error
        except Exception as error:
            safe_error = sanitize_meta_error(error)
            self.store.update_stage(
                submission_id,
                "FAILED",
                safe_error="The Meta request failed. No active ad was created.",
            )
            raise PostingError("The Meta request failed. No active ad was created.") from error

    def recent_posts(self, limit=20):
        return self.store.recent(limit=limit)
