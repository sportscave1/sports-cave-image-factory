from __future__ import annotations

import csv
import io
import re
from urllib.parse import unquote, urlparse


POSTING_IMPORT_SCHEMA_VERSION = "SPORTS_CAVE_POSTING_IMPORT_V2"
POSTING_IMPORT_LEGACY_SCHEMA_VERSION = "SPORTS_CAVE_POSTING_IMPORT_V1"
POSTING_IMPORT_FILENAME = "posting-import.csv"
POSTING_IMPORT_VARIATION_COUNT = 3
POSTING_IMPORT_PRIMARY_VARIATION = 1
POSTING_IMPORT_HEADERS = (
    "schema_version",
    "product_name",
    "product_handle",
    "product_url",
    "country",
    "sport_category",
    "campaign_type",
    "output_mode",
    "ad_number",
    "route_key",
    "route_label",
    "variation",
    "description_key",
    "description_label",
    "primary_text",
    "headline",
    "description",
    "cta",
)
POSTING_IMPORT_LEGACY_HEADERS = (
    "schema_version",
    "product_name",
    "product_handle",
    "product_url",
    "country",
    "sport_category",
    "campaign_type",
    "ad_number",
    "primary_text",
    "headline",
    "description",
)
POSTING_IMPORT_COUNTRY_MAP = {
    "aus": "AUS",
    "australia": "AUS",
    "usa": "USA",
    "united_states": "USA",
    "united_states_of_america": "USA",
    "uk": "UK",
    "united_kingdom": "UK",
    "can": "CAN",
    "canada": "CAN",
    "nz": "NZ",
    "new_zealand": "NZ",
}
POSTING_IMPORT_HEADER_ALIASES = {
    "sport": "sport_category",
    "category": "sport_category",
    "sport_or_category": "sport_category",
    "sport_and_category": "sport_category",
    "ad": "ad_number",
    "ad_no": "ad_number",
    "ad_num": "ad_number",
    "primary_copy": "primary_text",
    "meta_description": "description",
    "call_to_action": "cta",
}
POSTING_IMPORT_MAX_BYTES = 2 * 1024 * 1024
ADS_CSV_IMPORT_RUNTIME_VERSION = "2026-09-03-route-primary-text-v4"
ADS_COPY_SCHEMA_VERSION = "2"
ADS_COPY_CAMPAIGN_TYPE = "instant_experience"
ADS_COPY_HEADERS = (
    "schema_version",
    "campaign_type",
    "output_mode",
    "route_key",
    "route_label",
    "variation",
    "description_key",
    "description_label",
    "primary_text",
    "headline",
    "cta",
)
ADS_COPY_REQUIRED_HEADERS = frozenset(
    {
        "schema_version",
        "campaign_type",
        "output_mode",
        "route_key",
        "route_label",
        "variation",
        "primary_text",
        "headline",
        "cta",
    }
)


class PostingImportCSVError(ValueError):
    pass


def preserve_posting_text(value):
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n")


def posting_product_handle_from_url(value):
    parsed = urlparse(str(value or "").strip())
    parts = [unquote(part).strip() for part in parsed.path.split("/") if part.strip()]
    if len(parts) < 2 or parts[-2].casefold() != "products":
        return ""
    handle = parts[-1].strip().casefold()
    return handle if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", handle) else ""


def _normalise_token(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().casefold()).strip("_")


def _normalise_header(value):
    normalised = _normalise_token(str(value or "").lstrip("\ufeff"))
    return POSTING_IMPORT_HEADER_ALIASES.get(normalised, normalised)


def canonical_posting_country(value):
    clean = _normalise_token(value)
    country = POSTING_IMPORT_COUNTRY_MAP.get(clean)
    if not country:
        raise PostingImportCSVError("Country must be one of: AUS, USA, UK, CAN, NZ.")
    return country


def _default_variation_identity(variation):
    number = int(variation)
    return {
        "description_key": "primary" if number == 1 else f"option_{number}",
        "description_label": f"Description option {number}",
    }


def _normalise_ad_variations(raw_ad):
    raw_ad = dict(raw_ad or {})
    raw_variations = raw_ad.get("variations")
    if not isinstance(raw_variations, (list, tuple)):
        raw_variations = (raw_ad,)
    by_number = {}
    for fallback_number, raw_variation in enumerate(raw_variations, start=1):
        raw_variation = dict(raw_variation or {})
        try:
            variation_number = int(raw_variation.get("variation") or fallback_number)
        except (TypeError, ValueError):
            variation_number = fallback_number
        if variation_number not in range(1, POSTING_IMPORT_VARIATION_COUNT + 1):
            continue
        by_number[variation_number] = raw_variation

    variations = []
    for variation_number in range(1, POSTING_IMPORT_VARIATION_COUNT + 1):
        raw_variation = dict(by_number.get(variation_number) or {})
        defaults = _default_variation_identity(variation_number)
        variations.append(
            {
                "variation": variation_number,
                "description_key": str(
                    raw_variation.get("description_key") or defaults["description_key"]
                ).strip(),
                "description_label": str(
                    raw_variation.get("description_label") or defaults["description_label"]
                ).strip(),
                "primary_text": preserve_posting_text(raw_variation.get("primary_text")),
                "headline": preserve_posting_text(raw_variation.get("headline")),
                "description": preserve_posting_text(
                    raw_variation.get("description")
                    if raw_variation.get("description") is not None
                    else raw_ad.get("description") if variation_number == 1 else ""
                ),
                "cta": preserve_posting_text(raw_variation.get("cta")),
            }
        )
    return tuple(variations)


def build_ads_copy_rows(*, output_mode, ads):
    rows = []
    for ad_number, raw_ad in enumerate(tuple(ads or ()), start=1):
        raw_ad = dict(raw_ad or {})
        route_key = str(raw_ad.get("route_key") or f"ad_{ad_number}").strip()
        route_label = str(raw_ad.get("route_label") or f"Ad {ad_number}").strip()
        for variation in _normalise_ad_variations(raw_ad):
            rows.append(
                {
                    "schema_version": ADS_COPY_SCHEMA_VERSION,
                    "campaign_type": ADS_COPY_CAMPAIGN_TYPE,
                    "output_mode": str(output_mode or "").strip(),
                    "route_key": route_key,
                    "route_label": route_label,
                    "variation": variation["variation"],
                    "description_key": variation["description_key"],
                    "description_label": variation["description_label"],
                    "primary_text": variation["primary_text"],
                    "headline": variation["headline"],
                    "cta": variation["cta"],
                }
            )
    return validate_ads_copy_rows(rows, require_copy=False)


def build_posting_import_rows(
    *,
    product_name,
    product_handle="",
    product_url,
    country,
    sport_category,
    campaign_type,
    ads,
    output_mode="standard_three_descriptions",
):
    clean_url = str(product_url or "").strip()
    clean_handle = str(product_handle or "").strip().casefold()
    if not clean_handle:
        clean_handle = posting_product_handle_from_url(clean_url)
    rows = []
    for index, raw_ad in enumerate(tuple(ads or ()), start=1):
        raw_ad = dict(raw_ad or {})
        ad_number = raw_ad.get("ad_number") or index
        route_key = str(raw_ad.get("route_key") or f"ad_{ad_number}").strip()
        route_label = str(raw_ad.get("route_label") or f"Ad {ad_number}").strip()
        for variation in _normalise_ad_variations(raw_ad):
            rows.append(
                {
                    "schema_version": POSTING_IMPORT_SCHEMA_VERSION,
                    "product_name": str(product_name or "").strip(),
                    "product_handle": clean_handle,
                    "product_url": clean_url,
                    "country": canonical_posting_country(country),
                    "sport_category": str(sport_category or "").strip(),
                    "campaign_type": str(campaign_type or "").strip(),
                    "output_mode": str(output_mode or "standard_three_descriptions").strip(),
                    "ad_number": ad_number,
                    "route_key": route_key,
                    "route_label": route_label,
                    **variation,
                }
            )
    return validate_posting_import_rows(rows, require_primary_ads=False)


def _allowed(value, allowed_values, *, label):
    allowed = tuple(
        str(item or "").strip()
        for item in allowed_values or ()
        if str(item or "").strip()
    )
    if allowed and value not in allowed:
        raise PostingImportCSVError(f"{label} must be one of: {', '.join(allowed)}.")


def validate_ads_copy_rows(rows, *, require_copy=True):
    rows = [dict(row or {}) for row in rows or ()]
    expected_rows = 3 * POSTING_IMPORT_VARIATION_COUNT
    if len(rows) != expected_rows:
        raise PostingImportCSVError(
            f"Ads CSV must contain exactly {expected_rows} copy rows "
            f"(three routes with three description options each); found {len(rows)}."
        )

    parsed = []
    seen = set()
    route_order = []
    baseline = None
    for row_index, raw_row in enumerate(rows, start=1):
        row = {
            header: preserve_posting_text(raw_row.get(header))
            for header in ADS_COPY_HEADERS
        }
        schema_version = row["schema_version"].strip()
        if schema_version not in {ADS_COPY_SCHEMA_VERSION, "1"}:
            raise PostingImportCSVError(
                f"Row {row_index} has an unsupported schema_version."
            )
        row["campaign_type"] = row["campaign_type"].strip()
        if _normalise_token(row["campaign_type"]) != _normalise_token(
            ADS_COPY_CAMPAIGN_TYPE
        ):
            raise PostingImportCSVError(
                f"Row {row_index} campaign_type must be {ADS_COPY_CAMPAIGN_TYPE}."
            )
        row["output_mode"] = row["output_mode"].strip()
        if not row["output_mode"]:
            raise PostingImportCSVError(f"Row {row_index} is missing required output_mode.")
        route_key = row["route_key"].strip()
        route_label = row["route_label"].strip()
        if not route_key:
            raise PostingImportCSVError(f"Row {row_index} is missing required route_key.")
        if not route_label:
            raise PostingImportCSVError(f"Row {row_index} is missing required route_label.")
        try:
            variation = int(row["variation"].strip())
        except ValueError as error:
            raise PostingImportCSVError(
                f"Row {row_index} has an invalid variation."
            ) from error
        if variation not in range(1, POSTING_IMPORT_VARIATION_COUNT + 1):
            raise PostingImportCSVError("variation values must be exactly 1, 2 and 3.")
        identity = (route_key, variation)
        if identity in seen:
            raise PostingImportCSVError(
                f"Route {route_key} variation {variation} is duplicated."
            )
        seen.add(identity)
        if route_key not in route_order:
            route_order.append(route_key)

        defaults = _default_variation_identity(variation)
        row["description_key"] = (
            row["description_key"].strip() or defaults["description_key"]
        )
        row["description_label"] = (
            row["description_label"].strip() or defaults["description_label"]
        )
        if require_copy:
            for field, label in (
                ("primary_text", "Description"),
                ("headline", "Headline"),
                ("cta", "CTA"),
            ):
                if not row[field].strip():
                    raise PostingImportCSVError(
                        f"{route_label} variation {variation} {label} is required."
                    )
        shared = (_normalise_token(row["campaign_type"]), row["output_mode"])
        if baseline is None:
            baseline = shared
        elif shared != baseline:
            raise PostingImportCSVError(
                "All copy rows must use the same campaign_type and output_mode."
            )
        row["schema_version"] = ADS_COPY_SCHEMA_VERSION
        row["campaign_type"] = ADS_COPY_CAMPAIGN_TYPE
        row["route_key"] = route_key
        row["route_label"] = route_label
        row["variation"] = variation
        parsed.append(row)

    if len(route_order) != 3:
        raise PostingImportCSVError("Ads CSV must contain exactly three stable route_key values.")
    expected = {
        (route_key, variation)
        for route_key in route_order
        for variation in range(1, POSTING_IMPORT_VARIATION_COUNT + 1)
    }
    if seen != expected:
        raise PostingImportCSVError(
            "Each Ads CSV route must contain description options 1, 2 and 3."
        )
    route_index = {route_key: index for index, route_key in enumerate(route_order)}
    return tuple(
        sorted(
            parsed,
            key=lambda row: (route_index[row["route_key"]], row["variation"]),
        )
    )


def serialize_ads_copy_csv(rows, *, allow_incomplete=False):
    clean_rows = validate_ads_copy_rows(rows, require_copy=not allow_incomplete)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=ADS_COPY_HEADERS,
        lineterminator="\r\n",
        extrasaction="ignore",
    )
    writer.writeheader()
    writer.writerows(clean_rows)
    return output.getvalue().encode("utf-8-sig")


def _validate_shared_fields(row, row_index, *, allowed_countries, allowed_sports, allowed_campaign_types):
    for field in (
        "product_name",
        "product_handle",
        "product_url",
        "country",
        "sport_category",
        "campaign_type",
        "output_mode",
    ):
        row[field] = row[field].strip()
        if not row[field]:
            raise PostingImportCSVError(f"Row {row_index} is missing required {field}.")
    handle = row["product_handle"].casefold()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", handle):
        raise PostingImportCSVError(f"Row {row_index} has an invalid product_handle.")
    row["product_handle"] = handle
    parsed_url = urlparse(row["product_url"])
    if parsed_url.scheme.casefold() != "https" or not parsed_url.netloc:
        raise PostingImportCSVError(f"Row {row_index} has an invalid product_url.")
    url_handle = posting_product_handle_from_url(row["product_url"])
    if url_handle and url_handle != handle:
        raise PostingImportCSVError(
            f"Row {row_index} product_handle does not match product_url."
        )
    row["country"] = canonical_posting_country(row["country"])
    _allowed(row["country"], allowed_countries, label="Country")
    _allowed(row["sport_category"], allowed_sports, label="Sport/category")
    _allowed(row["campaign_type"], allowed_campaign_types, label="Campaign type")


def validate_posting_import_rows(
    rows,
    *,
    allowed_countries=(),
    allowed_sports=(),
    allowed_campaign_types=(),
    require_primary_ads=True,
):
    rows = [dict(row or {}) for row in rows or ()]
    expected_rows = 3 * POSTING_IMPORT_VARIATION_COUNT
    if len(rows) != expected_rows:
        raise PostingImportCSVError(
            f"Posting CSV must contain exactly {expected_rows} copy rows "
            f"(three ads with three description options each); found {len(rows)}."
        )

    parsed = []
    seen = set()
    baseline = None
    route_identity_by_ad = {}
    route_keys = set()
    shared_fields = (
        "product_name",
        "product_handle",
        "product_url",
        "country",
        "sport_category",
        "campaign_type",
        "output_mode",
    )
    for row_index, raw_row in enumerate(rows, start=1):
        row = {
            header: preserve_posting_text(raw_row.get(header))
            for header in POSTING_IMPORT_HEADERS
        }
        if row["schema_version"].strip() != POSTING_IMPORT_SCHEMA_VERSION:
            raise PostingImportCSVError(
                f"Row {row_index} has an unsupported schema_version. "
                f"Expected {POSTING_IMPORT_SCHEMA_VERSION}."
            )
        _validate_shared_fields(
            row,
            row_index,
            allowed_countries=allowed_countries,
            allowed_sports=allowed_sports,
            allowed_campaign_types=allowed_campaign_types,
        )
        try:
            ad_number = int(row["ad_number"].strip())
            variation = int(row["variation"].strip())
        except ValueError as error:
            raise PostingImportCSVError(
                f"Row {row_index} has an invalid ad_number or variation."
            ) from error
        if ad_number not in {1, 2, 3}:
            raise PostingImportCSVError("ad_number values must be exactly 1, 2 and 3.")
        if variation not in range(1, POSTING_IMPORT_VARIATION_COUNT + 1):
            raise PostingImportCSVError("variation values must be exactly 1, 2 and 3.")
        identity = (ad_number, variation)
        if identity in seen:
            raise PostingImportCSVError(
                f"Ad {ad_number} variation {variation} is duplicated."
            )
        seen.add(identity)

        row["route_key"] = row["route_key"].strip()
        row["route_label"] = row["route_label"].strip()
        row["description_key"] = row["description_key"].strip()
        row["description_label"] = row["description_label"].strip()
        for field in ("route_key", "route_label", "description_key", "description_label"):
            if not row[field]:
                raise PostingImportCSVError(f"Row {row_index} is missing required {field}.")
        route_identity = (row["route_key"], row["route_label"])
        prior_route = route_identity_by_ad.setdefault(ad_number, route_identity)
        if prior_route != route_identity:
            raise PostingImportCSVError(
                f"Ad {ad_number} has conflicting route identity values."
            )
        route_keys.add(row["route_key"])

        shared = tuple(row[field] for field in shared_fields)
        if baseline is None:
            baseline = shared
        elif shared != baseline:
            conflicts = [
                field
                for field, expected, actual in zip(shared_fields, baseline, shared)
                if expected != actual
            ]
            raise PostingImportCSVError(
                "All copy rows must use the same shared values. Conflicting: "
                + ", ".join(conflicts)
                + "."
            )
        if require_primary_ads and variation == POSTING_IMPORT_PRIMARY_VARIATION:
            if not row["primary_text"].strip():
                raise PostingImportCSVError(f"Ad {ad_number} Primary Text is required.")
            if not row["headline"].strip():
                raise PostingImportCSVError(f"Ad {ad_number} Headline is required.")
        row["schema_version"] = POSTING_IMPORT_SCHEMA_VERSION
        row["ad_number"] = ad_number
        row["variation"] = variation
        parsed.append(row)

    expected_identities = {
        (ad_number, variation)
        for ad_number in (1, 2, 3)
        for variation in range(1, POSTING_IMPORT_VARIATION_COUNT + 1)
    }
    if seen != expected_identities:
        raise PostingImportCSVError(
            "Posting CSV must contain every ad_number and variation combination from 1 to 3."
        )
    if len(route_keys) != 3:
        raise PostingImportCSVError("Each ad must use a different stable route_key.")
    return tuple(sorted(parsed, key=lambda row: (row["ad_number"], row["variation"])))


def _validate_legacy_posting_rows(
    rows,
    *,
    allowed_countries=(),
    allowed_sports=(),
    allowed_campaign_types=(),
):
    if len(rows) != 3:
        raise PostingImportCSVError(
            f"Legacy Posting CSV must contain exactly three ad rows; found {len(rows)}."
        )
    parsed = []
    seen_numbers = set()
    baseline = None
    shared_fields = (
        "product_name",
        "product_handle",
        "product_url",
        "country",
        "sport_category",
        "campaign_type",
    )
    for row_index, raw_row in enumerate(rows, start=1):
        row = {
            header: preserve_posting_text(raw_row.get(header))
            for header in POSTING_IMPORT_LEGACY_HEADERS
        }
        row["output_mode"] = "legacy_posting_v1"
        if row["schema_version"].strip() != POSTING_IMPORT_LEGACY_SCHEMA_VERSION:
            raise PostingImportCSVError(f"Row {row_index} has an unsupported schema_version.")
        _validate_shared_fields(
            row,
            row_index,
            allowed_countries=allowed_countries,
            allowed_sports=allowed_sports,
            allowed_campaign_types=allowed_campaign_types,
        )
        try:
            ad_number = int(row["ad_number"].strip())
        except ValueError as error:
            raise PostingImportCSVError(f"Row {row_index} has an invalid ad_number.") from error
        if ad_number not in {1, 2, 3}:
            raise PostingImportCSVError("ad_number values must be exactly 1, 2 and 3.")
        if ad_number in seen_numbers:
            raise PostingImportCSVError(f"ad_number {ad_number} is duplicated.")
        seen_numbers.add(ad_number)
        if not row["primary_text"].strip():
            raise PostingImportCSVError(f"Ad {ad_number} Primary Text is required.")
        if not row["headline"].strip():
            raise PostingImportCSVError(f"Ad {ad_number} Headline is required.")
        shared = tuple(row[field] for field in shared_fields)
        if baseline is None:
            baseline = shared
        elif shared != baseline:
            conflicts = [
                field
                for field, expected, actual in zip(shared_fields, baseline, shared)
                if expected != actual
            ]
            raise PostingImportCSVError(
                "All three rows must use the same shared values. Conflicting: "
                + ", ".join(conflicts)
                + "."
            )
        row["ad_number"] = ad_number
        parsed.append(row)
    if seen_numbers != {1, 2, 3}:
        raise PostingImportCSVError("ad_number values must be exactly 1, 2 and 3.")
    return tuple(sorted(parsed, key=lambda row: row["ad_number"]))


def serialize_posting_import_csv(rows, *, allow_incomplete=False):
    clean_rows = validate_posting_import_rows(
        rows,
        require_primary_ads=not allow_incomplete,
    )
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=POSTING_IMPORT_HEADERS,
        lineterminator="\r\n",
        extrasaction="ignore",
    )
    writer.writeheader()
    writer.writerows(clean_rows)
    return output.getvalue().encode("utf-8-sig")


def _decoded_csv(data):
    source = bytes(data or b"")
    if not source:
        raise PostingImportCSVError("Choose a Posting CSV to import.")
    if len(source) > POSTING_IMPORT_MAX_BYTES:
        raise PostingImportCSVError("Posting CSV must be smaller than 2 MB.")
    try:
        decoded = source.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise PostingImportCSVError("Save the Posting CSV as UTF-8 and try again.") from error
    if "\x00" in decoded:
        raise PostingImportCSVError("Posting CSV contains invalid text data.")
    return decoded


def _normalised_headers(raw_headers):
    headers = []
    for position, raw_header in enumerate(raw_headers):
        header = _normalise_header(raw_header)
        headers.append("index" if position == 0 and not header else header)
    return tuple(headers)


def _read_normalised_rows(data):
    decoded = _decoded_csv(data)
    try:
        reader = csv.DictReader(io.StringIO(decoded, newline=""))
        raw_headers = tuple(reader.fieldnames or ())
        if not raw_headers:
            raise PostingImportCSVError("Posting CSV has no header row.")
        headers = _normalised_headers(raw_headers)
        if any(not header for header in headers):
            raise PostingImportCSVError("Posting CSV contains an empty column header.")
        if len(headers) != len(set(headers)):
            raise PostingImportCSVError("Posting CSV contains duplicate column headers.")
        header_map = dict(zip(raw_headers, headers))
        rows = []
        for row_number, raw_row in enumerate(reader, start=2):
            if None in raw_row or any(value is None for value in raw_row.values()):
                raise PostingImportCSVError(
                    f"Posting CSV row {row_number} has a quoting or column-count problem."
                )
            row = {
                header_map[raw_header]: preserve_posting_text(value)
                for raw_header, value in raw_row.items()
            }
            if any(value.strip() for value in row.values()):
                rows.append(row)
    except PostingImportCSVError:
        raise
    except (csv.Error, AttributeError) as error:
        raise PostingImportCSVError(
            "Posting CSV could not be parsed. Check its quoting and line breaks."
        ) from error
    return headers, rows


def _read_normalised_headers(data):
    """Read only the dispatch header; the selected parser validates all rows."""

    decoded = _decoded_csv(data)
    try:
        reader = csv.reader(io.StringIO(decoded, newline=""))
        raw_headers = tuple(next(reader, ()))
        if not raw_headers:
            raise PostingImportCSVError("Posting CSV has no header row.")
        headers = _normalised_headers(raw_headers)
        if any(not header for header in headers):
            raise PostingImportCSVError("Posting CSV contains an empty column header.")
        if len(headers) != len(set(headers)):
            raise PostingImportCSVError("Posting CSV contains duplicate column headers.")
        return headers
    except PostingImportCSVError:
        raise
    except (csv.Error, AttributeError) as error:
        raise PostingImportCSVError(
            "Posting CSV could not be parsed. Check its quoting and line breaks."
        ) from error


def posting_import_csv_header_kind(data):
    headers = _read_normalised_headers(data)
    header_set = set(headers)
    if (set(POSTING_IMPORT_HEADERS) - {"description"}).issubset(header_set):
        return "canonical"
    if (set(POSTING_IMPORT_LEGACY_HEADERS) - {"description"}).issubset(header_set):
        return "legacy_posting"
    if ADS_COPY_REQUIRED_HEADERS.issubset(header_set):
        return "ads_copy"
    return "unknown"


def _batch_from_canonical_rows(clean_rows):
    first = clean_rows[0]
    ads = []
    for ad_number in (1, 2, 3):
        ad_rows = tuple(row for row in clean_rows if row["ad_number"] == ad_number)
        primary = next(
            row
            for row in ad_rows
            if row["variation"] == POSTING_IMPORT_PRIMARY_VARIATION
        )
        ads.append(
            {
                "ad_number": ad_number,
                "route_key": primary["route_key"],
                "route_label": primary["route_label"],
                "primary_text": primary["primary_text"],
                "headline": primary["headline"],
                "description": primary["description"],
                "cta": primary["cta"],
                "variations": tuple(
                    {
                        "variation": row["variation"],
                        "description_key": row["description_key"],
                        "description_label": row["description_label"],
                        "primary_text": row["primary_text"],
                        "headline": row["headline"],
                        "description": row["description"],
                        "cta": row["cta"],
                    }
                    for row in ad_rows
                ),
            }
        )
    return {
        "schema_version": POSTING_IMPORT_SCHEMA_VERSION,
        "source_schema_version": POSTING_IMPORT_SCHEMA_VERSION,
        "product_name": first["product_name"],
        "product_handle": first["product_handle"],
        "product_url": first["product_url"],
        "country": first["country"],
        "sport_category": first["sport_category"],
        "campaign_type": first["campaign_type"],
        "output_mode": first["output_mode"],
        "ads": tuple(ads),
        "rows": clean_rows,
    }


def _batch_from_legacy_rows(clean_rows):
    first = clean_rows[0]
    return {
        "schema_version": POSTING_IMPORT_SCHEMA_VERSION,
        "source_schema_version": POSTING_IMPORT_LEGACY_SCHEMA_VERSION,
        "product_name": first["product_name"],
        "product_handle": first["product_handle"],
        "product_url": first["product_url"],
        "country": first["country"],
        "sport_category": first["sport_category"],
        "campaign_type": first["campaign_type"],
        "output_mode": "",
        "ads": tuple(
            {
                "ad_number": row["ad_number"],
                "route_key": f"ad_{row['ad_number']}",
                "route_label": f"Ad {row['ad_number']}",
                "primary_text": row["primary_text"],
                "headline": row["headline"],
                "description": row["description"],
                "cta": "",
                "variations": (),
            }
            for row in clean_rows
        ),
        "rows": clean_rows,
    }


def _batch_from_ads_copy_rows(clean_rows, source_headers):
    route_order = []
    for row in clean_rows:
        if row["route_key"] not in route_order:
            route_order.append(row["route_key"])
    ads = []
    for ad_number, route_key in enumerate(route_order, start=1):
        route_rows = tuple(
            row for row in clean_rows if row["route_key"] == route_key
        )
        primary = next(row for row in route_rows if row["variation"] == 1)
        route_primary_text = next(
            row for row in route_rows if row["variation"] == ad_number
        )
        ads.append(
            {
                "ad_number": ad_number,
                "route_key": route_key,
                "route_label": primary["route_label"],
                # New Ads exports the same ordered three-description set under
                # every image route.  Posting pairs route 1/2/3 with Primary
                # Text 1/2/3 respectively; the route-specific variation-1
                # headline/CTA contract remains unchanged.
                "primary_text": route_primary_text["primary_text"],
                "headline": primary["headline"],
                "description": "",
                "cta": primary["cta"],
                "variations": tuple(
                    {
                        "variation": row["variation"],
                        "description_key": row["description_key"],
                        "description_label": row["description_label"],
                        "primary_text": row["primary_text"],
                        "headline": row["headline"],
                        "description": "",
                        "cta": row["cta"],
                    }
                    for row in route_rows
                ),
            }
        )
    first = clean_rows[0]
    return {
        "schema_version": POSTING_IMPORT_SCHEMA_VERSION,
        "source_schema_version": ADS_COPY_SCHEMA_VERSION,
        "source_schema_kind": "ads_copy",
        "source_headers": tuple(source_headers),
        "product_name": "",
        "product_handle": "",
        "product_url": "",
        "country": "",
        "sport_category": "",
        "campaign_type": first["campaign_type"],
        "output_mode": first["output_mode"],
        "ads": tuple(ads),
        "rows": clean_rows,
    }


def _batch_from_canonical_ads_copy(parsed, concepts):
    ads = []
    rows = []
    for ad_number, concept in enumerate(tuple(concepts or ()), start=1):
        route_key = str(concept.get("id") or "")
        route_label = (
            f"{str(concept.get('display_name') or route_key).upper()} — "
            f"{str(concept.get('supporting_label') or '')}"
        )
        variations = []
        for variation_number, raw_variation in enumerate(
            tuple((parsed or {}).get(route_key) or ()),
            start=1,
        ):
            variation = {
                "variation": variation_number,
                "description_key": str(
                    raw_variation.get("description_key") or ""
                ),
                "description_label": str(
                    raw_variation.get("description_label") or ""
                ),
                "primary_text": preserve_posting_text(
                    raw_variation.get("primary_text")
                ),
                "headline": preserve_posting_text(raw_variation.get("headline")),
                "description": "",
                "cta": preserve_posting_text(raw_variation.get("cta")),
            }
            variations.append(variation)
            rows.append(
                {
                    "schema_version": ADS_COPY_SCHEMA_VERSION,
                    "campaign_type": ADS_COPY_CAMPAIGN_TYPE,
                    "output_mode": "standard_three_descriptions",
                    "route_key": route_key,
                    "route_label": route_label,
                    **variation,
                }
            )
        primary = variations[POSTING_IMPORT_PRIMARY_VARIATION - 1]
        route_primary_text = variations[ad_number - 1]
        ads.append(
            {
                "ad_number": ad_number,
                "route_key": route_key,
                "route_label": route_label,
                "primary_text": route_primary_text["primary_text"],
                "headline": primary["headline"],
                "description": "",
                "cta": primary["cta"],
                "variations": tuple(variations),
            }
        )
    return {
        "schema_version": POSTING_IMPORT_SCHEMA_VERSION,
        "source_schema_version": ADS_COPY_SCHEMA_VERSION,
        "source_schema_kind": "ads_copy",
        "source_headers": ADS_COPY_HEADERS,
        "product_name": "",
        "product_handle": "",
        "product_url": "",
        "country": "",
        "sport_category": "",
        "campaign_type": "Instant Experience",
        "output_mode": "standard_three_descriptions",
        "ads": tuple(ads),
        "rows": tuple(rows),
    }


def parse_ads_import_csv(
    data,
    *,
    allowed_countries=(),
    allowed_sports=(),
    allowed_campaign_types=(),
    require_copy=True,
):
    headers, rows = _read_normalised_rows(data)
    header_set = set(headers)
    canonical_required = set(POSTING_IMPORT_HEADERS) - {"description"}
    if canonical_required.issubset(header_set):
        clean_rows = validate_posting_import_rows(
            rows,
            allowed_countries=allowed_countries,
            allowed_sports=allowed_sports,
            allowed_campaign_types=allowed_campaign_types,
            require_primary_ads=require_copy,
        )
        batch = _batch_from_canonical_rows(clean_rows)
        batch["source_schema_kind"] = "posting"
        batch["source_headers"] = tuple(headers)
        return batch
    if ADS_COPY_REQUIRED_HEADERS.issubset(header_set):
        clean_rows = validate_ads_copy_rows(rows, require_copy=require_copy)
        return _batch_from_ads_copy_rows(clean_rows, headers)
    legacy_required = set(POSTING_IMPORT_LEGACY_HEADERS) - {"description"}
    if legacy_required.issubset(header_set):
        clean_rows = _validate_legacy_posting_rows(
            rows,
            allowed_countries=allowed_countries,
            allowed_sports=allowed_sports,
            allowed_campaign_types=allowed_campaign_types,
        )
        batch = _batch_from_legacy_rows(clean_rows)
        batch["source_schema_kind"] = "posting_legacy"
        batch["source_headers"] = tuple(headers)
        return batch
    recognised = set(ADS_COPY_HEADERS) | set(POSTING_IMPORT_HEADERS)
    if not header_set.intersection(recognised):
        raise PostingImportCSVError("No recognised Sports Cave Ads CSV columns were found.")
    missing = [
        header for header in ADS_COPY_HEADERS if header not in header_set
    ]
    if missing:
        raise PostingImportCSVError(f"Missing required column: {missing[0]}.")
    raise PostingImportCSVError("The CSV does not match a supported Sports Cave Ads format.")


def parse_posting_import_csv(
    data,
    *,
    filename=POSTING_IMPORT_FILENAME,
    allowed_countries=(),
    allowed_sports=(),
    allowed_campaign_types=(),
    require_primary_ads=True,
):
    del filename  # A valid canonical CSV is identified by content, never its filename.
    if posting_import_csv_header_kind(data) == "ads_copy":
        # New Ads owns the Instant Experience CSV contract. Posting consumes the
        # canonical parsed structure and only adapts it into its existing three-ad
        # form model; it does not independently decide whether the Ads CSV is valid.
        import ads_page

        try:
            parsed = ads_page.parse_instant_experience_copy_csv(
                data,
                {
                    "campaign_type": "Instant Experience",
                    "output_mode": "standard_three_descriptions",
                },
            )
        except ads_page.InstantExperienceCopyCSVError as error:
            raise PostingImportCSVError(str(error)) from error
        _allowed("Instant Experience", allowed_campaign_types, label="Campaign type")
        return _batch_from_canonical_ads_copy(
            parsed,
            ads_page.INSTANT_EXPERIENCE_CONCEPTS,
        )
    batch = parse_ads_import_csv(
        data,
        allowed_countries=allowed_countries,
        allowed_sports=allowed_sports,
        allowed_campaign_types=allowed_campaign_types,
        require_copy=require_primary_ads,
    )
    return batch
