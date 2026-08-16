from datetime import date, datetime, time, timedelta, timezone
from collections import Counter
import csv
import io
import json
import logging
from pathlib import Path
import re
from time import monotonic

import os_accounts
import design_studio_styles
import sports_sales_calendar


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SPORTING_CALENDAR_PATH = DATA_DIR / "sporting_calendar.json"
COLLECTIONS_TASK_GROUP = "Collections to update"
DESIGN_TASK_GROUP = "New designs to complete"
UPLOAD_TASK_GROUP = "New products to be uploaded (in designs offline not uploaded folder)"
VARIANTS_TASK_GROUP = "Existing product updated — variants working"
LEGACY_UPLOAD_TASK_GROUPS = ("New product uploaded — set to Draft",)
MOCKUP_SCOPE_WEBSITE = "website mockups"
MOCKUP_SCOPE_ALL = "all mockups"
MOCKUP_SCOPE_OPTIONS = (MOCKUP_SCOPE_WEBSITE, MOCKUP_SCOPE_ALL)
TASK_GROUPS = (
    COLLECTIONS_TASK_GROUP,
    DESIGN_TASK_GROUP,
    UPLOAD_TASK_GROUP,
    VARIANTS_TASK_GROUP,
)
DESIGN_TASK_VISIBLE_LIMIT = 3
DESIGN_TASK_PREVIEW_WORD_LIMIT = 5
TASK_IMPORT_TEMPLATE_FILENAME = "sports-cave-task-import-template.csv"
TASK_EXPORT_FILENAME = "sports-cave-home-tasks.csv"
TASK_IMPORT_SCHEMA_VERSION = "sports_cave_task_import_v2"
TASK_IMPORT_MAX_BYTES = 2 * 1024 * 1024
TASK_IMPORT_METADATA_KEY = "task_import"
DESIGN_DETAILS_METADATA_KEY = "design_details"
TASK_IMPORT_SHARED_COLUMNS = (
    "task",
    "category",
    "task_section",
    "task_title",
)
DESIGN_TASK_CSV_COLUMNS = (
    "design_style",
    *design_studio_styles.DESIGN_DETAIL_KEYS,
)
TASK_IMPORT_LEGACY_DETAIL_COLUMNS = (
    "league_or_competition",
    "team_or_athlete",
    "moment_or_theme",
    "design_description",
    "priority",
    "due_date",
    "notes",
)
TASK_IMPORT_CSV_COLUMNS = (
    *TASK_IMPORT_SHARED_COLUMNS,
    *DESIGN_TASK_CSV_COLUMNS,
    *TASK_IMPORT_LEGACY_DETAIL_COLUMNS,
)
DESIGN_IDEA_SPORTS = (
    "NFL",
    "NBA",
    "Football / Soccer",
    "AFL",
    "NRL",
    "Cricket",
    "Formula 1 / Motorsport",
    "UFC / Boxing",
    "MLB / Baseball",
    "NHL / Ice Hockey",
    "Tennis",
    "Golf",
    "Horse Racing",
    "Other",
)
DESIGN_IDEA_STYLE_FIELDS = (
    ("ultimate_moment", "Ultimate Moment"),
    ("rivalry_faceoff", "Rivalry Face-Off"),
    ("legends_jersey_display", "Legends — Jerseys on Display"),
    ("nostalgic_tribute", "Nostalgic Moment"),
    ("motorsport_driver_car", "Motor Racing"),
    ("minimalist_hero", "Simple Minimalistic"),
    ("championship_achievement", "Specific Sporting Moment"),
    ("vintage_restoration", "Restored Collector Series"),
)
DESIGN_IDEA_STYLE_SLUGS = tuple(slug for slug, _label in DESIGN_IDEA_STYLE_FIELDS)
DESIGN_IDEA_DEFAULT_TOTAL = 10
DESIGN_IDEA_STYLE_WEIGHTS = {
    "Formula 1 / Motorsport": (
        ("motorsport_driver_car", 5),
        ("ultimate_moment", 3),
        ("nostalgic_tribute", 2),
        ("minimalist_hero", 2),
        ("championship_achievement", 1),
        ("vintage_restoration", 1),
        ("rivalry_faceoff", 1),
    ),
    "NFL": (
        ("rivalry_faceoff", 3),
        ("legends_jersey_display", 2),
        ("ultimate_moment", 2),
        ("nostalgic_tribute", 2),
        ("championship_achievement", 2),
        ("minimalist_hero", 1),
        ("vintage_restoration", 1),
    ),
    "Horse Racing": (
        ("ultimate_moment", 3),
        ("nostalgic_tribute", 3),
        ("minimalist_hero", 2),
        ("championship_achievement", 2),
        ("vintage_restoration", 1),
    ),
}
DESIGN_IDEA_GENERIC_STYLE_WEIGHTS = (
    ("ultimate_moment", 3),
    ("nostalgic_tribute", 2),
    ("minimalist_hero", 2),
    ("championship_achievement", 2),
    ("rivalry_faceoff", 1),
    ("legends_jersey_display", 1),
    ("vintage_restoration", 1),
)
TASK_IMPORT_DETAIL_FIELDS = (
    ("design_style", "Design style"),
    *design_studio_styles.DESIGN_DETAIL_FIELDS,
    ("league_or_competition", "League or competition"),
    ("team_or_athlete", "Team or athlete"),
    ("moment_or_theme", "Moment or theme"),
    ("design_description", "Design description"),
    ("priority", "Priority"),
    ("due_date", "Due date"),
    ("notes", "Notes"),
)
REGIONS = ("Australia", "USA", "UK", "Canada", "New Zealand")
ACTIVITY_LOG_LIMIT = 200
TASK_CACHE_TTL_SECONDS = 15
ACTIVITY_CACHE_TTL_SECONDS = 20
CALENDAR_CACHE_TTL_SECONDS = 300
EDITION_PRODUCT_CACHE_TTL_SECONDS = 300
DAILY_EXECUTION_CACHE_TTL_SECONDS = 15
DEFAULT_UPCOMING_DAYS = 60
ACTIVITY_VIEW_TODAY = "Today"
ACTIVITY_VIEW_LAST_7_DAYS = "Last 7 days"
ACTIVITY_VIEW_MONTH = "Month"
ACTIVITY_VIEW_ALL_TIME = "All time"
ACTIVITY_VIEWS = (
    ACTIVITY_VIEW_TODAY,
    ACTIVITY_VIEW_LAST_7_DAYS,
    ACTIVITY_VIEW_MONTH,
    ACTIVITY_VIEW_ALL_TIME,
)
ACTIVITY_VIEW_LIMITS = {
    ACTIVITY_VIEW_TODAY: None,
    ACTIVITY_VIEW_LAST_7_DAYS: None,
    ACTIVITY_VIEW_MONTH: None,
    ACTIVITY_VIEW_ALL_TIME: None,
}
ACTIVITY_SORT_NEWEST = "Newest first"
ACTIVITY_SORT_OLDEST = "Oldest first"
ACTIVITY_SORT_ACTION_ASC = "Action A-Z"
ACTIVITY_SORT_ACTION_DESC = "Action Z-A"
ACTIVITY_SORT_USER_ASC = "User A-Z"
ACTIVITY_SORT_USER_DESC = "User Z-A"
ACTIVITY_SORT_AREA_ASC = "Page/Area A-Z"
ACTIVITY_SORT_OPTIONS = (
    ACTIVITY_SORT_NEWEST,
    ACTIVITY_SORT_OLDEST,
    ACTIVITY_SORT_ACTION_ASC,
    ACTIVITY_SORT_ACTION_DESC,
    ACTIVITY_SORT_USER_ASC,
    ACTIVITY_SORT_USER_DESC,
    ACTIVITY_SORT_AREA_ASC,
)
MOCKUP_ACTIVITY_GROUP_WINDOW = timedelta(minutes=45)
MOCKUP_ACTIVITY_GROUP_ACTIONS = {"mockup_uploaded", "mockup_made"}
_TASK_CACHE = {}
_ACTIVITY_CACHE = {}
_CALENDAR_CACHE = {}
_EDITION_PRODUCT_CACHE = {}
_DAILY_EXECUTION_CACHE = {}
LOGGER = logging.getLogger(__name__)


class DashboardStorageError(RuntimeError):
    pass


class TaskCSVImportError(ValueError):
    pass


def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path, fallback):
    path = Path(path)
    if not path.exists():
        return dict(fallback)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(fallback)
    return data if isinstance(data, dict) else dict(fallback)


def _copy_rows(rows):
    return [dict(row) for row in rows or []]


def _cache_get(cache, key):
    cached = cache.get(key)
    if not cached:
        return None
    expires_at, value = cached
    if expires_at < monotonic():
        cache.pop(key, None)
        return None
    return _copy_rows(value)


def _cache_set(cache, key, value, ttl_seconds):
    cache[key] = (monotonic() + ttl_seconds, _copy_rows(value))
    return _copy_rows(value)


def clear_task_cache():
    _TASK_CACHE.clear()


def clear_activity_cache():
    _ACTIVITY_CACHE.clear()


def clear_daily_execution_cache(user_id=None, sheet_dates=None):
    clean_user_id = str(user_id or "").strip()
    clean_dates = {
        value.isoformat() if isinstance(value, date) else str(value or "").strip()
        for value in (sheet_dates or [])
    }
    if not clean_user_id and not clean_dates:
        _DAILY_EXECUTION_CACHE.clear()
        return
    for key in list(_DAILY_EXECUTION_CACHE):
        key_text = tuple(str(part or "") for part in (key if isinstance(key, tuple) else (key,)))
        if clean_user_id and clean_user_id not in key_text:
            continue
        if not clean_dates:
            _DAILY_EXECUTION_CACHE.pop(key, None)
            continue
        kind = key_text[0] if key_text else ""
        affected = False
        if kind == "daily_execution" and len(key_text) > 2:
            affected = key_text[2] in clean_dates
        elif kind == "daily_home" and len(key_text) > 2:
            home_date = date.fromisoformat(key_text[2])
            affected = any(value in {home_date.isoformat(), (home_date + timedelta(days=1)).isoformat()} for value in clean_dates)
        elif kind == "daily_week" and len(key_text) > 3:
            week_start = date.fromisoformat(key_text[2])
            week_end = date.fromisoformat(key_text[3])
            affected = any(week_start <= date.fromisoformat(value) <= week_end for value in clean_dates)
        elif kind == "daily_archive_detail":
            affected = True
        if affected:
            _DAILY_EXECUTION_CACHE.pop(key, None)


def clear_calendar_cache():
    _CALENDAR_CACHE.clear()


def clear_edition_product_cache():
    _EDITION_PRODUCT_CACHE.clear()


def clear_dashboard_caches():
    clear_task_cache()
    clear_activity_cache()
    clear_daily_execution_cache()
    clear_edition_product_cache()


def get_supabase_backend():
    try:
        import supabase_backend
    except Exception as error:
        raise DashboardStorageError("Dashboard saving is unavailable right now.") from error
    if not supabase_backend.is_configured():
        raise DashboardStorageError("Dashboard saving is not connected right now.")
    return supabase_backend


def _storage_error(error):
    if isinstance(error, DashboardStorageError):
        return str(error)
    return "Dashboard saving is unavailable right now."


def _daily_outcome_storage_error(error):
    if isinstance(error, DashboardStorageError):
        return str(error)
    try:
        import supabase_backend

        schema_message = supabase_backend.daily_execution_outcome_schema_error_message(error)
    except Exception:
        schema_message = ""
    if schema_message:
        return schema_message
    return (
        "Daily Planner could not save this task outcome. Retry. "
        "If it continues, contact an administrator."
    )


def _normalise_task(task):
    task = dict(task or {})
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    title = str(task.get("title") or task.get("text") or "").strip()
    section = normalize_task_category(task.get("section") or task.get("category"))
    return {
        **task,
        "id": str(task.get("id") or ""),
        "text": title,
        "title": title,
        "category": section,
        "section": section,
        "design_style": design_studio_styles.normalize_design_style(
            task.get("design_style") or metadata.get("design_style")
        ),
    }


def task_design_style(task):
    task = dict(task or {})
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    return design_studio_styles.normalize_design_style(
        task.get("design_style") or metadata.get("design_style")
    )


def task_design_style_label(task):
    return design_studio_styles.design_style_label(task_design_style(task))


def _task_created_at_sort_key(task):
    value = (task or {}).get("created_at")
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(
            str(value or "").replace("Z", "+00:00")
        )
    except (TypeError, ValueError):
        parsed = datetime.max.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc), str((task or {}).get("id") or "")


def ordered_task_group(tasks, group):
    group_tasks = [
        task for task in (tasks or []) if task.get("category") == group
    ]
    if group != DESIGN_TASK_GROUP:
        return group_tasks
    return sorted(group_tasks, key=_task_created_at_sort_key)


def compact_design_task_preview(value, word_limit=DESIGN_TASK_PREVIEW_WORD_LIMIT):
    words = str(value or "").split()
    try:
        safe_limit = max(int(word_limit), 1)
    except (TypeError, ValueError):
        safe_limit = DESIGN_TASK_PREVIEW_WORD_LIMIT
    preview = " ".join(words[:safe_limit])
    return f"{preview}..." if len(words) > safe_limit else preview


def _task_section_alias_key(value):
    text = str(value or "").strip().casefold()
    text = text.replace("\u2013", " ").replace("\u2014", " ").replace("\ufffd", " ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return "_".join(text.split())


def _task_section_aliases():
    aliases = {
        COLLECTIONS_TASK_GROUP: (
            "collection",
            "collections",
            "collection_update",
            "collection_updates",
            "collections_to_update",
        ),
        DESIGN_TASK_GROUP: (
            "design",
            "designs",
            "new_design",
            "new_designs",
            "new_design_tasks",
            "new_designs_to_complete",
            "designs_to_complete",
        ),
        UPLOAD_TASK_GROUP: (
            "upload",
            "uploads",
            "product_upload",
            "product_uploads",
            "new_product_upload",
            "new_product_uploads",
            "new_products",
            "products_to_upload",
            "new_products_to_be_uploaded",
            "new_products_to_be_uploaded_in_designs_offline_not_uploaded_folder",
            "offline_uploads",
            "offline_not_uploaded",
        ),
        VARIANTS_TASK_GROUP: (
            "variant",
            "variants",
            "product_variant",
            "product_variants",
            "variants_working",
            "existing_product_update",
            "existing_product_updated",
            "existing_product_updated_variants_working",
        ),
    }
    lookup = {}
    for section, section_aliases in aliases.items():
        lookup[_task_section_alias_key(section)] = section
        for alias in section_aliases:
            lookup[_task_section_alias_key(alias)] = section
    for legacy in LEGACY_UPLOAD_TASK_GROUPS:
        lookup[_task_section_alias_key(legacy)] = UPLOAD_TASK_GROUP
    return lookup


def normalize_task_category(category):
    category = str(category or "").strip()
    if category in LEGACY_UPLOAD_TASK_GROUPS:
        return UPLOAD_TASK_GROUP
    return category if category in TASK_GROUPS else TASK_GROUPS[0]


def normalize_task_import_section(section):
    clean = str(section or "").strip()
    if not clean:
        return ""
    return _task_section_aliases().get(_task_section_alias_key(clean), "")


def normalize_design_idea_sport(value):
    clean = " ".join(str(value or "").strip().casefold().split())
    for sport in DESIGN_IDEA_SPORTS:
        if clean == sport.casefold():
            return sport
    return ""


def normalize_design_idea_style_mix(style_mix=None):
    source = dict(style_mix or {})
    normalized = {}
    for slug, label in DESIGN_IDEA_STYLE_FIELDS:
        raw_value = source.get(slug, source.get(label, 0))
        try:
            count = int(raw_value or 0)
        except (TypeError, ValueError):
            count = 0
        normalized[slug] = max(count, 0)
    return normalized


def design_idea_style_mix_total(style_mix=None):
    return sum(normalize_design_idea_style_mix(style_mix).values())


def suggest_design_idea_style_mix(sport, total):
    selected_sport = normalize_design_idea_sport(sport)
    if not selected_sport:
        raise ValueError("Select a supported sport or collection.")
    try:
        requested_total = int(total)
    except (TypeError, ValueError) as error:
        raise ValueError("Number of design ideas must be between 1 and 30.") from error
    if not 1 <= requested_total <= 30:
        raise ValueError("Number of design ideas must be between 1 and 30.")

    weighted_styles = DESIGN_IDEA_STYLE_WEIGHTS.get(
        selected_sport,
        DESIGN_IDEA_GENERIC_STYLE_WEIGHTS,
    )
    total_weight = sum(weight for _slug, weight in weighted_styles)
    mix = {slug: 0 for slug in DESIGN_IDEA_STYLE_SLUGS}
    remainders = []
    allocated = 0
    for order, (slug, weight) in enumerate(weighted_styles):
        exact = requested_total * weight / total_weight
        count = int(exact)
        mix[slug] = count
        allocated += count
        remainders.append((exact - count, -order, slug))
    for _fraction, _order, slug in sorted(remainders, reverse=True)[
        : requested_total - allocated
    ]:
        mix[slug] += 1
    return mix


def _clean_task_csv_field(value):
    if value is None:
        return ""
    return str(value).replace("\r\n", "\n").replace("\r", "\n").strip()


def _design_details_from_sources(*sources):
    merged = {}
    for source in sources:
        if isinstance(source, dict):
            merged.update(source)
    details = design_studio_styles.normalize_design_details(merged)
    team_or_athlete = _clean_task_csv_field(merged.get("team_or_athlete"))
    if team_or_athlete and not details["principal_subject_one"]:
        rivals = re.split(
            r"\s+(?:vs\.?|versus)\s+",
            team_or_athlete,
            maxsplit=1,
            flags=re.I,
        )
        details["principal_subject_one"] = rivals[0].strip()
        if len(rivals) > 1 and not details["principal_subject_two"]:
            details["principal_subject_two"] = rivals[1].strip()
    if not details["team_country"]:
        details["team_country"] = team_or_athlete
    if not details["event_moment"]:
        details["event_moment"] = _clean_task_csv_field(merged.get("moment_or_theme"))
    if not details["special_instructions"]:
        details["special_instructions"] = _clean_task_csv_field(
            merged.get("design_description") or merged.get("notes")
        )
    return details


def design_task_details(task):
    task = dict(task or {})
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else task
    if not isinstance(metadata, dict):
        return design_studio_styles.normalize_design_details()
    imported = metadata.get(TASK_IMPORT_METADATA_KEY)
    brief = metadata.get("design_brief")
    saved = metadata.get(DESIGN_DETAILS_METADATA_KEY)
    root_details = {
        key: metadata.get(key)
        for key in (*design_studio_styles.DESIGN_DETAIL_KEYS, *TASK_IMPORT_LEGACY_DETAIL_COLUMNS)
        if key in metadata
    }
    return _design_details_from_sources(root_details, brief, imported, saved)


def validate_design_task_details(style_slug, details, task_text=""):
    clean_details = design_studio_styles.normalize_design_details(details)
    subjects = design_studio_styles.principal_subjects(clean_details)
    task_text = str(task_text or "")
    # Explicit CSV subject fields are authoritative. Only inspect prose when it
    # clearly contains a list, so collector titles are never mistaken for people.
    if not subjects or ("," in task_text and re.search(r"\b(?:and|&)\b", task_text, re.I)):
        for subject in design_studio_styles.principal_subjects({}, task_text):
            subject_key = subject.casefold()
            matches_existing = any(
                subject_key == item.casefold()
                or subject_key == (item.split()[-1].casefold() if item.split() else "")
                or subject_key.startswith(f"{item.casefold()} ")
                or item.casefold().startswith(f"{subject_key} ")
                for item in subjects
            )
            if not matches_existing:
                subjects.append(subject)
    if len(subjects) > 2:
        return [
            "This task exceeds the new Sports Cave limit of two principal people. "
            "Reduce it to one or two subjects before generating prompts."
        ]
    return design_studio_styles.validate_design_request(style_slug, clean_details)


def build_task_import_template_csv(tasks=None):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=TASK_IMPORT_CSV_COLUMNS)
    writer.writeheader()
    if tasks is not None:
        for task in tasks or []:
            normalised = _normalise_task(task)
            details = task_import_details(normalised)
            design_details = design_task_details(normalised)
            is_design_task = normalised.get("section") == DESIGN_TASK_GROUP
            title = normalised.get("title") or ""
            section = normalised.get("section") or ""
            writer.writerow(
                {
                    "task": title,
                    "category": section,
                    "task_section": section,
                    "task_title": title,
                    "design_style": task_design_style(normalised) if is_design_task else "",
                    **{
                        column: design_details.get(column, "") if is_design_task else ""
                        for column in design_studio_styles.DESIGN_DETAIL_KEYS
                    },
                    **{
                        column: details.get(column, "")
                        for column in TASK_IMPORT_LEGACY_DETAIL_COLUMNS
                    },
                }
            )
        return output.getvalue().encode("utf-8")
    return output.getvalue().encode("utf-8")


def _decode_task_import_csv(data, filename=""):
    if filename and not str(filename).casefold().endswith(".csv"):
        raise TaskCSVImportError("Choose a .csv file exported from the task template.")
    if isinstance(data, str):
        text = data
        byte_length = len(text.encode("utf-8"))
    else:
        try:
            raw = bytes(data or b"")
        except TypeError as error:
            raise TaskCSVImportError("Choose a valid CSV file.") from error
        byte_length = len(raw)
        if not raw:
            raise TaskCSVImportError("Choose a completed task CSV file.")
        if byte_length > TASK_IMPORT_MAX_BYTES:
            raise TaskCSVImportError("The task CSV must be smaller than 2 MB.")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise TaskCSVImportError("Save the task CSV as UTF-8 and try again.") from error
    text = text.lstrip("\ufeff")
    if byte_length > TASK_IMPORT_MAX_BYTES:
        raise TaskCSVImportError("The task CSV must be smaller than 2 MB.")
    if "\x00" in text[:2048]:
        raise TaskCSVImportError("Choose a valid text CSV file, not a binary file.")
    if not text.strip():
        raise TaskCSVImportError("Choose a completed task CSV file.")
    return text


def _normalise_duplicate_part(value):
    text = str(value or "").replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    return " ".join(text.split()).casefold()


def task_import_duplicate_key(section, task_title="", design_title="", team_or_athlete=""):
    return (
        _task_section_alias_key(section),
        _normalise_duplicate_part(task_title),
        _normalise_duplicate_part(design_title),
        _normalise_duplicate_part(team_or_athlete),
    )


def task_import_details(task):
    metadata = (task or {}).get("metadata") if isinstance(task, dict) else task
    if not isinstance(metadata, dict):
        return {}
    details = metadata.get(TASK_IMPORT_METADATA_KEY)
    if not isinstance(details, dict):
        details = metadata.get("design_brief")
    if not isinstance(details, dict):
        details = metadata if any(key in metadata for key, _label in TASK_IMPORT_DETAIL_FIELDS) else {}
    if not isinstance(details, dict):
        return {}
    fields = {
        key: _clean_task_csv_field(details.get(key))
        for key in (
            "design_style",
            *design_studio_styles.DESIGN_DETAIL_KEYS,
            *TASK_IMPORT_LEGACY_DETAIL_COLUMNS,
        )
    }
    canonical_details = design_task_details(task)
    for key, value in canonical_details.items():
        if value:
            fields[key] = value
    fields["design_style"] = task_design_style(task)
    if not any(fields.values()):
        return {}
    return fields


def task_import_summary(task):
    details = task_import_details(task)
    if not details:
        return ""
    preferred = (
        details.get("sport"),
        " vs ".join(
            value
            for value in (
                details.get("principal_subject_one"),
                details.get("principal_subject_two"),
            )
            if value
        )
        or details.get("team_or_athlete")
        or details.get("team_country"),
        details.get("league_or_competition"),
    )
    parts = [part for part in preferred if part]
    if not parts:
        parts = [details.get("priority"), details.get("due_date"), details.get("moment_or_theme")]
        parts = [part for part in parts if part]
    return " · ".join(parts[:3])


def design_task_list_details(task):
    task = _normalise_task(task)
    details = task_import_details(task)
    canonical = design_task_details(task)
    return {
        "task_id": task.get("id") or "",
        "design_title": canonical.get("design_title") or task.get("title") or "Untitled design",
        "design_style": task_design_style(task),
        "design_style_label": task_design_style_label(task),
        "sport": canonical.get("sport") or details.get("league_or_competition") or "",
        "principal_subject_one": canonical.get("principal_subject_one") or "",
        "principal_subject_two": canonical.get("principal_subject_two") or "",
        "priority": details.get("priority") or "",
        "created_at": task.get("created_at"),
    }


def task_csv_values(task):
    task = _normalise_task(task)
    details = task_import_details(task)
    section = task.get("section") or task.get("category") or ""
    title = task.get("title") or task.get("text") or ""
    values = {
        "task": title,
        "category": section,
        "task_section": section,
        "task_title": details.get("task_title") or title,
        "design_style": task_design_style(task),
    }
    for key in (*design_studio_styles.DESIGN_DETAIL_KEYS, *TASK_IMPORT_LEGACY_DETAIL_COLUMNS):
        values[key] = details.get(key) or ""
    return values


def _task_table_rank(values):
    match = re.search(r"\brank\s+(\d+)\b", str((values or {}).get("notes") or ""), re.I)
    return int(match.group(1)) if match else 10_000


def task_table_rows(tasks, group):
    rows = []
    priority_order = {"high": 0, "medium": 1, "low": 2}
    normalised_tasks = [_normalise_task(task) for task in tasks or []]
    for task in ordered_task_group(normalised_tasks, group):
        values = task_csv_values(task)
        created_at = task.get("created_at")
        rows.append(
            {
                "_task_id": str(task.get("id") or ""),
                "_created_at": created_at,
                "_created_label": str(created_at or ""),
                **values,
            }
        )
    if group == DESIGN_TASK_GROUP:
        rows.sort(
            key=lambda row: (
                priority_order.get(str(row.get("priority") or "").casefold(), 3),
                _task_table_rank(row),
                str(row.get("_created_at") or ""),
            )
        )
    return rows


def filter_task_table_rows(rows, *, search="", design_style="", sport="", priority=""):
    search_key = _normalise_duplicate_part(search)
    filtered = []
    for row in rows or []:
        if design_style and row.get("design_style") != design_style:
            continue
        if sport and row.get("sport") != sport:
            continue
        if priority and row.get("priority") != priority:
            continue
        if search_key:
            haystack = " ".join(
                _normalise_duplicate_part(row.get(column))
                for column in TASK_IMPORT_CSV_COLUMNS
            )
            if search_key not in haystack:
                continue
        filtered.append(row)
    return filtered


def _task_existing_duplicate_key(task):
    task = _normalise_task(task)
    details = task_import_details(task)
    task_title = details.get("task_title") if details else ""
    if task_title is None or task_title == "":
        task_title = task.get("title") or task.get("text") or ""
    return task_import_duplicate_key(
        task.get("section") or task.get("category") or "",
        task_title,
        details.get("design_title") if details else "",
        details.get("team_or_athlete") if details else "",
    )


TASK_IMPORT_ACTION_NEW = "Valid new"
TASK_IMPORT_ACTION_REACTIVATE = "Will reactivate"
TASK_IMPORT_ACTION_ACTIVE_DUPLICATE = "Existing active duplicate"
TASK_IMPORT_ACTION_COMPLETED_DUPLICATE = "Completed duplicate"
TASK_IMPORT_ACTION_INVALID = "Invalid"
_TASK_IMPORT_DELETED_STATUSES = {"deleted", "archived"}
_TASK_IMPORT_COMPLETED_STATUSES = {"complete", "completed"}


def _task_import_status_group(task):
    status = str((task or {}).get("status") or "open").strip().casefold()
    if status in _TASK_IMPORT_DELETED_STATUSES:
        return "deleted"
    if status in _TASK_IMPORT_COMPLETED_STATUSES:
        return "completed"
    return "active"


def _task_import_existing_index(tasks):
    index = {}
    priority = {"active": 3, "completed": 2, "deleted": 1}
    for task in tasks or []:
        if not task:
            continue
        duplicate_key = _task_existing_duplicate_key(task)
        group = _task_import_status_group(task)
        current = index.get(duplicate_key)
        if current is None or priority[group] > priority[current[0]]:
            index[duplicate_key] = (group, task)
    return index


def _task_csv_row_is_blank(row):
    values = []
    for key, value in (row or {}).items():
        if key is None and isinstance(value, (list, tuple)):
            values.extend(value)
            continue
        values.append(value)
    return not any(_clean_task_csv_field(value) for value in values)


def _task_import_metadata(values, *, section, title, row_number, filename=""):
    design_details = _design_details_from_sources(values)
    metadata = {
        "source": "task_csv_import",
        "design_style": values.get("design_style") or "",
        DESIGN_DETAILS_METADATA_KEY: design_details,
        TASK_IMPORT_METADATA_KEY: {
            "schema_version": TASK_IMPORT_SCHEMA_VERSION,
            "row_number": row_number,
            "task_section": values.get("task_section") or section,
            "section": section,
            "visible_title": title,
            **{
                column: values.get(column, "")
                for column in TASK_IMPORT_CSV_COLUMNS
                if column != "task_section"
            },
        },
    }
    if filename:
        metadata[TASK_IMPORT_METADATA_KEY]["filename"] = str(filename)[:250]
    return metadata


def preview_task_csv_import(data, filename="", existing_tasks=None):
    text = _decode_task_import_csv(data, filename)
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""))
        raw_fieldnames = reader.fieldnames or []
        fieldnames = [_clean_task_csv_field(name) for name in raw_fieldnames]
        if not fieldnames:
            raise TaskCSVImportError("The task CSV is missing a header row.")
        duplicated_headers = sorted(
            header
            for header, count in Counter(fieldnames).items()
            if header and count > 1
        )
        if duplicated_headers:
            raise TaskCSVImportError(
                f"The task CSV has duplicate column headers: {', '.join(duplicated_headers)}."
            )
        if not ({"task", "task_title", "design_title"} & set(fieldnames)):
            raise TaskCSVImportError(
                "The task CSV must include task, task_title or design_title."
            )
        if not ({"category", "task_section"} & set(fieldnames)):
            raise TaskCSVImportError(
                "The task CSV must include category or task_section."
            )
        header_map = {clean: raw for clean, raw in zip(fieldnames, raw_fieldnames)}
        rows = list(reader)
    except TaskCSVImportError:
        raise
    except csv.Error as error:
        raise TaskCSVImportError(
            "The task CSV could not be read. Check its quoting and line breaks."
        ) from error

    existing_index = _task_import_existing_index(existing_tasks or [])
    seen_actions = {}
    candidates = []
    errors = []
    active_duplicates = []
    completed_duplicates = []
    reactivations = []
    blank_count = 0
    section_counts = Counter()

    for offset, row in enumerate(rows, start=2):
        if _task_csv_row_is_blank(row):
            blank_count += 1
            continue
        values = {
            column: _clean_task_csv_field(row.get(header_map[column]))
            if column in header_map
            else ""
            for column in TASK_IMPORT_CSV_COLUMNS
        }
        section_value = values.get("category") or values.get("task_section")
        section = normalize_task_import_section(section_value)
        row_errors = []
        row_error_details = []

        def add_row_error(field, message):
            row_errors.append(message)
            row_error_details.append({"field": field, "message": message})

        if not section:
            add_row_error(
                "category",
                "category must match an existing task section or a supported short key."
            )
        title = values.get("task") or values.get("task_title") or values.get("design_title")
        if not title:
            add_row_error("task", "task is required.")
        raw_style = values.get("design_style")
        style_slug = design_studio_styles.normalize_design_style(raw_style)
        if raw_style and not style_slug:
            add_row_error(
                "design_style",
                f"Unknown design_style: {raw_style}. Accepted styles: "
                f"{', '.join(design_studio_styles.style_slugs())}."
            )
        if section == DESIGN_TASK_GROUP and not raw_style:
            add_row_error("design_style", "Style required for new design tasks.")
        values["design_style"] = style_slug
        values["task"] = title
        values["task_title"] = title
        values["category"] = section
        values["task_section"] = section
        if section == DESIGN_TASK_GROUP and style_slug:
            for message in validate_design_task_details(
                style_slug,
                _design_details_from_sources(values),
                title,
            ):
                add_row_error("principal_subjects", message)
        if row_errors:
            errors.append(
                {
                    "row_number": offset,
                    "section": section,
                    "title": title,
                    "values": values,
                    "errors": row_errors,
                    "error_details": row_error_details,
                }
            )
            continue
        duplicate_key = task_import_duplicate_key(
            section,
            values.get("task_title"),
            values.get("design_title"),
            values.get("team_or_athlete"),
        )
        existing_group, existing_task = existing_index.get(duplicate_key, ("", None))
        if duplicate_key in seen_actions or existing_group == "active":
            action = TASK_IMPORT_ACTION_ACTIVE_DUPLICATE
        elif existing_group == "completed":
            action = TASK_IMPORT_ACTION_COMPLETED_DUPLICATE
        elif existing_group == "deleted":
            action = TASK_IMPORT_ACTION_REACTIVATE
        else:
            action = TASK_IMPORT_ACTION_NEW
        item = {
            "row_number": offset,
            "section": section,
            "title": title,
            "values": values,
            "metadata": _task_import_metadata(
                values,
                section=section,
                title=title,
                row_number=offset,
                filename=filename,
            ),
            "duplicate_key": duplicate_key,
            "intended_action": action,
            "existing_task_id": str((existing_task or {}).get("id") or ""),
        }
        if action == TASK_IMPORT_ACTION_ACTIVE_DUPLICATE:
            active_duplicates.append(item)
        elif action == TASK_IMPORT_ACTION_COMPLETED_DUPLICATE:
            completed_duplicates.append(item)
        else:
            candidates.append(item)
            section_counts[section] += 1
            if action == TASK_IMPORT_ACTION_REACTIVATE:
                reactivations.append(item)
        seen_actions[duplicate_key] = action

    return {
        "filename": str(filename or ""),
        "valid_count": len(candidates),
        "new_count": len(candidates) - len(reactivations),
        "reactivate_count": len(reactivations),
        "active_duplicate_count": len(active_duplicates),
        "completed_duplicate_count": len(completed_duplicates),
        "total_row_count": len(rows) - blank_count,
        "blank_count": blank_count,
        "invalid_count": len(errors),
        "skipped_count": blank_count + len(errors),
        "duplicate_count": len(active_duplicates) + len(completed_duplicates),
        "section_counts": dict(section_counts),
        "tasks": candidates,
        "errors": errors,
        "duplicates": [*active_duplicates, *completed_duplicates],
        "active_duplicates": active_duplicates,
        "completed_duplicates": completed_duplicates,
        "reactivations": reactivations,
    }


def build_task_import_error_csv(preview):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=("row_number", "design_title", "field", "error"),
    )
    writer.writeheader()
    for item in (preview or {}).get("errors") or []:
        details = item.get("error_details") or [
            {"field": "row", "message": message}
            for message in item.get("errors") or []
        ]
        for detail in details:
            writer.writerow(
                {
                    "row_number": item.get("row_number") or "",
                    "design_title": (item.get("values") or {}).get("design_title") or item.get("title") or "",
                    "field": detail.get("field") or "row",
                    "error": detail.get("message") or "",
                }
            )
    return output.getvalue().encode("utf-8")


def _task_import_section_counts_text(section_counts):
    parts = []
    for section in TASK_GROUPS:
        count = int((section_counts or {}).get(section) or 0)
        if count:
            parts.append(f"{count} {section.casefold()}")
    return "; ".join(parts)


def format_task_import_result_message(result):
    imported_count = int((result or {}).get("imported_count") or 0)
    section_counts = {
        section: int(count or 0)
        for section, count in ((result or {}).get("section_counts") or {}).items()
        if int(count or 0) > 0
    }
    design_only = bool(section_counts) and set(section_counts) == {DESIGN_TASK_GROUP}
    if design_only:
        task_word = "design task" if imported_count == 1 else "design tasks"
    else:
        task_word = "task" if imported_count == 1 else "tasks"
    return (
        f"{imported_count} {task_word} imported — "
        f"{int((result or {}).get('created_count') or 0)} created, "
        f"{int((result or {}).get('reactivated_count') or 0)} reactivated, "
        f"{int((result or {}).get('skipped_count') or 0)} skipped, "
        f"{int((result or {}).get('failed_count') or 0)} failed."
    )


def import_task_csv_preview(preview):
    candidates = [dict(task) for task in (preview or {}).get("tasks") or []]
    try:
        backend = get_supabase_backend()
        from activity_log import get_activity_actor

        result = backend.import_dashboard_tasks_batch(
            candidates,
            actor=get_activity_actor(),
        )
        result = dict(result or {})
        result["filename"] = str((preview or {}).get("filename") or "")
        result["active_duplicate_count"] = int(result.get("active_duplicate_count") or 0) + int(
            (preview or {}).get("active_duplicate_count") or 0
        )
        result["completed_duplicate_count"] = int(
            result.get("completed_duplicate_count") or 0
        ) + int((preview or {}).get("completed_duplicate_count") or 0)
        result["duplicate_count"] = (
            result["active_duplicate_count"] + result["completed_duplicate_count"]
        )
        result["failed_count"] = int(result.get("failed_count") or 0) + int(
            (preview or {}).get("invalid_count") or 0
        )
        result["skipped_count"] = (
            int(result.get("active_duplicate_count") or 0)
            + int(result.get("completed_duplicate_count") or 0)
            + int((preview or {}).get("blank_count") or 0)
        )
        result["imported_count"] = int(result.get("created_count") or 0) + int(
            result.get("reactivated_count") or 0
        )
        clear_task_cache()
        clear_activity_cache()
        if result["imported_count"]:
            try:
                from activity_log import get_activity_actor, record_activity_log

                record_activity_log(
                    "task_csv_imported",
                    "Dashboard",
                    format_task_import_result_message(result),
                    entity_type="dashboard_task_import",
                    metadata={
                        "filename": result["filename"],
                        "imported_count": result["imported_count"],
                        "created_count": int(result.get("created_count") or 0),
                        "reactivated_count": int(result.get("reactivated_count") or 0),
                        "skipped_count": result["skipped_count"],
                        "section_counts": result.get("section_counts") or {},
                    },
                    actor=get_activity_actor(),
                )
                clear_activity_cache()
            except Exception:
                pass
        return result
    except DashboardStorageError:
        raise
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def normalize_mockup_scope(value):
    text = str(value or "").replace("_", " ").strip().casefold()
    if text in {"all", "all mockup", "all mockups"}:
        return MOCKUP_SCOPE_ALL
    if text in {"website", "web", "website mockup", "website mockups", "just website mockups"}:
        return MOCKUP_SCOPE_WEBSITE
    return MOCKUP_SCOPE_WEBSITE


def upload_task_title_for_design(task_text, mockup_scope):
    title = " ".join(str(task_text or "").split()).strip()
    if not title:
        title = "New design"
    return f"{title} ({normalize_mockup_scope(mockup_scope)})"


def list_tasks(status="open", *, section=None, limit=200):
    try:
        safe_limit = min(max(int(limit or 200), 1), 5000)
    except (TypeError, ValueError):
        safe_limit = 200
    clean_section = normalize_task_category(section) if section else ""
    try:
        backend = get_supabase_backend()
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error
    cache_key = (
        "tasks",
        id(backend),
        str(status or "open").strip().casefold(),
        clean_section,
        safe_limit,
    )
    cached = _cache_get(_TASK_CACHE, cache_key)
    if cached is not None:
        return [_normalise_task(task) for task in cached]
    try:
        try:
            raw_tasks = backend.list_dashboard_tasks(
                status=status,
                section=clean_section or None,
                limit=safe_limit,
            )
        except TypeError:
            raw_tasks = backend.list_dashboard_tasks(status=status, limit=safe_limit)
            if clean_section:
                raw_tasks = [
                    task
                    for task in raw_tasks or []
                    if normalize_task_category(task.get("section") or task.get("category"))
                    == clean_section
                ]
        tasks = [
            _normalise_task(task)
            for task in raw_tasks
        ]
        return _cache_set(_TASK_CACHE, cache_key, tasks, TASK_CACHE_TTL_SECONDS)
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def get_task(task_id):
    clean_task_id = str(task_id or "").strip()
    if not clean_task_id:
        return None
    try:
        backend = get_supabase_backend()
        if hasattr(backend, "get_dashboard_task"):
            task = backend.get_dashboard_task(clean_task_id)
            return _normalise_task(task) if task else None
        raw_tasks = backend.list_dashboard_tasks(status="all", limit=5000)
        return next(
            (
                _normalise_task(task)
                for task in raw_tasks or []
                if str(task.get("id") or "") == clean_task_id
            ),
            None,
        )
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def count_tasks(status="open", *, section=None):
    clean_section = normalize_task_category(section) if section else ""
    try:
        backend = get_supabase_backend()
        if hasattr(backend, "count_dashboard_tasks"):
            return int(
                backend.count_dashboard_tasks(
                    status=status,
                    section=clean_section or None,
                )
                or 0
            )
        return len(list_tasks(status=status, section=clean_section or None, limit=5000))
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def add_task(text, category, *, metadata=None, design_style=""):
    task_text = str(text or "").strip()
    if not task_text:
        raise ValueError("Task text is required.")
    section = normalize_task_category(category)
    metadata = dict(metadata or {})
    style_slug = design_studio_styles.normalize_design_style(
        design_style or metadata.get("design_style")
    )
    if section == DESIGN_TASK_GROUP and not style_slug:
        raise ValueError("Style required for new design tasks.")
    if style_slug:
        metadata["design_style"] = style_slug
    try:
        backend = get_supabase_backend()
        from activity_log import get_activity_actor

        created = backend.create_dashboard_task(
            task_text,
            section,
            metadata=metadata,
            design_style=style_slug,
            actor=get_activity_actor(),
        )
        task = _normalise_task(created)
        clear_task_cache()
        clear_activity_cache()
        return task
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def update_task_design_style(task_id, design_style):
    clean_task_id = str(task_id or "").strip()
    style_slug = design_studio_styles.normalize_design_style(design_style)
    if not clean_task_id:
        raise ValueError("Task id is required.")
    if not style_slug:
        raise ValueError("Style required.")
    try:
        backend = get_supabase_backend()
        from activity_log import get_activity_actor

        updated = backend.update_dashboard_task_design_style(
            clean_task_id,
            style_slug,
            actor=get_activity_actor(),
        )
        if not updated:
            raise ValueError(
                "The selected Home design task could not be found. Refresh the task list and try again."
            )
        clear_task_cache()
        clear_activity_cache()
        return _normalise_task(updated)
    except ValueError:
        raise
    except Exception as error:
        LOGGER.error(
            "Design task style save failed (%s; task_id=%s)",
            type(error).__name__,
            clean_task_id,
        )
        raise DashboardStorageError(
            "Design style could not be saved. Confirm the Design Studio V2 database migration has been applied."
        ) from error


def update_task_design_details(task_id, design_style, details):
    clean_task_id = str(task_id or "").strip()
    style_slug = design_studio_styles.normalize_design_style(design_style)
    if not clean_task_id:
        raise ValueError("Task id is required.")
    if not style_slug:
        raise ValueError("Style required.")
    clean_details = design_studio_styles.normalize_design_details(details)
    task = get_task(clean_task_id)
    validation_errors = validate_design_task_details(
        style_slug,
        clean_details,
        str((task or {}).get("title") or (task or {}).get("text") or ""),
    )
    if validation_errors:
        raise ValueError(" ".join(validation_errors))
    try:
        backend = get_supabase_backend()
        from activity_log import get_activity_actor

        updated = backend.update_dashboard_task_design_details(
            clean_task_id,
            style_slug,
            clean_details,
            actor=get_activity_actor(),
        )
        if not updated:
            raise ValueError(
                "The selected Home design task could not be found. Refresh the task list and try again."
            )
        clear_task_cache()
        clear_activity_cache()
        return _normalise_task(updated) if updated else None
    except ValueError:
        raise
    except Exception as error:
        LOGGER.error(
            "Design task details save failed (%s; task_id=%s)",
            type(error).__name__,
            clean_task_id,
        )
        raise DashboardStorageError(
            "Design details could not be saved. Confirm the Design Studio V2 database migration has been applied."
        ) from error


def can_manage_dashboard_tasks(user):
    return bool(
        os_accounts.account_is_active(user)
        and os_accounts.can_access_page(user, "Dashboard")
    )


def delete_design_task(task_id, *, user):
    clean_task_id = str(task_id or "").strip()
    if not clean_task_id:
        raise ValueError("Task id is required.")
    if not can_manage_dashboard_tasks(user):
        raise PermissionError("You do not have permission to delete design tasks.")
    try:
        backend = get_supabase_backend()
        from activity_log import get_activity_actor

        deleted = backend.delete_dashboard_task(
            clean_task_id,
            required_section=DESIGN_TASK_GROUP,
            deleted_by=str((user or {}).get("display_name") or (user or {}).get("username") or ""),
            actor=get_activity_actor(),
        )
        clear_task_cache()
        clear_activity_cache()
        return _normalise_task(deleted) if deleted else None
    except PermissionError:
        raise
    except Exception as error:
        LOGGER.error(
            "Design task deletion failed (%s; task_id=%s)",
            type(error).__name__,
            clean_task_id,
        )
        raise DashboardStorageError(
            "The design task could not be deleted right now. Refresh the list and try again."
        ) from error


def complete_task(task_id, *, metadata=None):
    try:
        backend = get_supabase_backend()
        from activity_log import get_activity_actor

        completed = backend.complete_dashboard_task(
            task_id,
            metadata=metadata or {},
            completed_by=get_activity_actor(),
            actor=get_activity_actor(),
        )
        clear_task_cache()
        clear_activity_cache()
        return _normalise_task(completed) if completed else None
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def complete_design_task_for_upload(task_id, task_text, mockup_scope, *, metadata=None):
    scope = normalize_mockup_scope(mockup_scope)
    completed = complete_task(
        task_id,
        metadata={
            **(metadata or {}),
            "next_task_section": UPLOAD_TASK_GROUP,
            "mockup_scope": scope,
        },
    )
    if completed is None:
        return None
    upload_task = add_task(
        upload_task_title_for_design(task_text or completed.get("text") or completed.get("title"), scope),
        UPLOAD_TASK_GROUP,
        metadata={
            "source_task_id": str(task_id or ""),
            "source_task_section": DESIGN_TASK_GROUP,
            "mockup_scope": scope,
        },
    )
    return {"completed": completed, "upload_task": upload_task}


DAILY_EXECUTION_TITLE = "Daily Task Execution Sheet - The 5 Million Dollar Man"
DAILY_EXECUTION_STATUS_PLANNED = "planned"
DAILY_EXECUTION_STATUS_ACTIVE = "active"
DAILY_EXECUTION_STATUS_COMPLETED = "completed"
DAILY_EXECUTION_STATUS_REVIEWED = "reviewed"
DAILY_EXECUTION_STATUS_ARCHIVED = "archived"
DAILY_EXECUTION_REVIEWED_STATUSES = (
    DAILY_EXECUTION_STATUS_COMPLETED,
    DAILY_EXECUTION_STATUS_REVIEWED,
    DAILY_EXECUTION_STATUS_ARCHIVED,
)
DAILY_TASK_STATUS_DONE = "done"
DAILY_TASK_STATUS_COULDNT_FINISH = "couldnt_finish"
DAILY_TASK_STATUS_SKIPPED = "skipped"
DAILY_TASK_FINISHED_STATUSES = (
    DAILY_TASK_STATUS_DONE,
    DAILY_TASK_STATUS_COULDNT_FINISH,
    DAILY_TASK_STATUS_SKIPPED,
)
DAILY_TIMER_OUTCOME_COMPLETED = "completed"
DAILY_TIMER_OUTCOME_DID_NOT_FINISH = "did_not_finish"
DAILY_TIMER_OUTCOME_SKIPPED = "skipped"
DAILY_TIMER_RUNNING_STATUSES = ("running", "paused", "expired")
DAILY_RATING_FIELDS = (
    "Focus",
    "Attention",
    "Flow Awareness",
    "Emotional Control",
    "Execution",
    "Vision Alignment",
    "Overall Score",
)


def _blank_top_tasks():
    return [
        {"task": "", "why": "", "time_blocked": "", "completed": False, "status": ""}
        for _ in range(3)
    ]


def _blank_additional_items(count=1):
    return [
        {"task": "", "details": "", "time_blocked": "", "completed": False, "status": ""}
        for _ in range(count)
    ]


def _coerce_daily_item_rows(items):
    if items is None:
        return []
    if isinstance(items, str):
        text = items.strip()
        if not text:
            return []
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            return [{"task": text}]
        return _coerce_daily_item_rows(decoded)
    if isinstance(items, dict):
        return [items]
    if isinstance(items, (list, tuple)):
        rows = []
        for item in items:
            if isinstance(item, dict):
                rows.append(item)
            elif isinstance(item, str):
                text = item.strip()
                if text:
                    rows.append({"task": text})
        return rows
    return []


def _normalise_top_tasks(items):
    rows = []
    for item in _coerce_daily_item_rows(items)[:3]:
        item = dict(item or {})
        status = _compact_text(item.get("status") or "").casefold()
        if status not in DAILY_TASK_FINISHED_STATUSES:
            status = DAILY_TASK_STATUS_DONE if bool(item.get("completed")) else ""
        completed = status == DAILY_TASK_STATUS_DONE
        rows.append(
            {
                "task": _compact_text(item.get("task") or item.get("title") or ""),
                "why": _compact_text(item.get("why") or item.get("outcome") or item.get("details") or ""),
                "time_blocked": _compact_text(item.get("time_blocked") or item.get("time") or ""),
                "completed": completed,
                "status": status,
                "completed_at": item.get("completed_at"),
                "finished_at": item.get("finished_at"),
                "outcome": _compact_text(item.get("outcome") or ""),
                "completion_method": _compact_text(item.get("completion_method") or ""),
                "skip_reason": _compact_text(item.get("skip_reason") or ""),
                "actual_elapsed_seconds": item.get("actual_elapsed_seconds"),
                "time_saved_seconds": item.get("time_saved_seconds"),
                "completed_before_expiry": bool(item.get("completed_before_expiry")),
                "outcome_version": max(int(item.get("outcome_version") or 0), 0),
                "outcome_history": list(item.get("outcome_history") or [])[-20:],
                "reopened_at": item.get("reopened_at"),
                "carried_from": _compact_text(item.get("carried_from") or ""),
            }
        )
    while len(rows) < 3:
        rows.append({"task": "", "why": "", "time_blocked": "", "completed": False, "status": ""})
    return rows


def _normalise_daily_task_status(item):
    item = dict(item or {})
    status = _compact_text(item.get("status") or "").casefold()
    if status not in DAILY_TASK_FINISHED_STATUSES:
        status = DAILY_TASK_STATUS_DONE if bool(item.get("completed")) else ""
    return status


def _normalise_additional_items(items, *, include_blank=True):
    rows = []
    for item in _coerce_daily_item_rows(items):
        item = dict(item or {})
        status = _normalise_daily_task_status(item)
        completed = status == DAILY_TASK_STATUS_DONE
        row = {
            "task": _compact_text(item.get("task") or item.get("note") or item.get("title") or ""),
            "details": _compact_text(item.get("details") or item.get("why") or item.get("outcome") or ""),
            "time_blocked": _compact_text(item.get("time_blocked") or item.get("time") or item.get("time_allocated") or ""),
            "completed": completed,
            "status": status,
            "completed_at": item.get("completed_at"),
            "finished_at": item.get("finished_at"),
            "outcome": _compact_text(item.get("outcome") or ""),
            "completion_method": _compact_text(item.get("completion_method") or ""),
            "skip_reason": _compact_text(item.get("skip_reason") or ""),
            "actual_elapsed_seconds": item.get("actual_elapsed_seconds"),
            "time_saved_seconds": item.get("time_saved_seconds"),
            "completed_before_expiry": bool(item.get("completed_before_expiry")),
            "outcome_version": max(int(item.get("outcome_version") or 0), 0),
            "outcome_history": list(item.get("outcome_history") or [])[-20:],
            "reopened_at": item.get("reopened_at"),
            "carried_from": _compact_text(item.get("carried_from") or ""),
        }
        if _daily_additional_item_has_content(row) or include_blank:
            rows.append(row)
    if include_blank:
        rows = [row for row in rows if _daily_additional_item_has_content(row)]
        rows.append(_blank_additional_items(1)[0])
    return rows


def _daily_additional_item_has_content(item):
    if not isinstance(item, dict):
        item = _coerce_daily_item_rows(item)
        item = item[0] if item else {}
    return bool(
        _compact_text(item.get("task") or "")
        or _compact_text(item.get("details") or "")
        or _compact_text(item.get("time_blocked") or "")
    )


def _normalise_additional_items_for_save(items):
    rows = []
    for item in _normalise_additional_items(items, include_blank=False):
        if _daily_additional_item_has_content(item):
            rows.append(
                {
                    "task": item.get("task") or "",
                    "details": item.get("details") or "",
                    "time_blocked": item.get("time_blocked") or "",
                    "completed": _normalise_daily_task_status(item) == DAILY_TASK_STATUS_DONE,
                    "status": item.get("status") or "",
                    "completed_at": item.get("completed_at"),
                    "finished_at": item.get("finished_at"),
                    "outcome": item.get("outcome") or "",
                    "completion_method": item.get("completion_method") or "",
                    "skip_reason": item.get("skip_reason") or "",
                    "actual_elapsed_seconds": item.get("actual_elapsed_seconds"),
                    "time_saved_seconds": item.get("time_saved_seconds"),
                    "completed_before_expiry": bool(item.get("completed_before_expiry")),
                    "outcome_version": max(int(item.get("outcome_version") or 0), 0),
                    "outcome_history": list(item.get("outcome_history") or [])[-20:],
                    "reopened_at": item.get("reopened_at"),
                    "carried_from": item.get("carried_from") or "",
                }
            )
    return rows


def _normalise_daily_sheet(sheet):
    sheet = dict(sheet or {})
    if not sheet:
        return {}
    top_tasks = _normalise_top_tasks(sheet.get("top_tasks") or [])
    additional_items = _normalise_additional_items(sheet.get("additional_items") or [])
    no_grey_zone = sheet.get("no_grey_zone") if isinstance(sheet.get("no_grey_zone"), dict) else {}
    ratings = sheet.get("ratings") if isinstance(sheet.get("ratings"), dict) else {}
    planning_data = sheet.get("planning_data") if isinstance(sheet.get("planning_data"), dict) else {}
    review_data = sheet.get("review_data") if isinstance(sheet.get("review_data"), dict) else {}
    archived_snapshot = sheet.get("archived_snapshot") if isinstance(sheet.get("archived_snapshot"), dict) else {}
    return {
        **sheet,
        "id": str(sheet.get("id") or ""),
        "user_id": str(sheet.get("user_id") or ""),
        "user_name": _compact_text(sheet.get("user_name") or ""),
        "sheet_date": str(sheet.get("sheet_date") or ""),
        "day_name": _compact_text(sheet.get("day_name") or ""),
        "timezone": _compact_text(sheet.get("timezone") or "Australia/Sydney"),
        "status": _compact_text(sheet.get("status") or DAILY_EXECUTION_STATUS_ACTIVE),
        "top_tasks": top_tasks,
        "additional_items": additional_items,
        "no_grey_zone": no_grey_zone,
        "ratings": ratings,
        "planning_data": planning_data,
        "review_data": review_data,
        "archived_snapshot": archived_snapshot,
        "daily_summary": str(sheet.get("daily_summary") or ""),
        "tomorrow_intention": str(sheet.get("tomorrow_intention") or ""),
        "generated_prompt": str(sheet.get("generated_prompt") or ""),
        "activated_at": sheet.get("activated_at"),
        "archived_at": sheet.get("archived_at"),
    }


def daily_execution_user_id(user):
    return str((user or {}).get("id") or "").strip()


def daily_execution_user_name(user):
    return _compact_text(
        (user or {}).get("display_name")
        or (user or {}).get("email")
        or (user or {}).get("username")
        or "Nathan"
    )


def can_manage_daily_planner(user):
    return os_accounts.is_admin(user)


def _require_daily_execution_admin(user):
    if not can_manage_daily_planner(user):
        raise DashboardStorageError("Daily Execution access is not available for this account.")
    return daily_execution_user_id(user)


def get_daily_execution_sheet(user, sheet_date):
    user_id = _require_daily_execution_admin(user)
    clean_date = sheet_date.isoformat() if isinstance(sheet_date, date) else str(sheet_date or "")
    cache_key = ("daily_execution", user_id, clean_date)
    cached = _cache_get(_DAILY_EXECUTION_CACHE, cache_key)
    if cached is not None:
        return cached[0] if cached else {}
    try:
        backend = get_supabase_backend()
        sheet = _normalise_daily_sheet(backend.get_daily_execution_sheet(user_id, clean_date))
        _cache_set(_DAILY_EXECUTION_CACHE, cache_key, [sheet] if sheet else [], DAILY_EXECUTION_CACHE_TTL_SECONDS)
        return sheet
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def get_daily_execution_home_sheets(user, today):
    user_id = _require_daily_execution_admin(user)
    clean_today = today.isoformat() if isinstance(today, date) else str(today or "")
    tomorrow = date.fromisoformat(clean_today) + timedelta(days=1)
    cache_key = ("daily_home", user_id, clean_today)

    def home_bundle(rows):
        by_date = {row.get("sheet_date"): row for row in rows}
        carryover_review = next(
            (
                row
                for row in rows
                if row.get("sheet_date") < clean_today
                and daily_execution_review_complete(row)
            ),
            {},
        )
        return {
            "today": by_date.get(clean_today, {}),
            "tomorrow": by_date.get(tomorrow.isoformat(), {}),
            "carryover_review": carryover_review,
        }

    cached = _cache_get(_DAILY_EXECUTION_CACHE, cache_key)
    if cached is not None:
        return home_bundle(cached)
    try:
        backend = get_supabase_backend()
        if hasattr(backend, "get_daily_execution_home_sheets"):
            rows = backend.get_daily_execution_home_sheets(user_id, clean_today)
            normalised = [_normalise_daily_sheet(row) for row in rows or [] if row]
        else:
            normalised = [
                row
                for row in (
                    get_daily_execution_sheet(user, clean_today),
                    get_daily_execution_sheet(user, tomorrow),
                )
                if row
            ]
        if not normalised and hasattr(backend, "list_daily_execution_sheets"):
            recovery_start = (date.fromisoformat(clean_today) - timedelta(days=31)).isoformat()
            recovery_rows = backend.list_daily_execution_sheets(
                user_id,
                recovery_start,
                clean_today,
                limit=1,
            )
            latest = _normalise_daily_sheet((recovery_rows or [{}])[0])
            if latest and daily_execution_review_complete(latest):
                normalised = [latest]
        _cache_set(_DAILY_EXECUTION_CACHE, cache_key, normalised, DAILY_EXECUTION_CACHE_TTL_SECONDS)
        return home_bundle(normalised)
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def create_daily_execution_sheet(user, sheet_date, timezone_name, *, status=None):
    user_id = _require_daily_execution_admin(user)
    clean_date = sheet_date.isoformat() if isinstance(sheet_date, date) else str(sheet_date or "")
    try:
        backend = get_supabase_backend()
        from activity_log import get_activity_actor

        kwargs = {
            "user_id": user_id,
            "user_name": daily_execution_user_name(user),
            "sheet_date": clean_date,
            "timezone_name": timezone_name,
            "actor": get_activity_actor(),
        }
        if status is not None:
            kwargs["status"] = status
        try:
            raw_sheet = backend.create_daily_execution_sheet(**kwargs)
        except TypeError:
            kwargs.pop("status", None)
            raw_sheet = backend.create_daily_execution_sheet(**kwargs)
        sheet = _normalise_daily_sheet(raw_sheet)
        clear_daily_execution_cache(user_id)
        clear_activity_cache()
        return sheet
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def save_daily_execution_top_tasks(sheet_id, top_tasks, *, user=None):
    user_id = _require_daily_execution_admin(user)
    try:
        backend = get_supabase_backend()
        sheet = _normalise_daily_sheet(
            backend.update_daily_execution_top_tasks(
                sheet_id,
                _normalise_top_tasks(top_tasks),
                user_id=user_id,
            )
        )
        clear_daily_execution_cache(user_id)
        return sheet
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def save_daily_execution_tasks(sheet_id, top_tasks, additional_items, *, user=None):
    user_id = _require_daily_execution_admin(user)
    try:
        backend = get_supabase_backend()
        sheet = _normalise_daily_sheet(
            backend.update_daily_execution_top_tasks(
                sheet_id,
                _normalise_top_tasks(top_tasks),
                _normalise_additional_items_for_save(additional_items),
                user_id=user_id,
            )
        )
        clear_daily_execution_cache(user_id)
        return sheet
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def set_daily_execution_mip_completed(sheet_id, index, completed, *, outcome=None, user=None):
    user_id = _require_daily_execution_admin(user)
    clean_outcome = _compact_text(outcome or "").casefold()
    if clean_outcome not in DAILY_TASK_FINISHED_STATUSES:
        clean_outcome = DAILY_TASK_STATUS_DONE if bool(completed) else ""
    try:
        backend = get_supabase_backend()
        sheet = _normalise_daily_sheet(
            backend.set_daily_execution_mip_completed(
                sheet_id,
                index,
                clean_outcome in DAILY_TASK_FINISHED_STATUSES,
                outcome=clean_outcome,
                user_id=user_id,
            )
        )
        clear_daily_execution_cache(user_id)
        clear_activity_cache()
        return sheet
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def complete_daily_execution_review(sheet_id, review_payload, *, user=None):
    user_id = _require_daily_execution_admin(user)
    try:
        backend = get_supabase_backend()
        from activity_log import get_activity_actor

        kwargs = {"actor": get_activity_actor()}
        kwargs["user_id"] = user_id
        raw_sheet = backend.complete_daily_execution_review(sheet_id, review_payload or {}, **kwargs)
        sheet = _normalise_daily_sheet(raw_sheet)
        clear_daily_execution_cache(user_id)
        clear_activity_cache()
        return sheet
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def save_daily_execution_prompt(sheet_id, prompt, *, user=None):
    user_id = _require_daily_execution_admin(user)
    try:
        backend = get_supabase_backend()
        sheet = _normalise_daily_sheet(
            backend.update_daily_execution_prompt(
                sheet_id,
                str(prompt or ""),
                user_id=user_id,
            )
        )
        clear_daily_execution_cache(user_id)
        return sheet
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def list_daily_execution_sheets(user, start_date, end_date, *, limit=10):
    user_id = _require_daily_execution_admin(user)
    try:
        backend = get_supabase_backend()
        rows = backend.list_daily_execution_sheets(
            user_id,
            start_date.isoformat() if isinstance(start_date, date) else str(start_date or ""),
            end_date.isoformat() if isinstance(end_date, date) else str(end_date or ""),
            limit=limit,
        )
        return [_normalise_daily_sheet(row) for row in rows or []]
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def save_daily_execution_plan(
    user,
    sheet_date,
    timezone_name,
    top_tasks,
    additional_items,
    planning_data,
    *,
    archive_sheet_id=None,
):
    clean_date = sheet_date.isoformat() if isinstance(sheet_date, date) else str(sheet_date or "")
    user_id = _require_daily_execution_admin(user)
    try:
        backend = get_supabase_backend()
        from activity_log import get_activity_actor

        if hasattr(backend, "save_daily_execution_plan"):
            raw = backend.save_daily_execution_plan(
                user_id=user_id,
                user_name=daily_execution_user_name(user),
                sheet_date=clean_date,
                timezone_name=timezone_name,
                top_tasks=_normalise_top_tasks(top_tasks),
                additional_items=_normalise_additional_items_for_save(additional_items),
                planning_data=dict(planning_data or {}),
                archive_sheet_id=str(archive_sheet_id or "").strip() or None,
                actor=get_activity_actor(),
            )
        else:
            existing = get_daily_execution_sheet(user, clean_date)
            if existing:
                raw = backend.update_daily_execution_top_tasks(
                    existing.get("id"),
                    _normalise_top_tasks(top_tasks),
                    _normalise_additional_items_for_save(additional_items),
                    user_id=user_id,
                )
            else:
                raw = backend.create_daily_execution_sheet(
                    user_id=user_id,
                    user_name=daily_execution_user_name(user),
                    sheet_date=clean_date,
                    timezone_name=timezone_name,
                    actor=get_activity_actor(),
                )
                raw = backend.update_daily_execution_top_tasks(
                    raw.get("id"),
                    _normalise_top_tasks(top_tasks),
                    _normalise_additional_items_for_save(additional_items),
                    user_id=user_id,
                )
        affected_dates = [clean_date]
        if archive_sheet_id:
            try:
                affected_dates.append((date.fromisoformat(clean_date) - timedelta(days=1)).isoformat())
            except ValueError:
                pass
        clear_daily_execution_cache(user_id, affected_dates)
        clear_activity_cache()
        return _normalise_daily_sheet(raw)
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def list_daily_execution_archive_summaries(user, start_date, end_date, *, limit=8):
    user_id = _require_daily_execution_admin(user)
    clean_start = start_date.isoformat() if isinstance(start_date, date) else str(start_date or "")
    clean_end = end_date.isoformat() if isinstance(end_date, date) else str(end_date or "")
    cache_key = ("daily_week", user_id, clean_start, clean_end, int(limit))
    cached = _cache_get(_DAILY_EXECUTION_CACHE, cache_key)
    if cached is not None:
        return [_normalise_daily_sheet(row) for row in cached]
    try:
        backend = get_supabase_backend()
        if hasattr(backend, "list_daily_execution_archive_summaries"):
            rows = backend.list_daily_execution_archive_summaries(
                user_id,
                clean_start,
                clean_end,
                limit=limit,
            )
        else:
            rows = backend.list_daily_execution_sheets(user_id, clean_start, clean_end, limit=limit)
        normalised = [_normalise_daily_sheet(row) for row in rows or []]
        _cache_set(_DAILY_EXECUTION_CACHE, cache_key, normalised, DAILY_EXECUTION_CACHE_TTL_SECONDS)
        return normalised
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def load_daily_execution_weekly_review(user, start_date, end_date, *, limit=1000):
    """Load authorised weekly sheets and timers without per-sheet queries."""
    if not os_accounts.can_access_reporting(user):
        _require_daily_execution_admin(user)
    clean_start = start_date.isoformat() if isinstance(start_date, date) else str(start_date or "")
    clean_end = end_date.isoformat() if isinstance(end_date, date) else str(end_date or "")
    user_id = "" if os_accounts.is_admin(user) else daily_execution_user_id(user)
    try:
        backend = get_supabase_backend()
        if hasattr(backend, "list_daily_execution_sheets_for_reporting"):
            sheets = backend.list_daily_execution_sheets_for_reporting(
                user_id, clean_start, clean_end, limit=limit
            )
        else:
            sheets = backend.list_daily_execution_sheets(
                user_id or daily_execution_user_id(user), clean_start, clean_end, limit=limit
            )
        sheets = [_normalise_daily_sheet(sheet) for sheet in sheets or []]
        sheet_ids = [sheet.get("id") for sheet in sheets if sheet.get("id")]
        timers = (
            backend.list_daily_execution_timers_for_sheets(user_id, sheet_ids)
            if sheet_ids and hasattr(backend, "list_daily_execution_timers_for_sheets")
            else []
        )
        return {
            "sheets": sheets,
            "timers": [_normalise_timer(timer) for timer in timers or []],
            "query_count": 2 if sheet_ids else 1,
        }
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def get_daily_execution_archive_detail(user, sheet_id):
    user_id = _require_daily_execution_admin(user)
    clean_id = str(sheet_id or "").strip()
    cache_key = ("daily_archive_detail", user_id, clean_id)
    cached = _cache_get(_DAILY_EXECUTION_CACHE, cache_key)
    if cached is not None:
        return _normalise_daily_sheet(cached[0]) if cached else {}
    try:
        backend = get_supabase_backend()
        if hasattr(backend, "get_daily_execution_archive_detail"):
            row = backend.get_daily_execution_archive_detail(user_id, clean_id)
        else:
            row = {}
        normalised = _normalise_daily_sheet(row)
        _cache_set(_DAILY_EXECUTION_CACHE, cache_key, [normalised] if normalised else [], DAILY_EXECUTION_CACHE_TTL_SECONDS)
        return normalised
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def parse_daily_task_duration_seconds(value):
    text = _compact_text(value or "").casefold()
    if not text:
        return 0
    range_match = re.search(
        r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*[-–]\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
        text,
    )
    if range_match:
        start_hour = int(range_match.group(1))
        start_minute = int(range_match.group(2) or 0)
        start_ampm = range_match.group(3)
        end_hour = int(range_match.group(4))
        end_minute = int(range_match.group(5) or 0)
        end_ampm = range_match.group(6) or start_ampm
        if start_ampm == "pm" and start_hour < 12:
            start_hour += 12
        if start_ampm == "am" and start_hour == 12:
            start_hour = 0
        if end_ampm == "pm" and end_hour < 12:
            end_hour += 12
        if end_ampm == "am" and end_hour == 12:
            end_hour = 0
        start_total = start_hour * 60 + start_minute
        end_total = end_hour * 60 + end_minute
        if end_total <= start_total:
            end_total += 24 * 60
        return max((end_total - start_total) * 60, 0)
    number_match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not number_match:
        return 0
    amount = float(number_match.group(1))
    if "sec" in text or re.search(r"\b\d+(?:\.\d+)?s\b", text):
        return max(int(round(amount)), 0)
    if "min" in text or re.search(r"\b\d+(?:\.\d+)?m\b", text):
        return max(int(round(amount * 60)), 0)
    return max(int(round(amount * 3600)), 0)


def format_duration_seconds(seconds):
    try:
        total = max(int(seconds or 0), 0)
    except (TypeError, ValueError):
        total = 0
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _daily_task_status_label(task, timer=None):
    status = _normalise_daily_task_status(task)
    timer_status = str((timer or {}).get("status") or "").strip().casefold()
    outcome = str((task or {}).get("outcome") or (timer or {}).get("outcome") or "").strip().casefold()
    if outcome == DAILY_TIMER_OUTCOME_SKIPPED or status == DAILY_TASK_STATUS_SKIPPED:
        return "Skipped"
    if outcome == DAILY_TIMER_OUTCOME_DID_NOT_FINISH or status == DAILY_TASK_STATUS_COULDNT_FINISH:
        return "Did not finish"
    if outcome == DAILY_TIMER_OUTCOME_COMPLETED or status == DAILY_TASK_STATUS_DONE:
        return "Completed"
    if timer_status == "expired" or (timer or {}).get("outcome_required"):
        return "Time up - outcome required"
    if timer_status == "running":
        return "Timer running"
    if timer_status == "paused":
        return "Paused"
    if timer_status == "stopped":
        return "Stopped"
    return "Planned"


def daily_execution_task_rows(sheet, timers=None):
    sheet = _normalise_daily_sheet(sheet)
    timer_lookup = {
        (str(timer.get("task_type") or ""), int(timer.get("task_index") or 0)): dict(timer)
        for timer in (timers or [])
    }
    rows = []
    for index, task in enumerate(sheet.get("top_tasks") or []):
        if not task.get("task"):
            continue
        timer = timer_lookup.get(("top", index), {})
        rows.append(
            {
                "row_id": f"{sheet.get('id')}::top::{index}",
                "sheet_id": sheet.get("id") or "",
                "work_date": sheet.get("sheet_date") or "",
                "task_type": "top",
                "task_index": index,
                "task": task.get("task") or "",
                "owner": sheet.get("user_name") or "",
                "category": "MIP",
                "details": task.get("why") or "",
                "allocated": task.get("time_blocked") or "",
                "allocated_seconds": parse_daily_task_duration_seconds(task.get("time_blocked")),
                "status": _daily_task_status_label(task, timer),
                "outcome": task.get("outcome") or timer.get("outcome") or "",
                "completion_method": task.get("completion_method") or timer.get("completion_method") or "",
                "skip_reason": task.get("skip_reason") or timer.get("skip_reason") or "",
                "actual_elapsed_seconds": timer.get("actual_elapsed_seconds") if timer else task.get("actual_elapsed_seconds"),
                "time_saved_seconds": task.get("time_saved_seconds") if task.get("time_saved_seconds") is not None else timer.get("time_saved_seconds"),
                "notes": task.get("why") or "",
                "completed_at": task.get("completed_at"),
                "finished_at": task.get("finished_at"),
                "timer": timer,
            }
        )
    for index, task in enumerate(sheet.get("additional_items") or []):
        if not _daily_additional_item_has_content(task):
            continue
        timer = timer_lookup.get(("additional", index), {})
        rows.append(
            {
                "row_id": f"{sheet.get('id')}::additional::{index}",
                "sheet_id": sheet.get("id") or "",
                "work_date": sheet.get("sheet_date") or "",
                "task_type": "additional",
                "task_index": index,
                "task": task.get("task") or task.get("details") or "",
                "owner": sheet.get("user_name") or "",
                "category": task.get("category") or "Other",
                "details": task.get("details") or "",
                "allocated": task.get("time_blocked") or "",
                "allocated_seconds": parse_daily_task_duration_seconds(task.get("time_blocked")),
                "status": _daily_task_status_label(task, timer),
                "outcome": task.get("outcome") or timer.get("outcome") or "",
                "completion_method": task.get("completion_method") or timer.get("completion_method") or "",
                "skip_reason": task.get("skip_reason") or timer.get("skip_reason") or "",
                "actual_elapsed_seconds": timer.get("actual_elapsed_seconds") if timer else task.get("actual_elapsed_seconds"),
                "time_saved_seconds": task.get("time_saved_seconds") if task.get("time_saved_seconds") is not None else timer.get("time_saved_seconds"),
                "notes": task.get("details") or "",
                "completed_at": task.get("completed_at"),
                "finished_at": task.get("finished_at"),
                "timer": timer,
            }
        )
    return rows


def _normalise_timer(timer):
    timer = dict(timer or {})
    if not timer:
        return {}
    return {
        **timer,
        "id": str(timer.get("id") or ""),
        "sheet_id": str(timer.get("sheet_id") or ""),
        "task_type": str(timer.get("task_type") or ""),
        "task_index": int(timer.get("task_index") or 0),
        "allocated_seconds": int(timer.get("allocated_seconds") or 0),
        "remaining_seconds": max(int(timer.get("remaining_seconds") or 0), 0),
        "elapsed_seconds": max(int(timer.get("elapsed_seconds") or timer.get("actual_elapsed_seconds") or 0), 0),
        "status": str(timer.get("status") or ""),
        "outcome": str(timer.get("outcome") or ""),
        "completion_method": str(timer.get("completion_method") or ""),
        "skip_reason": str(timer.get("skip_reason") or ""),
        "completed_before_expiry": bool(timer.get("completed_before_expiry")),
        "time_saved_seconds": max(int(timer.get("time_saved_seconds") or 0), 0),
    }


def reconcile_daily_planner_timers(user):
    user_id = _require_daily_execution_admin(user)
    try:
        backend = get_supabase_backend()
        if not hasattr(backend, "reconcile_daily_execution_timers"):
            return []
        return backend.reconcile_daily_execution_timers(
            user_id,
            actor=daily_execution_user_name(user),
        )
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def get_active_daily_planner_timer(user, *, reconcile=True):
    user_id = _require_daily_execution_admin(user)
    try:
        backend = get_supabase_backend()
        if not hasattr(backend, "get_daily_execution_active_timer"):
            return {}
        try:
            timer = backend.get_daily_execution_active_timer(
                user_id, reconcile=bool(reconcile)
            )
        except TypeError:
            timer = backend.get_daily_execution_active_timer(user_id)
        return _normalise_timer(timer)
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def start_daily_planner_timer(user, sheet_id, task_type, task_index, allocated_seconds):
    user_id = _require_daily_execution_admin(user)
    try:
        backend = get_supabase_backend()
        if not hasattr(backend, "start_daily_execution_task_timer"):
            raise DashboardStorageError("Daily Planner timers are not available until the timer migration is applied.")
        timer = backend.start_daily_execution_task_timer(
            user_id,
            sheet_id,
            task_type,
            task_index,
            allocated_seconds,
            actor=daily_execution_user_name(user),
        )
        clear_daily_execution_cache(user_id)
        clear_activity_cache()
        return _normalise_timer(timer)
    except ValueError as error:
        raise DashboardStorageError(str(error)) from error
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def pause_daily_planner_timer(user, timer_id):
    user_id = _require_daily_execution_admin(user)
    try:
        timer = get_supabase_backend().pause_daily_execution_task_timer(
            user_id,
            timer_id,
            actor=daily_execution_user_name(user),
        )
        clear_daily_execution_cache(user_id)
        return _normalise_timer(timer)
    except ValueError as error:
        raise DashboardStorageError(str(error)) from error
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def resume_daily_planner_timer(user, timer_id):
    user_id = _require_daily_execution_admin(user)
    try:
        timer = get_supabase_backend().resume_daily_execution_task_timer(
            user_id,
            timer_id,
            actor=daily_execution_user_name(user),
        )
        clear_daily_execution_cache(user_id)
        return _normalise_timer(timer)
    except ValueError as error:
        raise DashboardStorageError(str(error)) from error
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def stop_daily_planner_timer(user, timer_id):
    user_id = _require_daily_execution_admin(user)
    try:
        timer = get_supabase_backend().stop_daily_execution_task_timer(
            user_id,
            timer_id,
            actor=daily_execution_user_name(user),
        )
        clear_daily_execution_cache(user_id)
        return _normalise_timer(timer)
    except ValueError as error:
        raise DashboardStorageError(str(error)) from error
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def apply_daily_planner_timer_outcome(user, timer_id, outcome):
    user_id = _require_daily_execution_admin(user)
    try:
        result = get_supabase_backend().apply_daily_execution_timer_outcome(
            user_id,
            timer_id,
            outcome,
            actor=daily_execution_user_name(user),
        )
        sheet = _normalise_daily_sheet((result or {}).get("sheet") or {})
        if sheet.get("sheet_date"):
            clear_daily_execution_cache(user_id, [sheet.get("sheet_date")])
        else:
            clear_daily_execution_cache(user_id)
        clear_activity_cache()
        return {**(result or {}), "sheet": sheet, "timer": _normalise_timer((result or {}).get("timer") or {})}
    except ValueError as error:
        raise DashboardStorageError(str(error)) from error
    except Exception as error:
        raise DashboardStorageError(_daily_outcome_storage_error(error)) from error


def apply_daily_planner_task_outcome(
    user,
    sheet_id,
    task_type,
    task_index,
    outcome,
    *,
    timer_id=None,
    reason="",
):
    user_id = _require_daily_execution_admin(user)
    try:
        result = get_supabase_backend().apply_daily_execution_task_outcome(
            user_id,
            sheet_id,
            task_type,
            task_index,
            outcome,
            timer_id=timer_id,
            reason=reason,
            actor=daily_execution_user_name(user),
        )
        sheet = _normalise_daily_sheet((result or {}).get("sheet") or {})
        if sheet.get("sheet_date"):
            clear_daily_execution_cache(user_id, [sheet.get("sheet_date")])
        else:
            clear_daily_execution_cache(user_id)
        clear_activity_cache()
        return {
            **(result or {}),
            "sheet": sheet,
            "timer": _normalise_timer((result or {}).get("timer") or {}),
        }
    except ValueError as error:
        raise DashboardStorageError(str(error)) from error
    except Exception as error:
        raise DashboardStorageError(_daily_outcome_storage_error(error)) from error


def list_daily_execution_history(user, start_date, end_date, *, limit=1000):
    if os_accounts.can_access_reporting(user):
        user_id = ""
    else:
        user_id = _require_daily_execution_admin(user)
    clean_start = start_date.isoformat() if isinstance(start_date, date) else str(start_date or "")
    clean_end = end_date.isoformat() if isinstance(end_date, date) else str(end_date or "")
    try:
        backend = get_supabase_backend()
        if hasattr(backend, "list_daily_execution_sheets_for_reporting"):
            sheets = backend.list_daily_execution_sheets_for_reporting(
                user_id,
                clean_start,
                clean_end,
                limit=limit,
            )
        else:
            sheets = backend.list_daily_execution_sheets(user_id or daily_execution_user_id(user), clean_start, clean_end, limit=limit)
        sheets = [_normalise_daily_sheet(sheet) for sheet in sheets or []]
        sheet_ids = [sheet.get("id") for sheet in sheets if sheet.get("id")]
        timers = (
            backend.list_daily_execution_timers_for_sheets(user_id, sheet_ids)
            if hasattr(backend, "list_daily_execution_timers_for_sheets")
            else []
        )
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error
    timers_by_sheet = {}
    for timer in timers or []:
        timers_by_sheet.setdefault(str(timer.get("sheet_id") or ""), []).append(_normalise_timer(timer))
    rows = []
    for sheet in sheets:
        rows.extend(daily_execution_task_rows(sheet, timers_by_sheet.get(sheet.get("id") or "", [])))
    return rows


def daily_execution_completed_count(sheet):
    return sum(
        1
        for task in (sheet or {}).get("top_tasks") or []
        if task.get("task") and _normalise_daily_task_status(task) == DAILY_TASK_STATUS_DONE
    )


def daily_execution_filled_task_count(sheet):
    return sum(1 for task in (sheet or {}).get("top_tasks") or [] if task.get("task"))


def daily_execution_task_finished(task):
    task = dict(task or {})
    status = _compact_text(task.get("status") or "").casefold()
    return status in DAILY_TASK_FINISHED_STATUSES or bool(task.get("completed"))


def daily_execution_all_tasks_complete(sheet):
    summary = daily_execution_outcome_summary(sheet)
    return summary["total_planned"] > 0 and summary["unresolved"] == 0


def daily_execution_all_mips_complete(sheet):
    tasks = [task for task in (sheet or {}).get("top_tasks") or [] if task.get("task")]
    return len(tasks) == 3 and all(daily_execution_task_finished(task) for task in tasks)


def _daily_execution_named_tasks(sheet):
    normalised = _normalise_daily_sheet(sheet)
    for index, task in enumerate(normalised.get("top_tasks") or []):
        if _compact_text(task.get("task") or ""):
            yield "top", index, dict(task)
    for index, task in enumerate(normalised.get("additional_items") or []):
        if _compact_text(task.get("task") or task.get("details") or ""):
            yield "additional", index, dict(task)


def _daily_task_outcome_key(task):
    status = _normalise_daily_task_status(task)
    outcome = _compact_text((task or {}).get("outcome") or "").casefold()
    if status == DAILY_TASK_STATUS_DONE or outcome == DAILY_TIMER_OUTCOME_COMPLETED:
        return "completed"
    if status == DAILY_TASK_STATUS_SKIPPED or outcome == DAILY_TIMER_OUTCOME_SKIPPED:
        return "skipped"
    if status == DAILY_TASK_STATUS_COULDNT_FINISH or outcome == DAILY_TIMER_OUTCOME_DID_NOT_FINISH:
        return "did_not_finish"
    return "unresolved"


def daily_execution_outcome_summary(sheet, timers=None):
    """Return the authoritative task denominator and outcomes for one sheet."""
    timer_lookup = {
        (str(timer.get("task_type") or ""), int(timer.get("task_index") or 0)): dict(timer)
        for timer in (timers or [])
    }
    summary = {
        "total_planned": 0,
        "completed": 0,
        "did_not_finish": 0,
        "skipped": 0,
        "unresolved": 0,
        "completion_percentage": 0.0,
        "actual_focused_seconds": 0,
        "completed_tasks": [],
        "did_not_finish_tasks": [],
        "skipped_tasks": [],
        "unresolved_tasks": [],
    }
    for task_type, task_index, task in _daily_execution_named_tasks(sheet):
        timer = timer_lookup.get((task_type, task_index), {})
        key = _daily_task_outcome_key(task)
        name = _compact_text(task.get("task") or task.get("details") or "Daily Planner task")
        summary["total_planned"] += 1
        summary[key] += 1
        if key == "completed":
            summary["completed_tasks"].append(name)
        elif key == "did_not_finish":
            summary["did_not_finish_tasks"].append(name)
        elif key == "skipped":
            summary["skipped_tasks"].append(name)
        else:
            summary["unresolved_tasks"].append(name)
        elapsed = timer.get("actual_elapsed_seconds")
        if elapsed is None:
            elapsed = task.get("actual_elapsed_seconds")
        if elapsed is None and timer:
            allocated = max(int(timer.get("allocated_seconds") or 0), 0)
            remaining = max(int(timer.get("remaining_seconds") or 0), 0)
            elapsed = max(allocated - remaining, 0)
        summary["actual_focused_seconds"] += max(int(elapsed or 0), 0)
    if summary["total_planned"]:
        summary["completion_percentage"] = (
            summary["completed"] / summary["total_planned"] * 100
        )
    return summary


def daily_execution_review_complete(sheet):
    return str((sheet or {}).get("status") or "").strip().casefold() in DAILY_EXECUTION_REVIEWED_STATUSES


def daily_execution_unfinished_tasks(sheet):
    rows = []
    for source, items in (("mip", (sheet or {}).get("top_tasks") or []), ("other", (sheet or {}).get("additional_items") or [])):
        for index, item in enumerate(items):
            item = dict(item or {})
            if item.get("task") and _normalise_daily_task_status(item) == DAILY_TASK_STATUS_COULDNT_FINISH:
                rows.append(
                    {
                        "key": f"{source}:{index}:{_compact_text(item.get('task'))}",
                        "task": _compact_text(item.get("task") or ""),
                        "details": _compact_text(item.get("why") or item.get("details") or ""),
                        "time_blocked": _compact_text(item.get("time_blocked") or ""),
                        "source": source,
                    }
                )
    return rows


def daily_execution_week_bounds(anchor_date):
    day = anchor_date if isinstance(anchor_date, date) else date.fromisoformat(str(anchor_date))
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=6)


def _planned_hours(value):
    text = _compact_text(value or "").casefold()
    if not text:
        return 0.0
    range_match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(?:am|pm)?\s*[-–]\s*(\d{1,2})(?::(\d{2}))?\s*(?:am|pm)?\b", text)
    if range_match:
        start = int(range_match.group(1)) + int(range_match.group(2) or 0) / 60
        end = int(range_match.group(3)) + int(range_match.group(4) or 0) / 60
        if end < start:
            end += 12
        return max(end - start, 0.0)
    number_match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not number_match:
        return 0.0
    amount = float(number_match.group(1))
    if "min" in text or re.search(r"\b\d+(?:\.\d+)?m\b", text):
        return amount / 60
    return amount


def daily_execution_weekly_task_instances(sheets, timers=None, *, today=None):
    """Return deduplicated, non-future planned task instances for weekly analytics."""
    local_today = today or datetime.now(sports_sales_calendar.SYDNEY_TIMEZONE).date()
    if not isinstance(local_today, date):
        local_today = date.fromisoformat(str(local_today))
    rows = []
    for raw in sheets or []:
        sheet = _normalise_daily_sheet(raw)
        try:
            sheet_date = date.fromisoformat(str(sheet.get("sheet_date") or ""))
        except ValueError:
            continue
        if sheet_date <= local_today:
            rows.append(sheet)
    rows.sort(key=lambda row: str(row.get("sheet_date") or ""))
    timer_lookup = {
        (
            str(timer.get("sheet_id") or ""),
            str(timer.get("task_type") or ""),
            int(timer.get("task_index") or 0),
        ): dict(timer)
        for timer in (timers or [])
    }
    explicit_carry_names = {
        (
            str(sheet.get("user_id") or sheet.get("user_name") or ""),
            _compact_text(task.get("task") or task.get("details") or "").casefold(),
        )
        for sheet in rows
        for _task_type, _task_index, task in _daily_execution_named_tasks(sheet)
        if task.get("carried_from")
    }
    legacy_carry_names = {
        (
            str(sheet.get("user_id") or sheet.get("user_name") or ""),
            _compact_text(
                (task.get("task") or task.get("details") or "")
                if isinstance(task, dict)
                else task
            ).casefold(),
        )
        for sheet in rows
        for task in ((sheet.get("planning_data") or {}).get("carried_forward") or [])
        if _compact_text(
            (task.get("task") or task.get("details") or "")
            if isinstance(task, dict)
            else task
        )
    } - explicit_carry_names
    instances = {}
    canonical_by_occurrence = {}
    for sheet in rows:
        owner_key = str(sheet.get("user_id") or sheet.get("user_name") or "")
        sheet_date = str(sheet.get("sheet_date") or "")
        for task_type, task_index, task in _daily_execution_named_tasks(sheet):
            name = _compact_text(task.get("task") or task.get("details") or "Daily Planner task")
            name_key = name.casefold()
            carried_from = _compact_text(task.get("carried_from") or "")
            if carried_from:
                instance_key = canonical_by_occurrence.get(
                    (owner_key, carried_from, name_key),
                    (owner_key, "carry", carried_from, name_key),
                )
            elif (owner_key, name_key) in legacy_carry_names:
                instance_key = (owner_key, "legacy-carry", name_key)
            else:
                instance_key = (
                    owner_key,
                    sheet_date,
                    task_type,
                    task_index,
                )
            timer = timer_lookup.get((sheet.get("id") or "", task_type, task_index), {})
            actual = timer.get("actual_elapsed_seconds")
            if actual is None:
                actual = task.get("actual_elapsed_seconds")
            if actual is None and timer:
                remaining = int(timer.get("remaining_seconds") or 0)
                if str(timer.get("status") or "").casefold() == "running" and timer.get("deadline_at"):
                    try:
                        deadline = datetime.fromisoformat(
                            str(timer.get("deadline_at")).replace("Z", "+00:00")
                        )
                        if deadline.tzinfo is None:
                            deadline = deadline.replace(tzinfo=timezone.utc)
                        remaining = max(
                            int((deadline.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds()),
                            0,
                        )
                    except ValueError:
                        pass
                actual = max(
                    int(timer.get("allocated_seconds") or 0)
                    - remaining,
                    0,
                )
            instances[instance_key] = {
                "instance_key": "::".join(str(part) for part in instance_key),
                "sheet_id": sheet.get("id") or "",
                "work_date": sheet.get("sheet_date") or "",
                "owner_id": str(sheet.get("user_id") or ""),
                "owner": sheet.get("user_name") or "",
                "task_type": task_type,
                "task_index": task_index,
                "task": name,
                "outcome": _daily_task_outcome_key(task),
                "allocated_seconds": parse_daily_task_duration_seconds(task.get("time_blocked")),
                "actual_elapsed_seconds": max(int(actual or 0), 0),
                "completion_method": task.get("completion_method") or timer.get("completion_method") or "",
                "skip_reason": task.get("skip_reason") or timer.get("skip_reason") or "",
                "completed_at": timer.get("outcome_at") or task.get("completed_at") or task.get("finished_at"),
            }
            canonical_by_occurrence[(owner_key, sheet_date, name_key)] = instance_key
    return list(instances.values())


def daily_execution_weekly_summary(sheets, timers=None, *, today=None):
    local_today = today or datetime.now(sports_sales_calendar.SYDNEY_TIMEZONE).date()
    if not isinstance(local_today, date):
        local_today = date.fromisoformat(str(local_today))
    rows = []
    for raw in sheets or []:
        sheet = _normalise_daily_sheet(raw)
        try:
            sheet_date = date.fromisoformat(str(sheet.get("sheet_date") or ""))
        except ValueError:
            continue
        if sheet_date <= local_today:
            rows.append(sheet)
    instances = daily_execution_weekly_task_instances(rows, timers, today=local_today)
    completed_count = sum(row["outcome"] == "completed" for row in instances)
    did_not_finish_count = sum(row["outcome"] == "did_not_finish" for row in instances)
    skipped_count = sum(row["outcome"] == "skipped" for row in instances)
    unresolved_count = sum(row["outcome"] == "unresolved" for row in instances)
    total_planned = len(instances)
    completion_percentage = completed_count / total_planned * 100 if total_planned else 0.0
    staff_completion = {}
    for task in instances:
        owner_key = task.get("owner_id") or task.get("owner") or "Current user"
        member = staff_completion.setdefault(
            owner_key,
            {
                "staff_id": task.get("owner_id") or "",
                "staff": task.get("owner") or "Current user",
                "completed": 0,
                "did_not_finish": 0,
                "skipped": 0,
                "unresolved": 0,
                "total_planned": 0,
                "actual_focused_seconds": 0,
            },
        )
        member["total_planned"] += 1
        member[task["outcome"]] += 1
        member["actual_focused_seconds"] += task["actual_elapsed_seconds"]
    for member in staff_completion.values():
        member["completion_percentage"] = (
            member["completed"] / member["total_planned"] * 100
            if member["total_planned"]
            else 0.0
        )
    mip_done = sum(
        row["task_type"] == "top" and row["outcome"] == "completed" for row in instances
    )
    mip_open = sum(
        row["task_type"] == "top" and row["outcome"] != "completed" for row in instances
    )
    other_done = sum(
        row["task_type"] == "additional" and row["outcome"] == "completed"
        for row in instances
    )
    planned_hours = sum(row["allocated_seconds"] for row in instances) / 3600
    ratings = []
    reasons = []
    carried = []
    wins = []
    blockers = []
    for sheet in rows:
        review = sheet.get("review_data") or {}
        no_grey = sheet.get("no_grey_zone") or {}
        reason = _compact_text(review.get("could_not_finish") or no_grey.get("avoided") or "")
        if reason:
            reasons.append(reason)
            blockers.append(reason)
        win = _compact_text(review.get("worked_well") or review.get("completed") or sheet.get("daily_summary") or "")
        if win:
            wins.append(win)
        score = (sheet.get("ratings") or {}).get("Overall Score")
        try:
            if score is not None and float(score) > 0:
                ratings.append(float(score))
        except (TypeError, ValueError):
            pass
        for item in (sheet.get("planning_data") or {}).get("carried_forward") or []:
            task_name = _compact_text((item or {}).get("task") if isinstance(item, dict) else item)
            if task_name:
                carried.append(task_name)
    reason_counts = Counter(reasons)
    carry_counts = Counter(carried)
    repeated = [name for name, count in carry_counts.most_common() if count > 1]
    return {
        "days_planned": sum(1 for sheet in rows if daily_execution_filled_task_count(sheet) or any(_daily_additional_item_has_content(item) for item in sheet.get("additional_items") or [])),
        "days_reviewed": sum(1 for sheet in rows if daily_execution_review_complete(sheet)),
        "mip_completed": mip_done,
        "mip_not_completed": mip_open,
        "other_completed": other_done,
        "total_planned": total_planned,
        "completed": completed_count,
        "did_not_finish": did_not_finish_count,
        "skipped": skipped_count,
        "unresolved": unresolved_count,
        "completion_percentage": completion_percentage,
        "actual_focused_seconds": sum(row["actual_elapsed_seconds"] for row in instances),
        "staff_completion": sorted(
            staff_completion.values(), key=lambda row: row["staff"].casefold()
        ),
        "planned_hours": round(planned_hours, 1),
        "unfinished_reasons": [name for name, _count in reason_counts.most_common(3)],
        "average_day_rating": round(sum(ratings) / len(ratings), 1) if ratings else 0,
        "repeated_carryovers": repeated,
        "biggest_wins": wins[:3],
        "main_blockers": blockers[:3],
        "recommended_priorities": repeated[:3] or [name for name, _count in carry_counts.most_common(3)],
    }


def daily_execution_alerts(sheet, local_now, *, user_name="Nathan"):
    alerts = []
    name = _compact_text(user_name or "Nathan")
    if not sheet:
        alerts.append("Today's execution sheet has not been planned.")
        return alerts
    filled = daily_execution_filled_task_count(sheet)
    complete = daily_execution_completed_count(sheet)
    if filled == 0:
        alerts.append("Today's list has no tasks yet.")
    if local_now.hour >= 15 and complete < 2:
        alerts.append("Past 3pm: fewer than 2/3 tasks are closed.")
    if local_now.hour >= 19 and not daily_execution_review_complete(sheet):
        alerts.append("Past 7pm: Daily Review is still open.")
    return alerts


def _sheet_summary(sheet):
    if not sheet:
        return "- No sheet found."
    lines = [f"- {sheet.get('sheet_date')}: {sheet.get('status')}"]
    for index, task in enumerate(sheet.get("top_tasks") or [], start=1):
        if task.get("task"):
            marker = task.get("status") or ("done" if task.get("completed") else "open")
            lines.append(f"  MIP Task {index}: {task.get('task')} ({marker}) - {task.get('why') or 'No details noted'}")
    other_tasks = [
        item for item in (sheet.get("additional_items") or [])
        if _daily_additional_item_has_content(item)
    ]
    for index, item in enumerate(other_tasks[:10], start=1):
        marker = item.get("status") or ("done" if item.get("completed") else "open")
        lines.append(f"  Other task {index}: {item.get('task') or item.get('details')} ({marker})")
    if sheet.get("daily_summary"):
        lines.append(f"  Summary: {_compact_text(sheet.get('daily_summary'))}")
    if sheet.get("tomorrow_intention"):
        lines.append(f"  Tomorrow: {_compact_text(sheet.get('tomorrow_intention'))}")
    no_grey = sheet.get("no_grey_zone") or {}
    avoided = _compact_text(no_grey.get("avoided") or no_grey.get("half_done") or "")
    if avoided:
        lines.append(f"  Avoided/half-done: {avoided}")
    return "\n".join(lines)


def _tasks_summary(tasks):
    lines = []
    for task in (tasks or [])[:25]:
        title = _compact_text(task.get("text") or task.get("title") or "")
        if title:
            lines.append(f"- {title} [{task.get('category') or task.get('section') or 'Task'}]")
    return "\n".join(lines) if lines else "- No open Home tasks loaded."


def _activity_summary(entries):
    lines = []
    for entry in (entries or [])[:40]:
        message = _compact_text(entry.get("message") or "")
        actor = _compact_text(entry.get("actor") or "")
        if message:
            suffix = f" ({actor})" if actor else ""
            lines.append(f"- {message}{suffix}")
    return "\n".join(lines) if lines else "- No activity loaded."


def _event_summary(events):
    lines = []
    for event in (events or [])[:20]:
        title = _compact_text(event.get("title") or "")
        if not title:
            continue
        sport = _compact_text(event.get("sport") or "Event")
        regions = ", ".join(event.get("regions") or event.get("markets") or [])
        date_label = format_event_date_range(event)
        region_text = f", {regions}" if regions else ""
        lines.append(f"- {title} ({sport}{region_text}; {date_label})")
    return "\n".join(lines) if lines else "- No upcoming sports or sales calendar moments loaded."


def build_tomorrow_execution_prompt(
    *,
    today_sheet,
    yesterday_sheet,
    week_sheets,
    open_tasks,
    activity_entries,
    upcoming_events,
):
    incomplete_tasks = []
    for task in (today_sheet or {}).get("top_tasks") or []:
        if task.get("task") and not daily_execution_task_finished(task):
            incomplete_tasks.append(f"- {task.get('task')} - {task.get('why') or 'No details noted'}")
    calendar_summary = _event_summary(upcoming_events or [])
    week_summary = "\n".join(_sheet_summary(sheet) for sheet in (week_sheets or [])[:7]) or "- No recent execution sheets loaded."
    incomplete_text = "\n".join(incomplete_tasks) if incomplete_tasks else "- No incomplete tasks from today."
    return f"""You are Nathan's Sports Cave 12 Week Year execution coach.

Your job is to review the latest Sports Cave OS data and build tomorrow's execution plan.

Primary goal:
Move Sports Cave toward $5,000,000 revenue through daily focused execution.

Use the data below:
- Today's completed and incomplete tasks
- Yesterday's execution sheet
- Last 7 days of execution patterns
- Activity Log
- Open Home dashboard tasks
- Upcoming sales/sporting calendar events
- Notes, wins, lessons, distractions, and avoided tasks

Do not be motivational fluff.
Be direct, commercially honest, and execution-focused.

Identify:
1. What Nathan actually moved forward
2. What was avoided, delayed, or half-done
3. What is noise
4. What matters most for revenue
5. What must be protected tomorrow
6. The top 3 tasks for tomorrow
7. The small supporting tasks that keep momentum moving
8. The one task that would make tomorrow a win even if everything else fails

Create tomorrow's Daily Execution Sheet with:
- Top 3 tasks
- Why each task matters
- Suggested time block
- Additional small tasks
- No Grey Zone warning
- Tomorrow's ONE THING
- A blunt accountability note for Nathan

Rules:
- Prioritise revenue, product uploads, ads, mockups, customer/order issues, website improvements, and bottlenecks.
- Do not overload the day.
- Pick only 3 true priority tasks.
- Small tasks must support the priority tasks.
- If yesterday's same task was avoided, call it out.
- If something is a distraction, say so.
- Keep Nathan moving toward the 12 Week Year and $5M target.

SPORTS CAVE OS DATA

Today's sheet:
{_sheet_summary(today_sheet)}

Incomplete tasks:
{incomplete_text}

Yesterday's sheet:
{_sheet_summary(yesterday_sheet)}

Last 7 days:
{week_summary}

Activity Log:
{_activity_summary(activity_entries)}

Open Home dashboard tasks:
{_tasks_summary(open_tasks)}

Upcoming sports and sales calendar:
{calendar_summary}
"""


def _json_dict(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def humanise_event_type(value):
    text = str(value or "activity").replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else "Activity"


def clean_activity_source(value):
    source = str(value or "").replace("_", " ").strip()
    if not source:
        return "Sports Cave"
    known = {
        "ads": "Ads",
        "dashboard": "Dashboard",
        "edition ops": "Edition Ops",
        "sports cave os": "Sports Cave",
        "manual app": "Edition Ops",
        "orders": "Orders",
        "prodigi": "Prodigi",
        "social media reels studio": "Social Media Reels Studio",
        "supabase ledger": "Orders",
        "sports cave os manual override": "Edition Ops",
    }
    return known.get(source.casefold(), source[:1].upper() + source[1:])


_TECHNICAL_ACTIVITY_TERMS = (
    "metafield",
    "sync",
    "allocation",
    "schema",
    "api",
    "database",
    "supabase",
    "audit",
    "webhook",
    "payload",
    "mirror",
    "backend",
)

_HOME_SYSTEM_ACTIVITY_EVENT_TYPES = {
    "edition_order_auto_allocation",
    "edition_order_purchase_snapshot_allocation",
    "shopify_order_details_backfill",
    "shopify_product_metafield_mirror",
}

_HOME_SYSTEM_ACTIVITY_SOURCES = {
    "shopify_backfill",
    "supabase_ledger",
    "webhook",
}

_HOME_SYSTEM_ACTIVITY_ACTORS = {
    "sports_cave_os_sync",
}

_HOME_SYSTEM_ACTIVITY_PHRASES = (
    "auto allocation",
    "automatic fulfilment",
    "automatic fulfillment",
    "backend fulfilment",
    "backend fulfillment",
    "edition order auto allocation",
    "metafield mirror",
    "metafield updated",
    "purchase-time shopify edition snapshot",
    "shopify product metafield mirror",
    "shopify product metafield updated",
    "webhook",
)

_ACTIVITY_LABELS = {
    "ad_prompt_generated": "Ad prompt made",
    "certificate_generated": "Certificate generated",
    "certificate_generation_failed": "Certificate failed",
    "certificate_uploaded": "Certificate generated",
    "certificate_upload_failed": "Certificate failed",
    "dashboard_task_added": "Task added",
    "dashboard_task_completed": "Task completed",
    "daily_execution_completed": "Daily Review completed",
    "daily_execution_created": "Daily sheet created",
    "daily_execution_tomorrow_planned": "Tomorrow planned",
    "daily_execution_archived": "Daily sheet archived",
    "daily_execution_mip_completed": "Daily task completed",
    "daily_execution_task_completed": "Daily task completed",
    "design_prompt_saved": "Design prompt saved",
    "edition_product_updated": "Edition updated",
    "edition_updated": "Edition updated",
    "mockup_exported": "Mockup pack exported",
    "mockup_generated": "Mockup made",
    "mockup_made": "Mockup made",
    "mockup_uploaded": "Mockup uploaded",
    "mockup_pack_exported": "Mockup pack exported",
    "mockup_zip_exported": "Mockup pack exported",
    "order_fulfilled": "Order fulfilled",
    "order_fulfilled_certificate_generated": "Order fulfilled",
    "password_changed": "Password changed",
    "password_change_failed": "Password change failed",
    "product_edition_updated": "Edition updated",
    "product_uploaded": "Product uploaded",
    "profile_updated": "Profile updated",
    "prompt_pack_exported": "Mockup pack exported",
    "reel_prompt_saved": "Reel saved",
    "reel_saved": "Reel saved",
    "reel_video_uploaded": "Reel saved",
    "task_added": "Task added",
    "task_completed": "Task completed",
}

_RECOGNISED_ACTIVITY_PREFIXES = tuple(dict.fromkeys(_ACTIVITY_LABELS.values())) + (
    "Order updated",
)


def _compact_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def _metadata_text(metadata, *keys):
    metadata = metadata or {}
    for key in keys:
        value = metadata.get(key)
        if value not in (None, ""):
            return _compact_text(value)
    return ""


def _text_after_prefix(message, prefixes):
    lower_message = str(message or "").casefold()
    for prefix in prefixes:
        lower_prefix = prefix.casefold()
        if lower_message.startswith(lower_prefix):
            return _compact_text(str(message)[len(prefix) :].strip(" :-"))
    if ":" in str(message or ""):
        return _compact_text(str(message).split(":", 1)[1])
    return ""


def _format_order_ref(value):
    text = _compact_text(value)
    if not text:
        return ""
    if text.casefold().startswith("order "):
        text = text[6:].strip()
    if text and not text.startswith("#"):
        text = f"#{text}"
    return text


def _order_ref_from_activity(message, metadata):
    direct = _metadata_text(
        metadata,
        "order",
        "order_name",
        "shopify_order_name",
        "shopify_order_number",
        "order_number",
    )
    if direct:
        return _format_order_ref(direct)
    match = re.search(r"(#[A-Z]{0,8}\d[\w-]*|\bSC\d[\w-]*\b|\b\d{3,}\b)", str(message or ""), re.IGNORECASE)
    if match:
        return _format_order_ref(match.group(1))
    return ""


def _product_label_from_activity(message, metadata):
    label = _metadata_text(
        metadata,
        "product",
        "product_title",
        "product_name",
        "title",
        "prompt_name",
        "handle",
        "shopify_handle",
        "filename",
    )
    if label:
        return label
    return _text_after_prefix(
        message,
        (
            "Generated ad prompt",
            "Saved design prompt",
            "Saved reel prompt",
            "Uploaded reel video",
            "Generated mockup",
            "Created mockup",
            "Exported mockup pack",
            "Updated edition settings",
            "Generated certificate",
            "Uploaded certificate",
        ),
    )


def _task_label_from_activity(message, metadata):
    return _metadata_text(metadata, "title", "task", "task_title") or _text_after_prefix(
        message,
        ("Added task", "Task added", "Completed task", "Task completed"),
    )


def _message_has_technical_terms(message):
    lowered = str(message or "").casefold()
    return any(term in lowered for term in _TECHNICAL_ACTIVITY_TERMS)


def home_activity_row_is_visible(row):
    row = dict(row or {})
    payload = _json_dict(row.get("new_value"))
    metadata = _json_dict(row.get("activity_metadata") or payload.get("metadata"))
    action_type = _compact_text(
        row.get("activity_action_type") or payload.get("action_type") or row.get("event_type")
    ).casefold()
    source = _compact_text(row.get("source") or payload.get("source")).casefold()
    actor = _compact_text(row.get("actor") or payload.get("actor")).casefold()
    message = _compact_text(row.get("activity_message") or payload.get("message") or row.get("reason"))
    page = _compact_text(row.get("activity_page") or payload.get("page")).casefold()

    actor_type = _compact_text(metadata.get("actor_type") or payload.get("actor_type")).casefold()
    if metadata.get("is_system") is True or payload.get("is_system") is True:
        return False
    if actor_type in {"system", "webhook", "background", "automatic"}:
        return False
    if action_type in _HOME_SYSTEM_ACTIVITY_EVENT_TYPES:
        return False
    if "webhook" in action_type or "metafield_mirror" in action_type:
        return False
    if "auto_allocation" in action_type and "manual" not in action_type:
        return False
    if source in _HOME_SYSTEM_ACTIVITY_SOURCES or actor in _HOME_SYSTEM_ACTIVITY_ACTORS:
        return False

    combined = " ".join(part for part in (action_type, source, actor, page, message.casefold()) if part)
    return not any(phrase in combined for phrase in _HOME_SYSTEM_ACTIVITY_PHRASES)


def clean_activity_message(action_type, message, *, metadata=None, entity_type="", entity_id=""):
    metadata = metadata or {}
    action = str(action_type or "").strip().casefold()
    clean_message = _compact_text(message)
    product_label = _product_label_from_activity(clean_message, metadata)
    order_ref = _order_ref_from_activity(clean_message, metadata)

    if action == "order_fulfilled_certificate_generated" or "fulfilled + certificate generated" in clean_message.casefold():
        return f"Order {order_ref} fulfilled + certificate generated" if order_ref else "Order fulfilled + certificate generated"
    if action in {"task_added", "dashboard_task_added"}:
        task_label = _task_label_from_activity(clean_message, metadata)
        return f"Task added: {task_label}" if task_label else "Task added"
    if action in {"task_completed", "dashboard_task_completed"}:
        task_label = _task_label_from_activity(clean_message, metadata)
        return f"Task completed: {task_label}" if task_label else "Task completed"
    if action in {"certificate_generated", "certificate_uploaded"}:
        if order_ref:
            return f"Certificate generated for Order {order_ref}"
        if product_label:
            return f"Certificate generated: {product_label}"
        return "Certificate generated"
    if action == "order_fulfilled":
        return f"Order {order_ref} fulfilled" if order_ref else "Order fulfilled"
    if action in {"product_edition_updated", "edition_product_updated", "edition_updated"} or (
        "edition ops shopify" in clean_message.casefold() or "metafield" in clean_message.casefold()
    ):
        return f"Edition updated: {product_label}" if product_label and not _message_has_technical_terms(product_label) else "Edition updated"
    if action in {"mockup_generated", "mockup_made"}:
        return f"Mockup made: {product_label}" if product_label else "Mockup made"
    if action in {"mockup_zip_exported", "mockup_pack_exported", "prompt_pack_exported", "mockup_exported"}:
        return f"Mockup pack exported: {product_label}" if product_label else "Mockup pack exported"
    if action == "product_uploaded":
        return f"Product uploaded: {product_label}" if product_label else "Product uploaded"
    if action == "ad_prompt_generated":
        return f"Ad prompt made: {product_label}" if product_label else "Ad prompt made"
    if action == "design_prompt_saved":
        return f"Design prompt saved: {product_label}" if product_label else "Design prompt saved"
    if action in {"reel_prompt_saved", "reel_video_uploaded", "reel_saved"}:
        return f"Reel saved: {product_label}" if product_label else "Reel saved"
    if "auto allocation" in clean_message.casefold():
        return f"Order updated: {order_ref}" if order_ref else "Order updated"
    if not clean_message or _message_has_technical_terms(clean_message):
        return humanise_event_type(action)
    return clean_message


def activity_from_audit_row(row):
    row = dict(row or {})
    payload = _json_dict(row.get("new_value"))
    metadata = _json_dict(row.get("activity_metadata") or payload.get("metadata"))
    message = (
        str(row.get("activity_message") or "").strip()
        or str(payload.get("message") or "").strip()
        or str(row.get("reason") or "").strip()
        or humanise_event_type(row.get("event_type"))
    )
    page = (
        str(row.get("activity_page") or "").strip()
        or str(payload.get("page") or "").strip()
        or clean_activity_source(row.get("source"))
    )
    action_type = (
        str(row.get("activity_action_type") or "").strip()
        or str(payload.get("action_type") or row.get("event_type") or "").strip()
    )
    message = clean_activity_message(
        action_type,
        message,
        metadata=metadata,
        entity_type=row.get("entity_type") or "",
        entity_id=row.get("entity_id") or "",
    )
    return {
        "id": str(row.get("id") or ""),
        "action_type": action_type,
        "message": message,
        "page": page,
        "source": page,
        "created_at": row.get("created_at"),
        "entity_type": row.get("entity_type") or "",
        "entity_id": row.get("entity_id") or "",
        "actor": row.get("actor")
        or metadata.get("actor_display")
        or metadata.get("actor_name")
        or metadata.get("display_name")
        or metadata.get("email")
        or metadata.get("username")
        or "",
        "metadata": metadata,
    }


def split_activity_message(entry):
    entry = dict(entry or {})
    message = str(entry.get("message") or "").strip()
    action_type = str(entry.get("action_type") or "").strip().casefold()
    activity = _ACTIVITY_LABELS.get(action_type)

    for prefix in _RECOGNISED_ACTIVITY_PREFIXES:
        separator = f"{prefix}:"
        if message.casefold().startswith(separator.casefold()):
            return prefix, message[len(separator) :].lstrip()

    if activity:
        return activity, message
    return humanise_event_type(action_type) if action_type else "Activity", message


def _activity_product_slug(value):
    text = _compact_text(value).casefold()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text


def _mockup_product_label(entry, run_products=None):
    entry = dict(entry or {})
    metadata = entry.get("metadata") or {}
    label = _metadata_text(
        metadata,
        "product_handle",
        "shopify_handle",
        "handle",
        "product_slug",
        "product_name",
        "product_title",
        "product",
    )
    entity_id = _compact_text(entry.get("entity_id"))
    if not label and entity_id and run_products:
        label = _compact_text(run_products.get(entity_id))
    return label


def _mockup_item_label(entry):
    entry = dict(entry or {})
    metadata = entry.get("metadata") or {}
    label = _metadata_text(metadata, "mockup_name", "prompt_label", "scene_name")
    message = _compact_text(entry.get("message"))
    if not label:
        label = _text_after_prefix(
            message,
            (
                "Added mockup",
                "Uploaded mockup",
                "Mockup uploaded",
                "Created mockup",
                "Mockup made",
            ),
        )
    if not label:
        prompt_name = _metadata_text(metadata, "prompt", "prompt_name")
        if prompt_name:
            stem = re.sub(r"-prompt$", "", Path(prompt_name).stem, flags=re.IGNORECASE)
            number_match = re.match(r"^(\d+)[-_ ]+(.*)$", stem)
            if number_match:
                label = f"{number_match.group(1)} - {number_match.group(2).replace('-', ' ').title()}"
            else:
                label = stem.replace("-", " ").title()
    return label or message or "Mockup"


def _mockup_group_sort_key(label):
    match = re.match(r"^\s*(\d+)", str(label or ""))
    return (int(match.group(1)) if match else 10_000, str(label or "").casefold())


def group_mockup_activity_entries(entries, tzinfo=timezone.utc):
    """Group noisy per-image mockup rows without changing stored audit data."""
    source_entries = [dict(entry or {}) for entry in entries or []]
    run_products = {}
    for entry in source_entries:
        if clean_activity_source(entry.get("page") or entry.get("source")).casefold() != "mockups":
            continue
        product_label = _mockup_product_label(entry)
        entity_id = _compact_text(entry.get("entity_id"))
        if entity_id and product_label:
            run_products.setdefault(entity_id, product_label)

    grouped = []
    normal = []
    for entry in source_entries:
        action_type = _compact_text(entry.get("action_type")).casefold()
        area = clean_activity_source(entry.get("page") or entry.get("source"))
        if area.casefold() != "mockups" or action_type not in MOCKUP_ACTIVITY_GROUP_ACTIONS:
            normal.append(entry)
            continue

        created_at = _as_aware_datetime(entry.get("created_at"), timezone.utc)
        local_created_at = created_at.astimezone(tzinfo or timezone.utc) if created_at else None
        local_date = local_created_at.date().isoformat() if local_created_at else ""
        actor = _compact_text(entry.get("actor") or (entry.get("metadata") or {}).get("email"))
        entity_id = _compact_text(entry.get("entity_id"))
        product_label = _mockup_product_label(entry, run_products)
        product_slug = _activity_product_slug(product_label)

        match = None
        for candidate in grouped:
            if candidate["local_date"] != local_date or candidate["actor_key"] != actor.casefold():
                continue
            if candidate["product_slug"] != product_slug:
                continue
            same_run = bool(entity_id and candidate["entity_id"] == entity_id)
            close_in_time = bool(
                created_at
                and candidate["oldest_at"]
                and abs(candidate["oldest_at"] - created_at) <= MOCKUP_ACTIVITY_GROUP_WINDOW
            )
            if same_run or (not entity_id and not candidate["entity_id"] and close_in_time):
                match = candidate
                break

        if match is None:
            match = {
                "actor": actor,
                "actor_key": actor.casefold(),
                "created_at": entry.get("created_at"),
                "latest_at": created_at,
                "oldest_at": created_at,
                "entity_id": entity_id,
                "local_date": local_date,
                "product_label": product_label,
                "product_slug": product_slug,
                "entries": [],
            }
            grouped.append(match)
        elif created_at:
            if match["latest_at"] is None or created_at > match["latest_at"]:
                match["latest_at"] = created_at
                match["created_at"] = entry.get("created_at")
            if match["oldest_at"] is None or created_at < match["oldest_at"]:
                match["oldest_at"] = created_at
        match["entries"].append(entry)

    summaries = []
    for index, group in enumerate(grouped):
        item_labels = sorted(
            (_mockup_item_label(entry) for entry in group["entries"]),
            key=_mockup_group_sort_key,
        )
        count = len(item_labels)
        product_text = group["product_slug"]
        group_actions = {
            _compact_text(entry.get("action_type")).casefold()
            for entry in group["entries"]
        }
        action_word = "uploaded" if group_actions == {"mockup_uploaded"} else "made"
        count_text = (
            f"{count} mockup {action_word}"
            if count == 1
            else f"{count} mockups {action_word}"
        )
        details = f"{product_text} — {count_text}" if product_text else count_text
        summaries.append(
            {
                "id": f"mockup-group-{index}-{group['entity_id'] or group['local_date']}",
                "action_type": "mockup_activity_group",
                "message": f"Product mockups done: {details}",
                "page": "Mockups",
                "source": "Mockups",
                "created_at": group["created_at"],
                "entity_type": "mockup_run",
                "entity_id": group["entity_id"],
                "actor": group["actor"],
                "metadata": {
                    "mockup_count": count,
                    "product_handle": product_text,
                },
                "is_mockup_group": True,
                "mockup_items": item_labels,
            }
        )

    combined = normal + summaries
    combined.sort(
        key=lambda entry: _as_aware_datetime(entry.get("created_at"), timezone.utc)
        or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return combined


def activity_table_record(entry, tzinfo=timezone.utc):
    if entry.get("is_mockup_group"):
        activity = "Product mockups done"
        details = _text_after_prefix(entry.get("message"), ("Product mockups done",))
    else:
        activity, details = split_activity_message(entry)
    created_at = _as_aware_datetime(entry.get("created_at"), timezone.utc)
    if created_at is not None:
        local_created_at = created_at.astimezone(tzinfo or timezone.utc)
        date_text = local_created_at.strftime("%d %b %Y").lstrip("0")
        time_text = local_created_at.strftime("%d %b %Y %I:%M %p %Z").lstrip("0")
    else:
        date_text = ""
        time_text = ""
    metadata = entry.get("metadata") or {}
    item = _metadata_text(
        metadata,
        "item",
        "product",
        "product_title",
        "product_name",
        "order",
        "folder",
        "filename",
    )
    status = _metadata_text(metadata, "result", "status", "certificate_status")
    return {
        "Date": date_text,
        "Time": time_text,
        "Action": activity,
        "Activity": activity,
        "Details": details,
        "User": _compact_text(entry.get("actor") or (entry.get("metadata") or {}).get("email") or ""),
        "Page/Area": clean_activity_source(entry.get("page") or entry.get("source")),
        "Area": clean_activity_source(entry.get("page") or entry.get("source")),
        "Item or Product": item,
        "Result/Status": status,
        "Sort Timestamp": created_at or datetime.min.replace(tzinfo=timezone.utc),
    }


def _as_aware_datetime(value, fallback_tz=timezone.utc):
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=fallback_tz)
    return parsed


def activity_log_bounds(view, local_now, *, month_start=None):
    view = view if view in ACTIVITY_VIEWS else ACTIVITY_VIEW_TODAY
    if view == ACTIVITY_VIEW_ALL_TIME:
        return None, None

    local_now = local_now or datetime.now(timezone.utc)
    tzinfo = local_now.tzinfo or timezone.utc
    today = local_now.date()
    if view == ACTIVITY_VIEW_LAST_7_DAYS:
        start_day = today - timedelta(days=6)
        start = datetime.combine(start_day, time.min, tzinfo)
        end = datetime.combine(today + timedelta(days=1), time.min, tzinfo)
        return start, end
    if view == ACTIVITY_VIEW_MONTH:
        if isinstance(month_start, datetime):
            month_day = month_start.date()
        elif isinstance(month_start, date):
            month_day = month_start
        else:
            month_day = today.replace(day=1)
        start = datetime.combine(month_day.replace(day=1), time.min, tzinfo)
        if start.month == 12:
            next_month = date(start.year + 1, 1, 1)
        else:
            next_month = date(start.year, start.month + 1, 1)
        end = datetime.combine(next_month, time.min, tzinfo)
        return start, end

    start = datetime.combine(today, time.min, tzinfo)
    end = datetime.combine(today + timedelta(days=1), time.min, tzinfo)
    return start, end


def filter_activity_entries(entries, view, local_now, *, month_start=None):
    start, end = activity_log_bounds(view, local_now, month_start=month_start)
    if start is None and end is None:
        return list(entries or [])
    filtered = []
    for entry in entries or []:
        created_at = _as_aware_datetime(entry.get("created_at"), start.tzinfo if start else timezone.utc)
        if created_at is None:
            continue
        if start and created_at < start:
            continue
        if end and created_at >= end:
            continue
        filtered.append(entry)
    return filtered


def activity_limit_for_view(view, limit=None):
    view = view if view in ACTIVITY_VIEWS else ACTIVITY_VIEW_TODAY
    view_limit = ACTIVITY_VIEW_LIMITS.get(view, ACTIVITY_LOG_LIMIT)
    if limit is None:
        return view_limit
    try:
        requested = max(int(limit), 1)
    except (TypeError, ValueError):
        return view_limit
    return min(requested, int(view_limit or requested))


def activity_log_access_scope(user):
    if not os_accounts.can_view_activity_log(user):
        return None
    if os_accounts.is_reporting_owner(user):
        return {"all_users": True, "actor_user_id": "", "actor_email": ""}
    actor_user_id = str((user or {}).get("id") or "").strip()
    actor_email = os_accounts.normalise_login((user or {}).get("email"))
    if not actor_user_id and not actor_email:
        return None
    return {
        "all_users": False,
        "actor_user_id": actor_user_id,
        "actor_email": actor_email,
    }


def list_activity_entries(
    view=ACTIVITY_VIEW_TODAY,
    local_now=None,
    *,
    month_start=None,
    limit=None,
    user=None,
):
    access_scope = activity_log_access_scope(user)
    if access_scope is None:
        raise DashboardStorageError("Activity Log access is not available for this account.")
    local_now = local_now or datetime.now(timezone.utc)
    start, end = activity_log_bounds(view, local_now, month_start=month_start)
    safe_limit = activity_limit_for_view(view, limit)
    cache_key = (
        "activity",
        view if view in ACTIVITY_VIEWS else ACTIVITY_VIEW_TODAY,
        start.isoformat() if start else "",
        end.isoformat() if end else "",
        safe_limit or "all",
        "all" if access_scope["all_users"] else access_scope["actor_user_id"],
        "" if access_scope["all_users"] else access_scope["actor_email"],
    )
    cached = _cache_get(_ACTIVITY_CACHE, cache_key)
    if cached is not None:
        return cached
    try:
        backend = get_supabase_backend()
        rows = backend.list_activity_logs(
            start_at=start,
            end_at=end,
            limit=safe_limit,
            actor_user_id=None if access_scope["all_users"] else access_scope["actor_user_id"],
            actor_email=None if access_scope["all_users"] else access_scope["actor_email"],
        )
        entries = [activity_from_audit_row(row) for row in rows if home_activity_row_is_visible(row)]
        return _cache_set(_ACTIVITY_CACHE, cache_key, entries, ACTIVITY_CACHE_TTL_SECONDS)
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def activity_filter_options(records, field):
    values = sorted(
        {
            _compact_text(record.get(field))
            for record in records or []
            if _compact_text(record.get(field))
        },
        key=str.casefold,
    )
    return ("All", *values)


def filter_activity_records(
    records,
    *,
    user="All",
    action="All",
    area="All",
    status="All",
    search="",
):
    query = str(search or "").strip().casefold()
    filtered = []
    for record in records or []:
        if user != "All" and record.get("User") != user:
            continue
        if action != "All" and record.get("Action") != action:
            continue
        if area != "All" and record.get("Page/Area") != area:
            continue
        if status != "All" and record.get("Result/Status") != status:
            continue
        if query:
            haystack = " ".join(
                str(record.get(key) or "")
                for key in ("Action", "Item or Product", "Details", "User", "Page/Area", "Result/Status")
            ).casefold()
            if query not in haystack:
                continue
        filtered.append(dict(record))
    return filtered


def sort_activity_records(records, sort_order=ACTIVITY_SORT_NEWEST):
    rows = [dict(record) for record in records or []]
    sort_order = sort_order if sort_order in ACTIVITY_SORT_OPTIONS else ACTIVITY_SORT_NEWEST
    if sort_order == ACTIVITY_SORT_OLDEST:
        return sorted(rows, key=lambda row: row.get("Sort Timestamp") or datetime.min.replace(tzinfo=timezone.utc))
    if sort_order == ACTIVITY_SORT_ACTION_ASC:
        return sorted(rows, key=lambda row: str(row.get("Action") or "").casefold())
    if sort_order == ACTIVITY_SORT_ACTION_DESC:
        return sorted(rows, key=lambda row: str(row.get("Action") or "").casefold(), reverse=True)
    if sort_order == ACTIVITY_SORT_USER_ASC:
        return sorted(rows, key=lambda row: str(row.get("User") or "").casefold())
    if sort_order == ACTIVITY_SORT_USER_DESC:
        return sorted(rows, key=lambda row: str(row.get("User") or "").casefold(), reverse=True)
    if sort_order == ACTIVITY_SORT_AREA_ASC:
        return sorted(rows, key=lambda row: str(row.get("Page/Area") or "").casefold())
    return sorted(
        rows,
        key=lambda row: row.get("Sort Timestamp") or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )


def load_dashboard_state(
    activity_view=ACTIVITY_VIEW_TODAY,
    local_now=None,
    *,
    month_start=None,
    include_activity=True,
    include_tasks=True,
    user=None,
):
    state = {"tasks": [], "activity_log": [], "task_error": "", "activity_error": ""}
    if include_tasks:
        try:
            state["tasks"] = list_tasks(status="open")
        except DashboardStorageError as error:
            state["task_error"] = str(error)
    if not include_activity:
        return state
    try:
        state["activity_log"] = list_activity_entries(
            activity_view,
            local_now or datetime.now(timezone.utc),
            month_start=month_start,
            user=user,
        )
    except DashboardStorageError as error:
        state["activity_error"] = str(error)
    return state


def list_existing_edition_products(limit=1000):
    try:
        safe_limit = max(min(int(limit or 1000), 1500), 1)
    except (TypeError, ValueError):
        safe_limit = 1000
    cache_key = ("edition_products", safe_limit)
    cached = _cache_get(_EDITION_PRODUCT_CACHE, cache_key)
    if cached is not None:
        return cached
    try:
        backend = get_supabase_backend()
        if not hasattr(backend, "list_dashboard_edition_products"):
            raise DashboardStorageError("Product list is unavailable right now.")
        products = backend.list_dashboard_edition_products(limit=safe_limit)
        normalised = []
        for product in products or []:
            title = _compact_text(product.get("title") or product.get("product_title") or "")
            handle = _compact_text(product.get("handle") or product.get("shopify_handle") or "")
            if not title and not handle:
                continue
            normalised.append(
                {
                    "title": title or handle,
                    "handle": handle,
                    "category": _compact_text(product.get("category") or product.get("sport") or product.get("product_type") or ""),
                    "status": _compact_text(product.get("status") or ""),
                }
            )
        return _cache_set(_EDITION_PRODUCT_CACHE, cache_key, normalised, EDITION_PRODUCT_CACHE_TTL_SECONDS)
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def greeting_for_datetime(local_dt):
    hour = int(local_dt.hour)
    if 5 <= hour < 12:
        return "Good morning :)"
    if 12 <= hour < 17:
        return "Good afternoon :)"
    return "Good night :)"


def greeting_for_account(local_dt, user):
    base = greeting_for_datetime(local_dt).replace(" :)", "").strip()
    name = _compact_text(
        (user or {}).get("display_name")
        or (user or {}).get("email")
        or (user or {}).get("username")
    )
    return f"{base}, {name} :)" if name else base


def load_calendar_events(path=SPORTING_CALENDAR_PATH):
    path = Path(path)
    try:
        cache_key = (str(path), path.stat().st_mtime)
    except OSError:
        cache_key = (str(path), None)
    cached = _cache_get(_CALENDAR_CACHE, cache_key)
    if cached is not None:
        return cached
    data = _read_json(path, {"events": []})
    events = data.get("events") if isinstance(data.get("events"), list) else []
    return _cache_set(_CALENDAR_CACHE, cache_key, events, CALENDAR_CACHE_TTL_SECONDS)


def parse_event_date(value):
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def event_status(event, today):
    dates = sports_sales_calendar.confirmed_event_dates(event)
    if not dates:
        return "tbc"
    start, end = dates
    if start <= today <= end:
        return "active"
    if today < start:
        return "upcoming"
    return "past"


def days_until_event(event, today):
    dates = sports_sales_calendar.confirmed_event_dates(event)
    return (dates[0] - today).days if dates else None


def _event_matches_region(event, region):
    if not region or region == "All":
        return True
    return region in (event.get("regions") or [])


def _event_matches_sport(event, sport):
    return not sport or sport == "All" or event.get("sport") == sport


def filter_calendar_events(
    events,
    today,
    *,
    region="All",
    sport="All",
    status="Active/upcoming",
    upcoming_days=DEFAULT_UPCOMING_DAYS,
):
    filtered = []
    for event in events:
        if not _event_matches_region(event, region):
            continue
        if not _event_matches_sport(event, sport):
            continue
        current_status = event_status(event, today)
        days_until = days_until_event(event, today)
        if current_status == "tbc" or days_until is None:
            if status != "All":
                continue
            filtered.append(event)
            continue
        if status == "Active" and current_status != "active":
            continue
        if status == "Upcoming" and not (current_status == "upcoming" and days_until <= upcoming_days):
            continue
        if status == "Active/upcoming" and not (
            current_status == "active"
            or (current_status == "upcoming" and days_until <= upcoming_days)
        ):
            continue
        filtered.append(event)

    return sorted(
        filtered,
        key=lambda event: (
            event_status(event, today) == "tbc",
            event_status(event, today) != "active",
            abs(days_until_event(event, today) or 0),
            -int(event.get("importance") or 0),
            event.get("title") or "",
        ),
    )


def build_active_alerts(
    events,
    today,
    *,
    limit=4,
    upcoming_days=DEFAULT_UPCOMING_DAYS,
):
    active_items = []
    upcoming_items = []
    for event in events:
        importance = int(event.get("importance") or 0)
        if importance < 3:
            continue
        status = event_status(event, today)
        days_until = days_until_event(event, today)
        if status == "tbc" or days_until is None:
            continue
        if status == "active":
            score = 1000 + (importance * 20)
            active_items.append((score, event))
        elif status == "upcoming" and days_until <= upcoming_days:
            score = 700 + (importance * 20) - days_until
            upcoming_items.append((score, event))
        else:
            continue

    active_items.sort(key=lambda item: (-item[0], item[1].get("title") or ""))
    upcoming_items.sort(key=lambda item: (-item[0], item[1].get("title") or ""))

    alerts = []
    seen = set()

    def add_event(event):
        label = (event.get("alert_label") or event.get("title") or "").strip()
        if not label or label in seen or len(alerts) >= limit:
            return False
        seen.add(label)
        alerts.append({"label": label, "event": event, "status": event_status(event, today)})
        return True

    for _, event in active_items[:limit]:
        add_event(event)

    if upcoming_items and not any(alert["status"] == "upcoming" for alert in alerts):
        _, upcoming_event = upcoming_items[0]
        if len(alerts) >= limit:
            remove_index = len(alerts) - 1
            upcoming_sport = upcoming_event.get("sport")
            for index, alert in enumerate(alerts):
                event = alert.get("event") or {}
                if event.get("sport") == upcoming_sport and event.get("type") == "Season":
                    remove_index = index
                    break
            removed = alerts.pop(remove_index)
            seen.discard(removed["label"])
        add_event(upcoming_event)

    for _, event in upcoming_items:
        if len(alerts) >= limit:
            break
        add_event(event)

    return alerts


def build_home_event_rows(events, today, *, limit=8):
    """Return a compact, balanced live/upcoming list from confirmed calendar dates."""
    today = today if isinstance(today, date) else date.fromisoformat(str(today))
    candidates = []
    for event in events or []:
        dates = sports_sales_calendar.confirmed_event_dates(event)
        if not dates or dates[1] < today or int(event.get("importance") or 0) < 3:
            continue
        start, end = dates
        status = "Live" if start <= today <= end else "Coming soon"
        candidates.append(
            {
                "event": dict(event),
                "event_id": _compact_text(event.get("id") or event.get("title") or ""),
                "name": _compact_text(event.get("title") or event.get("alert_label") or "Event"),
                "category": "Sale" if sports_sales_calendar.event_kind(event) == "sale" else _compact_text(event.get("sport") or "Sport"),
                "type": _compact_text(event.get("type") or ("Sale" if sports_sales_calendar.event_kind(event) == "sale" else "Sport")),
                "status": status,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "date_label": format_event_date_range(event),
                "days_remaining": (end - today).days if status == "Live" else (start - today).days,
                "importance": int(event.get("importance") or 0),
                "market": ", ".join(sports_sales_calendar.market_codes(event)),
            }
        )

    def base_key(row):
        anchor = date.fromisoformat(row["end_date"] if row["status"] == "Live" else row["start_date"])
        return (anchor, -row["importance"], row["name"].casefold())

    def select_balanced(rows, count):
        ordered = sorted(rows, key=base_key)
        selected = []
        seen_ids = set()
        seen_categories = set()

        def add(row):
            if row["event_id"] in seen_ids or len(selected) >= count:
                return
            seen_ids.add(row["event_id"])
            seen_categories.add(row["category"])
            selected.append(row)

        sale = next((row for row in ordered if row["category"] == "Sale"), None)
        sport = next((row for row in ordered if row["category"] != "Sale"), None)
        if sale:
            add(sale)
        if sport:
            add(sport)
        for row in ordered:
            if row["category"] not in seen_categories:
                add(row)
        for row in ordered:
            add(row)
        return selected

    safe_limit = max(0, min(int(limit or 8), 8))
    live = [row for row in candidates if row["status"] == "Live"]
    upcoming = [row for row in candidates if row["status"] == "Coming soon"]
    live_limit = min(len(live), min(4, safe_limit)) if upcoming else safe_limit
    selected = select_balanced(live, live_limit)
    selected.extend(select_balanced(upcoming, safe_limit - len(selected)))
    if len(selected) < safe_limit:
        chosen = {row["event_id"] for row in selected}
        remaining = [row for row in candidates if row["event_id"] not in chosen]
        remaining.sort(key=lambda row: (row["status"] != "Live", base_key(row)))
        selected.extend(remaining[: safe_limit - len(selected)])
    return sorted(
        selected[:safe_limit],
        key=lambda row: (
            row["status"] != "Live",
            date.fromisoformat(row["end_date"] if row["status"] == "Live" else row["start_date"]),
            -row["importance"],
            row["name"].casefold(),
        ),
    )


def _weekly_work_timestamp(value, fallback):
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            parsed = fallback
    else:
        parsed = fallback
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _weekly_work_account(activity, users):
    actor_id = str(activity.get("actor_id") or "")
    if actor_id:
        match = next((user for user in users if str(user.get("id") or "") == actor_id), None)
        if match:
            return match
    actor = os_accounts.normalise_login(activity.get("actor") or activity.get("actor_email"))
    matches = [
        user
        for user in users
        if actor
        and actor
        in {
            os_accounts.normalise_login(user.get("username")),
            os_accounts.normalise_login(user.get("email")),
            os_accounts.normalise_login(user.get("display_name")),
        }
    ]
    return matches[0] if len(matches) == 1 else None


def build_home_weekly_work_snapshot(user, local_now=None):
    """Build role-scoped weekly KPIs and tables from one backend work bundle."""
    if not os_accounts.account_is_active(user):
        raise DashboardStorageError("This Week's Work is not available for this account.")
    sydney_now = local_now or datetime.now(timezone.utc).astimezone(
        sports_sales_calendar.SYDNEY_TIMEZONE
    )
    if sydney_now.tzinfo is None:
        sydney_now = sydney_now.replace(tzinfo=sports_sales_calendar.SYDNEY_TIMEZONE)
    else:
        sydney_now = sydney_now.astimezone(sports_sales_calendar.SYDNEY_TIMEZONE)
    week_start = sydney_now.date() - timedelta(days=sydney_now.date().weekday())
    week_end = week_start + timedelta(days=6)
    start_local = datetime.combine(week_start, time.min, tzinfo=sports_sales_calendar.SYDNEY_TIMEZONE)
    try:
        backend = get_supabase_backend()
        bundle = backend.load_home_weekly_work_bundle(
            daily_execution_user_id(user),
            week_start,
            week_end,
            start_local.astimezone(timezone.utc),
            sydney_now.astimezone(timezone.utc),
            include_team=os_accounts.is_admin(user),
        )
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error

    users = [dict(row or {}) for row in bundle.get("users") or []]
    if not os_accounts.is_admin(user):
        users = [row for row in users if str(row.get("id") or "") == daily_execution_user_id(user)]
    user_ids = {str(row.get("id") or "") for row in users}
    staff = {
        str(row.get("id") or ""): {
            "staff_id": str(row.get("id") or ""),
            "staff": _compact_text(row.get("display_name") or row.get("username") or "Staff member"),
            "role": _compact_text(row.get("role") or "worker").title(),
            "total_planned": 0,
            "completed_tasks": 0,
            "did_not_finish": 0,
            "skipped": 0,
            "unresolved": 0,
            "completion_percentage": 0.0,
            "allocated_seconds": 0,
            "actual_seconds": 0,
            "meaningful_actions": 0,
            "last_activity": None,
        }
        for row in users
    }
    timer_rows = [dict(timer or {}) for timer in bundle.get("timers") or []]
    completed_work = []
    task_instances = daily_execution_weekly_task_instances(
        [
            sheet
            for sheet in bundle.get("sheets") or []
            if str((sheet or {}).get("user_id") or "") in user_ids
        ],
        timer_rows,
        today=sydney_now.date(),
    )
    for task in task_instances:
        owner_id = str(task.get("owner_id") or "")
        if owner_id not in staff:
            continue
        fallback = datetime.combine(
            date.fromisoformat(task.get("work_date")),
            time(hour=12),
            tzinfo=sports_sales_calendar.SYDNEY_TIMEZONE,
        ).astimezone(timezone.utc)
        member = staff[owner_id]
        member["total_planned"] += 1
        member["allocated_seconds"] += max(int(task.get("allocated_seconds") or 0), 0)
        member["actual_seconds"] += max(int(task.get("actual_elapsed_seconds") or 0), 0)
        outcome = task.get("outcome") or "unresolved"
        if outcome == "completed":
            member["completed_tasks"] += 1
        elif outcome == "did_not_finish":
            member["did_not_finish"] += 1
        elif outcome == "skipped":
            member["skipped"] += 1
        else:
            member["unresolved"] += 1
            continue
        completed_at = _weekly_work_timestamp(task.get("completed_at"), fallback)
        if not (start_local.astimezone(timezone.utc) <= completed_at <= sydney_now.astimezone(timezone.utc)):
            continue
        member["last_activity"] = max(
            filter(None, (member["last_activity"], completed_at)), default=completed_at
        )
        completed_work.append(
            {
                "timestamp": completed_at,
                "staff": member["staff"],
                "staff_id": owner_id,
                "work": task.get("task") or "Daily Planner task",
                "area": "Daily Planner",
                "status": {
                    "completed": "Completed",
                    "did_not_finish": "Did not finish",
                    "skipped": "Skipped",
                }[outcome],
                "actual_seconds": max(int(task.get("actual_elapsed_seconds") or 0), 0),
                "row_id": f"planner:{task.get('instance_key')}",
            }
        )

    import daily_activity_reporting

    seen_activity = set()
    for raw in bundle.get("activities") or []:
        if not daily_activity_reporting.activity_is_meaningful_work(raw):
            continue
        try:
            activity = daily_activity_reporting.classify_activity(raw)
        except (TypeError, ValueError):
            continue
        if not activity or activity.get("action", "").startswith("daily_planner_task_"):
            continue
        account = _weekly_work_account(activity, users)
        if not account:
            continue
        owner_id = str(account.get("id") or "")
        if owner_id not in staff:
            continue
        payload = raw.get("new_value") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (TypeError, ValueError, json.JSONDecodeError):
                payload = {}
        metadata = payload.get("metadata") if isinstance(payload, dict) else {}
        if not isinstance(metadata, dict):
            metadata = {}
        dedupe_key = _compact_text(metadata.get("event_key") or "") or "|".join(
            (
                _compact_text(raw.get("event_type") or activity.get("action") or ""),
                _compact_text(raw.get("entity_type") or ""),
                _compact_text(raw.get("entity_id") or ""),
                _compact_text(activity.get("details") or "").casefold(),
            )
        )
        if dedupe_key in seen_activity:
            continue
        seen_activity.add(dedupe_key)
        timestamp = _weekly_work_timestamp(activity.get("created_at"), sydney_now.astimezone(timezone.utc))
        member = staff[owner_id]
        member["meaningful_actions"] += 1
        member["last_activity"] = max(
            filter(None, (member["last_activity"], timestamp)), default=timestamp
        )
        completed_work.append(
            {
                "timestamp": timestamp,
                "staff": member["staff"],
                "staff_id": owner_id,
                "work": _compact_text(activity.get("details") or activity.get("item") or activity.get("action") or "Work completed"),
                "area": _compact_text(activity.get("category") or activity.get("page") or "Sports Cave"),
                "status": "Completed" if activity.get("status") == "success" else str(activity.get("status") or "Completed").title(),
                "actual_seconds": 0,
                "row_id": f"activity:{dedupe_key}",
            }
        )

    team = sorted(staff.values(), key=lambda row: row["staff"].casefold())
    for member in team:
        member["completion_percentage"] = (
            member["completed_tasks"] / member["total_planned"] * 100
            if member["total_planned"]
            else 0.0
        )
    completed_work.sort(key=lambda row: row["timestamp"], reverse=True)
    total_planned = sum(row["total_planned"] for row in team)
    tasks_completed = sum(row["completed_tasks"] for row in team)
    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "covered_until": sydney_now.isoformat(),
        "is_team_view": os_accounts.is_admin(user),
        "metrics": {
            "tasks_completed": tasks_completed,
            "tasks_not_finished": sum(row["did_not_finish"] for row in team),
            "tasks_skipped": sum(row["skipped"] for row in team),
            "tasks_unresolved": sum(row["unresolved"] for row in team),
            "tasks_total": total_planned,
            "completion_percentage": tasks_completed / total_planned * 100 if total_planned else 0.0,
            "actual_seconds": sum(row["actual_seconds"] for row in team),
            "meaningful_actions": sum(row["meaningful_actions"] for row in team),
            "staff_active": sum(
                bool(row["total_planned"] or row["meaningful_actions"])
                for row in team
            ),
        },
        "team": team,
        "completed_work": completed_work,
        "query_count": int(bundle.get("query_count") or 1),
    }


def format_event_date_range(event):
    if sports_sales_calendar.event_is_tbc(event):
        return sports_sales_calendar.format_event_date(event)
    dates = sports_sales_calendar.confirmed_event_dates(event)
    if not dates:
        return "Date TBC"
    start, end = dates
    if start == end:
        return start.strftime("%d %b %Y")
    if start.year == end.year:
        if start.month == end.month:
            return f"{start.strftime('%d')} - {end.strftime('%d %b %Y')}"
        return f"{start.strftime('%d %b')} - {end.strftime('%d %b %Y')}"
    return f"{start.strftime('%d %b %Y')} - {end.strftime('%d %b %Y')}"


def build_new_design_ideas_prompt(
    sport,
    total_ideas,
    style_mix,
    *,
    exclude_existing=True,
    calendar_relevance=True,
):
    selected_sport = normalize_design_idea_sport(sport)
    if not selected_sport:
        raise ValueError("Select a supported sport or collection.")
    try:
        requested_total = int(total_ideas)
    except (TypeError, ValueError) as error:
        raise ValueError("Number of design ideas must be between 1 and 30.") from error
    if not 1 <= requested_total <= 30:
        raise ValueError("Number of design ideas must be between 1 and 30.")

    normalized_mix = normalize_design_idea_style_mix(style_mix)
    allocated_total = sum(normalized_mix.values())
    if allocated_total != requested_total:
        raise ValueError(
            f"Design style allocation must equal {requested_total}; currently allocated {allocated_total}."
        )
    style_lines = "\n".join(
        f"- {label} (CSV design_style: {slug}): {normalized_mix[slug]}"
        for slug, label in DESIGN_IDEA_STYLE_FIELDS
    )
    csv_header = ",".join(TASK_IMPORT_CSV_COLUMNS)
    duplicate_rules = (
        """The new concepts must not duplicate existing Sports Cave products.

Avoid:
* The same athlete with substantially the same story
* The same rivalry with substantially the same title or composition
* The same historic moment
* Minor renaming of an existing product
* Ideas already overrepresented in the selected collection

Look for meaningful commercial gaps in the existing range."""
        if exclude_existing
        else "Existing-product exclusion is not a mandatory gate, but identify any obvious overlap rather than presenting it as a new range gap."
    )
    calendar_rules = (
        """Use current web research to consider:
* Upcoming anniversaries
* Current tournaments, finals or championships
* Hall of Fame or retirement relevance
* Major rivalry renewals
* Historically important calendar dates
* Current fan interest

Current relevance should strengthen a genuinely collectible concept. Do not force weak news angles."""
        if calendar_relevance
        else "Do not use current calendar or news relevance as a required ranking signal. Prioritise enduring collector demand."
    )

    return f"""You are the Sports Cave product researcher, commercial range planner and premium collector-art creative director.

Your task is to produce exactly {requested_total} new {selected_sport} collector-art concepts for Sports Cave.

SHOPIFY RESEARCH - REQUIRED

Use the connected Shopify account in read-only mode.

Find and inspect the Sports Cave Shopify collection that best matches:

{selected_sport}

Review the collection's current products, titles, athletes, teams, rivalries, sporting moments, themes and design angles. If an exact collection is unavailable, use the closest matching collection and relevant product tags, and state which collection or fallback was inspected.

Do not create, edit, publish, archive or delete anything in Shopify. Do not claim access to sales information that is unavailable. Never include Shopify credentials, tokens or private administration data in the response.

EXISTING RANGE

{duplicate_rules}

CURRENT RELEVANCE

{calendar_rules}

COMMERCIAL STANDARD

Every concept must be designed for Sports Cave: "Premium Limited-Edition Sports Wall Art For Fans Who Collect Moments, Not Posters."

Prioritise fan identity, nostalgia, legacy, rivalry, championship history, national or team pride, emotional ownership, strong framed-wall appeal, Shopify-thumbnail readability and genuine bestseller potential.

SUBJECT LIMIT - ABSOLUTE

Every concept must contain either one principal person or two principal people. Never propose three or more principal people. Never place multiple names inside one principal-subject field.

Use one player by default. Use two only for a genuine rivalry, comparison, cross-generation legends concept, meaningful player partnership, or team-versus-team story represented by one hero from each team. No background player portraits, ghost players, team collages or groups.

STYLE ALLOCATION - EXACT

Create exactly the following number of ideas for each style. Store the stable slug shown after "CSV design_style" in the CSV:

{style_lines}

Total required: {requested_total}

Do not substitute styles. Do not create more or fewer ideas than requested.

STYLE RULES

Ultimate Moment:
Use one exact, historically remembered sporting event. The moment, season, date, venue, uniforms and emotional meaning must be accurate.

Rivalry Face-Off:
Use two genuine rivals or opposing heroes with a valid historical connection. Do not manufacture fake rivalries.

Legends - Jerseys on Display:
Use one or two legends. Make jersey identity, number, era and supporter nostalgia central. This is a legacy display, not an aggressive rivalry.

Nostalgic Moment:
Use one or two subjects connected to a beloved era, emotional memory, city, team or generation.

Motor Racing:
Use one driver as the principal person, with the exact vehicle as the supporting hero. A second driver is allowed only for a genuine rivalry or historic one-two finish. Preserve era-accurate livery, sponsors, number, circuit and vehicle model.

Simple Minimalistic:
Use one dominant hero, strong negative space, minimal text and restrained team colour. The athlete's identity must carry the design.

Specific Sporting Moment:
Use a clearly identifiable real play, celebration, finish, goal, shot, catch, overtake, knockout or performance. It must be more specific than a general career tribute.

Restored Collector Series:
Use one or two subjects from a historically important archival photograph. Restore the source into a premium collector piece without inventing missing historical details.

REALISM AND ACCURACY

Every concept must support a realistic photographic composite using real source photography for all principal subjects. Do not propose AI-generated likenesses, invented uniforms, incorrect numbers, fake vehicles or liveries, inaccurate venues, unverified statistics, fake quotes, fake signatures or generic background athletes.

Every final design must be landscape 4:3 with a premium dark Sports Cave collector treatment, strong negative space, a thin border and restrained gold. The official supplied Sports Cave limited-edition plaque must be composited as an exact asset and never recreated or retyped.

TITLE RULES

Give every design a cinematic, emotionally meaningful collector title, preferably two to five words. Titles must be distinct from existing Sports Cave product titles, avoid generic phrases such as "Player Wall Art", match the exact story and never promise an achievement that did not happen.

OUTPUT - IMPORT-READY CSV ONLY

Return one import-ready CSV code block with exactly this header and column order:

{csv_header}

Create exactly {requested_total} data rows and populate every design-related field.

Use these fixed values:
category = {DESIGN_TASK_GROUP}
task_section = {DESIGN_TASK_GROUP}
task = Create {selected_sport} design - {{DESIGN_TITLE}}
task_title = Create {selected_sport} design - {{DESIGN_TITLE}}

FIELD REQUIREMENTS

design_style: Use the exact stable slug from the requested allocation.
design_title: The final uppercase collector title.
sport: {selected_sport}
principal_subject_one: One person only.
principal_subject_two: One person only or blank.
team_country: Relevant team, teams or country; use "Team A vs Team B" only for a genuine rivalry.
season_era: Exact season, year range or historical era.
event_moment: Precise emotional or historical story.
venue_location: Correct stadium, arena, circuit, course, city or location.
uniform_equipment_livery: Accurate jersey, number, colours, helmet, equipment, vehicle, livery and era requirements.
essential_text: Only text that must appear in the artwork; keep it minimal.
special_instructions: Concise, complete generation direction covering hero arrangement, composition, lighting, minimal background, realism, source-image preservation, the maximum-two-subject rule, landscape 4:3, thin border and exact supplied plaque usage.
league_or_competition: Correct league, tournament or competition.
team_or_athlete: Search-friendly athlete/team description.
moment_or_theme: Emotional hook.
design_description: Concise commercial description of what the collector artwork celebrates.
priority: High, Medium or Low based on commercial strength, Shopify range gap and current relevance.
due_date: Blank unless there is a real time-sensitive event or anniversary.
notes: Briefly explain the Shopify collection gap and why the selected style is appropriate.

CSV RULES

Properly escape commas and quotation marks. Do not output a Markdown table. Do not omit columns. Do not add commentary before or after the CSV. Do not leave required design fields blank. Do not include more than two principal people. Ensure the style totals exactly match the requested allocation. Ensure every concept is materially different from the current Shopify collection and from the other generated concepts.

Before returning the CSV, silently verify the exact row count, exact style allocation, maximum two principal people per row, no duplicate titles, no duplicated existing Shopify concepts, all required fields, credible historical/uniform details and a clear reason each fan would want the concept on their wall."""
