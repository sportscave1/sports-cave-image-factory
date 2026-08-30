"""Persisted two-prompt SEO Blog research and article workflow."""

from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
from pathlib import Path
import re
import uuid
from urllib.parse import urlparse

from sports_cave_prompt_blocks import build_sports_cave_image_realism_rules


BASE_DIR = Path(__file__).resolve().parent
MIGRATION = "20260817_analytics_seo_blog_rebuild.sql"
WORKSPACE_KEY = "sports-cave"
STATE_PREFIX = "seo-blog-v2-"
GLOBAL_MARKET = "All Countries / Global"
COMMON_TARGET_MARKETS = (
    "Australia",
    "United States",
    "United Kingdom",
    "Canada",
    "New Zealand",
)
ISO_COUNTRIES = (
    "Afghanistan", "Åland Islands", "Albania", "Algeria", "American Samoa", "Andorra",
    "Angola", "Anguilla", "Antarctica", "Antigua and Barbuda", "Argentina", "Armenia",
    "Aruba", "Australia", "Austria", "Azerbaijan", "Bahamas", "Bahrain", "Bangladesh",
    "Barbados", "Belarus", "Belgium", "Belize", "Benin", "Bermuda", "Bhutan", "Bolivia",
    "Bonaire, Sint Eustatius and Saba", "Bosnia and Herzegovina", "Botswana", "Bouvet Island",
    "Brazil", "British Indian Ocean Territory", "Brunei", "Bulgaria", "Burkina Faso", "Burundi",
    "Cabo Verde", "Cambodia", "Cameroon", "Canada", "Cayman Islands",
    "Central African Republic", "Chad", "Chile", "China", "Christmas Island",
    "Cocos (Keeling) Islands", "Colombia", "Comoros", "Congo",
    "Congo, Democratic Republic of the", "Cook Islands", "Costa Rica", "Côte d'Ivoire",
    "Croatia", "Cuba", "Curaçao", "Cyprus", "Czechia", "Denmark", "Djibouti", "Dominica",
    "Dominican Republic", "Ecuador", "Egypt", "El Salvador", "Equatorial Guinea", "Eritrea",
    "Estonia", "Eswatini", "Ethiopia", "Falkland Islands", "Faroe Islands", "Fiji", "Finland",
    "France", "French Guiana", "French Polynesia", "French Southern Territories", "Gabon",
    "Gambia", "Georgia", "Germany", "Ghana", "Gibraltar", "Greece", "Greenland", "Grenada",
    "Guadeloupe", "Guam", "Guatemala", "Guernsey", "Guinea", "Guinea-Bissau", "Guyana",
    "Haiti", "Heard Island and McDonald Islands", "Holy See", "Honduras", "Hong Kong",
    "Hungary", "Iceland", "India", "Indonesia", "Iran", "Iraq", "Ireland", "Isle of Man",
    "Israel", "Italy", "Jamaica", "Japan", "Jersey", "Jordan", "Kazakhstan", "Kenya",
    "Kiribati", "Kuwait", "Kyrgyzstan", "Laos", "Latvia", "Lebanon", "Lesotho", "Liberia",
    "Libya", "Liechtenstein", "Lithuania", "Luxembourg", "Macao", "Madagascar", "Malawi",
    "Malaysia", "Maldives", "Mali", "Malta", "Marshall Islands", "Martinique", "Mauritania",
    "Mauritius", "Mayotte", "Mexico", "Micronesia", "Moldova", "Monaco", "Mongolia",
    "Montenegro", "Montserrat", "Morocco", "Mozambique", "Myanmar", "Namibia", "Nauru",
    "Nepal", "Netherlands", "New Caledonia", "New Zealand", "Nicaragua", "Niger", "Nigeria",
    "Niue", "Norfolk Island", "North Korea", "North Macedonia", "Northern Mariana Islands",
    "Norway", "Oman", "Pakistan", "Palau", "Palestine", "Panama", "Papua New Guinea",
    "Paraguay", "Peru", "Philippines", "Pitcairn", "Poland", "Portugal", "Puerto Rico",
    "Qatar", "Réunion", "Romania", "Russia", "Rwanda", "Saint Barthélemy",
    "Saint Helena, Ascension and Tristan da Cunha", "Saint Kitts and Nevis", "Saint Lucia",
    "Saint Martin (French part)", "Saint Pierre and Miquelon", "Saint Vincent and the Grenadines",
    "Samoa", "San Marino", "Sao Tome and Principe", "Saudi Arabia", "Senegal", "Serbia",
    "Seychelles", "Sierra Leone", "Singapore", "Sint Maarten (Dutch part)", "Slovakia",
    "Slovenia", "Solomon Islands", "Somalia", "South Africa",
    "South Georgia and the South Sandwich Islands", "South Korea", "South Sudan", "Spain",
    "Sri Lanka", "Sudan", "Suriname", "Svalbard and Jan Mayen", "Sweden", "Switzerland",
    "Syria", "Taiwan", "Tajikistan", "Tanzania", "Thailand", "Timor-Leste", "Togo",
    "Tokelau", "Tonga", "Trinidad and Tobago", "Tunisia", "Türkiye", "Turkmenistan",
    "Turks and Caicos Islands", "Tuvalu", "Uganda", "Ukraine", "United Arab Emirates",
    "United Kingdom", "United States", "United States Minor Outlying Islands", "Uruguay",
    "Uzbekistan", "Vanuatu", "Venezuela", "Vietnam", "Virgin Islands, British",
    "Virgin Islands, U.S.", "Wallis and Futuna", "Western Sahara", "Yemen", "Zambia", "Zimbabwe",
)
TARGET_MARKET_OPTIONS = (
    GLOBAL_MARKET,
    *COMMON_TARGET_MARKETS,
    *(country for country in ISO_COUNTRIES if country not in COMMON_TARGET_MARKETS),
)
MARKETS = TARGET_MARKET_OPTIONS
LANGUAGES = (
    "English (International)",
    "English (Australia)",
    "English (United States)",
    "English (United Kingdom)",
    "English (Canada)",
    "English (New Zealand)",
)
MARKET_LANGUAGE = {
    GLOBAL_MARKET: "English (International)",
    "Australia": "English (Australia)",
    "United States": "English (United States)",
    "United Kingdom": "English (United Kingdom)",
    "Canada": "English (Canada)",
    "New Zealand": "English (New Zealand)",
}
PUBLICATION_PREFERENCES = ("Draft", "Schedule after approval")
STATUSES = (
    "Idea", "Brief ready", "Generating", "Needs review", "Approved",
    "Shopify draft", "Scheduled", "Published", "Error",
)
SPORT_OPTIONS = (
    "All Sports / General Sports",
    "Australian Rules Football / AFL",
    "Rugby League / NRL",
    "Rugby Union",
    "Soccer / Football",
    "American Football / NFL",
    "College Football / NCAA",
    "Basketball / NBA",
    "College Basketball / NCAA",
    "WNBA",
    "Baseball / MLB",
    "Cricket",
    "Tennis",
    "Golf",
    "Formula 1",
    "Supercars",
    "Motorsport - General",
    "NASCAR",
    "IndyCar",
    "MotoGP / Motorcycle Racing",
    "Rally / WRC",
    "Le Mans / Endurance Racing",
    "Boxing",
    "MMA / UFC",
    "Professional Wrestling / WWE",
    "Ice Hockey / NHL",
    "Horse Racing",
    "Athletics / Track and Field",
    "Olympics",
    "Swimming",
    "Surfing",
    "Cycling",
    "Netball",
    "Darts",
    "Snooker / Pool",
    "Field Hockey",
    "Lacrosse",
    "Sailing",
    "Other",
)
SEARCH_INTENT_OPTIONS = (
    "Informational - Fan Education",
    "Informational - Athlete / Player Profile",
    "Informational - Team Story",
    "Informational - Career Retrospective",
    "Informational - Historical / Nostalgic Story",
    "Informational - Iconic Moment / Ultimate Moment",
    "Informational - Championship / Season Story",
    "Informational - Records / Statistics",
    "Informational - Rivalry / Head-to-Head",
    "Informational - Fan Debate",
    "Informational - FAQ / People Also Ask",
    "Informational - Evergreen Explainer",
    "Informational - Timely / Trending Story",
    "Informational - Anniversary / Milestone",
    "Informational - Legacy / Tribute",
    "Commercial - Sports Wall Art Guide",
    "Commercial - Collector Guide",
    "Commercial - Gift Guide",
    "Commercial - Best Of / Listicle",
    "Commercial - Product Comparison",
    "Commercial - Room / Man Cave Inspiration",
    "Commercial - Sports Decor Inspiration",
    "Commercial - Collection Buying Guide",
    "Product Support - Individual Product SEO",
    "Product Support - Collection SEO",
    "Product Support - Internal Linking Support",
    "Product Support - Product Story / Meaning",
    "Product Support - Athlete/Product Connection",
    "Search Opportunity - Low CTR Support",
    "Search Opportunity - Position 4-20 Support",
    "Search Opportunity - Long-Tail Keyword Support",
    "Search Opportunity - Topical Authority Support",
    "Other / Custom",
)
CSV_FIELDS = (
    "project_title",
    "gsc_seed_query",
    "target_markets",
    "sport",
    "search_intent_article_type",
    "language",
    "draft_schedule_preference",
    "topic_entity",
    "timely_hook",
    "recommended_article_angle",
    "working_article_title",
    "primary_keyword",
    "supporting_keywords",
    "related_entities",
    "fan_questions",
    "product_collection_title",
    "product_collection_url",
    "verified_internal_links",
    "link_building_authority_angle",
    "youtube_url",
    "target_word_count",
    "tags",
    "author",
    "target_shopify_blog",
)
CSV_MULTI_VALUE_FIELDS = (
    "target_markets",
    "supporting_keywords",
    "related_entities",
    "fan_questions",
    "verified_internal_links",
    "tags",
)
CSV_MULTI_VALUE_DELIMITER = ";"
CSV_MAX_BYTES = 2 * 1024 * 1024
RESEARCH_SETUP_FIELDS = (
    "gsc_seed_query", "target_markets", "sport", "search_intent", "language",
    "publication_preference", "target_title", "target_url", "author", "target_blog",
)
ARTICLE_BRIEF_FIELDS = (
    *RESEARCH_SETUP_FIELDS,
    "subject", "recommended_article_angle", "working_article_title", "primary_keyword",
)
IMAGE_ROLES = (
    ("featured", "16:9", "1600x900"),
    ("editorial", "3:2", "1600x1067"),
    ("product_room_mockup", "4:3", "1600x1200"),
)


class BlogWorkflowError(RuntimeError):
    pass


class BlogBriefCSVError(BlogWorkflowError):
    def __init__(self, issues):
        self.issues = tuple(str(issue) for issue in issues)
        super().__init__("; ".join(self.issues))


def _hash(value):
    payload = value if isinstance(value, str) else json.dumps(value, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _clean_list(value):
    if isinstance(value, str):
        separator = r"[;\n]+" if ";" in value or "\n" in value else r","
        value = re.split(separator, value)
    return [str(item).strip() for item in value or [] if str(item).strip()]


def _country_alias(value):
    aliases = {
        "all": GLOBAL_MARKET,
        "all countries": GLOBAL_MARKET,
        "global": GLOBAL_MARKET,
        "all countries / global": GLOBAL_MARKET,
        "au": "Australia",
        "australia": "Australia",
        "us": "United States",
        "usa": "United States",
        "united states of america": "United States",
        "uk": "United Kingdom",
        "gb": "United Kingdom",
        "ca": "Canada",
        "nz": "New Zealand",
    }
    text = str(value or "").strip()
    return aliases.get(text.casefold(), text)


def normalize_target_markets(value, *, previous=None, reject_mixed=False):
    selected = [_country_alias(item) for item in _clean_list(value)]
    selected = list(dict.fromkeys(item for item in selected if item))
    invalid = [item for item in selected if item not in TARGET_MARKET_OPTIONS]
    if invalid:
        raise BlogWorkflowError("Unsupported target market: " + ", ".join(invalid) + ".")
    if not selected:
        return [GLOBAL_MARKET]
    specific = [item for item in selected if item != GLOBAL_MARKET]
    if GLOBAL_MARKET in selected and specific:
        if reject_mixed:
            raise BlogWorkflowError(
                f"Choose {GLOBAL_MARKET} or individual countries, not both."
            )
        previous_values = {_country_alias(item) for item in _clean_list(previous)}
        if GLOBAL_MARKET in previous_values:
            selected = specific
        else:
            selected = [GLOBAL_MARKET]
    return [item for item in TARGET_MARKET_OPTIONS if item in selected]


def default_language_for_markets(markets):
    selected = normalize_target_markets(markets)
    if len(selected) == 1:
        return MARKET_LANGUAGE.get(selected[0], "English (International)")
    return "English (International)"


def _taxonomy_value(value, options, custom_label):
    text = str(value or "").strip()
    if text in options:
        return text, ""
    prefix = f"{custom_label}:"
    if text.casefold().startswith(prefix.casefold()):
        custom = text[len(prefix):].strip()
        return custom_label, custom
    return text, ""


def _taxonomy_csv_value(value, custom_value, custom_label):
    value = str(value or "").strip()
    custom_value = str(custom_value or "").strip()
    return f"{custom_label}: {custom_value}" if value == custom_label and custom_value else value


def normalize_brief(brief):
    brief = dict(brief or {})
    legacy_market = brief.get("target_market")
    brief["target_markets"] = normalize_target_markets(
        brief.get("target_markets") or ([legacy_market] if legacy_market else None)
    )
    brief.pop("target_market", None)
    brief["gsc_seed_query"] = str(
        brief.get("gsc_seed_query") or brief.get("selected_opportunity") or ""
    ).strip()
    brief["subject"] = str(brief.get("subject") or brief.get("topic_entity") or "").strip()
    brief["sport"] = {
        "AFL": "Australian Rules Football / AFL",
        "NRL": "Rugby League / NRL",
        "Football": "Soccer / Football",
        "Soccer": "Soccer / Football",
        "NFL": "American Football / NFL",
        "NBA": "Basketball / NBA",
        "MLB": "Baseball / MLB",
        "Formula 1 / Motorsport": "Motorsport - General",
        "UFC / Boxing": "MMA / UFC",
        "NHL": "Ice Hockey / NHL",
    }.get(str(brief.get("sport") or "").strip(), str(brief.get("sport") or "").strip())
    brief["search_intent"] = str(
        brief.get("search_intent") or brief.get("search_intent_article_type") or ""
    ).strip()
    brief["search_intent"] = {
        "Historical explainer": "Informational - Historical / Nostalgic Story",
        "Guide": "Informational - Fan Education",
        "New sports editorial": "Search Opportunity - Topical Authority Support",
        "Supporting guide or existing article refresh": "Search Opportunity - Position 4-20 Support",
        "Existing article refresh": "Search Opportunity - Low CTR Support",
    }.get(brief["search_intent"], brief["search_intent"])
    brief["publication_preference"] = str(
        brief.get("publication_preference") or brief.get("draft_schedule_preference") or "Draft"
    ).strip()
    brief["target_title"] = str(
        brief.get("target_title") or brief.get("product_collection_title") or ""
    ).strip()
    brief["target_url"] = str(
        brief.get("target_url") or brief.get("product_collection_url") or ""
    ).strip()
    brief["internal_links"] = _clean_list(
        brief.get("internal_links") or brief.get("verified_internal_links")
    )
    brief["target_length"] = str(
        brief.get("target_length") or brief.get("target_word_count") or ""
    ).strip()
    brief["target_blog"] = str(
        brief.get("target_blog") or brief.get("target_shopify_blog") or ""
    ).strip()
    if not str(brief.get("link_building_authority_angle") or "").strip():
        legacy_authority = [
            str(brief.get(field) or "").strip()
            for field in ("backlink_objective", "link_worthy_angle", "outreach_audience")
        ]
        brief["link_building_authority_angle"] = " | ".join(
            value for value in legacy_authority if value
        )
    brief["supporting_keywords"] = _clean_list(brief.get("supporting_keywords"))
    brief["related_entities"] = _clean_list(brief.get("related_entities"))
    brief["fan_questions"] = _clean_list(brief.get("fan_questions"))
    brief["tags"] = _clean_list(brief.get("tags"))
    for retired in (
        "approved_source_assets", "assets_permitted", "safe_non_identifiable_images",
        "backlink_objective", "link_worthy_angle", "outreach_audience",
    ):
        brief.pop(retired, None)
    return brief


def _validate_url(value, label, *, optional=False):
    text = str(value or "").strip()
    if optional and not text:
        return
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise BlogWorkflowError(f"{label} must be a complete public URL.")


def validate_brief(brief, *, article_ready=False):
    brief = normalize_brief(brief)
    fields = ARTICLE_BRIEF_FIELDS if article_ready else RESEARCH_SETUP_FIELDS
    missing = [field.replace("_", " ") for field in fields if not brief.get(field)]
    if brief.get("sport") == "Other" and not str(brief.get("sport_custom") or "").strip():
        missing.append("custom sport")
    if brief.get("search_intent") == "Other / Custom" and not str(brief.get("search_intent_custom") or "").strip():
        missing.append("custom search intent / article type")
    if brief.get("sport") not in SPORT_OPTIONS:
        missing.append("supported sport")
    if brief.get("search_intent") not in SEARCH_INTENT_OPTIONS:
        missing.append("supported search intent / article type")
    if brief.get("language") not in LANGUAGES:
        missing.append("supported language")
    if brief.get("publication_preference") not in PUBLICATION_PREFERENCES:
        missing.append("draft / schedule preference")
    if missing:
        raise BlogWorkflowError("Complete: " + ", ".join(dict.fromkeys(missing)) + ".")
    _validate_url(brief.get("target_url"), "Target product or collection URL")
    _validate_url(brief.get("youtube_url"), "YouTube URL", optional=True)
    return brief


def prefill_from_opportunity(brief, opportunity):
    """Fill blanks only; manual edits always win."""
    result = dict(brief or {})
    opportunity = dict(opportunity or {})
    recommended_intent = {
        "New sports editorial": "Search Opportunity - Topical Authority Support",
        "Supporting guide or existing article refresh": "Search Opportunity - Position 4-20 Support",
        "Existing article refresh": "Search Opportunity - Low CTR Support",
    }.get(str(opportunity.get("recommended_article_type") or ""))
    candidates = {
        "gsc_seed_query": opportunity.get("query"),
        "selected_opportunity": opportunity.get("query"),
        "subject": opportunity.get("query"),
        "search_intent": recommended_intent,
        "opportunity_snapshot": opportunity,
    }
    for field, value in candidates.items():
        if not result.get(field) and value:
            result[field] = value
    return result


def build_blog_opportunities(query_rows, *, data_through_date=""):
    result = []
    for row in query_rows or ():
        source = dict(row or {})
        candidate = {
            **source,
            "mapped_target": bool(source.get("current_page") or source.get("matched_page")),
            "content_gap": not bool(source.get("current_page") or source.get("matched_page")),
            "cannibalisation_risk": source.get("cannibalisation_risk") or 0,
        }
        score = __import__("seo_metrics").opportunity_score(candidate)
        position = float(source.get("average_position") or 0)
        ctr = float(source.get("ctr") or 0)
        if candidate["content_gap"]:
            article_type = "New sports editorial"
        elif 4 <= position <= 20 and ctr < 0.05:
            article_type = "Supporting guide or existing article refresh"
        else:
            article_type = "Existing article refresh"
        numeric_score = float(score["score"])
        confidence = "High" if numeric_score >= 60 else "Medium" if numeric_score >= 30 else "Low"
        result.append(
            {
                **source,
                "recommended_article_type": article_type,
                "confidence": confidence,
                "data_through_date": str(data_through_date or ""),
                "score": score["score"],
                "score_explanation": score["explanation"],
                "matched_page": source.get("current_page") or source.get("matched_page") or "",
            }
        )
    return sorted(result, key=lambda row: (row["score"], row.get("impressions") or 0), reverse=True)


def _semicolon_list(value):
    if isinstance(value, str):
        value = value.split(CSV_MULTI_VALUE_DELIMITER)
    return [str(item).strip() for item in value or [] if str(item).strip()]


def blog_brief_csv_row(project_title, brief, *, opportunity=None):
    brief = normalize_brief(brief)
    opportunity = dict(opportunity or brief.get("opportunity_snapshot") or {})
    return {
        "project_title": str(project_title or brief.get("project_title") or "").strip(),
        "gsc_seed_query": str(
            brief.get("gsc_seed_query") or opportunity.get("query") or ""
        ).strip(),
        "target_markets": CSV_MULTI_VALUE_DELIMITER.join(brief.get("target_markets") or []),
        "sport": _taxonomy_csv_value(brief.get("sport"), brief.get("sport_custom"), "Other"),
        "search_intent_article_type": _taxonomy_csv_value(
            brief.get("search_intent"), brief.get("search_intent_custom"), "Other / Custom"
        ),
        "language": str(brief.get("language") or "").strip(),
        "draft_schedule_preference": str(brief.get("publication_preference") or "").strip(),
        "topic_entity": str(brief.get("subject") or "").strip(),
        "timely_hook": str(brief.get("timely_hook") or "").strip(),
        "recommended_article_angle": str(brief.get("recommended_article_angle") or "").strip(),
        "working_article_title": str(brief.get("working_article_title") or "").strip(),
        "primary_keyword": str(brief.get("primary_keyword") or "").strip(),
        "supporting_keywords": CSV_MULTI_VALUE_DELIMITER.join(brief.get("supporting_keywords") or []),
        "related_entities": CSV_MULTI_VALUE_DELIMITER.join(brief.get("related_entities") or []),
        "fan_questions": CSV_MULTI_VALUE_DELIMITER.join(brief.get("fan_questions") or []),
        "product_collection_title": str(brief.get("target_title") or "").strip(),
        "product_collection_url": str(brief.get("target_url") or "").strip(),
        "verified_internal_links": CSV_MULTI_VALUE_DELIMITER.join(brief.get("internal_links") or []),
        "link_building_authority_angle": str(
            brief.get("link_building_authority_angle") or ""
        ).strip(),
        "youtube_url": str(brief.get("youtube_url") or "").strip(),
        "target_word_count": str(brief.get("target_length") or "").strip(),
        "tags": CSV_MULTI_VALUE_DELIMITER.join(brief.get("tags") or []),
        "author": str(brief.get("author") or "").strip(),
        "target_shopify_blog": str(brief.get("target_blog") or "").strip(),
    }


def blog_brief_csv_bytes(project_title, brief, *, opportunity=None):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, lineterminator="\r\n")
    writer.writeheader()
    writer.writerow(blog_brief_csv_row(project_title, brief, opportunity=opportunity))
    return output.getvalue().encode("utf-8-sig")


def _decode_blog_csv(data, filename=""):
    if filename and not str(filename).casefold().endswith(".csv"):
        raise BlogBriefCSVError(("Choose a .csv file exported from this Blog brief.",))
    if isinstance(data, str):
        text = data
        size = len(text.encode("utf-8"))
    else:
        try:
            raw = bytes(data or b"")
        except TypeError as error:
            raise BlogBriefCSVError(("Choose a valid Blog brief CSV file.",)) from error
        size = len(raw)
        if not raw:
            raise BlogBriefCSVError(("Choose a completed Blog brief CSV file.",))
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise BlogBriefCSVError(("Save the Blog brief CSV as UTF-8 and try again.",)) from error
    if size > CSV_MAX_BYTES:
        raise BlogBriefCSVError(("The Blog brief CSV must be smaller than 2 MB.",))
    if "\x00" in text[:4096] or not text.strip():
        raise BlogBriefCSVError(("Choose a valid text CSV file.",))
    return text.lstrip("\ufeff")


def _target_conflict(current_brief, imported_brief):
    current = normalize_brief(current_brief)
    imported = normalize_brief(imported_brief)
    current_url = str(current.get("target_url") or "").strip().rstrip("/").casefold()
    imported_url = str(imported.get("target_url") or "").strip().rstrip("/").casefold()
    current_title = " ".join(str(current.get("target_title") or "").split()).casefold()
    imported_title = " ".join(str(imported.get("target_title") or "").split()).casefold()
    if (imported_url or imported_title) and not (current_url or current_title):
        return (
            "No Shopify product/collection is selected for this Blog project. "
            f"The CSV targets '{imported.get('target_title') or imported.get('target_url')}'. "
            "Choose that matching Shopify target before importing."
        )
    url_conflict = bool(current_url and imported_url and current_url != imported_url)
    title_conflict = bool(current_title and imported_title and current_title != imported_title)
    if not (url_conflict or title_conflict):
        return ""
    return (
        "This CSV targets "
        f"'{imported.get('target_title') or imported.get('target_url')}', but the current Shopify "
        f"selection is '{current.get('target_title') or current.get('target_url')}'. "
        "Choose the matching Shopify product/collection, or deliberately keep the current selection."
    )


def parse_blog_brief_csv(data, *, filename="", current_brief=None):
    text = _decode_blog_csv(data, filename)
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""))
        raw_headers = list(reader.fieldnames or ())
        headers = [str(value or "").strip() for value in raw_headers]
        duplicates = [name for name, count in Counter(headers).items() if name and count > 1]
        if duplicates:
            raise BlogBriefCSVError(("Duplicate CSV headers: " + ", ".join(duplicates) + ".",))
        if tuple(headers) != CSV_FIELDS:
            raise BlogBriefCSVError(("Use the Blog brief CSV headers exactly: " + ", ".join(CSV_FIELDS) + ".",))
        rows = [row for row in reader if any(str(value or "").strip() for value in row.values())]
    except BlogBriefCSVError:
        raise
    except csv.Error as error:
        raise BlogBriefCSVError(("The Blog brief CSV could not be read. Check its quoting and line breaks.",)) from error
    if len(rows) != 1:
        raise BlogBriefCSVError(("The Blog brief CSV must contain exactly one completed data row.",))
    row = {field: str(rows[0].get(field) or "").strip() for field in CSV_FIELDS}
    if None in rows[0] or any(value is None for value in rows[0].values()):
        raise BlogBriefCSVError(("The Blog brief CSV has an unexpected or missing value.",))
    try:
        target_markets = normalize_target_markets(
            _semicolon_list(row["target_markets"]), reject_mixed=True
        )
        sport, sport_custom = _taxonomy_value(row["sport"], SPORT_OPTIONS, "Other")
        search_intent, search_intent_custom = _taxonomy_value(
            row["search_intent_article_type"], SEARCH_INTENT_OPTIONS, "Other / Custom"
        )
        imported_brief = validate_brief(
            {
                "project_title": row["project_title"],
                "gsc_seed_query": row["gsc_seed_query"],
                "selected_opportunity": row["gsc_seed_query"],
                "target_markets": target_markets,
                "sport": sport,
                "sport_custom": sport_custom,
                "search_intent": search_intent,
                "search_intent_custom": search_intent_custom,
                "language": row["language"],
                "publication_preference": row["draft_schedule_preference"],
                "subject": row["topic_entity"],
                "timely_hook": row["timely_hook"],
                "recommended_article_angle": row["recommended_article_angle"],
                "working_article_title": row["working_article_title"],
                "primary_keyword": row["primary_keyword"],
                "supporting_keywords": _semicolon_list(row["supporting_keywords"]),
                "related_entities": _semicolon_list(row["related_entities"]),
                "fan_questions": _semicolon_list(row["fan_questions"]),
                "target_title": row["product_collection_title"],
                "target_url": row["product_collection_url"],
                "internal_links": _semicolon_list(row["verified_internal_links"]),
                "link_building_authority_angle": row["link_building_authority_angle"],
                "youtube_url": row["youtube_url"],
                "target_length": row["target_word_count"],
                "tags": _semicolon_list(row["tags"]),
                "author": row["author"],
                "target_blog": row["target_shopify_blog"],
            },
            article_ready=True,
        )
    except BlogWorkflowError as error:
        raise BlogBriefCSVError((str(error),)) from error
    conflict = (
        _target_conflict(current_brief or {}, imported_brief)
        if current_brief is not None
        else ""
    )
    return {
        "row": row,
        "brief": imported_brief,
        "target_conflict": bool(conflict),
        "target_conflict_message": conflict,
    }


def merge_imported_brief(current_brief, imported_brief, *, keep_current_target=False):
    current = normalize_brief(current_brief)
    imported = normalize_brief(imported_brief)
    preserved_metadata = {
        key: current.get(key)
        for key in ("target_entity_id", "target_entity_type", "target_sport", "source_artwork")
        if current.get(key)
    }
    if keep_current_target:
        imported["target_title"] = current.get("target_title") or ""
        imported["target_url"] = current.get("target_url") or ""
    return {**current, **imported, **preserved_metadata}


def _evidence_lines(brief, opportunity, source_date):
    values = (
        ("Source", "Google Search Console saved query/page data"),
        ("Data through", source_date or opportunity.get("data_through_date") or "Not available"),
        ("Seed query", brief.get("gsc_seed_query") or opportunity.get("query") or ""),
        ("Clicks", opportunity.get("clicks")),
        ("Impressions", opportunity.get("impressions")),
        ("CTR", opportunity.get("ctr")),
        ("Impression-weighted position", opportunity.get("average_position")),
        ("Change", opportunity.get("change") or opportunity.get("ranking_change") or opportunity.get("click_change")),
        ("Matched page", opportunity.get("matched_page") or opportunity.get("current_page") or ""),
        ("Confidence", opportunity.get("confidence") or ""),
        ("Why", opportunity.get("score_explanation") or ""),
    )
    return "\n".join(f"- {label}: {value if value not in (None, '') else 'Not available'}" for label, value in values)


def build_prompt_1(project_id, brief, *, source_date="", opportunity=None):
    brief = validate_brief(brief)
    opportunity = dict(opportunity or brief.get("opportunity_snapshot") or {})
    project_title = str(brief.get("project_title") or brief.get("subject") or "").strip()
    csv_text = blog_brief_csv_bytes(
        project_title, brief, opportunity=opportunity
    ).decode("utf-8-sig").strip()
    markets = "; ".join(brief.get("target_markets") or [])
    market_rule = (
        "Write for international search and fan intent without unnecessarily localising the whole article. "
        "A sport may naturally skew towards particular countries, but do not force a country focus."
        if brief.get("target_markets") == [GLOBAL_MARKET]
        else f"Account for search audiences in these explicitly selected markets: {markets}."
    )
    return f"""SPORTS CAVE RESEARCH BLOG BRIEF - PROMPT 1

PURPOSE
Research and complete one Blog brief CSV. Do not write the final article yet.

PROJECT ID: {project_id}
PROJECT TITLE: {project_title or 'Untitled brief'}

SELECTED REAL GSC OPPORTUNITY
{_evidence_lines(brief, opportunity, source_date)}
This query is the starting search opportunity, not an instruction to keep it unchanged as the final primary keyword.
Any stronger keyword or long-tail variation must stay closely tied to the same real search intent.

SELECTED SPORTS CAVE PRODUCT OR COLLECTION
- Type: {brief.get('target_entity_type') or 'Product or collection'}
- Title: {brief.get('target_title') or ''}
- Exact URL: {brief.get('target_url') or ''}

TARGETING
- Target markets: {markets}
- Market guidance: {market_rule}
- Sport: {_taxonomy_csv_value(brief.get('sport'), brief.get('sport_custom'), 'Other')}
- Search intent / article type: {_taxonomy_csv_value(brief.get('search_intent'), brief.get('search_intent_custom'), 'Other / Custom')}
- Language: {brief.get('language') or ''}
- Draft / schedule preference: {brief.get('publication_preference') or ''}

RESEARCH INSTRUCTIONS
1. Use the selected real GSC query as the starting search opportunity.
2. Research the selected topic properly using authoritative, current sources.
3. Visit and scan the supplied Sports Cave product or collection URL.
4. Review the wider Sports Cave website where useful.
5. Find ONLY real, verified Sports Cave internal links. Never invent an internal URL.
6. Determine the strongest article angle, primary keyword, supporting keywords, relevant entities,
   fan questions / People Also Ask style questions, genuine timely hook, internal linking opportunities,
   sensible target length, tags and a link-building angle only where genuinely useful.
7. Keep the article commercially relevant to Sports Cave without turning it into a product advertisement.
8. Build around fan interest first, then guide readers naturally towards the selected product or collection.
9. Avoid keyword stuffing.
10. Prefer real search intent and useful fan content.
11. Fact-check athlete, team, event, date, record and history claims where relevant.
12. When target market is Global, make the brief internationally appropriate.
13. When target markets are specific countries, account for those search audiences.
14. Include a YouTube URL only when it is genuinely relevant and verified; otherwise leave youtube_url blank.
15. If there is no legitimate timely hook, leave timely_hook blank. Never manufacture urgency.
16. Do not invent a backlink opportunity just to fill the field. Blank optional fields are acceptable.
17. Preserve operationally fixed fields: selected product/collection title and URL, author, target Shopify blog,
    explicit target markets, language and draft/schedule preference.
18. Output the completed CSV in EXACTLY the required schema and preserve semicolon-separated multi-value cells.

CSV SCHEMA
{','.join(CSV_FIELDS)}

PARTIALLY FILLED CSV
{csv_text}

OUTPUT RULES
- Return the header row and exactly one completed data row.
- Return no markdown explanation and no text before or after the CSV.
- Do not use a code fence if possible.
- Quote CSV cells correctly when they contain commas, quotation marks or line breaks.
- Never include credentials, secrets, private API payloads or invented Sports Cave URLs.
""".strip()


def _brief_lines(brief):
    row = blog_brief_csv_row(brief.get("project_title") or "", brief)
    return "\n".join(
        f"- {field}: {row.get(field) or '[blank]'}"
        for field in CSV_FIELDS
    )


def build_prompt_2(project, brief=None):
    project = dict(project or {})
    brief = validate_brief(brief or project.get("brief") or {}, article_ready=True)
    realism = build_sports_cave_image_realism_rules(include_product_lock=True)
    return f"""SPORTS CAVE SEO BLOG ARTICLE AND IMAGE CREATION - PROMPT 2

Continue in the same conversation as Prompt 1 and use the completed research brief below.
PROJECT ID: {project.get('project_id') or ''}

COMPLETED BLOG BRIEF
{_brief_lines(brief)}

ARTICLE CONTRACT
- Research current facts using authoritative sources and distinguish sourced facts from editorial interpretation.
- Fact-check dates, scores, seasons, venues, achievements, quotes and statistics.
- Never invent personal experience, quotations, search volume, sporting history, product facts or source evidence.
- Produce original, people-first premium sports editorial writing. Do not imitate a named writer or publication.
- Write as a knowledgeable sports journalist, not a product-page copywriter.
- Establish the search intent in the first 100 words and sustain one central topic and intent.
- Use specific verified games, seasons, teams, arenas, achievements and cultural context.
- Target approximately {brief.get('target_length') or '1,100-1,700'} words when the subject supports it; never add filler.
- Use natural sentence variation and readable paragraphs. Avoid generic AI phrases, repetitive conclusions,
  keyword stuffing, exaggerated marketing language and excessive em dashes.
- Keep the sports story first. Traffic first, conversion second.
- Place one relevant, natural Sports Cave product or collection connection in the final third using this exact URL:
  {brief.get('target_url') or ''}
- Use descriptive crawlable anchors and ONLY the verified internal links in the brief. Never invent an internal URL.
- Produce clean Shopify-safe semantic HTML with no body H1 because Shopify renders the article title as H1.
- Use H2/H3 only where useful. Include a list, table or FAQs only when they improve the reader's answer.
- Supply SEO title, meta description, handle, excerpt, author and tags. Never promise rankings.

IMAGE PACKAGE CONTRACT
Create, provide or find the appropriate final blog images as the available tools allow; do not merely claim they exist.
Return exactly these default roles at the highest supported resolution while preserving each ratio:
1. Featured image: 16:9, target 1600x900.
2. Editorial/support image: 3:2, target 1600x1067.
3. Product/room mockup: 4:3, target 1600x1200.
For every image provide its purpose, placement marker, descriptive hyphenated WebP filename, unique natural alt text,
optional caption, verified source/reference and final asset or download reference. Do not put advertising or keyword
text in images. For an identifiable athlete, use only a real source you can verify is suitable; when that is unavailable,
use a relevant non-identifiable editorial environment and never generate or approximate the athlete's likeness.

{realism}

OUTPUT CONTRACT
Return a complete article package with:
1. Article title, SEO title, meta description, handle, excerpt, author and tags.
2. The complete final Shopify-safe HTML, with no body H1 and no placeholders.
3. A verified internal-link map and concise fact-check/source notes.
4. The complete three-image plan and the actual image assets or usable final references when available.
5. A short QA checklist confirming search intent, factual review, exact Sports Cave URL placement in the final third,
   verified internal links, image roles/ratios/alt text and absence of placeholders.

Do not output JSON. Do not write to Shopify, publish, schedule, request credentials or claim that anything was uploaded.
""".strip()


class PostgresBlogProjectStore:
    def __init__(self, backend=None):
        self.backend = backend
        self._schema_ready = False

    def _backend(self):
        if self.backend is not None:
            return self.backend
        import supabase_backend
        return supabase_backend

    def ensure_schema(self):
        if self._schema_ready:
            return
        migration = BASE_DIR / "migrations" / MIGRATION
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(migration.read_text(encoding="utf-8"))
            connection.commit()
        self._schema_ready = True

    def list_projects(self, *, owner_id="", include_all=False, limit=50):
        self.ensure_schema()
        clauses = ["workspace_key=%s"]
        params = [WORKSPACE_KEY]
        if owner_id and not include_all:
            clauses.append("owner_id=%s")
            params.append(str(owner_id))
        params.append(int(limit))
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT * FROM seo_blog_projects_v2 WHERE {' AND '.join(clauses)} "
                    "ORDER BY updated_at DESC LIMIT %s",
                    params,
                )
                rows = cursor.fetchall() or []
        return [dict(row) for row in rows]

    def get_project(self, project_id):
        self.ensure_schema()
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM seo_blog_projects_v2 WHERE workspace_key=%s AND project_id=%s",
                    (WORKSPACE_KEY, project_id),
                )
                row = cursor.fetchone()
        return dict(row or {})

    def list_shopify_targets(self, limit=500):
        """Read the saved Shopify/canonical inventory; never call Shopify from the Blog route."""
        self.ensure_schema()
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT shopify_product_id AS id, 'Product' AS entity_type, title,
                           online_store_url AS url, product_type AS sport, image_url AS source_artwork
                    FROM shopify_products
                    WHERE UPPER(COALESCE(status, 'ACTIVE'))='ACTIVE'
                      AND COALESCE(online_store_url, '')<>''
                    UNION ALL
                    SELECT shopify_resource_id AS id, page_type AS entity_type, title,
                           canonical_url AS url, '' AS sport, '' AS source_artwork
                    FROM seo_canonical_pages
                    WHERE workspace_key=%s AND is_active=TRUE
                      AND LOWER(page_type)='collection'
                    ORDER BY entity_type, title
                    LIMIT %s
                    """,
                    (WORKSPACE_KEY, int(limit)),
                )
                rows = cursor.fetchall() or []
        return [dict(row) for row in rows]

    def save_project(self, project):
        project = dict(project or {})
        project_id = str(project.get("project_id") or uuid.uuid4())
        brief = dict(project.get("brief") or {})
        self.ensure_schema()
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO seo_blog_projects_v2(
                        project_id, workspace_key, owner_id, owner_name, status, title,
                        primary_keyword, target_url, brief, opportunity_snapshot,
                        prompt_1, prompt_1_hash, content_package, image_manifest,
                        prompt_2, prompt_2_hash, shopify_article_id, shopify_handle,
                        draft_url, live_url, qa_results, last_error, published_at, updated_at
                    ) VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,
                        %s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,now()
                    )
                    ON CONFLICT (project_id) DO UPDATE SET
                        owner_id=EXCLUDED.owner_id, owner_name=EXCLUDED.owner_name,
                        status=EXCLUDED.status, title=EXCLUDED.title,
                        primary_keyword=EXCLUDED.primary_keyword, target_url=EXCLUDED.target_url,
                        brief=EXCLUDED.brief, opportunity_snapshot=EXCLUDED.opportunity_snapshot,
                        prompt_1=EXCLUDED.prompt_1, prompt_1_hash=EXCLUDED.prompt_1_hash,
                        content_package=EXCLUDED.content_package, image_manifest=EXCLUDED.image_manifest,
                        prompt_2=EXCLUDED.prompt_2, prompt_2_hash=EXCLUDED.prompt_2_hash,
                        shopify_article_id=EXCLUDED.shopify_article_id,
                        shopify_handle=EXCLUDED.shopify_handle, draft_url=EXCLUDED.draft_url,
                        live_url=EXCLUDED.live_url, qa_results=EXCLUDED.qa_results,
                        last_error=EXCLUDED.last_error, published_at=EXCLUDED.published_at,
                        updated_at=now()
                    RETURNING *
                    """,
                    (
                        project_id, WORKSPACE_KEY, project.get("owner_id") or "",
                        project.get("owner_name") or "", project.get("status") or "Idea",
                        project.get("title") or brief.get("article_title") or "",
                        project.get("primary_keyword") or brief.get("primary_keyword") or "",
                        project.get("target_url") or brief.get("target_url") or "",
                        json.dumps(brief, default=str),
                        json.dumps(project.get("opportunity_snapshot") or {}, default=str),
                        project.get("prompt_1") or "", project.get("prompt_1_hash") or "",
                        json.dumps(project.get("content_package") or {}, default=str),
                        json.dumps(project.get("image_manifest") or [], default=str),
                        project.get("prompt_2") or "", project.get("prompt_2_hash") or "",
                        project.get("shopify_article_id") or "", project.get("shopify_handle") or "",
                        project.get("draft_url") or "", project.get("live_url") or "",
                        json.dumps(project.get("qa_results") or {}, default=str),
                        project.get("last_error") or "", project.get("published_at"),
                    ),
                )
                saved = cursor.fetchone() or {}
            connection.commit()
        return dict(saved)

    def record_event(self, project_id, *, actor_id, actor_name, action_type, idempotency_key, metadata=None):
        self.ensure_schema()
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO seo_blog_project_events_v2(
                        id, project_id, actor_id, actor_name, action_type,
                        idempotency_key, safe_metadata
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
                    ON CONFLICT (project_id, idempotency_key) DO NOTHING
                    RETURNING id
                    """,
                    (
                        str(uuid.uuid4()), project_id, str(actor_id or ""), str(actor_name or ""),
                        str(action_type or ""), str(idempotency_key or ""),
                        json.dumps(metadata or {}, default=str),
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
        return bool(row)


def prompt_hash(prompt):
    return _hash(str(prompt or ""))


def utc_timestamp():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
