from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
import requests


REVIEW_MODEL_ENV = "OPENAI_AD_REVIEW_MODEL"
REVIEW_API_KEY_ENVS = ("OPENAI_API_KEY", "SPORTS_CAVE_OPENAI_API_KEY")
DEFAULT_REVIEW_MODEL = "gpt-5"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
MAX_REVIEW_IMAGE_BYTES = 20 * 1024 * 1024
MAX_REVIEW_TOTAL_BYTES = 60 * 1024 * 1024
MAX_REVIEW_SOURCE_PIXELS = 30_000_000
MAX_REVIEW_IMAGE_EDGE = 1600
MAX_SCREENSHOTS = 10
MAX_CREATIVES = 10
ACCEPTED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
ACCEPTED_VERDICTS = {
    "Ready to Launch",
    "Small Changes",
    "Needs Work",
    "Do Not Launch",
}
ACCEPTED_PRIORITIES = {"Critical", "High", "Medium", "Optional"}
ACCEPTED_LAUNCH_DECISIONS = {
    "Launch it",
    "Make these changes first",
    "Rebuild the weak creatives before launch",
}
SCORE_RUBRIC = (
    ("Stop-scroll visual impact", 20),
    ("Product visibility, fidelity and premium realism", 15),
    ("Creative variety and campaign sequencing", 15),
    ("Copy strength and Sports Cave tone", 15),
    ("Conversion intent and funnel alignment", 15),
    ("Trust, authentic scarcity, offer and CTA", 10),
    ("Mobile readability and Meta execution", 10),
)


class AdsReviewError(RuntimeError):
    def __init__(self, message, *, code="review_failed"):
        super().__init__(message)
        self.code = code


class AdsReviewValidationError(ValueError):
    pass


def review_image_signature(data):
    return hashlib.sha256(bytes(data or b"")).hexdigest()


def sanitize_review_filename(value):
    clean = re.sub(r"[\x00-\x1f\x7f]+", "", str(value or "image"))
    clean = re.sub(r'[<>:"/\\|?*]', "_", clean)
    clean = re.sub(r"\s+", " ", clean).strip(" .")
    return (clean or "image")[:180]


def validate_review_image(data, *, filename=""):
    source_bytes = bytes(data or b"")
    safe_name = sanitize_review_filename(filename)
    if not source_bytes:
        raise AdsReviewValidationError("This image is empty.")
    if len(source_bytes) > MAX_REVIEW_IMAGE_BYTES:
        raise AdsReviewValidationError("This image is too large. Upload an image under 20 MB.")

    source = None
    oriented = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            source = Image.open(io.BytesIO(source_bytes))
            source_format = str(source.format or "").upper()
            if source_format not in ACCEPTED_IMAGE_FORMATS:
                raise AdsReviewValidationError(
                    "Unsupported image type. Upload a PNG, JPG, JPEG or WebP image."
                )
            width, height = source.size
            if width <= 0 or height <= 0 or width * height > MAX_REVIEW_SOURCE_PIXELS:
                raise AdsReviewValidationError("This image is too large to review safely.")
            source.verify()
            source.close()
            source = Image.open(io.BytesIO(source_bytes))
            oriented = ImageOps.exif_transpose(source)
            oriented.load()

        mime_type = "image/jpeg" if source_format == "JPEG" else f"image/{source_format.casefold()}"
        return {
            "id": review_image_signature(source_bytes)[:20],
            "signature": review_image_signature(source_bytes),
            "filename": safe_name,
            "format": source_format,
            "mime_type": mime_type,
            "width": int(oriented.width),
            "height": int(oriented.height),
            "size": len(source_bytes),
            "data": source_bytes,
        }
    except AdsReviewValidationError:
        raise
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        SyntaxError,
        ValueError,
    ) as error:
        raise AdsReviewValidationError(
            "This file is corrupt or is not a supported PNG, JPG, JPEG or WebP image."
        ) from error
    finally:
        for image in (oriented, source):
            if image is not None:
                try:
                    image.close()
                except Exception:
                    pass


def validate_review_upload_set(screenshots, creatives):
    screenshots = list(screenshots or ())
    creatives = list(creatives or ())
    if len(screenshots) > MAX_SCREENSHOTS:
        raise AdsReviewValidationError(f"Upload no more than {MAX_SCREENSHOTS} Meta screenshots.")
    if len(creatives) > MAX_CREATIVES:
        raise AdsReviewValidationError(f"Upload no more than {MAX_CREATIVES} creative images.")
    total = sum(int(item.get("size") or 0) for item in screenshots + creatives)
    if total > MAX_REVIEW_TOTAL_BYTES:
        raise AdsReviewValidationError("The review images exceed the 60 MB combined limit.")


def _review_image_data_uri(item):
    source = None
    oriented = None
    resized = None
    converted = None
    try:
        source = Image.open(io.BytesIO(bytes(item["data"])))
        oriented = ImageOps.exif_transpose(source)
        oriented.load()
        resized = oriented.copy()
        resized.thumbnail((MAX_REVIEW_IMAGE_EDGE, MAX_REVIEW_IMAGE_EDGE), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        if resized.mode in {"RGBA", "LA"} or "transparency" in resized.info:
            converted = resized.convert("RGBA")
            converted.save(output, format="PNG", optimize=True)
            mime_type = "image/png"
        else:
            converted = resized.convert("RGB")
            converted.save(output, format="JPEG", quality=88, optimize=True, progressive=True)
            mime_type = "image/jpeg"
        encoded = base64.b64encode(output.getvalue()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"
    finally:
        for image in (converted, resized, oriented, source):
            if image is not None:
                try:
                    image.close()
                except Exception:
                    pass


def review_response_schema():
    breakdown_item = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "category": {"type": "string"},
            "points_earned": {"type": "number"},
            "points_available": {"type": "integer"},
        },
        "required": ["category", "points_earned", "points_available"],
    }
    priority_item = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "priority": {"type": "string", "enum": sorted(ACCEPTED_PRIORITIES)},
            "what_is_wrong": {"type": "string"},
            "conversion_risk": {"type": "string"},
            "exact_correction": {"type": "string"},
            "expected_impact": {"type": "string"},
        },
        "required": [
            "priority",
            "what_is_wrong",
            "conversion_risk",
            "exact_correction",
            "expected_impact",
        ],
    }
    creative_item = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "image_number": {"type": "integer"},
            "purpose": {"type": "string"},
            "score": {"type": "number"},
            "visual_verdict": {"type": "string"},
            "copy_alignment": {"type": "string"},
            "required_correction": {"type": "string"},
        },
        "required": [
            "image_number",
            "purpose",
            "score",
            "visual_verdict",
            "copy_alignment",
            "required_correction",
        ],
    }
    copy_item = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "field": {"type": "string"},
            "verdict": {"type": "string"},
            "original": {"type": "string"},
            "replacement": {"type": "string"},
            "current_character_count": {"type": "integer"},
            "maximum_character_count": {"type": "integer"},
            "replacement_character_count": {"type": "integer"},
            "unsupported_claims": {"type": "string"},
        },
        "required": [
            "field",
            "verdict",
            "original",
            "replacement",
            "current_character_count",
            "maximum_character_count",
            "replacement_character_count",
            "unsupported_claims",
        ],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "overall_score": {"type": "number"},
            "verdict": {"type": "string", "enum": sorted(ACCEPTED_VERDICTS)},
            "brutal_truth": {"type": "string"},
            "score_breakdown": {
                "type": "array",
                "minItems": len(SCORE_RUBRIC),
                "maxItems": len(SCORE_RUBRIC),
                "items": breakdown_item,
            },
            "strengths": {"type": "array", "items": {"type": "string"}},
            "priority_changes": {"type": "array", "items": priority_item},
            "creative_reviews": {"type": "array", "items": creative_item},
            "copy_review": {"type": "array", "items": copy_item},
            "recommended_final_copy": {"type": "string"},
            "launch_decision": {
                "type": "string",
                "enum": sorted(ACCEPTED_LAUNCH_DECISIONS),
            },
            "next_actions": {
                "type": "array",
                "maxItems": 3,
                "items": {"type": "string"},
            },
            "test_recommendation": {"type": "string"},
            "unverified_items": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "overall_score",
            "verdict",
            "brutal_truth",
            "score_breakdown",
            "strengths",
            "priority_changes",
            "creative_reviews",
            "copy_review",
            "recommended_final_copy",
            "launch_decision",
            "next_actions",
            "test_recommendation",
            "unverified_items",
        ],
    }


def build_review_instructions(carousel_character_limit):
    rubric_lines = "\n".join(f"- {name}: {points} points" for name, points in SCORE_RUBRIC)
    return f"""You are the final campaign approver and senior Meta Ads growth strategist for Sports Cave, a premium limited-edition sports wall-art business.

Review only what is visible in the supplied finished-ad screenshots, creative images and final copy. Never assume an expected element exists. If a fact or execution detail cannot be verified, use this exact wording: Unable to verify from the supplied ad.

FACT AND FAN-LANGUAGE CHECK
- Check that every claim and phrase is factually supported by the supplied material and makes sense in genuine fan language.
- Flag false context, invented achievements, awkward terminology, accidental meanings, wording fans could reasonably ridicule, and country-inappropriate terms.
- Never invent athletes, teams, records, dates, achievements, product features, edition quantities, reviews, delivery promises, guarantees, prices or discounts.
- Do not infer artwork accuracy when no suitable source comparison is supplied.

WEIGHTED SCORE
{rubric_lines}
Award points honestly, total them out of 100, and set overall_score to the total divided by 10 with one decimal place. A polished campaign is not automatically high-converting.
- 9.0-10.0: Ready to Launch
- 8.0-8.9: Small Changes
- 7.0-7.9: Needs Work
- Below 7.0: Do Not Launch
For scores of 9 or more, prevent unnecessary perfectionism: say it is ready to test and recommend only changes realistically likely to improve sales.

SPORTS CAVE STANDARD
- Stop the scroll, make the framed artwork the immediate hero and keep it readable at mobile thumbnail size.
- Judge premium realism, product fidelity, collector value, emotional identity, nostalgia, rivalry, pride, ownership and legacy.
- Judge authentic scarcity, natural CTA, funnel-stage fit, landing-page consistency, country terminology and mobile readability.
- Reject robotic AI language, over-explaining and generic words such as elevate, transform, ultimate, masterpiece and must-have.
- Inspect borders, artwork changes, faces, uniforms, colours, wording, badges, signatures, plaques, edition plates, frame cropping, proportions, warping, glass, reflections, pasted-on appearance, lighting, scale, perspective, architecture, duplicate objects, fake luxury, distracting props and repeated visual treatments.
- Do not recommend obvious sports props merely to clarify the sport.

CAROUSEL STANDARD
When this is a Carousel, evaluate the deliberate sequence: product identity and stop-scroll; moment or emotional memory; legacy, rivalry or deeper meaning; fan ownership and belonging; authentic scarcity and action. Flag repeated messages, rooms, walls, colours, camera angles, compositions or emotional purposes. Every card must earn its place.

COPY VALIDATION
The live Ads-page maximum for each trimmed Carousel headline and each trimmed Carousel description is {int(carousel_character_limit)} characters. Use that supplied live value, not a remembered limit. Spaces and punctuation count. For every over-limit line, report the exact current count, the maximum, a stronger compliant replacement and its recalculated count. Do not apply this Carousel limit to other copy fields.

OUTPUT DISCIPLINE
- Be direct, commercial and specific. Do not pad the review with cosmetic suggestions.
- Preserve strong copy. Only include recommended_final_copy when copy changes are genuinely required; otherwise return an empty string.
- Review every supplied final creative in its supplied order.
- Use Keep as is when a creative needs no correction.
- Return no more than three exact next actions and one high-leverage first test.
- Return only the required structured response."""


def build_review_context(context, final_copy):
    clean_context = {
        "product_name": str(context.get("product_name") or "").strip(),
        "product_category": str(context.get("category") or "").strip(),
        "target_country": str(context.get("country") or "").strip(),
        "campaign_type": str(context.get("campaign_type") or "").strip(),
        "campaign_angle": str(context.get("campaign_angle") or "").strip(),
        "generated_primary_text": str(context.get("generated_primary_text") or "").strip(),
        "headlines": list(context.get("headlines") or ()),
        "descriptions": list(context.get("descriptions") or ()),
        "cta": str(context.get("cta") or "").strip(),
        "product_url": str(context.get("product_url") or "").strip(),
        "final_copy": str(final_copy or "").strip(),
        "carousel_character_limit": int(context.get("carousel_character_limit") or 0),
    }
    return json.dumps(clean_context, ensure_ascii=False, indent=2)


def build_multimodal_content(context, screenshots, creatives, final_copy):
    content = [
        {
            "type": "input_text",
            "text": (
                "Review this finished Sports Cave campaign. Campaign context and exact final copy:\n"
                + build_review_context(context, final_copy)
            ),
        }
    ]
    for index, item in enumerate(screenshots or (), start=1):
        content.append(
            {
                "type": "input_text",
                "text": f"Finished Meta ad screenshot {index}: {item['filename']}",
            }
        )
        content.append(
            {
                "type": "input_image",
                "image_url": _review_image_data_uri(item),
                "detail": "high",
            }
        )
    for index, item in enumerate(creatives or (), start=1):
        content.append(
            {
                "type": "input_text",
                "text": f"Final creative image {index}: {item['filename']}",
            }
        )
        content.append(
            {
                "type": "input_image",
                "image_url": _review_image_data_uri(item),
                "detail": "high",
            }
        )
    return content


def build_review_request_payload(context, screenshots, creatives, final_copy, *, model=None):
    validate_review_upload_set(screenshots, creatives)
    character_limit = int(context.get("carousel_character_limit") or 0)
    return {
        "model": str(model or os.getenv(REVIEW_MODEL_ENV) or DEFAULT_REVIEW_MODEL).strip(),
        "instructions": build_review_instructions(character_limit),
        "input": [
            {
                "role": "user",
                "content": build_multimodal_content(
                    context,
                    screenshots,
                    creatives,
                    final_copy,
                ),
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "sports_cave_final_ad_review",
                "description": "A complete, fact-safe Sports Cave Meta ad review.",
                "strict": True,
                "schema": review_response_schema(),
            }
        },
        "store": False,
    }


def _api_key():
    for name in REVIEW_API_KEY_ENVS:
        value = str(os.getenv(name) or "").strip()
        if value:
            return value
    raise AdsReviewError(
        "Final Ad Review is not configured yet. Ask an administrator to configure the review service.",
        code="not_configured",
    )


def _extract_output_text(response_data):
    direct = response_data.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    for output in response_data.get("output") or ():
        if not isinstance(output, dict):
            continue
        for content in output.get("content") or ():
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
    raise AdsReviewValidationError("The review response did not contain a structured result.")


def _parse_json_text(value):
    text = str(value or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def verdict_for_score(score):
    numeric_score = float(score)
    if numeric_score >= 9:
        return "Ready to Launch"
    if numeric_score >= 8:
        return "Small Changes"
    if numeric_score >= 7:
        return "Needs Work"
    return "Do Not Launch"


def validate_review_response(value, *, expected_creatives=None):
    if not isinstance(value, dict):
        raise AdsReviewValidationError("The review result is invalid.")
    required = set(review_response_schema()["required"])
    if not required.issubset(value):
        raise AdsReviewValidationError("The review result is incomplete.")
    if value.get("verdict") not in ACCEPTED_VERDICTS:
        raise AdsReviewValidationError("The review verdict is invalid.")
    if value.get("launch_decision") not in ACCEPTED_LAUNCH_DECISIONS:
        raise AdsReviewValidationError("The review launch decision is invalid.")
    if not isinstance(value.get("next_actions"), list) or len(value["next_actions"]) > 3:
        raise AdsReviewValidationError("The review next actions are invalid.")

    breakdown = value.get("score_breakdown")
    if not isinstance(breakdown, list) or len(breakdown) != len(SCORE_RUBRIC):
        raise AdsReviewValidationError("The score breakdown is invalid.")
    expected = dict(SCORE_RUBRIC)
    seen = set()
    total = 0.0
    for row in breakdown:
        if not isinstance(row, dict):
            raise AdsReviewValidationError("The score breakdown is invalid.")
        category = str(row.get("category") or "")
        available = row.get("points_available")
        earned = row.get("points_earned")
        if category not in expected or category in seen or available != expected[category]:
            raise AdsReviewValidationError("The score breakdown is invalid.")
        if not isinstance(earned, (int, float)) or isinstance(earned, bool):
            raise AdsReviewValidationError("The score breakdown is invalid.")
        if float(earned) < 0 or float(earned) > float(available):
            raise AdsReviewValidationError("The score breakdown is invalid.")
        seen.add(category)
        total += float(earned)
    if seen != set(expected):
        raise AdsReviewValidationError("The score breakdown is invalid.")

    for change in value.get("priority_changes") or ():
        if not isinstance(change, dict) or change.get("priority") not in ACCEPTED_PRIORITIES:
            raise AdsReviewValidationError("A priority change is invalid.")
    for review in value.get("creative_reviews") or ():
        score = review.get("score") if isinstance(review, dict) else None
        if not isinstance(score, (int, float)) or not 0 <= float(score) <= 10:
            raise AdsReviewValidationError("A creative review score is invalid.")
    if expected_creatives:
        reviewed_numbers = {
            int(review.get("image_number") or 0)
            for review in value.get("creative_reviews") or ()
            if isinstance(review, dict)
        }
        if not set(range(1, int(expected_creatives) + 1)).issubset(reviewed_numbers):
            raise AdsReviewValidationError("A supplied creative is missing from the review.")

    normalized = dict(value)
    normalized["overall_score"] = round(total / 10.0, 1)
    normalized["verdict"] = verdict_for_score(normalized["overall_score"])
    normalized["next_actions"] = [str(item) for item in value["next_actions"][:3]]
    return normalized


def _post_response(payload, api_key, request_post):
    try:
        response = request_post(
            OPENAI_RESPONSES_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=(10, 120),
        )
    except requests.Timeout as error:
        raise AdsReviewError(
            "The review timed out. Your uploads are still here; try Review Again.",
            code="timeout",
        ) from error
    except requests.RequestException as error:
        raise AdsReviewError(
            "The review service is temporarily unavailable. Try Review Again.",
            code="network",
        ) from error
    if response.status_code == 429:
        raise AdsReviewError(
            "The review service is busy right now. Wait a moment and try Review Again.",
            code="rate_limit",
        )
    if response.status_code >= 400:
        raise AdsReviewError(
            "The review could not be completed. Your uploads are still available to retry.",
            code="upstream",
        )
    try:
        return response.json()
    except ValueError as error:
        raise AdsReviewValidationError("The review response was not valid JSON.") from error


def _repair_payload(raw_output, model):
    return {
        "model": model,
        "instructions": (
            "Repair the supplied result into the required JSON schema. Preserve its conclusions, "
            "scores and factual uncertainty. Return only the structured response."
        ),
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Repair this review result:\n" + str(raw_output or "")[:30000],
                    }
                ],
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "sports_cave_final_ad_review_repair",
                "strict": True,
                "schema": review_response_schema(),
            }
        },
        "store": False,
    }


def request_final_ad_review(
    context,
    screenshots,
    creatives,
    final_copy,
    *,
    request_post=None,
    api_key=None,
):
    post = request_post or requests.post
    resolved_api_key = api_key or _api_key()
    payload = build_review_request_payload(context, screenshots, creatives, final_copy)
    response_data = _post_response(payload, resolved_api_key, post)
    raw_output = _extract_output_text(response_data)
    try:
        return validate_review_response(
            _parse_json_text(raw_output),
            expected_creatives=len(creatives or ()),
        )
    except (AdsReviewValidationError, json.JSONDecodeError, TypeError, ValueError):
        repair = _post_response(
            _repair_payload(raw_output, payload["model"]),
            resolved_api_key,
            post,
        )
        try:
            return validate_review_response(
                _parse_json_text(_extract_output_text(repair)),
                expected_creatives=len(creatives or ()),
            )
        except (AdsReviewValidationError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise AdsReviewError(
                "The review result could not be validated. Try Review Again.",
                code="invalid_response",
            ) from error
