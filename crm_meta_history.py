"""Private CRM ad reporting from Meta's GET-only API."""
from datetime import date, datetime, timezone
import re
from threading import Lock
from time import monotonic
from zoneinfo import ZoneInfo

import meta_ads_client as meta
import meta_review_live as live
from meta_reporting_contract import validate_account
from meta_review_analysis import normalize_metrics, number

CORE_FIELDS = live.INSIGHT_FIELDS + ",account_id"
EXTRA_FIELDS = (
    "unique_clicks,unique_ctr,cost_per_unique_click,unique_inline_link_clicks,unique_inline_link_click_ctr,"
    "cost_per_unique_inline_link_click,"
    "unique_outbound_clicks,unique_outbound_clicks_ctr,unique_actions,conversions,conversion_values,"
    "cost_per_conversion,inline_post_engagement,instagram_profile_follow,instagram_profile_visits,"
    "video_play_actions,video_thruplay_watched_actions,video_avg_time_watched_actions,"
    "video_continuous_2_sec_watched_actions,video_15_sec_watched_actions,video_time_watched_actions,"
    "video_p25_watched_actions,video_p50_watched_actions,video_p75_watched_actions,"
    "video_p95_watched_actions,video_p100_watched_actions,quality_ranking,engagement_rate_ranking,"
    "conversion_rate_ranking,instant_experience_clicks_to_open,instant_experience_clicks_to_start,"
    "instant_experience_outbound_clicks"
).split(",")
FIELDS = CORE_FIELDS.split(",") + EXTRA_FIELDS
IDENTITY_FIELDS = "account_id,date_start,date_stop,ad_id"
VIDEO_FIELDS = tuple(field for field in EXTRA_FIELDS if field.startswith("video_"))
OPTIONAL_REQUEST_LIMIT = 8
PAGE_SIZE = 20
CACHE_TTL = 120
CACHE_LIMIT = 8
_cache = {}
_lock = Lock()


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("Use account dates in YYYY-MM-DD format.")
    try:
        day = date.fromisoformat(value)
    except ValueError:
        raise ValueError("Use valid account dates.") from None
    if day.year < 2000:
        raise ValueError("Use account dates from 2000 onward.")
    return day


def meta_history_args(arguments):
    since, until = _date(arguments.get("since")), _date(arguments.get("until"))
    if not 0 <= (until - since).days < 7:
        raise ValueError("Choose 1–7 account dates per request.")
    cursor = arguments.get("cursor", "")
    refresh = arguments.get("refresh", False)
    if type(refresh) is not bool or not isinstance(cursor, str) or (cursor and refresh):
        raise ValueError("Use a boolean refresh on the first page and next_cursor on later pages.")
    if not cursor:
        return since, until, None, refresh
    match = re.fullmatch(r"([0-9]{4}-[0-9]{2}-[0-9]{2})/([0-9]{1,30})", cursor)
    if not match or not since <= _date(match[1]) <= until:
        raise ValueError("Use next_cursor from the preceding page.")
    return since, until, (date.fromisoformat(match[1]), match[2]), refresh


def _index_rows(rows, account_id, since, until):
    ordered = {}
    for row in rows:
        ad_id = row.get("ad_id")
        day = _date(row.get("date_start"))
        if (row.get("date_start") != row.get("date_stop") or not since <= day <= until
                or str(row.get("account_id")) != account_id or not re.fullmatch(r"[0-9]{1,30}", str(ad_id))):
            raise ValueError("Meta returned a row outside the requested account, date or ad level.")
        key = day, str(ad_id)
        if key in ordered and row != ordered[key]:
            raise ValueError("Meta returned conflicting rows for the same ad and date.")
        ordered[key] = row
    return ordered


def _optional_error(error):
    return str(error.error_code) in ("3", "100", "10", "200")


def _read_extras(reader, path, params, base_rows, account_id, since, until, first_error):
    pending = [tuple(EXTRA_FIELDS)]
    rejected, accepted, unverified = set(), set(), set()
    error = first_error
    attempts = 0
    while pending and attempts < OPTIONAL_REQUEST_LIMIT:
        fields = pending.pop(0)
        if error is None:
            attempts += 1
            try:
                rows = reader.pages(path, {**params, "fields": ",".join((IDENTITY_FIELDS, *fields))})
                for key, row in _index_rows(rows, account_id, since, until).items():
                    if key in base_rows:
                        base_rows[key].update({field: row[field] for field in fields if field in row})
                accepted.update(fields)
                continue
            except meta.MetaAdsApiError as failure:
                if not _optional_error(failure):
                    raise
                error = failure
            except TimeoutError:
                unverified.update(fields)
                break
        # Meta often identifies the invalid field. Treat a name as definitive
        # only when the error explicitly describes an unsupported field.
        match = re.search(r"(?:nonexisting field|unknown field|invalid field)\s*\(?['\"]?(\w+)",
                          str(error), re.IGNORECASE)
        named = match[1] if match else None
        if named in fields:
            rejected.add(named)
            rest = tuple(field for field in fields if field != named)
            if rest:
                pending.insert(0, rest)
        elif len(fields) == 1:
            rejected.add(fields[0])
        elif (videos := tuple(field for field in fields if field in VIDEO_FIELDS)) and len(videos) < len(fields):
            pending.extend((videos, tuple(field for field in fields if field not in VIDEO_FIELDS)))
        else:
            midpoint = len(fields) // 2
            pending.extend((fields[:midpoint], fields[midpoint:]))
        error = None
    unverified.update(field for group in pending for field in group)
    return accepted, rejected, unverified


def _read_likes(reader, path, params, base_rows, account_id, since, until):
    if not any(item.get("action_type") == "post_reaction" and (number(item.get("value")) or 0) > 0
               for row in base_rows.values() for item in (row.get("actions") or [])
               if isinstance(item, dict)):
        return "no_reported_reactions"
    try:
        rows = reader.pages(path, {**params, "fields": IDENTITY_FIELDS + ",actions",
                                   "action_breakdowns": "action_type,action_reaction"})
    except meta.MetaAdsApiError as error:
        if not _optional_error(error):
            raise
        return "rejected"
    except TimeoutError:
        return "unverified"
    for key, row in _index_rows(rows, account_id, since, until).items():
        if key not in base_rows:
            continue
        likes = [number(item.get("value")) for item in (row.get("actions") or [])
                 if isinstance(item, dict) and item.get("action_type") == "post_reaction"
                 and str(item.get("action_reaction", "")).lower() == "like"]
        if len(likes) == 1 and likes[0] is not None:
            base_rows[key]["_paid_post_likes"] = likes[0]
    return "accepted"


def _fetch(config, since, until, reader):
    path = config["ad_account_id"]
    account_id = path.removeprefix("act_")
    account = validate_account(reader.get(path, {"fields": "account_id,currency,timezone_name"}), account_id)
    if until > datetime.now(ZoneInfo(account["timezone_name"])).date():
        raise ValueError("Choose dates through today in the Meta ad-account timezone.")
    params = {**live.date_params(since, until), "level": "ad", "time_increment": 1,
              "use_unified_attribution_setting": "true", "action_report_time": "impression"}
    path += "/insights"
    try:
        rows = reader.pages(path, {**params, "fields": ",".join(FIELDS)})
        ordered = _index_rows(rows, account_id, since, until)
        accepted, rejected, unverified = set(EXTRA_FIELDS), set(), set()
    except meta.MetaAdsApiError as error:
        if not _optional_error(error):
            raise
        ordered = _index_rows(reader.pages(path, {**params, "fields": CORE_FIELDS}), account_id, since, until)
        accepted, rejected, unverified = _read_extras(reader, path, params, ordered, account_id, since, until, error)
    likes = _read_likes(reader, path, params, ordered, account_id, since, until)
    coverage = {"accepted": sorted(accepted), "rejected": sorted(rejected), "unverified": sorted(unverified),
                "returned": sorted({field for row in ordered.values() for field in accepted if row.get(field) is not None}),
                "paid_post_likes_breakdown": likes}
    return account, sorted(ordered.items()), datetime.now(timezone.utc).isoformat(), coverage


def _snapshot(config, since, until, refresh):
    key = live.scope(config), since, until
    with _lock:
        cached = _cache.get(key)
        if not refresh and cached and cached[0] > monotonic():
            return cached[1]

    def load():
        snapshot = _fetch(config, since, until, live.Reader(config, max_pages=30, seconds=28))
        with _lock:
            _cache.pop(key, None)
            _cache[key] = monotonic() + CACHE_TTL, snapshot
            while len(_cache) > CACHE_LIMIT:
                del _cache[next(iter(_cache))]
        return snapshot

    return live.singleflight(("crm-meta-history", key), load)


def _report_row(row):
    fields = {key: row[key] for key in FIELDS if key in row}
    metrics = normalize_metrics(fields)
    metrics.pop("_reported_rates")
    actions = fields.get("actions")
    metrics["page_likes"] = next(
        (number(item.get("value")) for item in actions
         if isinstance(item, dict) and item.get("action_type") == "like"),
        None,
    ) if isinstance(actions, list) else None
    metrics["paid_post_likes"] = row.get("_paid_post_likes")
    # Preserve the historical likes key, which reported the Meta 'like' action.
    metrics["likes"] = metrics["page_likes"]
    for field in VIDEO_FIELDS:
        entries = fields.get(field)
        metrics[field] = (
            number(entries[0].get("value"))
            if isinstance(entries, list) and len(entries) == 1 and isinstance(entries[0], dict)
            else None
        )
    return {"date": fields["date_start"], "ad_id": fields["ad_id"], "ad_name": fields.get("ad_name"),
            "adset_id": fields.get("adset_id"), "adset_name": fields.get("adset_name"),
            "campaign_id": fields.get("campaign_id"), "campaign_name": fields.get("campaign_name"),
            "metrics": metrics, "meta_fields": fields}


def meta_ad_history(since, until, after, refresh):
    config = meta.get_meta_config()
    account, all_rows, captured, coverage = _snapshot(config, since, until, refresh)
    remaining = [(key, row) for key, row in all_rows if after is None or key > after]
    page = remaining[:PAGE_SIZE]
    next_cursor = None
    if len(remaining) > PAGE_SIZE:
        day, ad_id = page[-1][0]
        next_cursor = f"{day.isoformat()}/{ad_id}"
    return {
        "since": since.isoformat(), "until": until.isoformat(), "currency": account["currency"],
        "timezone": account["timezone_name"], "captured_at": captured,
        "action_report_time": "impression", "attribution": "Per-ad-set settings.",
        "rows": [_report_row(row) for _, row in page], "next_cursor": next_cursor,
        "total_rows": len(all_rows), "core_metrics_only": not coverage["accepted"],
        "extra_field_coverage": coverage,
        "basis": "Live paid Meta Insights by ad and account date. Missing fields are unknown. "
                 "Reach and frequency are per ad and date. Today's results may change.",
    }
