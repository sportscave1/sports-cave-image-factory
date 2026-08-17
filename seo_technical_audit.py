"""Background-only technical SEO inventory and audit services."""

from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import uuid
from urllib.parse import urljoin, urlparse

import requests

import google_seo
import google_seo_import


BASE_DIR = Path(__file__).resolve().parent
MIGRATION = "20260817_analytics_seo_blog_rebuild.sql"
WORKSPACE_KEY = google_seo.GOOGLE_SEO_WORKSPACE_KEY
URL_INSPECTION_ENDPOINT = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
AUDIT_PAGE_LIMIT = 100
INSPECTION_PAGE_LIMIT = 20
INTERNAL_LINK_CHECK_LIMIT = 50


class TechnicalAuditError(RuntimeError):
    pass


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
    if 300 <= int(status_code or 0) < 400 or final_url.rstrip("/") != str(url).rstrip("/"):
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
    elif parser.canonical.rstrip("/") != final_url.rstrip("/"):
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
    source = urlparse(str(source_url or ""))
    output = []
    seen = set()
    for href in parser.links:
        target = urljoin(str(source_url or ""), str(href or "").strip()).split("#", 1)[0]
        parsed = urlparse(target)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.casefold() != source.netloc.casefold():
            continue
        clean = target.rstrip("/") or target
        if clean in seen or clean == str(source_url or "").rstrip("/"):
            continue
        seen.add(clean)
        output.append(clean)
    return output


def broken_internal_link_findings(source_url, html_text, *, request_get, cache, remaining):
    checked = 0
    broken = []
    for target in internal_link_targets(source_url, html_text):
        if checked >= max(0, int(remaining)):
            break
        checked += 1
        if target not in cache:
            try:
                response = request_get(
                    target,
                    timeout=google_seo.GOOGLE_HTTP_TIMEOUT_SECONDS,
                    allow_redirects=True,
                )
                cache[target] = int(getattr(response, "status_code", 0) or 0)
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
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute((BASE_DIR / "migrations" / MIGRATION).read_text(encoding="utf-8"))
            connection.commit()
        self._schema_ready = True

    def priority_urls(self, limit=AUDIT_PAGE_LIMIT):
        self.ensure_schema()
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT canonical_url, page_type, title, shopify_resource_id
                    FROM seo_canonical_pages
                    WHERE workspace_key=%s AND is_active=TRUE
                      AND LOWER(page_type) IN ('product','collection','blog','article','page','home')
                    ORDER BY CASE LOWER(page_type) WHEN 'home' THEN 1 WHEN 'product' THEN 2
                              WHEN 'collection' THEN 3 WHEN 'blog' THEN 4 WHEN 'article' THEN 4 ELSE 5 END,
                             last_seen_at DESC
                    LIMIT %s
                    """,
                    (WORKSPACE_KEY, int(limit)),
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


def run_background_audit(
    *,
    store=None,
    connection_store=None,
    request_get=requests.get,
    page_limit=AUDIT_PAGE_LIMIT,
    inspection_limit=INSPECTION_PAGE_LIMIT,
):
    """Run bounded network work from a worker, never from a Streamlit render."""
    store = store or PostgresTechnicalAuditStore()
    connection_store = connection_store or google_seo.default_store()
    access_token, connection = google_seo.access_token_for_connection(
        connection_store, google_seo.load_config()
    )
    site_url = str(connection.get("gsc_site_url") or "")
    client = google_seo_import.GoogleSEOReportingClient(access_token)
    try:
        sitemaps = _fetch_sitemaps(client, site_url)
    except Exception:
        sitemaps = []
    written = 0
    processed = 0
    claim_rechecks = getattr(store, "claim_rechecks", None)
    queued = claim_rechecks(limit=min(20, int(page_limit))) if callable(claim_rechecks) else []
    queue_by_url = {str(row.get("canonical_url") or ""): row for row in queued}
    priority = list(store.priority_urls(limit=page_limit))
    priority_by_url = {str(row.get("canonical_url") or ""): row for row in priority}
    work_items = [
        priority_by_url.get(url) or {"canonical_url": url, "page_type": "", "title": ""}
        for url in queue_by_url
        if url
    ] + [row for row in priority if str(row.get("canonical_url") or "") not in queue_by_url]
    link_cache = {}
    link_checks = 0
    for index, item in enumerate(work_items[: int(page_limit)]):
        url = str(item.get("canonical_url") or "")
        if not url:
            continue
        processed += 1
        try:
            response = request_get(url, timeout=google_seo.GOOGLE_HTTP_TIMEOUT_SECONDS, allow_redirects=True)
            findings = audit_html(
                url,
                status_code=response.status_code,
                headers=response.headers,
                html_text=response.text,
                final_url=response.url,
                page_type=item.get("page_type") or "",
            )
            link_findings, checked = broken_internal_link_findings(
                url,
                response.text,
                request_get=request_get,
                cache=link_cache,
                remaining=INTERNAL_LINK_CHECK_LIMIT - link_checks,
            )
            link_checks += checked
            findings.extend(link_findings)
        except Exception:
            findings = [_finding(
                "fetch_failed", "High", "The background HTML audit could not fetch this URL.",
                "Confirm that the public URL is reachable, then queue a recheck.",
                "The technical state could not be verified.",
            )]
        if index < int(inspection_limit) and site_url:
            try:
                findings.extend(inspection_findings(url, _inspect_url(client, site_url, url)))
            except Exception:
                pass
        try:
            written += store.save_url_findings(url, findings)
            queued_request = queue_by_url.get(url) or {}
            complete = getattr(store, "complete_recheck", None)
            if queued_request and callable(complete):
                complete(queued_request.get("id"))
        except Exception as error:
            queued_request = queue_by_url.get(url) or {}
            complete = getattr(store, "complete_recheck", None)
            if queued_request and callable(complete):
                complete(queued_request.get("id"), error="The background recheck could not save its findings.")
            continue
    return {
        "status": "completed",
        "processed": processed,
        "written": written,
        "data_through_date": datetime.now(timezone.utc).date().isoformat(),
    }
