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
import zipfile

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
    "gsc_seed_query",
    "target_markets",
    "sport",
    "search_intent_article_type",
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
    "youtube_url",
    "target_word_count",
    "tags",
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
SPORTS_CAVE_VOCABULARY_ERROR = (
    "Sports Cave brand rule: replace 'poster' terminology with premium "
    "wall-art / collector terminology."
)
PROHIBITED_CUSTOMER_VOCABULARY = re.compile(r"\bposters?\b", re.IGNORECASE)
CUSTOMER_FACING_BRIEF_FIELDS = (
    ("subject", "topic / entity"),
    ("timely_hook", "timely hook"),
    ("recommended_article_angle", "recommended article angle"),
    ("working_article_title", "working article title"),
    ("primary_keyword", "primary keyword"),
    ("supporting_keywords", "supporting keywords"),
    ("fan_questions", "fan questions"),
    ("target_title", "product / collection title"),
    ("tags", "tags"),
    ("link_building_authority_angle", "link-building / authority angle"),
)
PREFERRED_SPORTS_CAVE_VOCABULARY = (
    "limited-edition sports wall art",
    "framed sports wall art",
    "sports wall art",
    "collector wall art",
    "collector edition",
    "numbered edition",
    "limited edition",
    "premium sports art",
    "framed sports art",
    "sports artwork",
    "collector series",
    "framed collector art",
    "athlete wall art",
    "team wall art",
    "football wall art",
    "basketball wall art",
    "motorsport wall art",
    "cricket wall art",
)
RESEARCH_SETUP_FIELDS = (
    "gsc_seed_query",
)
ARTICLE_BRIEF_FIELDS = (
    "gsc_seed_query", "target_markets", "sport", "search_intent", "subject",
    "recommended_article_angle", "working_article_title", "primary_keyword",
    "supporting_keywords", "related_entities", "fan_questions", "target_title",
    "target_url", "internal_links", "target_length", "tags",
)
PRODUCT_REFERENCE_FIELDS = ("page_type", "title", "url", "sport_or_category")
SPORTS_CAVE_HOSTS = {"sportscaveshop.com", "www.sportscaveshop.com"}
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
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
        return []
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
    if not selected:
        return "English (International)"
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
        brief.get("target_markets") or ([legacy_market] if legacy_market else [])
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


def _validate_sports_cave_url(value, label):
    _validate_url(value, label)
    host = (urlparse(str(value or "").strip()).hostname or "").casefold()
    if host not in SPORTS_CAVE_HOSTS:
        raise BlogWorkflowError(f"{label} must be a real Sports Cave storefront URL.")


def _validate_youtube_url(value):
    text = str(value or "").strip()
    if not text:
        return
    _validate_url(text, "YouTube URL")
    host = (urlparse(text).hostname or "").casefold()
    if host not in YOUTUBE_HOSTS:
        raise BlogWorkflowError("YouTube URL must use a real YouTube domain.")


def prohibited_customer_vocabulary_fields(brief):
    """Return derived, customer-facing brief fields that break the brand vocabulary lock.

    Raw GSC evidence and URL fields are intentionally excluded. A real query or verified
    legacy handle can contain the prohibited search term without being rewritten.
    """
    brief = normalize_brief(brief)
    found = []
    for field, label in CUSTOMER_FACING_BRIEF_FIELDS:
        value = brief.get(field)
        values = value if isinstance(value, (list, tuple, set)) else (value,)
        if any(PROHIBITED_CUSTOMER_VOCABULARY.search(str(item or "")) for item in values):
            found.append(label)
    return tuple(found)


def validate_sports_cave_vocabulary(brief):
    brief = normalize_brief(brief)
    fields = prohibited_customer_vocabulary_fields(brief)
    if fields:
        raise BlogWorkflowError(
            f"{SPORTS_CAVE_VOCABULARY_ERROR} Found in: {', '.join(fields)}."
        )
    return brief


def validate_brief(brief, *, article_ready=False):
    brief = normalize_brief(brief)
    fields = ARTICLE_BRIEF_FIELDS if article_ready else RESEARCH_SETUP_FIELDS
    missing = [field.replace("_", " ") for field in fields if not brief.get(field)]
    if article_ready:
        if brief.get("sport") == "Other" and not str(brief.get("sport_custom") or "").strip():
            missing.append("custom sport")
        if brief.get("search_intent") == "Other / Custom" and not str(brief.get("search_intent_custom") or "").strip():
            missing.append("custom search intent / article type")
        if brief.get("sport") not in SPORT_OPTIONS:
            missing.append("supported sport")
        if brief.get("search_intent") not in SEARCH_INTENT_OPTIONS:
            missing.append("supported search intent / article type")
    if missing:
        raise BlogWorkflowError("Complete: " + ", ".join(dict.fromkeys(missing)) + ".")
    if article_ready:
        validate_sports_cave_vocabulary(brief)
        _validate_sports_cave_url(
            brief.get("target_url"), "Target product or collection URL"
        )
        for internal_url in brief.get("internal_links") or []:
            _validate_sports_cave_url(internal_url, "Verified internal link")
        _validate_youtube_url(brief.get("youtube_url"))
    return brief


def prefill_from_opportunity(brief, opportunity):
    """Start fresh research from one saved GSC opportunity."""
    result = normalize_brief(brief)
    opportunity = dict(opportunity or {})
    seed_query = str(opportunity.get("query") or "").strip()
    if not seed_query:
        raise BlogWorkflowError("Choose a saved GSC opportunity first.")
    for field in (
        "target_markets", "sport", "sport_custom", "search_intent",
        "search_intent_custom", "subject", "timely_hook",
        "recommended_article_angle", "working_article_title", "primary_keyword",
        "supporting_keywords", "related_entities", "fan_questions", "target_title",
        "target_url", "internal_links", "youtube_url", "target_length", "tags",
        "link_building_authority_angle",
        "target_entity_id", "target_entity_type", "target_sport", "source_artwork",
    ):
        result.pop(field, None)
    result.update(
        gsc_seed_query=seed_query,
        selected_opportunity=seed_query,
        opportunity_snapshot=opportunity,
    )
    return normalize_brief(result)


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
        "gsc_seed_query": str(
            brief.get("gsc_seed_query") or opportunity.get("query") or ""
        ).strip(),
        "target_markets": CSV_MULTI_VALUE_DELIMITER.join(brief.get("target_markets") or []),
        "sport": _taxonomy_csv_value(brief.get("sport"), brief.get("sport_custom"), "Other"),
        "search_intent_article_type": _taxonomy_csv_value(
            brief.get("search_intent"), brief.get("search_intent_custom"), "Other / Custom"
        ),
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
        "youtube_url": str(brief.get("youtube_url") or "").strip(),
        "target_word_count": str(brief.get("target_length") or "").strip(),
        "tags": CSV_MULTI_VALUE_DELIMITER.join(brief.get("tags") or []),
    }


def blog_brief_csv_bytes(project_title, brief, *, opportunity=None):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, lineterminator="\r\n")
    writer.writeheader()
    writer.writerow(blog_brief_csv_row(project_title, brief, opportunity=opportunity))
    return output.getvalue().encode("utf-8-sig")


def blog_brief_template_csv_bytes(brief, *, opportunity=None):
    brief = normalize_brief(brief)
    opportunity = dict(opportunity or brief.get("opportunity_snapshot") or {})
    row = {field: "" for field in CSV_FIELDS}
    row["gsc_seed_query"] = str(
        brief.get("gsc_seed_query") or opportunity.get("query") or ""
    ).strip()
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, lineterminator="\r\n")
    writer.writeheader()
    writer.writerow(row)
    return output.getvalue().encode("utf-8-sig")


def _is_sports_cave_url(value):
    parsed = urlparse(str(value or "").strip())
    return (
        parsed.scheme in {"http", "https"}
        and (parsed.hostname or "").casefold() in SPORTS_CAVE_HOSTS
    )


def product_reference_csv_bytes(product_context):
    rows = []
    seen_urls = set()
    for source in product_context or ():
        source = dict(source or {})
        url = str(source.get("url") or "").strip()
        normalized_url = url.rstrip("/").casefold()
        if not _is_sports_cave_url(url) or normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)
        rows.append(
            {
                "page_type": str(
                    source.get("entity_type") or source.get("page_type") or ""
                ).strip(),
                "title": str(source.get("title") or source.get("name") or "").strip(),
                "url": url,
                "sport_or_category": str(source.get("sport") or "").strip(),
            }
        )
    rows.sort(key=lambda row: (row["page_type"].casefold(), row["title"].casefold(), row["url"]))
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=PRODUCT_REFERENCE_FIELDS, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


def build_research_pack(
    project_id,
    brief,
    *,
    source_date="",
    opportunity=None,
    product_context=None,
):
    prompt = build_prompt_1(
        project_id,
        brief,
        source_date=source_date,
        opportunity=opportunity,
        product_context=product_context,
    )
    template = blog_brief_template_csv_bytes(brief, opportunity=opportunity)
    product_reference = product_reference_csv_bytes(product_context)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("PROMPT_1_RESEARCH.txt", prompt.encode("utf-8"))
        archive.writestr("BLOG_BRIEF_TEMPLATE.csv", template)
        reference_text = product_reference.decode("utf-8-sig")
        if len(reference_text.splitlines()) > 1:
            archive.writestr("SPORTS_CAVE_PAGE_REFERENCE.csv", product_reference)
    return output.getvalue()


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
                "gsc_seed_query": row["gsc_seed_query"],
                "selected_opportunity": row["gsc_seed_query"],
                "target_markets": target_markets,
                "sport": sport,
                "sport_custom": sport_custom,
                "search_intent": search_intent,
                "search_intent_custom": search_intent_custom,
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
                "youtube_url": row["youtube_url"],
                "target_length": row["target_word_count"],
                "tags": _semicolon_list(row["tags"]),
            },
            article_ready=True,
        )
    except BlogWorkflowError as error:
        raise BlogBriefCSVError((str(error),)) from error
    current_seed = str(
        normalize_brief(current_brief or {}).get("gsc_seed_query") or ""
    ).strip()
    imported_seed = str(imported_brief.get("gsc_seed_query") or "").strip()
    if current_seed and imported_seed.casefold() != current_seed.casefold():
        raise BlogBriefCSVError(
            (
                "This completed CSV belongs to a different GSC opportunity. "
                f"Expected '{current_seed}' but received '{imported_seed}'.",
            )
        )
    return {
        "row": row,
        "brief": imported_brief,
    }


def merge_imported_brief(current_brief, imported_brief):
    current = normalize_brief(current_brief)
    imported = normalize_brief(imported_brief)
    merged = {**current, **imported}
    for stale_target_field in (
        "target_entity_id", "target_entity_type", "target_sport", "source_artwork"
    ):
        merged.pop(stale_target_field, None)
    return normalize_brief(merged)


def _evidence_lines(brief, opportunity, source_date):
    reporting_context = dict(opportunity.get("reporting_context") or {})
    values = (
        ("Source", "Google Search Console saved query/page data"),
        ("Data through", source_date or opportunity.get("data_through_date") or "Not available"),
        ("Seed query", brief.get("gsc_seed_query") or opportunity.get("query") or ""),
        ("Report period", reporting_context.get("period")),
        ("Report market", reporting_context.get("market")),
        ("Report device", reporting_context.get("device")),
        ("Search type", reporting_context.get("search_type")),
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


def build_prompt_1(
    project_id,
    brief,
    *,
    source_date="",
    opportunity=None,
    product_context=None,
):
    brief = validate_brief(brief)
    opportunity = dict(opportunity or brief.get("opportunity_snapshot") or {})
    csv_text = blog_brief_template_csv_bytes(
        brief, opportunity=opportunity
    ).decode("utf-8-sig").strip()
    reference_text = product_reference_csv_bytes(product_context).decode("utf-8-sig")
    reference_count = max(0, len(reference_text.splitlines()) - 1)
    product_reference_note = (
        f"The research pack includes SPORTS_CAVE_PAGE_REFERENCE.csv with {reference_count} "
        "read-only candidates from the existing synced Sports Cave product/canonical-page index. "
        "Use it for discovery only and verify every chosen page on the public storefront."
        if reference_count
        else "No saved product reference is supplied. Research the public Sports Cave storefront directly."
    )
    return f"""SPORTS CAVE SEO BLOG STRATEGY RESEARCH - PROMPT 1

ROLE AND PURPOSE
You are completing a Sports Cave SEO Blog research brief. Do not write the final article yet.
Use the Sports Cave project knowledge or memory available in this ChatGPT project as brand context.
Use live research for current facts, current products and current URLs.

The selected Google Search Console opportunity is the starting point. Do not assume the GSC wording
is automatically the final target keyword. Research the opportunity and determine the strongest
SEO, fan-interest and commercially relevant content strategy.

PROJECT ID: {project_id}

SELECTED REAL GSC OPPORTUNITY
{_evidence_lines(brief, opportunity, source_date)}

SPORTS CAVE STOREFRONT CONTEXT
Public storefront: https://www.sportscaveshop.com/
{product_reference_note}

RESEARCH EVERYTHING
1. Determine what the searcher actually wants.
2. Choose the best primary keyword closely tied to the real GSC opportunity.
3. Find useful supporting keywords and long-tail terms without keyword stuffing.
4. Identify relevant semantic entities.
5. Identify useful fan questions and People Also Ask-style questions.
6. Classify the sport.
7. Determine the dominant search intent.
8. Choose the best article type and format.
9. Recommend the strongest fan-first article angle.
10. Create a compelling working article title.
11. Define the athlete, team, rivalry, event, season or other central topic.
12. Include a timely hook only when one genuinely exists; never manufacture urgency.
13. Decide the best target country or countries using the GSC evidence, sport, subject, likely fan
    demand and Sports Cave context. Use "All Countries / Global" only when international targeting
    is genuinely strongest. Do not mechanically assign a sport to a country.
14. Recommend a useful article length based on search intent and subject depth, never filler.
15. Choose concise, relevant tags.
16. Research the CURRENT public Sports Cave storefront and choose the best genuine live product or
    collection for natural commercial support. Never fabricate a product or assume it is live.
17. Supply the exact verified Sports Cave product/collection URL. If the ideal product does not exist,
    choose the most relevant real collection or broader Sports Cave destination.
18. Find other real Sports Cave internal links that strengthen SEO and navigation. Never invent a URL.
19. Include a YouTube URL only when it is genuinely useful, relevant and verified; otherwise leave it blank.
20. Supply every other requested CSV field that Prompt 2 needs to create the strongest article and images.

SPORTS CAVE BRAND AND SEO STANDARD
- Premium sports and collector editorial: knowledgeable, specific, original and fan-first.
- Attract organic search traffic, build topical authority and lead naturally toward a relevant Sports Cave page.
- Keep traffic first and conversion second. Never turn the brief into a long product advertisement.
- Fact-check real names, dates, scores, seasons, venues, results, records and historical claims.
- Avoid generic AI filler, fake urgency, spammy keyword stuffing and forced product mentions.
- Use only verified links. Never expose credentials, secrets, private API payloads or customer/order data.

SPORTS CAVE KEYWORD AND BRAND LOCK - MANDATORY
- Sports Cave is a premium limited-edition sports wall-art and collector brand, not a poster shop.
- Never choose "poster" or "posters" as a primary keyword, supporting keyword, article phrase,
  title/meta phrase, tag, anchor text, image filename, image alt text or caption.
- A raw GSC seed query may contain that language. Preserve gsc_seed_query exactly because it is real Google demand evidence,
  but do not blindly copy it into the Sports Cave SEO strategy.
- Translate that demand into natural premium vocabulary such as athlete wall art, athlete framed wall art,
  athlete limited-edition wall art, team wall art, collector wall art, numbered sports art or premium
  framed sports art when relevant to the actual search intent.
- Shared preferred vocabulary: {', '.join(PREFERRED_SPORTS_CAVE_VOCABULARY)}.
- Do not mechanically replace every term with "limited edition" and do not keyword-stuff. Choose the
  most natural wall-art or collector wording for the subject and audience.
- A verified legacy Sports Cave URL can retain its exact historical slug. Never rename, approximate or
  break a real URL merely because its machine-readable handle contains prohibited customer-facing wording.

CLASSIFICATION GUIDANCE
Sport must use one exact Sports Cave taxonomy value below. If none fits, use "Other: <custom sport>".
{'; '.join(SPORT_OPTIONS)}

Search intent/article type must use one exact value below. If none fits, use
"Other / Custom: <custom classification>".
{'; '.join(SEARCH_INTENT_OPTIONS)}

CSV SCHEMA — DO NOT ADD, REMOVE, RENAME OR REORDER COLUMNS
{','.join(CSV_FIELDS)}

BLANK BLOG BRIEF TEMPLATE
{csv_text}

CSV COMPLETION RULES
- Preserve gsc_seed_query exactly as supplied.
- Complete every research field except timely_hook and youtube_url, which may be blank when not legitimate.
- Use semicolons inside multi-value cells: target_markets, supporting_keywords, related_entities,
  fan_questions, verified_internal_links and tags.
- Return the header row and exactly one completed data row.
- Return no markdown, explanation, code fence or text before or after the CSV.
- Quote CSV cells correctly when they contain commas, quotation marks or line breaks.
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

SPORTS CAVE CUSTOMER-FACING VOCABULARY LOCK - MANDATORY
- Sports Cave is a premium limited-edition sports wall-art and collector brand, not a poster shop.
- Never use "poster" or "posters" in the final customer-facing package, including the article title,
  SEO title, meta description, excerpt, tags, headings, HTML body, internal-link anchor text, image
  filenames, alt text or captions.
- This rule still applies when the raw GSC query, competitors or source research use that terminology.
  Raw GSC evidence may remain unchanged in research context, but it is not final Sports Cave wording.
- Use natural language such as wall art, framed wall art, limited-edition wall art, sports artwork,
  collector edition, numbered edition or premium sports art only where relevant. Do not keyword-stuff
  or mechanically repeat "limited edition".
- Shared preferred vocabulary: {', '.join(PREFERRED_SPORTS_CAVE_VOCABULARY)}.
- Preserve the exact destination of any verified legacy URL even when its immutable slug contains the
  prohibited term; use a brand-safe descriptive anchor and never rename or approximate the URL.
- Before returning the final package, run a case-insensitive vocabulary check across every customer-facing
  field and correct any violation without changing the search intent.

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
   verified internal links, image roles/ratios/alt text, absence of placeholders and compliance with the
   Sports Cave customer-facing vocabulary lock.

Do not output JSON. Do not write to Shopify, publish, schedule, request credentials or claim that anything was uploaded.
""".strip()


def build_publish_prompt(project=None):
    """Build the universal, conversation-bound final Shopify publishing contract.

    The final Prompt 2 package in ChatGPT is authoritative. Only the stable project ID is
    included here so stale CSV or brief values can never overwrite an approved final package.
    """
    project = dict(project or {})
    project_id = str(project.get("project_id") or "").strip()
    realism = build_sports_cave_image_realism_rules(include_product_lock=True)
    return f"""SPORTS CAVE SEO BLOG - FINAL SHOPIFY PUBLISH

ROLE
You are completing the final publishing stage of the Sports Cave SEO Blog workflow in the SAME ChatGPT conversation
that created the approved article and image package.

Do not restart research, write a different article, redesign Sports Cave artwork or fall back to
stale CSV values. The FINAL approved package produced earlier in this conversation is the source
of truth. The Sports Cave OS application only generated this prompt; it has not uploaded images,
called Shopify or published anything.

PROJECT ID: {project_id}

SOURCE OF TRUTH
Use the final approved package already present in this conversation for:
- research decisions, target markets, sport and search intent
- primary and supporting keywords, article angle and final article title
- final Shopify-safe HTML
- SEO title, meta description, Shopify handle and excerpt
- author and tags
- verified Sports Cave internal links and product/collection connection
- fact-check notes
- image roles, placement markers, filenames, alt text and captions

Prompt 2 may have refined the strategy after the CSV was imported. Its final approved package wins.
If any required part of that final package is unavailable, stop and identify the missing component.
Do not reconstruct it from memory or guess.

FINAL APPROVED IMAGE ASSETS
The user will upload exactly three final approved WebP assets with this prompt:
1. Featured / cover image - 16:9, target 1600x900.
2. Editorial / support image - 3:2, target 1600x1067.
3. Product / room mockup - 4:3, target 1600x1200.

Identify each asset from its filename, dimensions, visible content and the approved image plan from
earlier in this conversation. Do not guess when roles are genuinely ambiguous. Stop before publishing
if a mandatory asset is missing, duplicated, corrupt, distorted, the wrong artwork or not the approved file.

Use the actual supplied WebPs directly. Do not create or regenerate an image during publishing unless a
strictly technical format conversion is required. Upload every approved file to Shopify and use only its
permanent Shopify CDN URL. Never use a ChatGPT, sandbox, blob, base64, signed temporary or third-party
hotlink in the final article.

For each image record its role, final filename, Shopify CDN URL, approved unique alt text and dimensions.
Set the 16:9 asset as the Shopify article image. Insert the editorial and room/product images at their
approved placement markers with correct width and height attributes and loading="lazy" below the fold.
Preserve aspect ratios. Do not duplicate the cover at the top of the body unless the approved package
explicitly requires it.

{realism}

1. INSPECT SHOPIFY BEFORE WRITING
- Connect to the connected Sports Cave Shopify store and verify the store identity.
- Locate the established public Sports Cave editorial blog. Normally use the existing News blog unless
  current Shopify structure proves another established editorial blog is correct.
- Verify the blog ID and handle. Never create another Shopify blog without explicit user instruction.
- Discover the CURRENT Shopify Admin API GraphQL query, mutation and input schema before mutation.
- Validate every GraphQL operation against that schema before executing it. Never guess field names.
- Re-check every Sports Cave internal URL from the approved package against the live storefront.

2. PREVENT DUPLICATES
Search existing articles for the exact approved handle, exact title and substantially identical content.
- No match: create the article.
- Same unpublished article from this workflow: update that same article.
- Same correctly published article: do not create another copy; read back and validate the existing article.
- Same handle attached to different content: stop and report the conflict.
Never create a second article as a workaround for a partial failure.

3. BUILD THE FINAL SHOPIFY HTML
- Use the approved final Shopify-safe HTML and make only technical corrections required for valid markup,
  CDN image insertion, removal of an accidental body H1, exact verified links or Shopify field constraints.
- Shopify renders the article title as H1. The body must contain no H1.
- Preserve the approved H2/H3 hierarchy, fan-first article, facts, SEO strategy and natural commercial
  connection in the final third.
- Insert inline images with semantic figure/img markup, approved alt text, correct width/height and optional
  approved captions. Lazy-load below-fold images.
- Preserve every verified internal URL exactly. Never invent, approximate or silently replace a URL.
- Remove every placeholder. No temporary URLs, base64 images, scripts or duplicate JSON-LD in the body.

4. SPORTS CAVE VOCABULARY SAFETY GATE - MANDATORY
Before any Shopify mutation, scan all customer-facing content case-insensitively for the prohibited words
"poster" and "posters". Check the title, HTML body, headings, excerpt, SEO title, meta description, tags,
internal-link anchor text, image filenames, alt text and captions.

Sports Cave is a premium limited-edition sports wall-art and collector brand. Use natural alternatives such
as sports wall art, framed wall art, limited-edition wall art, premium sports art, sports artwork, collector
wall art, collector edition, numbered edition, collector series, athlete wall art or team wall art as the
subject and search intent require. Do not mechanically use "limited edition" everywhere and do not keyword-stuff.
Shared preferred vocabulary: {', '.join(PREFERRED_SPORTS_CAVE_VOCABULARY)}.

If prohibited customer-facing wording exists, make the smallest brand-safe correction before publication.
Do not redo research, alter the approved search intent or corrupt raw GSC evidence. A verified historical
Shopify URL may retain its exact legacy slug even if the machine-readable URL contains the prohibited term;
do not rename it or break redirects. If wording cannot be corrected safely without changing the approved
strategy, stop instead of publishing.

5. POPULATE SHOPIFY ARTICLE FIELDS
Using the current supported Admin API schema, populate every applicable native field from the approved package:
- title
- complete final HTML body
- summary / excerpt
- exact approved handle
- author
- concise approved tags
- featured article WebP and approved alt text
- immediate published status

PUBLISH THE APPROVED ARTICLE LIVE once validation succeeds. Do not stop at Draft and do not schedule it
unless the approved package and the user explicitly require scheduling instead of immediate publication.

6. APPLY SHOPIFY SEO METADATA
Set Shopify's supported article SEO metafields using the current schema and proper supported types:
- namespace global, key title_tag, value approved SEO title
- namespace global, key description_tag, value approved meta description

Check sensible metadata length and search intent without rewriting the approved strategy. Never create
seo.hidden, noindex, nofollow or unsupported SEO fields. The article is intended to be indexable.

7. PRE-PUBLISH INTEGRITY CHECK
Before mutation verify:
- approved search intent and primary keyword remain natural
- title, SEO title, meta description, handle, excerpt, author and tags are present
- no body H1 and headings are logical
- all internal URLs are current and verified
- the Sports Cave commercial link is natural and in its intended section
- facts remain consistent with the approved package
- all three WebPs are uploaded, correctly assigned and use unique approved alt text
- inline images use permanent Shopify CDN URLs with correct proportions
- no placeholders, temporary URLs, duplicate article or noindex instruction exists
- the Sports Cave vocabulary safety gate passes

Fix only safe technical or brand-vocabulary issues. Stop when a major requirement cannot be fixed without
changing the approved content strategy.

8. PUBLISH AND READ BACK
Execute the validated create or update mutation with immediate live publication. After the mutation, query
Shopify again and verify the saved article ID, blog, title, handle, body, summary, author, tags, featured image,
featured alt text where exposed, isPublished=true, publishedAt, global.title_tag and global.description_tag.
Correct any safe field that did not persist. Do not report success from the mutation request alone.

9. LIVE STOREFRONT QA
Build the public URL from the verified domain, blog handle and article handle, then open it and validate where
technically possible:
- successful public response and visible correct article title
- exactly one main H1 and no body H1
- sensible heading hierarchy and readable article HTML
- featured and inline images load, are not broken or distorted, and expose useful unique alt text
- internal Sports Cave links work
- document title and meta description match the approved SEO values
- canonical points to the exact article URL
- no noindex directive or accidental nofollow exists
- no placeholders, temporary image URLs or non-Shopify image hotlinks remain
- Article or BlogPosting structured data is present when the existing theme supplies it
- normal Shopify sitemap discoverability where practical
- Sports Cave vocabulary gate still passes on the rendered customer-facing page

Do not inject duplicate JSON-LD or edit the live theme. Report missing theme structured data separately.
Never claim Google has indexed, ranked or rewarded the article merely because it was published.

FAILURE RULES
Never guess through missing assets, ambiguous blog selection, duplicate conflicts, API/schema errors,
permission failures, image upload failures, invalid HTML, SEO metafield failures or publication failures.
Do not silently omit SEO metadata, the cover image or live publication. Identify the exact failure and what
remains. Do not create another article to recover from a partial mutation.

FINAL RESPONSE
Return this concise evidence-based report and never mark PASS without checking it:

PUBLISHED: YES

Article:
[final article title]

Live URL:
[public Sports Cave article URL]

Target keyword:
[approved primary keyword]

Shopify blog:
[verified blog title]

SEO title:
[final SEO title] ([character count])

Meta description:
[final meta description] ([character count])

Handle:
[verified handle]

Images:
- Featured WebP: PASS
- Editorial WebP: PASS
- Room/Product WebP: PASS

SEO validation:
- Published: PASS
- Indexable: PASS
- Canonical: PASS
- One H1: PASS
- SEO title: PASS
- Meta description: PASS
- Internal links: PASS
- Image alt text: PASS
- Shopify CDN images: PASS
- No placeholders: PASS
- Sports Cave vocabulary: PASS

Mark anything that could not be verified as MANUAL REVIEW REQUIRED. Do not output JSON, request credentials
or claim an upload/publication occurred when it did not.
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
