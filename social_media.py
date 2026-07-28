import math
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse, urlunparse
from zoneinfo import ZoneInfo


SOCIAL_MEDIA_PAGE_KEY = "social_media"
AI_REELS_PAGE_KEY = "social_media_ai_reels"
LEGACY_REELS_PAGE_KEY = "social_media_reels_studio"
SOCIAL_MEDIA_ROUTE = "Social Media"
AI_REELS_ROUTE = "AI Reels"
LEGACY_REELS_ROUTE = "Social Media Reels Studio"
SOCIAL_TIMEZONE = "Australia/Sydney"
SYDNEY_TZ = ZoneInfo(SOCIAL_TIMEZONE)

PLATFORMS = ("Instagram", "Facebook", "Pinterest", "TikTok", "YouTube")
FOCUS_OPTIONS = ("Create", "Post", "Schedule", "Community", "Plan", "Review")
CONTENT_FORMATS = (
    "Reel",
    "Static post",
    "Carousel",
    "Story",
    "Short",
    "Pin",
    "Video",
    "Other",
)
MARKETS = ("Australia", "USA", "UK", "Canada", "New Zealand", "Global")
POST_STATUSES = ("Planned", "Created", "Scheduled", "Live")

SOCIAL_PROFILES = (
    ("Instagram", "https://www.instagram.com/sportscaveshop/"),
    ("Facebook", "https://www.facebook.com/profile.php?id=100090408036260"),
    ("Pinterest", "https://au.pinterest.com/SportsCaveShop/"),
    ("TikTok", "https://www.tiktok.com/@sportscaveshop"),
    ("YouTube", "https://www.youtube.com/channel/UCDZjmaJrIXMvh7z6r123lig"),
)
SOCIAL_PROFILE_URLS = dict(SOCIAL_PROFILES)
PLATFORM_HOSTS = {
    "Instagram": ("instagram.com",),
    "Facebook": ("facebook.com", "fb.watch"),
    "Pinterest": ("pinterest.com", "pin.it"),
    "TikTok": ("tiktok.com",),
    "YouTube": ("youtube.com", "youtu.be"),
}

PLAN_REVIEW_FIELDS = (
    "what_worked",
    "what_learned",
    "improve_next",
    "blockers",
)
MAX_PRIORITY_COUNT = 3


class SocialValidationError(ValueError):
    pass


def _compact_text(value, *, limit=500):
    return re.sub(r"\s+", " ", str(value or "").strip())[:limit]


def _multiline_text(value, *, limit=2000):
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return text[:limit]


def _aware_utc(value=None):
    value = value or datetime.now(timezone.utc)
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise SocialValidationError("A timezone-aware timestamp is required.")
    return value.astimezone(timezone.utc)


def sydney_today(now=None):
    return _aware_utc(now).astimezone(SYDNEY_TZ).date()


def sydney_week_bounds(value=None, *, now=None):
    selected = value or sydney_today(now)
    if isinstance(selected, str):
        selected = date.fromisoformat(selected)
    if not isinstance(selected, date):
        raise SocialValidationError("A valid Sydney date is required.")
    start = selected - timedelta(days=selected.weekday())
    return start, start + timedelta(days=6)


def normalise_platforms(values):
    selected = []
    for platform in values or ():
        clean = _compact_text(platform, limit=40)
        if clean in PLATFORMS and clean not in selected:
            selected.append(clean)
    return selected


def normalise_focus(values):
    selected = []
    for focus in values or ():
        clean = _compact_text(focus, limit=40)
        if clean in FOCUS_OPTIONS and clean not in selected:
            selected.append(clean)
    return selected


def optional_nonnegative_int(value, *, field_name="Metric"):
    if value is None or value == "":
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise SocialValidationError(f"{field_name} must be a whole number.") from error
    if result < 0:
        raise SocialValidationError(f"{field_name} cannot be negative.")
    return result


def _host_matches(host, allowed_hosts):
    host = str(host or "").casefold().rstrip(".")
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in allowed_hosts)


def validate_public_url(value, *, platform=""):
    clean = str(value or "").strip()
    if not clean:
        return ""
    if len(clean) > 1000 or any(character in clean for character in ("\r", "\n", "\t")):
        raise SocialValidationError("Enter a valid public post URL.")
    parsed = urlparse(clean)
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
    ):
        raise SocialValidationError("Public post links must use a valid https address.")
    clean_platform = _compact_text(platform, limit=40)
    allowed_hosts = PLATFORM_HOSTS.get(clean_platform)
    if allowed_hosts and not _host_matches(parsed.hostname, allowed_hosts):
        raise SocialValidationError(f"Enter a valid {clean_platform} public post URL.")
    if not allowed_hosts and not any(
        _host_matches(parsed.hostname, hosts)
        for hosts in PLATFORM_HOSTS.values()
    ):
        raise SocialValidationError("Enter a supported social-media post URL.")
    return urlunparse(parsed._replace(fragment=""))


def _normalise_priorities(priorities):
    rows = []
    for index, priority in enumerate(list(priorities or ())[:MAX_PRIORITY_COUNT], start=1):
        priority = dict(priority or {})
        task = _compact_text(priority.get("task"), limit=240)
        if task:
            rows.append(
                {
                    "priority_index": index,
                    "task": task,
                    "completed": bool(priority.get("completed")),
                }
            )
    return rows


def calculate_daily_score(priorities, review):
    rows = _normalise_priorities(priorities)
    available_weight = sum(2 if row["priority_index"] == 1 else 1 for row in rows)
    completed_weight = sum(
        2 if row["priority_index"] == 1 else 1
        for row in rows
        if row["completed"]
    )
    priority_points = (
        8.0 * completed_weight / available_weight
        if available_weight
        else 0.0
    )
    review = dict(review or {})
    review_points = 0.5 * sum(
        bool(_multiline_text(review.get(field), limit=2000))
        for field in PLAN_REVIEW_FIELDS
    )
    return round(min(max(priority_points + review_points, 0.0), 10.0), 1)


def normalise_daily_plan(payload, *, plan_date=None, timezone_name=SOCIAL_TIMEZONE):
    payload = dict(payload or {})
    selected_date = plan_date or payload.get("plan_date") or sydney_today()
    if isinstance(selected_date, str):
        selected_date = date.fromisoformat(selected_date)
    priorities = _normalise_priorities(payload.get("priorities"))
    review = {
        "what_worked": _multiline_text(payload.get("what_worked"), limit=2000),
        "what_learned": _multiline_text(payload.get("what_learned"), limit=2000),
        "improve_next": _multiline_text(payload.get("improve_next"), limit=2000),
        "blockers": _multiline_text(payload.get("blockers"), limit=2000),
    }
    normalised = {
        "plan_date": selected_date,
        "timezone": _compact_text(timezone_name or SOCIAL_TIMEZONE, limit=80),
        "focus_areas": normalise_focus(payload.get("focus_areas")),
        "priorities": priorities,
        "content_plan": _multiline_text(payload.get("content_plan"), limit=3000),
        "planned_platforms": normalise_platforms(payload.get("planned_platforms")),
        "planned_post_count": optional_nonnegative_int(
            payload.get("planned_post_count"),
            field_name="Planned posts",
        ),
        "improvement_test": _multiline_text(payload.get("improvement_test"), limit=1500),
        **review,
    }
    normalised["score"] = calculate_daily_score(priorities, review)
    normalised["review_complete"] = all(review.values())
    return normalised


def validate_daily_plan(payload, *, completing=False):
    plan = normalise_daily_plan(payload, plan_date=payload.get("plan_date"))
    errors = []
    top_priority = next(
        (
            row
            for row in plan["priorities"]
            if row["priority_index"] == 1
        ),
        None,
    )
    if not top_priority:
        errors.append("Top priority is required.")
    if not plan["content_plan"]:
        errors.append("Content plan is required.")
    if completing and not plan["review_complete"]:
        errors.append("Complete the four end-of-day review questions before finishing the day.")
    if errors:
        raise SocialValidationError(" ".join(errors))
    return plan


def _normalise_metric_row(platform, row):
    row = dict(row or {})
    status = _compact_text(row.get("status") or "Planned", limit=30).title()
    if status not in POST_STATUSES:
        raise SocialValidationError(f"Choose a valid {platform} status.")
    return {
        "platform": platform,
        "status": status,
        "scheduled_published_at": row.get("scheduled_published_at"),
        "public_url": validate_public_url(row.get("public_url"), platform=platform),
        "reach_views": optional_nonnegative_int(
            row.get("reach_views"),
            field_name=f"{platform} reach or views",
        ),
        "engagements": optional_nonnegative_int(
            row.get("engagements"),
            field_name=f"{platform} engagements",
        ),
        "link_clicks": optional_nonnegative_int(
            row.get("link_clicks"),
            field_name=f"{platform} link clicks",
        ),
        "saves_shares": optional_nonnegative_int(
            row.get("saves_shares"),
            field_name=f"{platform} saves or shares",
        ),
        "result_note": _multiline_text(row.get("result_note"), limit=1200),
    }


def normalise_post(payload):
    payload = dict(payload or {})
    content_name = _compact_text(payload.get("content_name"), limit=240)
    if not content_name:
        raise SocialValidationError("Post or content name is required.")
    content_format = _compact_text(payload.get("content_format") or "Reel", limit=40)
    if content_format not in CONTENT_FORMATS:
        raise SocialValidationError("Choose a valid content format.")
    market = _compact_text(payload.get("market") or "Global", limit=40)
    if market not in MARKETS:
        raise SocialValidationError("Choose a valid market.")
    created_date = payload.get("created_date") or sydney_today()
    if isinstance(created_date, str):
        created_date = date.fromisoformat(created_date)
    platform_payload = payload.get("platforms") or {}
    if isinstance(platform_payload, (list, tuple)):
        platform_payload = {platform: {} for platform in platform_payload}
    platform_rows = [
        _normalise_metric_row(platform, platform_payload.get(platform))
        for platform in normalise_platforms(platform_payload.keys())
    ]
    if not platform_rows:
        raise SocialValidationError("Select at least one platform.")
    return {
        "content_name": content_name,
        "campaign": _compact_text(payload.get("campaign"), limit=240),
        "content_format": content_format,
        "market": market,
        "created_date": created_date,
        "notes": _multiline_text(payload.get("notes"), limit=2000),
        "platforms": platform_rows,
    }


def normalise_weekly_report(payload, *, week_start=None):
    payload = dict(payload or {})
    start, end = sydney_week_bounds(week_start or payload.get("week_start"))
    metrics = []
    raw_metrics = payload.get("platform_metrics") or {}
    for platform in PLATFORMS:
        row = dict(raw_metrics.get(platform) or {})
        normalised = {
            "platform": platform,
            "audience_total": optional_nonnegative_int(
                row.get("audience_total"),
                field_name=f"{platform} audience",
            ),
            "reach_views": optional_nonnegative_int(
                row.get("reach_views"),
                field_name=f"{platform} reach or views",
            ),
            "engagements": optional_nonnegative_int(
                row.get("engagements"),
                field_name=f"{platform} engagements",
            ),
            "outbound_clicks": optional_nonnegative_int(
                row.get("outbound_clicks"),
                field_name=f"{platform} outbound clicks",
            ),
            "posts_published": optional_nonnegative_int(
                row.get("posts_published"),
                field_name=f"{platform} published posts",
            ),
            "best_post_url": validate_public_url(
                row.get("best_post_url"),
                platform=platform,
            ),
            "best_post_result": _compact_text(row.get("best_post_result"), limit=600),
        }
        if any(value not in (None, "") for key, value in normalised.items() if key != "platform"):
            metrics.append(normalised)
    return {
        "week_start": start,
        "week_end": end,
        "performed_best": _multiline_text(payload.get("performed_best"), limit=2000),
        "learned": _multiline_text(payload.get("learned"), limit=2000),
        "test_next": _multiline_text(payload.get("test_next"), limit=2000),
        "platform_metrics": metrics,
    }


def metric_change(current, previous):
    if current is None or previous is None:
        return None
    return int(current) - int(previous)


def weekly_comparisons(current_metrics, previous_metrics):
    previous_by_platform = {
        row.get("platform"): dict(row or {})
        for row in previous_metrics or ()
    }
    comparisons = []
    for current in current_metrics or ():
        current = dict(current or {})
        platform = current.get("platform")
        previous = previous_by_platform.get(platform, {})
        comparisons.append(
            {
                **current,
                "audience_change": metric_change(
                    current.get("audience_total"),
                    previous.get("audience_total"),
                ),
                "reach_views_change": metric_change(
                    current.get("reach_views"),
                    previous.get("reach_views"),
                ),
                "engagements_change": metric_change(
                    current.get("engagements"),
                    previous.get("engagements"),
                ),
            }
        )
    return comparisons


def weekly_summary(report, previous_metrics=()):
    report = dict(report or {})
    comparisons = weekly_comparisons(
        report.get("platform_metrics") or (),
        previous_metrics,
    )
    strongest = max(
        comparisons,
        key=lambda row: (
            row.get("engagements") if row.get("engagements") is not None else -1,
            row.get("reach_views") if row.get("reach_views") is not None else -1,
        ),
        default={},
    )
    best_post = next(
        (
            row
            for row in comparisons
            if row.get("best_post_url") or row.get("best_post_result")
        ),
        {},
    )
    return {
        "comparisons": comparisons,
        "total_posts": sum(
            row.get("posts_published") or 0
            for row in comparisons
        ),
        "total_audience_growth": sum(
            row.get("audience_change") or 0
            for row in comparisons
            if row.get("audience_change") is not None
        ),
        "strongest_platform": strongest.get("platform") or "",
        "best_post_url": best_post.get("best_post_url") or "",
        "best_post_result": best_post.get("best_post_result") or "",
    }
