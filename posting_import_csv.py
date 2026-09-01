from __future__ import annotations

import csv
import io
import re
from urllib.parse import unquote, urlparse


POSTING_IMPORT_SCHEMA_VERSION = "SPORTS_CAVE_POSTING_IMPORT_V1"
POSTING_IMPORT_FILENAME = "posting-import.csv"
POSTING_IMPORT_HEADERS = (
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
    "AUS": "AUS",
    "Australia": "AUS",
    "USA": "USA",
    "UK": "UK",
    "CAN": "CAN",
    "Canada": "CAN",
    "NZ": "NZ",
    "New Zealand": "NZ",
}
POSTING_IMPORT_MAX_BYTES = 2 * 1024 * 1024


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


def canonical_posting_country(value):
    clean = str(value or "").strip()
    country = POSTING_IMPORT_COUNTRY_MAP.get(clean)
    if not country:
        raise PostingImportCSVError(
            "Country must be one of: AUS, USA, UK, CAN, NZ."
        )
    return country


def build_posting_import_rows(
    *,
    product_name,
    product_handle="",
    product_url,
    country,
    sport_category,
    campaign_type,
    ads,
):
    clean_url = str(product_url or "").strip()
    clean_handle = str(product_handle or "").strip().casefold()
    if not clean_handle:
        clean_handle = posting_product_handle_from_url(clean_url)
    rows = []
    for index, raw_ad in enumerate(tuple(ads or ()), start=1):
        raw_ad = dict(raw_ad or {})
        rows.append(
            {
                "schema_version": POSTING_IMPORT_SCHEMA_VERSION,
                "product_name": str(product_name or "").strip(),
                "product_handle": clean_handle,
                "product_url": clean_url,
                "country": canonical_posting_country(country),
                "sport_category": str(sport_category or "").strip(),
                "campaign_type": str(campaign_type or "").strip(),
                "ad_number": raw_ad.get("ad_number") or index,
                "primary_text": preserve_posting_text(raw_ad.get("primary_text")),
                "headline": preserve_posting_text(raw_ad.get("headline")),
                "description": preserve_posting_text(raw_ad.get("description")),
            }
        )
    return validate_posting_import_rows(rows)


def _allowed(value, allowed_values, *, label):
    allowed = tuple(str(item or "").strip() for item in allowed_values or () if str(item or "").strip())
    if allowed and value not in allowed:
        raise PostingImportCSVError(
            f"{label} must be one of: {', '.join(allowed)}."
        )


def validate_posting_import_rows(
    rows,
    *,
    allowed_countries=(),
    allowed_sports=(),
    allowed_campaign_types=(),
):
    rows = [dict(row or {}) for row in rows or ()]
    if len(rows) != 3:
        raise PostingImportCSVError(
            f"Posting CSV must contain exactly three ad rows; found {len(rows)}."
        )

    parsed = []
    seen_numbers = set()
    shared_fields = (
        "product_name",
        "product_handle",
        "product_url",
        "country",
        "sport_category",
        "campaign_type",
    )
    baseline = None
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
        try:
            ad_number = int(row["ad_number"].strip())
        except ValueError as error:
            raise PostingImportCSVError(
                f"Row {row_index} has an invalid ad_number."
            ) from error
        if ad_number not in {1, 2, 3}:
            raise PostingImportCSVError("ad_number values must be exactly 1, 2 and 3.")
        if ad_number in seen_numbers:
            raise PostingImportCSVError(f"ad_number {ad_number} is duplicated.")
        seen_numbers.add(ad_number)

        for field in shared_fields:
            row[field] = row[field].strip()
            if not row[field]:
                raise PostingImportCSVError(
                    f"Row {row_index} is missing required {field}."
                )
        handle = row["product_handle"].casefold()
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", handle):
            raise PostingImportCSVError(
                f"Row {row_index} has an invalid product_handle."
            )
        row["product_handle"] = handle
        parsed_url = urlparse(row["product_url"])
        if parsed_url.scheme.casefold() != "https" or not parsed_url.netloc:
            raise PostingImportCSVError(
                f"Row {row_index} has an invalid product_url."
            )
        url_handle = posting_product_handle_from_url(row["product_url"])
        if url_handle and url_handle != handle:
            raise PostingImportCSVError(
                f"Row {row_index} product_handle does not match product_url."
            )
        row["country"] = canonical_posting_country(row["country"])
        _allowed(row["country"], allowed_countries, label="Country")
        _allowed(row["sport_category"], allowed_sports, label="Sport/category")
        _allowed(row["campaign_type"], allowed_campaign_types, label="Campaign type")
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
        row["schema_version"] = POSTING_IMPORT_SCHEMA_VERSION
        row["ad_number"] = ad_number
        parsed.append(row)

    if seen_numbers != {1, 2, 3}:
        raise PostingImportCSVError("ad_number values must be exactly 1, 2 and 3.")
    return tuple(sorted(parsed, key=lambda row: row["ad_number"]))


def serialize_posting_import_csv(rows):
    clean_rows = validate_posting_import_rows(rows)
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


def parse_posting_import_csv(
    data,
    *,
    filename=POSTING_IMPORT_FILENAME,
    allowed_countries=(),
    allowed_sports=(),
    allowed_campaign_types=(),
):
    if not str(filename or "").casefold().endswith(".csv"):
        raise PostingImportCSVError("Upload posting-import.csv as a .csv file.")
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
    try:
        reader = csv.DictReader(io.StringIO(decoded, newline=""))
        headers = tuple(reader.fieldnames or ())
        if headers != POSTING_IMPORT_HEADERS:
            raise PostingImportCSVError(
                "Posting CSV headers must remain exactly: "
                + ", ".join(POSTING_IMPORT_HEADERS)
                + "."
            )
        rows = []
        for row_number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise PostingImportCSVError(
                    f"Posting CSV row {row_number} has a quoting or column-count problem."
                )
            if any(preserve_posting_text(value).strip() for value in row.values()):
                rows.append(row)
    except PostingImportCSVError:
        raise
    except (csv.Error, AttributeError) as error:
        raise PostingImportCSVError(
            "Posting CSV could not be read. Check its quoting and line breaks."
        ) from error

    clean_rows = validate_posting_import_rows(
        rows,
        allowed_countries=allowed_countries,
        allowed_sports=allowed_sports,
        allowed_campaign_types=allowed_campaign_types,
    )
    first = clean_rows[0]
    return {
        "schema_version": POSTING_IMPORT_SCHEMA_VERSION,
        "product_name": first["product_name"],
        "product_handle": first["product_handle"],
        "product_url": first["product_url"],
        "country": first["country"],
        "sport_category": first["sport_category"],
        "campaign_type": first["campaign_type"],
        "ads": tuple(
            {
                "ad_number": row["ad_number"],
                "primary_text": row["primary_text"],
                "headline": row["headline"],
                "description": row["description"],
            }
            for row in clean_rows
        ),
        "rows": clean_rows,
    }
