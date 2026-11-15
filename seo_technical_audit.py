"""Background-only technical SEO inventory and audit services."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from html.parser import HTMLParser
import json
import logging
import os
from pathlib import Path
import threading
import time
import uuid
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from dotenv import load_dotenv
import requests

import google_seo
import google_seo_import


BASE_DIR = Path(__file__).resolve().parent
MIGRATIONS = (
    "20260817_analytics_seo_blog_rebuild.sql",
    "20260819_technical_audit_safety.sql",
)
WORKSPACE_KEY = google_seo.GOOGLE_SEO_WORKSPACE_KEY
URL_INSPECTION_ENDPOINT = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
AUDIT_PAGE_LIMIT = 20
FULL_AUDIT_PAGE_LIMIT = 500
INSPECTION_PAGE_LIMIT = 20
INTERNAL_LINK_CHECK_LIMIT = 20
RECHECK_PAGE_LIMIT = 20
AUDIT_STALE_DAYS = 7
AUDIT_LEASE_SECONDS = 30 * 60
REQUEST_INTERVAL_SECONDS = 1.0
DAILY_STOREFRONT_REQUEST_LIMIT = 60
FULL_STOREFRONT_REQUEST_LIMIT = 1_200
MAX_REDIRECTS = 5
MAX_REQUEST_ATTEMPTS = 2
RETRY_STATUS_CODES = frozenset({429, 502, 503, 504})
HEAD_FALLBACK_STATUS_CODES = frozenset({400, 403, 405, 501})
TRACKING_QUERY_PARAMETERS = frozenset(
    {
        "_ga",
        "_gl",
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "ref",
        "referrer",
    }
)
CRAWLER_USER_AGENT = "SportsCaveOSTechnicalSEOAudit/1.0"
CRAWLER_HEADERS = {
    "User-Agent": CRAWLER_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
}
_PROCESS_AUDIT_LOCK = threading.Lock()


class TechnicalAuditError(RuntimeError):
    pass


def utc_now():
    return datetime.now(timezone.utc)


def normalize_url(url):
    """Return one request identity for equivalent public storefront URLs."""
    raw = str(url or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        return ""
    scheme = "https"
    host = parsed.hostname.casefold().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return ""
    try:
        port = parsed.port
    except ValueError:
        return ""
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    path = parsed.path or "/"
    while "//" in path:
        path = path.replace("//", "/")
    if path != "/":
        path = path.rstrip("/")
    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = str(key or "").casefold()
        if lowered.startswith("utm_") or lowered in TRACKING_QUERY_PARAMETERS:
            continue
        query_items.append((key, value))
    query = urlencode(sorted(query_items), doseq=True)
    return urlunparse((scheme, netloc, path, "", query, ""))


@dataclass(frozen=True)
class CrawlResponse:
    status_code: int
    headers: dict
    text: str
    url: str


class RequestBudgetExceeded(TechnicalAuditError):
    pass


class _InjectedRequestSession:
    """Compatibility adapter for tests that inject the legacy request callable."""

    def __init__(self, request_get, request_head=None):
        self.request_get = request_get
        self.request_head = request_head or request_get
        self.headers = {}

    def request(self, method, url, **kwargs):
        callback = self.request_head if str(method).upper() == "HEAD" else self.request_get
        return callback(url, **kwargs)

    def get(self, url, **kwargs):
        return self.request_get(url, **kwargs)

    def post(self, url, **kwargs):
        return requests.post(url, **kwargs)

    def close(self):
        return None


class StorefrontCrawler:
    """One cookie-preserving, rate-limited and request-budgeted audit client."""

    def __init__(
        self,
        session,
        *,
        request_interval_seconds=REQUEST_INTERVAL_SECONDS,
        request_limit=DAILY_STOREFRONT_REQUEST_LIMIT,
        timeout=google_seo.GOOGLE_HTTP_TIMEOUT_SECONDS,
        max_redirects=MAX_REDIRECTS,
        max_attempts=MAX_REQUEST_ATTEMPTS,
        clock=time.monotonic,
        sleeper=time.sleep,
    ):
        self.session = session
        self.session.headers.update(CRAWLER_HEADERS)
        self.request_interval_seconds = max(0.0, float(request_interval_seconds or 0))
        self.request_limit = max(1, int(request_limit or 1))
        self.timeout = timeout
        self.max_redirects = max(0, int(max_redirects or 0))
        self.max_attempts = max(1, int(max_attempts or 1))
        self.clock = clock
        self.sleeper = sleeper
        self._last_request_at = None
        self._page_cache = {}
        self._status_cache = {}
        self.stats = {
            "pages_fetched": 0,
            "head_requests": 0,
            "get_requests": 0,
            "cache_hits": 0,
            "duplicate_urls_skipped": 0,
            "redirects": 0,
            "failed_requests": 0,
            "total_storefront_requests": 0,
        }

    def _throttle(self):
        now_value = self.clock()
        if self._last_request_at is not None:
            wait_seconds = self.request_interval_seconds - (now_value - self._last_request_at)
            if wait_seconds > 0:
                self.sleeper(wait_seconds)
                now_value = self.clock()
        self._last_request_at = now_value

    def _request_once(self, method, url, *, stream=False):
        method = str(method or "GET").upper()
        last_error = None
        for attempt in range(self.max_attempts):
            if self.stats["total_storefront_requests"] >= self.request_limit:
                raise RequestBudgetExceeded("The technical audit storefront request budget was exhausted.")
            self._throttle()
            self.stats["total_storefront_requests"] += 1
            self.stats["head_requests" if method == "HEAD" else "get_requests"] += 1
            try:
                response = self.session.request(
                    method,
                    url,
                    timeout=self.timeout,
                    allow_redirects=False,
                    stream=stream,
                )
            except Exception as error:
                last_error = error
                if attempt + 1 >= self.max_attempts:
                    self.stats["failed_requests"] += 1
                    raise
                continue
            status_code = int(getattr(response, "status_code", 0) or 0)
            if status_code in RETRY_STATUS_CODES and attempt + 1 < self.max_attempts:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
                continue
            return response
        self.stats["failed_requests"] += 1
        raise last_error or TechnicalAuditError("The storefront request failed.")

    def _request_following_redirects(self, method, url, *, stream=False):
        current_url = normalize_url(url)
        if not current_url:
            raise TechnicalAuditError("The storefront URL is invalid.")
        allowed_host = urlparse(current_url).netloc
        redirect_seen = {current_url}
        for redirect_index in range(self.max_redirects + 1):
            response = self._request_once(method, current_url, stream=stream)
            status_code = int(getattr(response, "status_code", 0) or 0)
            headers = dict(getattr(response, "headers", {}) or {})
            location = str(headers.get("Location") or headers.get("location") or "").strip()
            if status_code not in {301, 302, 303, 307, 308} or not location:
                text_value = "" if stream or method == "HEAD" else str(getattr(response, "text", "") or "")
                final_url = normalize_url(getattr(response, "url", "") or current_url) or current_url
                close = getattr(response, "close", None)
                if callable(close):
                    close()
                if status_code == 0 or status_code >= 400:
                    self.stats["failed_requests"] += 1
                return CrawlResponse(status_code, headers, text_value, final_url)
            if redirect_index >= self.max_redirects:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
                self.stats["failed_requests"] += 1
                raise TechnicalAuditError("The storefront redirect limit was exceeded.")
            next_url = normalize_url(urljoin(current_url, location))
            close = getattr(response, "close", None)
            if callable(close):
                close()
            if not next_url or next_url in redirect_seen:
                self.stats["failed_requests"] += 1
                raise TechnicalAuditError("The storefront returned an invalid redirect loop.")
            if urlparse(next_url).netloc != allowed_host:
                # Record the redirect finding without following an external destination.
                self.stats["redirects"] += 1
                return CrawlResponse(status_code, headers, "", next_url)
            redirect_seen.add(next_url)
            self.stats["redirects"] += 1
            current_url = next_url
        raise TechnicalAuditError("The storefront redirect could not be resolved.")

    def fetch_page(self, url):
        normalized = normalize_url(url)
        if not normalized:
            raise TechnicalAuditError("The storefront page URL is invalid.")
        if normalized in self._page_cache:
            self.stats["cache_hits"] += 1
            self.stats["duplicate_urls_skipped"] += 1
            return self._page_cache[normalized]
        response = self._request_following_redirects("GET", normalized)
        self._page_cache[normalized] = response
        self._status_cache[normalized] = response.status_code
        self.stats["pages_fetched"] += 1
        return response

    def check_status(self, url):
        normalized = normalize_url(url)
        if not normalized:
            return 0
        if normalized in self._status_cache:
            self.stats["cache_hits"] += 1
            self.stats["duplicate_urls_skipped"] += 1
            return self._status_cache[normalized]
        response = self._request_following_redirects("HEAD", normalized, stream=True)
        if response.status_code in HEAD_FALLBACK_STATUS_CODES:
            response = self._request_following_redirects("GET", normalized, stream=True)
        self._status_cache[normalized] = response.status_code
        return response.status_code
class _HTMLAuditParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title_parts = []
        self.in_title = False
        self.meta_description = ""
        self.meta_robots = ""
        self.canonical = ""
        self.h1_count = 0
        self.images = []
        self.links = []
        self.schema_types = set()

    def handle_starttag(self, tag, attrs):
        tag = str(tag or "").casefold()
        values = {str(key).casefold(): str(value or "") for key, value in attrs}
        if tag == "title":
            self.in_title = True
        elif tag == "meta":
            name = values.get("name", "").casefold()
            if name == "description":
                self.meta_description = values.get("content", "").strip()
            elif name == "robots":
                self.meta_robots = values.get("content", "").strip()
        elif tag == "link" and values.get("rel", "").casefold() == "canonical":
            self.canonical = values.get("href", "").strip()
        elif tag == "h1":
            self.h1_count += 1
        elif tag == "img":
            self.images.append({"src": values.get("src", ""), "alt": values.get("alt", "").strip()})
        elif tag == "a":
            self.links.append(values.get("href", "").strip())
        elif tag == "script" and values.get("type", "").casefold() == "application/ld+json":
            self.schema_types.add("JSON-LD")

    def handle_endtag(self, tag):
        if str(tag or "").casefold() == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(str(data or ""))


def _finding(code, severity, summary, correction, impact, *, source="HTML audit", **extra):
    return {
        "source": source,
        "severity": severity,
        "issue_code": code,
        "issue_summary": summary,
        "correction_steps": correction,
        "likely_impact": impact,
        **extra,
    }


def audit_html(url, *, status_code, headers=None, html_text="", final_url="", page_type=""):
    """Return deterministic VA-safe findings for one fetched public URL."""
    headers = {str(key).casefold(): str(value or "") for key, value in dict(headers or {}).items()}
    final_url = str(final_url or url)
    findings = []
    if int(status_code or 0) >= 400 or int(status_code or 0) == 0:
        findings.append(_finding(
            "http_error", "Critical", f"The page returned HTTP {int(status_code or 0) or 'no response'}.",
            "Check the Shopify resource, redirects and public availability, then run a background recheck.",
            "Search engines and visitors may be unable to reach the page.", http_status=int(status_code or 0),
        ))
        return findings
    if 300 <= int(status_code or 0) < 400 or normalize_url(final_url) != normalize_url(url):
        findings.append(_finding(
            "redirect", "Medium", f"The URL resolves to {final_url}.",
            "Update internal links and the canonical inventory to the final public URL.",
            "Redirect chains can waste crawl effort and weaken canonical consistency.",
            http_status=int(status_code or 0), redirect_url=final_url,
        ))

    parser = _HTMLAuditParser()
    parser.feed(str(html_text or ""))
    title = " ".join(" ".join(parser.title_parts).split())
    robots = parser.meta_robots.casefold()
    if "noindex" in robots or "noindex" in headers.get("x-robots-tag", "").casefold():
        findings.append(_finding(
            "noindex", "Critical", "The page instructs search engines not to index it.",
            "Confirm the page should be public, then remove the noindex directive through an authorised Shopify workflow.",
            "The page is not eligible to appear in organic search while noindex remains.", robots_state="noindex",
        ))
    if not title:
        findings.append(_finding(
            "missing_title", "High", "The page has no HTML title.",
            "Add a concise, page-specific title in Shopify.", "Search results lack a reliable title signal.",
        ))
    if not parser.meta_description:
        findings.append(_finding(
            "missing_meta_description", "Medium", "The page has no meta description.",
            "Add a useful summary that accurately describes the visible page.",
            "Google has less authored context for a search-result snippet.",
        ))
    if parser.h1_count != 1:
        findings.append(_finding(
            "h1_count", "High" if parser.h1_count == 0 else "Medium",
            f"The page contains {parser.h1_count} H1 headings.",
            "Keep one visible page H1 and move subordinate headings to H2/H3.",
            "An unclear heading hierarchy can make the page topic harder to interpret.",
        ))
    if not parser.canonical:
        findings.append(_finding(
            "missing_canonical", "High", "The page has no canonical link element.",
            "Set the preferred public URL through the Shopify theme or supported SEO field.",
            "Duplicate URL variants may compete for indexing signals.", user_canonical="",
        ))
    elif normalize_url(parser.canonical) != normalize_url(final_url):
        findings.append(_finding(
            "canonical_mismatch", "High", f"The page canonical points to {parser.canonical}.",
            "Confirm the intended canonical and correct either the inventory URL or canonical field.",
            "Google may select a different URL than the one being optimised.", user_canonical=parser.canonical,
        ))
    missing_alt = [row.get("src") for row in parser.images if not row.get("alt")]
    if missing_alt:
        findings.append(_finding(
            "missing_image_alt", "Medium", f"{len(missing_alt)} images have empty alt text.",
            "Describe each meaningful image naturally; leave only decorative images intentionally empty.",
            "Image accessibility and image-search context are incomplete.", affected_urls=missing_alt[:25],
        ))
    if str(page_type or "").casefold() in {"product", "blog", "article"} and not parser.schema_types:
        findings.append(_finding(
            "missing_structured_data", "Medium", "No JSON-LD structured data was found in the rendered HTML.",
            "Inspect the live theme output before adding one valid Product or Article block through an authorised workflow.",
            "Eligible rich-result information may be unavailable. Do not add duplicate schema if another renderer supplies it.",
        ))
    return findings


def internal_link_targets(source_url, html_text):
    """Return unique same-host HTTP links from rendered HTML."""
    parser = _HTMLAuditParser()
    parser.feed(str(html_text or ""))
    normalized_source = normalize_url(source_url)
    source = urlparse(normalized_source)
    output = []
    seen = set()
    for href in parser.links:
        target = normalize_url(urljoin(normalized_source, str(href or "").strip()))
        parsed = urlparse(target)
        if parsed.scheme not in {"http", "https"} or parsed.netloc != source.netloc:
            continue
        if target in seen or target == normalized_source:
            continue
        seen.add(target)
        output.append(target)
    return output


def broken_internal_link_findings(
    source_url,
    html_text,
    *,
    cache,
    remaining,
    crawler=None,
    request_get=None,
):
    checked = 0
    broken = []
    for target in internal_link_targets(source_url, html_text):
        if checked >= max(0, int(remaining)):
            break
        checked += 1
        if target not in cache:
            try:
                if crawler is not None:
                    cache[target] = int(crawler.check_status(target) or 0)
                elif request_get is not None:
                    response = request_get(
                        target,
                        timeout=google_seo.GOOGLE_HTTP_TIMEOUT_SECONDS,
                        allow_redirects=True,
                    )
                    cache[target] = int(getattr(response, "status_code", 0) or 0)
                else:
                    raise TechnicalAuditError("No background link checker was provided.")
            except Exception:
                cache[target] = 0
        if cache[target] == 0 or cache[target] >= 400:
            broken.append(target)
    if not broken:
        return [], checked
    return [
        _finding(
            "broken_internal_links", "High", f"{len(broken)} internal links failed the background check.",
            "Open each affected URL, correct or remove the link in Shopify, then queue a recheck.",
            "Visitors and search crawlers may reach unavailable pages.", affected_urls=broken[:25],
        )
    ], checked


def inspection_findings(url, payload):
    """Translate URL Inspection evidence without describing it as a live test."""
    result = dict((payload or {}).get("inspectionResult") or {})
    index = dict(result.get("indexStatusResult") or {})
    rich = dict(result.get("richResultsResult") or {})
    verdict = str(index.get("verdict") or "").upper()
    common = {
        "source": "GSC URL Inspection",
        "inspection_payload": {
            "inspection_result_link": result.get("inspectionResultLink") or "",
            "verdict": verdict,
            "coverage_state": index.get("coverageState") or "",
            "indexing_state": index.get("indexingState") or "",
            "robots_txt_state": index.get("robotsTxtState") or "",
            "page_fetch_state": index.get("pageFetchState") or "",
            "last_crawl_time": index.get("lastCrawlTime") or "",
            "google_canonical": index.get("googleCanonical") or "",
            "user_canonical": index.get("userCanonical") or "",
            "sitemap": list(index.get("sitemap") or []),
            "crawled_as": index.get("crawledAs") or "",
            "rich_results_verdict": rich.get("verdict") or "",
        },
        "index_state": index.get("indexingState") or verdict,
        "coverage_state": index.get("coverageState") or "",
        "robots_state": index.get("robotsTxtState") or "",
        "fetch_state": index.get("pageFetchState") or "",
        "last_crawl": index.get("lastCrawlTime") or None,
        "google_canonical": index.get("googleCanonical") or "",
        "user_canonical": index.get("userCanonical") or "",
        "sitemap": list(index.get("sitemap") or []),
        "crawler_type": index.get("crawledAs") or "",
        "rich_result_issues": list(rich.get("detectedItems") or []),
    }
    if verdict and verdict not in {"PASS", "NEUTRAL"}:
        return [_finding(
            "gsc_index_status", "High", index.get("coverageState") or f"Google inspection verdict: {verdict}.",
            "Open this URL in Search Console, review the saved inspection evidence and correct the reported cause.",
            "Google may not index the preferred URL.", **common,
        )]
    return []


class PostgresTechnicalAuditStore:
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
        migrations = [BASE_DIR / "migrations" / filename for filename in MIGRATIONS]
        if not all(migration.is_file() for migration in migrations):
            raise TechnicalAuditError("Technical audit storage is unavailable.")
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                for migration in migrations:
                    cursor.execute(migration.read_text(encoding="utf-8"))
            connection.commit()
        self._schema_ready = True

    def priority_urls(self, limit=AUDIT_PAGE_LIMIT, *, full=False):
        self.ensure_schema()
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT page.canonical_url, page.page_type, page.title, page.shopify_resource_id,
                           state.last_audited_at, state.last_status, state.next_eligible_at
                    FROM seo_canonical_pages AS page
                    LEFT JOIN seo_technical_page_state AS state
                      ON state.workspace_key=page.workspace_key
                     AND state.canonical_url=page.canonical_url
                    WHERE page.workspace_key=%s AND page.is_active=TRUE
                      AND LOWER(page.page_type) IN ('product','collection','blog','article','page','home')
                      AND (
                        %s OR state.normalized_url IS NULL OR state.next_eligible_at IS NULL
                        OR state.next_eligible_at <= now()
                        OR page.last_seen_at > state.last_audited_at
                      )
                    ORDER BY CASE
                               WHEN state.normalized_url IS NULL THEN 1
                               WHEN page.last_seen_at > state.last_audited_at THEN 2
                               WHEN state.next_eligible_at <= now() THEN 3
                               ELSE 4
                             END,
                             CASE LOWER(page.page_type) WHEN 'home' THEN 1 WHEN 'product' THEN 2
                              WHEN 'collection' THEN 3 WHEN 'blog' THEN 4 WHEN 'article' THEN 4 ELSE 5 END,
                             state.last_audited_at NULLS FIRST,
                             page.last_seen_at DESC
                    LIMIT %s
                    """,
                    (WORKSPACE_KEY, bool(full), int(limit)),
                )
                rows = cursor.fetchall() or []
        return [dict(row) for row in rows]

    def save_url_findings(self, url, findings):
        findings = [dict(row) for row in findings or []]
        codes = [row.get("issue_code") for row in findings if row.get("issue_code")]
        self.ensure_schema()
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE seo_technical_url_audits_v2 SET status='Resolved', last_seen_at=now()
                    WHERE workspace_key=%s AND canonical_url=%s AND status='Open'
                      AND NOT (issue_code=ANY(%s))
                    """,
                    (WORKSPACE_KEY, url, codes or ["__none__"]),
                )
                for row in findings:
                    cursor.execute(
                        """
                        INSERT INTO seo_technical_url_audits_v2(
                            workspace_key, canonical_url, source, severity, issue_code,
                            issue_summary, correction_steps, likely_impact, affected_urls,
                            http_status, redirect_url, robots_state, index_state, coverage_state,
                            fetch_state, last_crawl, google_canonical, user_canonical, sitemap,
                            crawler_type, rich_result_issues, inspection_payload, status, checked_at
                        ) VALUES (
                            %s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                            %s::jsonb,%s,%s::jsonb,%s::jsonb,'Open',now()
                        )
                        ON CONFLICT (workspace_key, canonical_url, source, issue_code) DO UPDATE SET
                            severity=EXCLUDED.severity, issue_summary=EXCLUDED.issue_summary,
                            correction_steps=EXCLUDED.correction_steps, likely_impact=EXCLUDED.likely_impact,
                            affected_urls=EXCLUDED.affected_urls, http_status=EXCLUDED.http_status,
                            redirect_url=EXCLUDED.redirect_url, robots_state=EXCLUDED.robots_state,
                            index_state=EXCLUDED.index_state, coverage_state=EXCLUDED.coverage_state,
                            fetch_state=EXCLUDED.fetch_state, last_crawl=EXCLUDED.last_crawl,
                            google_canonical=EXCLUDED.google_canonical, user_canonical=EXCLUDED.user_canonical,
                            sitemap=EXCLUDED.sitemap, crawler_type=EXCLUDED.crawler_type,
                            rich_result_issues=EXCLUDED.rich_result_issues,
                            inspection_payload=EXCLUDED.inspection_payload, status='Open',
                            last_seen_at=now(), checked_at=now()
                        """,
                        (
                            WORKSPACE_KEY, url, row.get("source") or "HTML audit",
                            row.get("severity") or "Info", row.get("issue_code") or "",
                            row.get("issue_summary") or "", row.get("correction_steps") or "",
                            row.get("likely_impact") or "", json.dumps(row.get("affected_urls") or []),
                            row.get("http_status"), row.get("redirect_url") or "",
                            row.get("robots_state") or "", row.get("index_state") or "",
                            row.get("coverage_state") or "", row.get("fetch_state") or "",
                            row.get("last_crawl"), row.get("google_canonical") or "",
                            row.get("user_canonical") or "", json.dumps(row.get("sitemap") or []),
                            row.get("crawler_type") or "", json.dumps(row.get("rich_result_issues") or []),
                            json.dumps(row.get("inspection_payload") or {}),
                        ),
                    )
            connection.commit()
        return len(findings)

    def queue_recheck(self, url, *, requested_by=""):
        self.ensure_schema()
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO seo_technical_recheck_queue_v2(id, workspace_key, canonical_url, requested_by)
                    VALUES (%s,%s,%s,%s)
                    ON CONFLICT (workspace_key, canonical_url) WHERE status IN ('queued','running')
                    DO UPDATE SET requested_by=EXCLUDED.requested_by, requested_at=now()
                    RETURNING id
                    """,
                    (str(uuid.uuid4()), WORKSPACE_KEY, url, str(requested_by or "")[:200]),
                )
                row = cursor.fetchone()
            connection.commit()
        return dict(row or {})

    def claim_rechecks(self, limit=20):
        self.ensure_schema()
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH candidates AS (
                        SELECT id FROM seo_technical_recheck_queue_v2
                        WHERE workspace_key=%s AND status='queued'
                        ORDER BY requested_at
                        FOR UPDATE SKIP LOCKED LIMIT %s
                    )
                    UPDATE seo_technical_recheck_queue_v2 AS request
                    SET status='running', error_summary=''
                    FROM candidates WHERE request.id=candidates.id
                    RETURNING request.*
                    """,
                    (WORKSPACE_KEY, int(limit)),
                )
                rows = cursor.fetchall() or []
            connection.commit()
        return [dict(row) for row in rows]

    def complete_recheck(self, request_id, *, error=""):
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE seo_technical_recheck_queue_v2
                    SET status=%s, completed_at=now(), error_summary=%s
                    WHERE id=%s RETURNING *
                    """,
                    ("failed" if error else "completed", str(error or "")[:300], request_id),
                )
                row = cursor.fetchone() or {}
            connection.commit()
        return dict(row)

    def start_audit_run(self, run_id, *, trigger_source, mode, lease_owner):
        self.ensure_schema()
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO seo_technical_audit_runs(
                        id, workspace_key, trigger_source, mode, status,
                        lease_owner, lock_state, started_at
                    ) VALUES (%s,%s,%s,%s,'starting',%s,'pending',now())
                    RETURNING *
                    """,
                    (
                        str(run_id), WORKSPACE_KEY, str(trigger_source or "background")[:100],
                        str(mode or "daily")[:20], str(lease_owner or "")[:200],
                    ),
                )
                row = cursor.fetchone() or {}
            connection.commit()
        return dict(row)

    def acquire_audit_lease(self, run_id, lease_owner, *, lease_seconds=AUDIT_LEASE_SECONDS):
        self.ensure_schema()
        expires_at = utc_now() + timedelta(seconds=max(60, int(lease_seconds or 0)))
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO seo_technical_audit_leases(
                        workspace_key, audit_run_id, lease_owner, acquired_at, lease_expires_at
                    ) VALUES (%s,%s,%s,now(),%s)
                    ON CONFLICT (workspace_key) DO UPDATE SET
                        audit_run_id=EXCLUDED.audit_run_id,
                        lease_owner=EXCLUDED.lease_owner,
                        acquired_at=now(),
                        lease_expires_at=EXCLUDED.lease_expires_at,
                        updated_at=now()
                    WHERE seo_technical_audit_leases.lease_expires_at IS NULL
                       OR seo_technical_audit_leases.lease_expires_at < now()
                    RETURNING workspace_key
                    """,
                    (WORKSPACE_KEY, str(run_id), str(lease_owner or "")[:200], expires_at),
                )
                row = cursor.fetchone()
                if row:
                    cursor.execute(
                        """
                        UPDATE seo_technical_audit_runs
                        SET status='running', lock_state='acquired', lease_expires_at=%s,
                            updated_at=now()
                        WHERE id=%s
                        """,
                        (expires_at, str(run_id)),
                    )
            connection.commit()
        return bool(row)

    def renew_audit_lease(self, run_id, lease_owner, *, lease_seconds=AUDIT_LEASE_SECONDS):
        expires_at = utc_now() + timedelta(seconds=max(60, int(lease_seconds or 0)))
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE seo_technical_audit_leases
                    SET lease_expires_at=%s, updated_at=now()
                    WHERE workspace_key=%s AND audit_run_id=%s AND lease_owner=%s
                      AND lease_expires_at >= now()
                    RETURNING workspace_key
                    """,
                    (expires_at, WORKSPACE_KEY, str(run_id), str(lease_owner or "")[:200]),
                )
                row = cursor.fetchone()
                if row:
                    cursor.execute(
                        """
                        UPDATE seo_technical_audit_runs
                        SET lease_expires_at=%s, updated_at=now() WHERE id=%s
                        """,
                        (expires_at, str(run_id)),
                    )
            connection.commit()
        return bool(row)

    def release_audit_lease(self, run_id, lease_owner):
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE seo_technical_audit_leases
                    SET lease_expires_at=now(), updated_at=now()
                    WHERE workspace_key=%s AND audit_run_id=%s AND lease_owner=%s
                    """,
                    (WORKSPACE_KEY, str(run_id), str(lease_owner or "")[:200]),
                )
            connection.commit()

    def save_page_state(
        self,
        *,
        run_id,
        normalized_url,
        canonical_url,
        page_type,
        shopify_resource_id,
        status_code,
        content_fingerprint,
        findings,
        stale_days=AUDIT_STALE_DAYS,
    ):
        next_eligible_at = utc_now() + timedelta(days=max(1, int(stale_days or 1)))
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO seo_technical_page_state(
                        workspace_key, normalized_url, canonical_url, page_type,
                        shopify_resource_id, last_audited_at, last_status,
                        content_fingerprint, last_technical_result, next_eligible_at,
                        last_audit_run_id
                    ) VALUES (%s,%s,%s,%s,%s,now(),%s,%s,%s::jsonb,%s,%s)
                    ON CONFLICT (workspace_key, normalized_url) DO UPDATE SET
                        canonical_url=EXCLUDED.canonical_url,
                        page_type=EXCLUDED.page_type,
                        shopify_resource_id=EXCLUDED.shopify_resource_id,
                        last_audited_at=now(),
                        last_status=EXCLUDED.last_status,
                        content_fingerprint=EXCLUDED.content_fingerprint,
                        last_technical_result=EXCLUDED.last_technical_result,
                        next_eligible_at=EXCLUDED.next_eligible_at,
                        last_audit_run_id=EXCLUDED.last_audit_run_id,
                        updated_at=now()
                    RETURNING normalized_url
                    """,
                    (
                        WORKSPACE_KEY, str(normalized_url), str(canonical_url),
                        str(page_type or "")[:40], str(shopify_resource_id or "")[:200],
                        int(status_code or 0), str(content_fingerprint or "")[:64],
                        json.dumps(list(findings or [])), next_eligible_at, str(run_id),
                    ),
                )
                row = cursor.fetchone() or {}
            connection.commit()
        return dict(row)

    def finish_audit_run(self, run_id, *, status, metrics, error_summary="", lock_state="released"):
        metrics = dict(metrics or {})
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE seo_technical_audit_runs
                    SET status=%s, completed_at=now(), pages_scheduled=%s,
                        pages_fetched=%s, head_requests=%s, get_requests=%s,
                        cache_hits=%s, duplicate_urls_skipped=%s, redirects=%s,
                        failed_requests=%s, total_storefront_requests=%s,
                        runtime_seconds=%s, lock_state=%s, error_summary=%s,
                        updated_at=now()
                    WHERE id=%s RETURNING *
                    """,
                    (
                        str(status or "failed")[:30], int(metrics.get("pages_scheduled") or 0),
                        int(metrics.get("pages_fetched") or 0), int(metrics.get("head_requests") or 0),
                        int(metrics.get("get_requests") or 0), int(metrics.get("cache_hits") or 0),
                        int(metrics.get("duplicate_urls_skipped") or 0), int(metrics.get("redirects") or 0),
                        int(metrics.get("failed_requests") or 0),
                        int(metrics.get("total_storefront_requests") or 0),
                        float(metrics.get("runtime_seconds") or 0), str(lock_state or "")[:30],
                        str(error_summary or "")[:500], str(run_id),
                    ),
                )
                row = cursor.fetchone() or {}
            connection.commit()
        return dict(row)


def _fetch_sitemaps(client, site_url):
    from urllib.parse import quote
    payload = client._get(
        f"{google_seo.GSC_SITES_ENDPOINT}/{quote(str(site_url), safe='')}/sitemaps",
        stage="gsc_sitemaps",
    )
    return [str(row.get("path") or "") for row in payload.get("sitemap") or [] if row.get("path")]


def _inspect_url(client, site_url, url):
    return client._post(
        URL_INSPECTION_ENDPOINT,
        {"inspectionUrl": url, "siteUrl": site_url, "languageCode": "en-AU"},
        stage="gsc_url_inspection",
    )


def _call_store(store, method_name, *args, **kwargs):
    method = getattr(store, method_name, None)
    if not callable(method):
        return None
    return method(*args, **kwargs)


def _priority_urls(store, *, limit, full):
    try:
        return list(store.priority_urls(limit=limit, full=full))
    except TypeError:
        # Compatibility for small in-memory stores used by existing callers/tests.
        return list(store.priority_urls(limit=limit))


def _audit_log(event, *, run_id, **details):
    payload = {"event": event, "audit_run_id": str(run_id), **details}
    logging.getLogger(__name__).info(json.dumps(payload, sort_keys=True, default=str))


def run_background_audit(
    *,
    store=None,
    connection_store=None,
    session=None,
    session_factory=requests.Session,
    request_get=None,
    request_head=None,
    page_limit=None,
    inspection_limit=INSPECTION_PAGE_LIMIT,
    internal_link_limit=INTERNAL_LINK_CHECK_LIMIT,
    request_interval_seconds=REQUEST_INTERVAL_SECONDS,
    request_limit=None,
    trigger_source="technical-maintenance",
    mode="daily",
    full=False,
    worker_id="",
    clock=time.monotonic,
    sleeper=time.sleep,
):
    """Run one leased, stateful and request-budgeted technical audit."""
    store = store or PostgresTechnicalAuditStore()
    connection_store = connection_store or google_seo.default_store()
    full = bool(full or str(mode or "").casefold() == "full")
    mode = "full" if full else "daily"
    page_limit = int(page_limit or (FULL_AUDIT_PAGE_LIMIT if full else AUDIT_PAGE_LIMIT))
    page_limit = max(1, min(page_limit, FULL_AUDIT_PAGE_LIMIT if full else AUDIT_PAGE_LIMIT))
    internal_link_limit = max(0, int(internal_link_limit or 0))
    inspection_limit = max(0, int(inspection_limit or 0))
    request_limit = max(
        1,
        int(request_limit or (FULL_STOREFRONT_REQUEST_LIMIT if full else DAILY_STOREFRONT_REQUEST_LIMIT)),
    )
    run_id = str(uuid.uuid4())
    lease_owner = str(
        worker_id
        or os.environ.get("RENDER_INSTANCE_ID")
        or os.environ.get("HOSTNAME")
        or f"process-{os.getpid()}"
    )[:200]
    started_at = utc_now()
    started_clock = clock()
    metrics = {
        "audit_run_id": run_id,
        "started_at": started_at.isoformat(),
        "completed_at": None,
        "trigger_source": str(trigger_source or "technical-maintenance")[:100],
        "mode": mode,
        "pages_scheduled": 0,
        "pages_fetched": 0,
        "head_requests": 0,
        "get_requests": 0,
        "cache_hits": 0,
        "duplicate_urls_skipped": 0,
        "redirects": 0,
        "failed_requests": 0,
        "total_storefront_requests": 0,
        "runtime_seconds": 0.0,
        "lock_state": "pending",
        "processed": 0,
        "written": 0,
    }
    _call_store(
        store,
        "start_audit_run",
        run_id,
        trigger_source=metrics["trigger_source"],
        mode=mode,
        lease_owner=lease_owner,
    )

    process_lock_acquired = False
    has_durable_lease = callable(getattr(store, "acquire_audit_lease", None))
    if has_durable_lease:
        lease_acquired = bool(
            store.acquire_audit_lease(run_id, lease_owner, lease_seconds=AUDIT_LEASE_SECONDS)
        )
    else:
        process_lock_acquired = _PROCESS_AUDIT_LOCK.acquire(blocking=False)
        lease_acquired = process_lock_acquired
    if not lease_acquired:
        metrics.update(
            {
                "status": "already_running",
                "completed_at": utc_now().isoformat(),
                "runtime_seconds": max(0.0, clock() - started_clock),
                "lock_state": "already_running",
                "data_through_date": utc_now().date().isoformat(),
            }
        )
        _call_store(
            store,
            "finish_audit_run",
            run_id,
            status="already_running",
            metrics=metrics,
            lock_state="already_running",
        )
        _audit_log("technical_audit_already_running", run_id=run_id, **metrics)
        return metrics

    metrics["lock_state"] = "acquired"
    _audit_log(
        "technical_audit_started",
        run_id=run_id,
        trigger_source=metrics["trigger_source"],
        mode=mode,
        page_limit=page_limit,
        request_limit=request_limit,
        lock_state="acquired",
    )

    owned_session = session is None
    try:
        if session is None:
            session = (
                _InjectedRequestSession(request_get, request_head=request_head)
                if request_get is not None
                else session_factory()
            )
        crawler = StorefrontCrawler(
            session,
            request_interval_seconds=request_interval_seconds,
            request_limit=request_limit,
            clock=clock,
            sleeper=sleeper,
        )
    except Exception as error:
        metrics.update(
            {
                "status": "failed",
                "completed_at": utc_now().isoformat(),
                "runtime_seconds": max(0.0, clock() - started_clock),
                "lock_state": "released",
                "data_through_date": utc_now().date().isoformat(),
            }
        )
        if has_durable_lease:
            _call_store(store, "release_audit_lease", run_id, lease_owner)
        elif process_lock_acquired:
            _PROCESS_AUDIT_LOCK.release()
        _call_store(
            store,
            "finish_audit_run",
            run_id,
            status="failed",
            metrics=metrics,
            error_summary=str(error or "The audit HTTP session could not start.")[:500],
            lock_state="released",
        )
        _audit_log(
            "technical_audit_failed",
            run_id=run_id,
            status="failed",
            trigger_source=metrics["trigger_source"],
            mode=mode,
            lock_state="released",
            error_summary="The audit HTTP session could not start.",
        )
        return metrics
    written = 0
    processed = 0
    audit_status = "completed"
    error_summary = ""
    try:
        google_client = None
        site_url = ""
        try:
            access_token, connection = google_seo.access_token_for_connection(
                connection_store, google_seo.load_config()
            )
            site_url = str(connection.get("gsc_site_url") or "")
            google_client = google_seo_import.GoogleSEOReportingClient(
                access_token,
                request_get=session.get,
                request_post=session.post,
            )
            if site_url:
                _fetch_sitemaps(google_client, site_url)
        except Exception:
            # The HTML audit remains useful when optional GSC evidence is unavailable.
            google_client = None
            site_url = ""

        claim_rechecks = getattr(store, "claim_rechecks", None)
        queued = (
            list(claim_rechecks(limit=min(RECHECK_PAGE_LIMIT, page_limit)))
            if callable(claim_rechecks)
            else []
        )
        priority = _priority_urls(store, limit=page_limit, full=full)
        work_items = []
        queue_by_url = {}
        seen_urls = set()
        priority_by_url = {
            normalize_url(row.get("canonical_url")): row
            for row in priority
            if normalize_url(row.get("canonical_url"))
        }
        for queued_row in queued:
            normalized = normalize_url(queued_row.get("canonical_url"))
            if not normalized:
                continue
            queue_by_url[normalized] = queued_row
            if normalized in seen_urls:
                crawler.stats["duplicate_urls_skipped"] += 1
                continue
            seen_urls.add(normalized)
            item = dict(priority_by_url.get(normalized) or {})
            item.update(
                {
                    "canonical_url": str(queued_row.get("canonical_url") or normalized),
                    "_normalized_url": normalized,
                }
            )
            work_items.append(item)
        for priority_row in priority:
            normalized = normalize_url(priority_row.get("canonical_url"))
            if not normalized:
                continue
            if normalized in seen_urls:
                crawler.stats["duplicate_urls_skipped"] += 1
                continue
            seen_urls.add(normalized)
            item = dict(priority_row)
            item["_normalized_url"] = normalized
            work_items.append(item)
        work_items = work_items[:page_limit]
        metrics["pages_scheduled"] = len(work_items)

        fetched = []
        for index, item in enumerate(work_items):
            normalized = item["_normalized_url"]
            findings = []
            response = None
            try:
                response = crawler.fetch_page(normalized)
                findings.extend(
                    audit_html(
                        normalized,
                        status_code=response.status_code,
                        headers=response.headers,
                        html_text=response.text,
                        final_url=response.url,
                        page_type=item.get("page_type") or "",
                    )
                )
            except Exception:
                findings.append(
                    _finding(
                        "fetch_failed",
                        "High",
                        "The background HTML audit could not fetch this URL.",
                        "Confirm that the public URL is reachable, then queue a recheck.",
                        "The technical state could not be verified.",
                    )
                )
            fetched.append((index, item, response, findings))
            if index and index % 10 == 0 and has_durable_lease:
                if not store.renew_audit_lease(
                    run_id, lease_owner, lease_seconds=AUDIT_LEASE_SECONDS
                ):
                    raise TechnicalAuditError("The technical audit lease was lost.")

        # Top-level pages are fetched first so link checks reuse their cached statuses.
        link_cache = {}
        link_checks = 0
        for index, item, response, findings in fetched:
            normalized = item["_normalized_url"]
            if response is not None and link_checks < internal_link_limit:
                link_findings, checked = broken_internal_link_findings(
                    normalized,
                    response.text,
                    crawler=crawler,
                    cache=link_cache,
                    remaining=internal_link_limit - link_checks,
                )
                link_checks += checked
                findings.extend(link_findings)
            if index < inspection_limit and google_client is not None and site_url:
                try:
                    findings.extend(
                        inspection_findings(
                            normalized,
                            _inspect_url(google_client, site_url, normalized),
                        )
                    )
                except Exception:
                    pass
            queued_request = queue_by_url.get(normalized) or {}
            try:
                written += int(store.save_url_findings(normalized, findings) or 0)
                _call_store(
                    store,
                    "save_page_state",
                    run_id=run_id,
                    normalized_url=normalized,
                    canonical_url=str(item.get("canonical_url") or normalized),
                    page_type=item.get("page_type") or "",
                    shopify_resource_id=item.get("shopify_resource_id") or "",
                    status_code=response.status_code if response is not None else 0,
                    content_fingerprint=(
                        hashlib.sha256(response.text.encode("utf-8")).hexdigest()
                        if response is not None
                        else ""
                    ),
                    findings=findings,
                )
                if queued_request:
                    _call_store(store, "complete_recheck", queued_request.get("id"))
                processed += 1
            except Exception:
                if queued_request:
                    _call_store(
                        store,
                        "complete_recheck",
                        queued_request.get("id"),
                        error="The background recheck could not save its findings.",
                    )
        metrics["processed"] = processed
        metrics["written"] = written
    except Exception as error:
        audit_status = "failed"
        error_summary = str(error or "Technical audit failed.")[:500]
    finally:
        metrics.update(crawler.stats)
        metrics.update(
            {
                "status": audit_status,
                "processed": processed,
                "written": written,
                "completed_at": utc_now().isoformat(),
                "runtime_seconds": max(0.0, clock() - started_clock),
                "lock_state": "released",
                "data_through_date": utc_now().date().isoformat(),
            }
        )
        if owned_session:
            try:
                session.close()
            except Exception:
                pass
        try:
            if has_durable_lease:
                _call_store(store, "release_audit_lease", run_id, lease_owner)
            elif process_lock_acquired:
                _PROCESS_AUDIT_LOCK.release()
        except Exception:
            metrics["lock_state"] = "expires_after_release_error"
        _call_store(
            store,
            "finish_audit_run",
            run_id,
            status=audit_status,
            metrics=metrics,
            error_summary=error_summary,
            lock_state="released",
        )
        _audit_log(
            "technical_audit_completed" if audit_status == "completed" else "technical_audit_failed",
            run_id=run_id,
            status=audit_status,
            trigger_source=metrics["trigger_source"],
            mode=mode,
            pages_scheduled=metrics["pages_scheduled"],
            pages_fetched=metrics["pages_fetched"],
            head_requests=metrics["head_requests"],
            get_requests=metrics["get_requests"],
            cache_hits=metrics["cache_hits"],
            duplicate_urls_skipped=metrics["duplicate_urls_skipped"],
            redirects=metrics["redirects"],
            failed_requests=metrics["failed_requests"],
            total_storefront_requests=metrics["total_storefront_requests"],
            runtime_seconds=round(metrics["runtime_seconds"], 3),
            lock_state=metrics["lock_state"],
            error_summary=error_summary,
        )
    return metrics


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run a controlled Sports Cave technical SEO audit.")
    parser.add_argument("mode", choices=("daily", "full"), nargs="?", default="daily")
    parser.add_argument("--trigger", default="technical-maintenance-cli")
    parser.add_argument("--page-limit", type=int, default=None)
    args = parser.parse_args(argv)
    load_dotenv(BASE_DIR / ".env", override=False)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    result = run_background_audit(
        mode=args.mode,
        full=args.mode == "full",
        trigger_source=args.trigger,
        page_limit=args.page_limit,
    )
    print(json.dumps(result, sort_keys=True, default=str))
    return 0 if result.get("status") in {"completed", "already_running"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
