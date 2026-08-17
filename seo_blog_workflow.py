"""Persisted two-prompt SEO blog workflow and validation contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import uuid
from urllib.parse import urlparse

from sports_cave_prompt_blocks import build_sports_cave_image_realism_rules


BASE_DIR = Path(__file__).resolve().parent
MIGRATION = "20260817_analytics_seo_blog_rebuild.sql"
WORKSPACE_KEY = "sports-cave"
STATE_PREFIX = "seo-blog-v2-"
MARKETS = ("AU", "US", "UK", "CA", "NZ")
LANGUAGES = (
    "English (Australia)",
    "English (United States)",
    "English (United Kingdom)",
    "English (Canada)",
    "English (New Zealand)",
)
MARKET_LANGUAGE = dict(zip(MARKETS, LANGUAGES))
PUBLICATION_PREFERENCES = ("Draft", "Schedule after approval")
STATUSES = (
    "Idea", "Brief ready", "Generating", "Needs review", "Approved",
    "Shopify draft", "Scheduled", "Published", "Error",
)
REQUIRED_BRIEF_FIELDS = (
    "target_market", "sport", "subject", "search_intent", "primary_keyword",
    "target_title", "target_url", "author", "target_blog",
)
IMAGE_ROLES = (
    ("featured", "16:9", "1600x900"),
    ("editorial", "3:2", "1600x1067"),
    ("product_room_mockup", "4:3", "1600x1200"),
)
PLACEHOLDER_PATTERN = re.compile(
    r"\b(?:TODO|TBC|TBD|PLACEHOLDER|INSERT (?:LINK|IMAGE|FACT)|LOREM IPSUM)\b",
    re.IGNORECASE,
)


class BlogWorkflowError(RuntimeError):
    pass


class ContentPackageError(BlogWorkflowError):
    def __init__(self, issues):
        self.issues = tuple(str(issue) for issue in issues)
        super().__init__("; ".join(self.issues))


class _ArticleHTMLInspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.h1_count = 0
        self.words = []
        self.links = []
        self.images = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        tag = tag.casefold()
        if tag == "h1":
            self.h1_count += 1
        elif tag == "a":
            self.links.append(str(values.get("href") or ""))
        elif tag == "img":
            self.images.append({"src": values.get("src") or "", "alt": values.get("alt") or ""})

    def handle_data(self, data):
        self.words.extend(re.findall(r"\b[\w'-]+\b", str(data or "")))


def _hash(value):
    payload = value if isinstance(value, str) else json.dumps(value, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _clean_list(value):
    if isinstance(value, str):
        value = value.split(",")
    return [str(item).strip() for item in value or [] if str(item).strip()]


def validate_brief(brief):
    brief = dict(brief or {})
    missing = [field.replace("_", " ") for field in REQUIRED_BRIEF_FIELDS if not str(brief.get(field) or "").strip()]
    if str(brief.get("target_market") or "") not in MARKETS:
        missing.append("supported target market")
    if missing:
        raise BlogWorkflowError("Complete: " + ", ".join(dict.fromkeys(missing)) + ".")
    target_url = str(brief.get("target_url") or "").strip()
    parsed = urlparse(target_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise BlogWorkflowError("Target product or collection URL must be a complete public URL.")
    if brief.get("approved_source_assets") and not brief.get("assets_permitted"):
        raise BlogWorkflowError("Confirm that the supplied athlete or product source assets are permitted for use.")
    if not brief.get("approved_source_assets") and not brief.get("safe_non_identifiable_images"):
        raise BlogWorkflowError(
            "Confirm approved source imagery or choose the non-identifiable editorial-image fallback."
        )
    brief["supporting_keywords"] = _clean_list(brief.get("supporting_keywords"))
    brief["related_entities"] = _clean_list(brief.get("related_entities"))
    brief["fan_questions"] = _clean_list(brief.get("fan_questions"))
    brief["internal_links"] = _clean_list(brief.get("internal_links"))
    brief["tags"] = _clean_list(brief.get("tags"))
    brief["approved_source_assets"] = _clean_list(brief.get("approved_source_assets"))
    return brief


def prefill_from_opportunity(brief, opportunity):
    """Fill blanks only; manual edits always win."""
    result = dict(brief or {})
    opportunity = dict(opportunity or {})
    candidates = {
        "primary_keyword": opportunity.get("query"),
        "selected_opportunity": opportunity.get("query"),
        "target_url": opportunity.get("matched_page") or opportunity.get("current_page"),
        "search_intent": opportunity.get("recommended_article_type"),
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


def _json_contract(project_id):
    image_rows = [
        {
            "role": role,
            "aspect_ratio": ratio,
            "target_dimensions": dimensions,
            "purpose": "",
            "placement_marker": "",
            "filename": "descriptive-hyphenated-filename.webp",
            "alt_text": "",
            "caption": "",
            "source_asset_mapping": [],
            "final_asset_reference": "",
        }
        for role, ratio, dimensions in IMAGE_ROLES
    ]
    return json.dumps(
        {
            "project_id": project_id,
            "article_title": "",
            "seo_title": "",
            "meta_description": "",
            "handle": "",
            "excerpt": "",
            "author": "",
            "tags": [],
            "primary_query": "",
            "supporting_queries": [],
            "search_intent": "",
            "source_fact_check_notes": [],
            "final_html": "",
            "internal_link_map": [],
            "product_collection_link_placement": "final third",
            "image_manifest": image_rows,
            "video_metadata": None,
        },
        indent=2,
    )


def build_prompt_1(project_id, brief, *, source_date="", opportunity=None):
    brief = validate_brief(brief)
    opportunity = dict(opportunity or brief.get("opportunity_snapshot") or {})
    evidence = {
        "source": "Google Search Console saved query/page data",
        "data_through": source_date or opportunity.get("data_through_date") or "Not available",
        "query": opportunity.get("query") or brief.get("selected_opportunity") or "",
        "clicks": opportunity.get("clicks"),
        "impressions": opportunity.get("impressions"),
        "ctr": opportunity.get("ctr"),
        "impression_weighted_position": opportunity.get("average_position"),
        "change": opportunity.get("change") or opportunity.get("ranking_change"),
        "matched_page": opportunity.get("matched_page") or opportunity.get("current_page") or "",
        "confidence": opportunity.get("confidence") or "",
        "score_explanation": opportunity.get("score_explanation") or "",
    }
    product = {
        "entity_id": brief.get("target_entity_id") or "",
        "title": brief["target_title"],
        "url": brief["target_url"],
        "sport": brief.get("target_sport") or brief["sport"],
        "source_artwork": brief.get("source_artwork") or "",
    }
    realism = build_sports_cave_image_realism_rules(include_product_lock=True)
    return f"""SPORTS CAVE SEO BLOG ARTICLE AND IMAGE PACKAGE - PROMPT 1

PROJECT ID: {project_id}

SAVED BRIEF (authoritative; do not silently replace any value):
{json.dumps(brief, indent=2, sort_keys=True, default=str)}

OBSERVED SEARCH EVIDENCE (not search volume; do not extrapolate unsupported demand):
{json.dumps(evidence, indent=2, sort_keys=True, default=str)}

EXACT PRODUCT OR COLLECTION MAPPING:
{json.dumps(product, indent=2, sort_keys=True, default=str)}

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
- Place one relevant, natural Sports Cave product or collection connection in the final third using the exact URL above.
- Use descriptive crawlable internal-link anchors and only the exact verified links in the saved brief.
- Produce clean Shopify-safe semantic HTML with no body H1 because Shopify renders the article title as H1.
- Use H2/H3 only where useful. Include a list/table/FAQs only when they improve the reader's answer.
- Never promise rankings.

IMAGE PACKAGE CONTRACT
Generate the actual image assets when image generation is available; do not merely claim they were generated.
Return exactly these default roles, at the highest supported resolution while preserving each ratio:
1. Featured image: 16:9, target 1600x900.
2. Editorial/support image: 3:2, target 1600x1067.
3. Product/room mockup: 4:3, target 1600x1200.
For every image return purpose, placement marker, descriptive hyphenated WebP filename, unique natural alt text,
optional caption, exact source-asset mapping and final asset reference. Do not put advertising or keyword text in images.
Use an approved real source asset for any identifiable athlete. If none is mapped, use a relevant non-identifiable
editorial environment; never generate or approximate an athlete likeness.

{realism}

OUTPUT CONTRACT
Return one JSON object matching this exact structure, followed by the actual generated image assets when available:
{_json_contract(project_id)}

The JSON must contain the complete final HTML and complete three-item image manifest. Do not use placeholders.
""".strip()


def parse_content_package(payload):
    if isinstance(payload, dict):
        return dict(payload)
    text = str(payload or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL)
    try:
        value = json.loads(text)
    except (TypeError, ValueError) as error:
        raise ContentPackageError(("Content package must be valid JSON.",)) from error
    if not isinstance(value, dict):
        raise ContentPackageError(("Content package must be one JSON object.",))
    return value


def validate_content_package(payload, *, project_id, target_url, allow_manual_review=False):
    package = parse_content_package(payload)
    issues = []
    if str(package.get("project_id") or "") != str(project_id or ""):
        issues.append("Project ID does not match this blog project.")
    for key in (
        "article_title", "seo_title", "meta_description", "handle", "excerpt", "author",
        "primary_query", "search_intent", "source_fact_check_notes", "final_html",
        "internal_link_map", "product_collection_link_placement",
    ):
        if not package.get(key):
            issues.append(f"Missing {key.replace('_', ' ')}.")
    inspector = _ArticleHTMLInspector()
    inspector.feed(str(package.get("final_html") or ""))
    if inspector.h1_count:
        issues.append("Article body contains an H1; Shopify supplies the page H1.")
    word_count = len(inspector.words)
    if word_count < 700:
        issues.append(f"Article body is only {word_count} words; manual review is required.")
    target_url = str(target_url or "").strip()
    if target_url and target_url not in inspector.links:
        issues.append("The exact product or collection URL is missing from the article HTML.")
    if target_url:
        html_text = str(package.get("final_html") or "")
        position = html_text.find(target_url)
        if position >= 0 and position < len(html_text) * (2 / 3):
            issues.append("The product or collection link appears before the final third.")
    manifest = list(package.get("image_manifest") or [])
    if len(manifest) != len(IMAGE_ROLES):
        issues.append("Image manifest must contain exactly the featured, editorial and product-room roles.")
    by_role = {str(row.get("role") or ""): row for row in manifest if isinstance(row, dict)}
    for role, ratio, dimensions in IMAGE_ROLES:
        row = by_role.get(role) or {}
        if str(row.get("aspect_ratio") or "") != ratio:
            issues.append(f"{role} image must use {ratio}.")
        for field in (
            "purpose", "placement_marker", "filename", "alt_text",
            "source_asset_mapping", "final_asset_reference",
        ):
            if not row.get(field):
                issues.append(f"{role} image is missing {field.replace('_', ' ')}.")
        filename = str(row.get("filename") or "")
        if filename and (not filename.endswith(".webp") or not re.fullmatch(r"[a-z0-9-]+\.webp", filename)):
            issues.append(f"{role} filename must be lowercase, hyphenated WebP.")
    serialized = json.dumps(package, default=str)
    if PLACEHOLDER_PATTERN.search(serialized):
        issues.append("The package contains a placeholder or unfinished marker.")
    valid = not issues
    if issues and not allow_manual_review:
        raise ContentPackageError(issues)
    return {
        "valid": valid,
        "manual_review": bool(issues and allow_manual_review),
        "issues": issues,
        "word_count": word_count,
        "package": package,
        "image_manifest": manifest,
    }


def validate_shopify_readback(project, readback, *, require_unpublished=True):
    """Compare the evidence returned after Shopify draft creation with the approved package."""
    project = dict(project or {})
    package = dict(project.get("content_package") or {})
    readback = dict(readback or {})
    issues = []
    for field in ("article_id", "handle", "admin_url", "preview_url"):
        if not str(readback.get(field) or "").strip():
            issues.append(f"Shopify read-back is missing {field.replace('_', ' ')}.")
    expected = {
        "title": package.get("article_title"),
        "html": package.get("final_html"),
        "handle": package.get("handle"),
        "excerpt": package.get("excerpt"),
        "author": package.get("author"),
        "tags": package.get("tags") or [],
        "seo_title": package.get("seo_title"),
        "meta_description": package.get("meta_description"),
    }
    for field, value in expected.items():
        actual = readback.get(field)
        if field == "tags":
            matches = sorted(str(item) for item in actual or []) == sorted(str(item) for item in value or [])
        else:
            matches = str(actual or "") == str(value or "")
        if not matches:
            issues.append(f"Shopify read-back {field.replace('_', ' ')} does not match the approved package.")
    expected_images = {
        str(row.get("role") or ""): (str(row.get("alt_text") or ""), str(row.get("final_asset_reference") or ""))
        for row in package.get("image_manifest") or []
    }
    actual_images = {
        str(row.get("role") or ""): (str(row.get("alt_text") or ""), str(row.get("url") or ""))
        for row in readback.get("images") or []
    }
    for role, (alt_text, _asset_reference) in expected_images.items():
        actual_alt, actual_url = actual_images.get(role, ("", ""))
        if actual_alt != alt_text or not actual_url.startswith("https://"):
            issues.append(f"Shopify read-back image {role or 'unknown'} is missing its CDN URL or exact alt text.")
    visibility = str(readback.get("visibility") or "").casefold()
    if require_unpublished and visibility not in {"draft", "unpublished"}:
        issues.append("The Shopify article was not confirmed as an unpublished draft.")
    if issues:
        raise BlogWorkflowError("; ".join(issues))
    return {"valid": True, "article_id": readback["article_id"], "handle": readback["handle"]}


def shopify_write_capability(env=None):
    env = env or os.environ
    configured = bool(str(env.get("SHOPIFY_STORE_DOMAIN") or "").strip())
    authenticated = bool(
        str(env.get("SHOPIFY_ADMIN_ACCESS_TOKEN") or "").strip()
        or str(env.get("SHOPIFY_CLIENT_ID") or "").strip()
    )
    blog_write = str(env.get("SHOPIFY_BLOG_WRITE_ENABLED") or "").casefold() in {"1", "true", "yes"}
    file_write = str(env.get("SHOPIFY_FILE_WRITE_ENABLED") or "").casefold() in {"1", "true", "yes"}
    return {
        "available": bool(configured and authenticated and blog_write and file_write),
        "store_configured": configured,
        "authenticated_backend": authenticated,
        "blog_write_confirmed": blog_write,
        "file_write_confirmed": file_write,
    }


def build_prompt_2(project, validation, *, capability=None):
    project = dict(project or {})
    validation = dict(validation or {})
    if not validation.get("valid") and not validation.get("manual_review"):
        raise BlogWorkflowError("Validate the imported article and image package before creating Prompt 2.")
    capability = dict(capability or {})
    if not capability.get("available"):
        raise BlogWorkflowError(
            "Shopify blog and file-write capability is not confirmed. Stop here; do not request credentials in chat."
        )
    package = validation.get("package") or project.get("content_package") or {}
    return f"""SPORTS CAVE SHOPIFY BLOG DRAFT AND PUBLISHING - PROMPT 2

Continue in the same conversation as Prompt 1.
PROJECT ID: {project.get('project_id') or ''}
EXISTING SHOPIFY ARTICLE ID (update this exact draft when present): {project.get('shopify_article_id') or 'None'}
TARGET SHOPIFY BLOG: {(project.get('brief') or {}).get('target_blog') or ''}
EXPECTED CONTENT PACKAGE HASH: {_hash(package)}

CONTENT PACKAGE:
{json.dumps(package, indent=2, sort_keys=True, default=str)}

EXECUTION CONTRACT
1. Confirm a real Shopify connection with article and file-write capability. Never request an Admin token or credential in chat.
2. Never claim success without Shopify read-back evidence.
3. Resolve the exact Sports Cave store, destination blog, author and project.
4. Search project ID, existing article ID, title and handle first. Prevent duplicates and never overwrite an unrelated live article.
5. Check keyword cannibalisation; report a conflict rather than silently creating a competing article.
6. Verify all internal links and image assets. Upload every image once to Shopify Files, wait until processing is ready,
   then insert returned CDN URLs at the manifest placement markers with the exact alt text.
7. Build sanitised responsive semantic HTML. Set featured image, excerpt, tags, handle and author. Keep one page H1 only.
8. Create or update an UNPUBLISHED DRAFT first. Set SEO title/meta description using currently supported GraphQL
   fields or global title_tag and description_tag metafields where appropriate.
9. Read the entire draft back. Return article ID, handle, Admin/preview URL and a QA table covering title, HTML,
   featured image, all image URLs/alt text, handle, excerpt, tags, SEO metadata and unpublished visibility.
10. STOP and ask for explicit "Publish now" or schedule confirmation.
11. Only after that separate confirmation, publish/schedule this exact existing draft and read it back again.
12. On rerun, resume or update the same article ID. If any permission, image, link, metadata or schema operation fails,
    leave it unpublished and report the exact blocker.

Do not add duplicate JSON-LD when the theme already emits Article schema. Do not expose credentials or private payloads.
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
