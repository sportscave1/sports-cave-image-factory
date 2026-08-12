from copy import deepcopy
import csv
from datetime import date, datetime, timezone
import io
import json
import os
from pathlib import Path
import re
import threading
import uuid
from urllib.parse import urlparse, urlunparse


SEO_PAGE_KEY = "seo"
SEO_OVERVIEW_ROUTE = "SEO Overview"
SEO_CITATIONS_ROUTE = "Citations"
SEO_BLOG_ROUTE = "Blog Content"
SEO_INTERNAL_LINKING_ROUTE = "Internal Linking"
SEO_BACKLINKS_ROUTE = "Backlinks & Outreach"
SEO_KEYWORDS_ROUTE = "Keyword Research & Mapping"
SEO_ROUTES = (
    SEO_OVERVIEW_ROUTE,
    SEO_CITATIONS_ROUTE,
    SEO_BLOG_ROUTE,
    SEO_INTERNAL_LINKING_ROUTE,
    SEO_BACKLINKS_ROUTE,
    SEO_KEYWORDS_ROUTE,
)
SEO_NAV_LABELS = {
    SEO_OVERVIEW_ROUTE: "Overview",
    SEO_CITATIONS_ROUTE: "Citations",
    SEO_BLOG_ROUTE: "Blog Content",
    SEO_INTERNAL_LINKING_ROUTE: "Internal Linking",
    SEO_BACKLINKS_ROUTE: "Backlinks & Outreach",
    SEO_KEYWORDS_ROUTE: "Keyword Research & Mapping",
}

SEO_MIGRATION = "20260812_seo_workspace_v1.sql"
SEO_SCHEMA_VERSION = 1
SEO_WORKSPACE_KEY = "sports-cave"
BASE_DIR = Path(__file__).resolve().parent
LOCAL_STORE_PATH = BASE_DIR / "output" / "_cache" / "seo_workspace.json"

BLOG_STATUSES = (
    "Idea",
    "Brief",
    "Draft",
    "Human Review",
    "Ready for Owner",
    "Published",
    "Archived",
)
CITATION_STATUSES = (
    "To Do",
    "In Progress",
    "Pending Verification",
    "Live",
    "Skipped",
)
LINK_VERIFICATION_STATUSES = (
    "Not Checked",
    "Verified",
    "Needs Update",
    "Broken",
    "Not Applicable",
)
OUTREACH_STATUSES = (
    "Research",
    "Qualified",
    "Outreach Draft",
    "Sent",
    "Follow-up Due",
    "Replied",
    "Live",
    "Rejected",
)
KEYWORD_PAGE_TYPES = ("Product", "Collection", "Blog")
KEYWORD_INTENTS = ("Strong", "Possible", "Informational", "Irrelevant", "Needs Review")
KEYWORD_PRIORITIES = ("High", "Medium", "Low")
KEYWORD_MAPPING_STATUSES = ("Unreviewed", "Approved", "Mapped", "Rejected", "Conflict")
TARGET_MARKETS = ("Australia", "United States", "United Kingdom", "Canada", "New Zealand")

SEO_COLLECTIONS = {
    "blog_records",
    "link_plans",
    "target_library",
    "citations",
    "outreach_records",
    "keywords",
    "keyword_mappings",
    "prompt_templates",
}

BUSINESS_DETAILS = {
    "business_name": "Sports Cave",
    "website": "https://www.sportscaveshop.com",
    "base_description": (
        "Sports Cave creates premium sports wall art for fans, collectors and man caves "
        "worldwide, featuring iconic sporting moments from basketball, cricket, motorsport and more."
    ),
}

WEEKLY_TARGETS = (
    "One meaningful blog/content deliverable",
    "20-30 qualified outreach prospects",
    "10-15 personalised outreach messages",
    "10-15 reputable citation actions",
    "Review keyword mapping",
    "Flag blockers immediately",
)

INTERNAL_LINK_TARGETS = (
    ("target-homepage", "Homepage", "https://www.sportscaveshop.com"),
    ("target-soccer", "Soccer", "https://www.sportscaveshop.com/collections/soccer"),
    ("target-nba", "NBA / Basketball", "https://www.sportscaveshop.com/collections/nba"),
    ("target-cricket", "Cricket", "https://www.sportscaveshop.com/collections/cricket"),
    (
        "target-motor-racing",
        "Motor Racing",
        "https://www.sportscaveshop.com/collections/motor-racing-wall-art",
    ),
    ("target-combat", "Combat Sports", "https://www.sportscaveshop.com/collections/combat-art"),
    (
        "target-horse-racing",
        "Horse Racing",
        "https://www.sportscaveshop.com/collections/horse-racing-wall-art",
    ),
    ("target-tennis", "Tennis", "https://www.sportscaveshop.com/collections/tennis-wall-art"),
)

BLOG_TOPIC_RESEARCH_TEMPLATE = """You are an SEO strategist and sports content researcher for Sports Cave, a premium sports wall art brand.

INPUT
Product or Collection: {{name}}
URL: {{url}}
Sport: {{sport}}
Target Market: {{market}}
Known Keyword Data: {{keyword_data}}

Find five article topics that:
- A real sports fan would want to read
- Match genuine search intent
- Use a specific athlete, rivalry, moment, collector question or fan-space need
- Can connect naturally to Sports Cave without becoming an advertisement
- Do not depend on invented facts or search data

Return a table containing:
1. SEO-friendly article title
2. Primary keyword
3. Search intent
4. Why a fan would search for it
5. Natural Sports Cave connection

Select one option and label it BEST ARTICLE TO WRITE.

Do not write the article yet."""

ARTICLE_WRITING_TEMPLATE = """You are a senior sports journalist writing for the Sports Cave Journal.

Write a premium, human-sounding sports feature based on:

Title: {{title}}
Primary Search Intent: {{search_intent}}
Primary Keyword: {{primary_keyword}}
Supporting Keywords: {{supporting_keywords}}
Sport or Player: {{sport_or_player}}
Target Market: {{market}}
Collection: {{collection_name}}
Collection URL: {{collection_url}}
Product URL: {{product_url_or_none}}

Requirements:
- Write for sports fans first
- Establish the topic within the first 100 words
- Focus on one central intent
- Use specific, verified details real fans recognise
- Use natural rhythm and emotional storytelling
- Avoid generic AI phrasing, filler and repetition
- Target approximately 1,100-1,700 words without padding
- Use five to seven meaningful H2 sections where appropriate
- Connect the story naturally to fan culture, collecting or sports wall art in the final third
- Include the relevant collection link naturally
- Include the product link only if one has been verified
- Use the homepage naturally in the conclusion
- End with a calm, relevant CTA
- Do not mention SEO, rankings, keywords or GSC
- Do not invent facts

Output the finished article only."""

KEYWORD_EXTRACTION_TEMPLATE = """You are an SEO strategist for Sports Cave, a premium sports wall art brand.

Analyse the provided Google Search Console query data.

Use only the supplied data. Do not invent volume or performance.

Select keywords that could realistically lead to a purchase of sports wall art.

Classify each useful query as Product, Collection or Blog.
Classify intent as Strong, Possible, Informational, Irrelevant or Needs Review.

Return a table with:
Category | Keyword | Type | Intent | Priority | Notes | Clicks | Impressions | CTR | Position

Prioritise natural purchase intent such as wall art, framed, poster, print, decor, man cave, gift or athlete/team searches combined with a product term.

Do not keep informational queries merely because they have impressions.
Do not explain the process."""

SITE_QUALIFICATION_TEMPLATE = """You are reviewing a website for a possible brand-safe Sports Cave backlink or creator collaboration.

Website: {{website}}
Relevant Page: {{page}}
Opportunity: {{opportunity}}

Assess content quality, relevance, brand safety, whether the site is active and human-run, whether outbound links appear reasonable, whether a real reader would benefit, and any signs of a link farm, PBN, paid-link marketplace or SEO-only website.

Return:
1. Approve, Reject or Needs Review
2. Short reason
3. Red flags
4. Most natural collaboration angle
5. Best Sports Cave target page type

Do not approve a site only because it has an SEO metric."""

OUTREACH_TEMPLATE = """Subject: Sports Cave idea for [article or topic]

Hi [Name],

I came across your article on [topic] and enjoyed the section about [specific detail].

I'm with Sports Cave, a sports wall art brand used by collectors and man cave owners around the world.

Your readers may find [specific collection, article or product] useful as a real example within the piece. If it helps, I can suggest one short line that fits the article naturally.

Either way, it was a great read.

Best,
[Sender Name]
Sports Cave"""


class SEOValidationError(ValueError):
    pass


class SEOStoreError(RuntimeError):
    pass


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_safe(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _default_target_library():
    return [
        {
            "id": target_id,
            "label": label,
            "url": url,
            "verification_status": "Needs Verification",
            "created_at": "",
            "updated_at": "",
            "owner_id": "",
            "archived_at": "",
        }
        for target_id, label, url in INTERNAL_LINK_TARGETS
    ]


def _default_prompt_templates():
    rows = (
        ("prompt-blog-topic-research", "Blog topic research", BLOG_TOPIC_RESEARCH_TEMPLATE),
        ("prompt-article-writing", "Article writing", ARTICLE_WRITING_TEMPLATE),
        ("prompt-keyword-extraction", "Keyword extraction", KEYWORD_EXTRACTION_TEMPLATE),
        ("prompt-site-qualification", "Site qualification", SITE_QUALIFICATION_TEMPLATE),
        ("prompt-initial-outreach", "Initial outreach", OUTREACH_TEMPLATE),
    )
    return [
        {
            "id": template_id,
            "name": name,
            "template": template,
            "created_at": "",
            "updated_at": "",
            "owner_id": "",
            "archived_at": "",
        }
        for template_id, name, template in rows
    ]


def default_state():
    return {
        "schema_version": SEO_SCHEMA_VERSION,
        "settings": {
            "business_details": deepcopy(BUSINESS_DETAILS),
            "integrations": {
                "gsc": {"status": "Not connected", "planned": True},
                "ga4": {"status": "Not connected", "planned": True},
            },
            "weekly_targets": list(WEEKLY_TARGETS),
            "primary_markets": ["Australia", "United States", "United Kingdom"],
            "secondary_markets": ["Canada", "New Zealand"],
        },
        "blog_records": [],
        "link_plans": [],
        "target_library": _default_target_library(),
        "citations": [],
        "outreach_records": [],
        "keywords": [],
        "keyword_mappings": [],
        "prompt_templates": _default_prompt_templates(),
    }


def normalise_state(value):
    raw = dict(value or {}) if isinstance(value, dict) else {}
    state = default_state()
    settings = raw.get("settings") if isinstance(raw.get("settings"), dict) else {}
    state["settings"].update(deepcopy(settings))
    business = settings.get("business_details") if isinstance(settings.get("business_details"), dict) else {}
    state["settings"]["business_details"] = {**BUSINESS_DETAILS, **deepcopy(business)}
    integrations = settings.get("integrations") if isinstance(settings.get("integrations"), dict) else {}
    state["settings"]["integrations"] = {
        **state["settings"]["integrations"],
        **deepcopy(integrations),
    }
    for collection in SEO_COLLECTIONS:
        if collection in raw and isinstance(raw[collection], list):
            state[collection] = [dict(row) for row in raw[collection] if isinstance(row, dict)]
    state["schema_version"] = SEO_SCHEMA_VERSION
    return state


class LocalSEOStore:
    def __init__(self, path=LOCAL_STORE_PATH):
        self.path = Path(path)
        self._lock = threading.RLock()

    def load(self):
        with self._lock:
            if not self.path.is_file():
                return default_state()
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError) as error:
                raise SEOStoreError("SEO workspace data could not be read.") from error
            return normalise_state(payload)

    def save(self, state, *, actor_id=""):
        payload = normalise_state(_json_safe(state))
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(f"{self.path.name}.{uuid.uuid4().hex}.tmp")
            try:
                temporary.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                temporary.replace(self.path)
            except OSError as error:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
                raise SEOStoreError("SEO workspace data could not be saved.") from error
        return payload


class PostgresSEOStore:
    def __init__(self, backend=None):
        self.backend = backend
        self._schema_ready = False
        self._lock = threading.Lock()

    def _backend(self):
        if self.backend is not None:
            return self.backend
        import supabase_backend

        return supabase_backend

    def ensure_schema(self):
        if self._schema_ready:
            return
        with self._lock:
            if self._schema_ready:
                return
            migration_path = BASE_DIR / "migrations" / SEO_MIGRATION
            if not migration_path.is_file():
                raise SEOStoreError("SEO workspace migration is unavailable.")
            sql = migration_path.read_text(encoding="utf-8")
            try:
                with self._backend().connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(sql)
                    conn.commit()
            except Exception as error:
                raise SEOStoreError("SEO workspace storage could not be prepared.") from error
            self._schema_ready = True

    def load(self):
        self.ensure_schema()
        try:
            with self._backend().connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT payload FROM seo_workspace_state WHERE workspace_key=%s LIMIT 1",
                        (SEO_WORKSPACE_KEY,),
                    )
                    row = cur.fetchone() or {}
        except Exception as error:
            raise SEOStoreError("SEO workspace data could not be loaded.") from error
        payload = row.get("payload") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (TypeError, ValueError, json.JSONDecodeError):
                payload = {}
        return normalise_state(payload)

    def save(self, state, *, actor_id=""):
        self.ensure_schema()
        payload = normalise_state(_json_safe(state))
        try:
            with self._backend().connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO seo_workspace_state(
                            workspace_key, schema_version, payload, updated_by, updated_at
                        )
                        VALUES (%s, %s, %s::jsonb, %s, now())
                        ON CONFLICT (workspace_key) DO UPDATE SET
                            schema_version=EXCLUDED.schema_version,
                            payload=EXCLUDED.payload,
                            updated_by=EXCLUDED.updated_by,
                            updated_at=now()
                        """,
                        (
                            SEO_WORKSPACE_KEY,
                            SEO_SCHEMA_VERSION,
                            json.dumps(payload, ensure_ascii=False),
                            str(actor_id or "")[:200],
                        ),
                    )
                conn.commit()
        except Exception as error:
            raise SEOStoreError("SEO workspace data could not be saved.") from error
        return payload


_DEFAULT_STORE = None


def default_store():
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        try:
            import supabase_backend

            configured = supabase_backend.is_configured()
        except Exception:
            configured = False
        _DEFAULT_STORE = PostgresSEOStore() if configured else LocalSEOStore()
    return _DEFAULT_STORE


def active_records(state, collection):
    if collection not in SEO_COLLECTIONS:
        raise ValueError(f"Unknown SEO collection: {collection}")
    return [dict(row) for row in state.get(collection, []) if not row.get("archived_at")]


def upsert_record(state, collection, payload, *, actor=None, record_id=""):
    if collection not in SEO_COLLECTIONS:
        raise ValueError(f"Unknown SEO collection: {collection}")
    actor = dict(actor or {})
    now = utc_now()
    rows = [dict(row) for row in state.get(collection, [])]
    selected_id = str(record_id or payload.get("id") or uuid.uuid4())
    existing_index = next((index for index, row in enumerate(rows) if str(row.get("id")) == selected_id), None)
    existing = rows[existing_index] if existing_index is not None else {}
    record = {
        **existing,
        **_json_safe(dict(payload or {})),
        "id": selected_id,
        "owner_id": str(payload.get("owner_id") or existing.get("owner_id") or actor.get("id") or ""),
        "owner": str(payload.get("owner") or existing.get("owner") or actor.get("display_name") or actor.get("email") or ""),
        "created_at": existing.get("created_at") or now,
        "updated_at": now,
        "archived_at": str(payload.get("archived_at") or existing.get("archived_at") or ""),
    }
    if existing_index is None:
        rows.append(record)
    else:
        rows[existing_index] = record
    state[collection] = rows
    return record


def archive_record(state, collection, record_id, *, actor=None):
    rows = state.get(collection, [])
    selected = next((dict(row) for row in rows if str(row.get("id")) == str(record_id)), None)
    if not selected:
        raise SEOValidationError("The selected SEO record no longer exists.")
    selected["archived_at"] = utc_now()
    return upsert_record(state, collection, selected, actor=actor, record_id=record_id)


def validate_public_url(value, *, required=False, label="URL"):
    clean = str(value or "").strip()
    if not clean:
        if required:
            raise SEOValidationError(f"{label} is required.")
        return ""
    if len(clean) > 1200 or any(char in clean for char in ("\r", "\n", "\t")):
        raise SEOValidationError(f"Enter a valid {label.lower()}.")
    parsed = urlparse(clean)
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise SEOValidationError(f"Enter a valid public {label.lower()}.")
    return urlunparse(parsed._replace(fragment=""))


def validate_citation(payload):
    row = dict(payload or {})
    if not str(row.get("platform") or "").strip():
        raise SEOValidationError("Platform name is required.")
    for field, label in (("signup_url", "Signup URL"), ("profile_url", "Profile URL")):
        row[field] = validate_public_url(
            row.get(field),
            required=bool(row.get("status") == "Live" and field == "profile_url"),
            label=label,
        )
    if row.get("status") == "Live":
        missing = []
        if not row.get("profile_url"):
            missing.append("profile URL")
        if not bool(row.get("publicly_accessible")):
            missing.append("public accessibility confirmation")
        if str(row.get("website_displayed") or "") != "Yes":
            missing.append("Website Displayed = Yes")
        if not str(row.get("username_handle") or row.get("notes") or "").strip():
            missing.append("completion details")
        if missing:
            raise SEOValidationError("A citation cannot be Live until it has " + ", ".join(missing) + ".")
    return row


def validate_outreach(payload):
    row = dict(payload or {})
    if not str(row.get("site_creator") or "").strip():
        raise SEOValidationError("Site or creator name is required.")
    row["website"] = validate_public_url(row.get("website"), required=True, label="Website URL")
    row["live_url"] = validate_public_url(row.get("live_url"), label="Live URL")
    try:
        follow_up_count = int(row.get("follow_up_count") or 0)
    except (TypeError, ValueError) as error:
        raise SEOValidationError("Follow-up count must be zero or one.") from error
    if follow_up_count not in {0, 1}:
        raise SEOValidationError("Only one follow-up is allowed.")
    row["follow_up_count"] = follow_up_count
    if row.get("status") == "Rejected" and not str(row.get("rejection_reason") or "").strip():
        raise SEOValidationError("A rejected prospect needs a short reason.")
    if row.get("status") == "Live":
        required = {
            "live_url": "live URL",
            "target_page": "Sports Cave target page",
            "anchor_text": "exact anchor text",
            "relevant_placement": "relevant placement confirmation",
            "verification_date": "verification date",
        }
        missing = [label for field, label in required.items() if not row.get(field)]
        if missing:
            raise SEOValidationError("A backlink cannot be Live until it has " + ", ".join(missing) + ".")
    return row


def validate_link_plan(payload):
    row = dict(payload or {})
    if not str(row.get("source_blog") or "").strip():
        raise SEOValidationError("Source blog is required.")
    row["homepage_url"] = validate_public_url(row.get("homepage_url"), required=True, label="Homepage URL")
    row["collection_url"] = validate_public_url(row.get("collection_url"), required=True, label="Collection URL")
    if bool(row.get("no_product_link")):
        row["product_url"] = ""
        row["product_anchor_text"] = ""
    else:
        row["product_url"] = validate_public_url(row.get("product_url"), label="Product URL")
    return row


def word_count(value):
    return len(re.findall(r"\b[\w'-]+\b", str(value or "")))


def heading_count(value, level=2):
    marker = "#" * max(int(level), 1)
    return len(re.findall(rf"(?m)^\s*{re.escape(marker)}\s+\S", str(value or "")))


def meta_validation(meta_title, meta_description):
    title_length = len(str(meta_title or "").strip())
    description_length = len(str(meta_description or "").strip())
    return {
        "meta_title_length": title_length,
        "meta_description_length": description_length,
        "meta_title_valid": 50 <= title_length <= 60,
        "meta_description_valid": 140 <= description_length <= 160,
    }


def slugify(value):
    clean = re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")
    return re.sub(r"-{2,}", "-", clean)


def build_publish_ready_pack(blog):
    blog = dict(blog or {})
    product_url = str(blog.get("product_url") or "").strip() or "Omitted"
    checklist = blog.get("review_checklist") or []
    checklist_lines = "\n".join(f"- {item}" for item in checklist) or "- Not completed"
    return f"""SPORTS CAVE BLOG PUBLISH-READY PACK

ARTICLE
Title: {blog.get('article_title') or ''}
Status: {blog.get('status') or ''}
Primary keyword: {blog.get('primary_keyword') or ''}
Target market: {blog.get('target_market') or ''}

{blog.get('article_draft') or ''}

SEO AND LINKS
SEO title: {blog.get('seo_title') or ''}
Meta title: {blog.get('meta_title') or ''}
Meta description: {blog.get('meta_description') or ''}
Suggested URL slug: {blog.get('url_slug') or ''}
Excerpt: {blog.get('excerpt') or ''}
Homepage link: {blog.get('homepage_url') or ''}
Collection link: {blog.get('collection_url') or ''}
Product link: {product_url}
Shopify tags: {blog.get('shopify_tags') or ''}

ASSETS
Hero image: {blog.get('hero_image_filename') or ''}
Hero alt text: {blog.get('hero_image_alt') or ''}
Supporting image: {blog.get('supporting_image_filename') or ''}
Supporting alt text: {blog.get('supporting_image_alt') or ''}
YouTube URL: {blog.get('youtube_url') or ''}

REVIEW CHECKLIST
{checklist_lines}
""".strip()


def render_prompt_template(template, variables):
    rendered = str(template or "")
    for key, value in dict(variables or {}).items():
        rendered = rendered.replace("{{" + str(key) + "}}", str(value or ""))
    return rendered


def suggest_buyer_intent(query):
    clean = str(query or "").casefold()
    strong_terms = ("wall art", "poster", "print", "framed", "decor", "man cave", "gift", "buy")
    informational_terms = ("stats", "statistics", "age", "score", "scores", "biography", "history of")
    if any(term in clean for term in strong_terms):
        return "Strong"
    if any(term in clean for term in informational_terms):
        return "Informational"
    if "best" in clean:
        return "Possible"
    return "Needs Review"


def suggest_page_type(query):
    clean = str(query or "").casefold()
    if any(term in clean for term in ("wall art", "poster", "print", "framed")):
        return "Collection"
    return "Blog"


def _parse_number(value, *, whole=False, percent=False):
    raw = str(value or "").strip().replace(",", "")
    if not raw:
        return 0 if whole else 0.0
    if percent and raw.endswith("%"):
        raw = raw[:-1].strip()
    number = float(raw)
    if number < 0:
        raise ValueError("negative")
    if whole and not number.is_integer():
        raise ValueError("not whole")
    return int(number) if whole else number


def parse_gsc_csv(content, *, existing_keywords=()):
    if isinstance(content, bytes):
        text = content.decode("utf-8-sig")
    else:
        text = str(content or "").lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    headers = reader.fieldnames or []
    header_map = {str(header or "").strip().casefold(): header for header in headers}
    if "query" not in header_map:
        raise SEOValidationError("The CSV must contain a Query column.")
    known = {"query", "clicks", "impressions", "ctr", "position"}
    existing = {str(row.get("keyword") or row.get("raw_query") or "").strip().casefold() for row in existing_keywords}
    seen = set()
    rows = []
    invalid = []
    skipped = []
    for source_row_number, source in enumerate(reader, start=2):
        raw_query = str(source.get(header_map["query"], "") or "").strip()
        query_key = raw_query.casefold()
        if not raw_query:
            invalid.append({"row": source_row_number, "query": "", "reason": "Query is blank"})
            continue
        if query_key in seen or query_key in existing:
            skipped.append({"row": source_row_number, "query": raw_query, "reason": "Duplicate query"})
            continue
        try:
            clicks = _parse_number(source.get(header_map.get("clicks"), 0), whole=True)
            impressions = _parse_number(source.get(header_map.get("impressions"), 0), whole=True)
            ctr = _parse_number(source.get(header_map.get("ctr"), 0), percent=True)
            position = _parse_number(source.get(header_map.get("position"), 0))
        except (TypeError, ValueError):
            invalid.append({"row": source_row_number, "query": raw_query, "reason": "Invalid numeric value"})
            continue
        seen.add(query_key)
        extra = {
            header: source.get(header)
            for header in headers
            if str(header or "").strip().casefold() not in known
        }
        rows.append(
            {
                "raw_query": raw_query,
                "keyword": raw_query,
                "clicks": clicks,
                "impressions": impressions,
                "ctr": ctr,
                "average_position": position,
                "source": "GSC CSV",
                "source_row": source_row_number,
                "extra_columns": extra,
                "buyer_intent": suggest_buyer_intent(raw_query),
                "page_type": suggest_page_type(raw_query),
                "priority": "Medium",
                "mapping_status": "Unreviewed",
                "target_market": "",
                "target_url": "",
                "category": "",
                "sport_player": "",
                "notes": "",
                "imported_date": date.today().isoformat(),
            }
        )
    return {
        "headers": headers,
        "rows": rows,
        "invalid": invalid,
        "skipped": skipped,
        "importable_count": len(rows),
        "invalid_count": len(invalid),
        "skipped_count": len(skipped),
    }


def commit_gsc_import(state, preview, *, actor=None):
    imported = []
    for row in preview.get("rows") or []:
        imported.append(upsert_record(state, "keywords", row, actor=actor))
    return {
        "imported": len(imported),
        "skipped": int(preview.get("skipped_count") or 0),
        "invalid": int(preview.get("invalid_count") or 0),
        "records": imported,
    }


def keyword_csv_bytes(records):
    output = io.StringIO(newline="")
    fields = (
        "Category",
        "Keyword",
        "Type",
        "Priority",
        "Notes",
        "Clicks",
        "Impressions",
        "CTR",
        "Position",
        "Target URL",
        "Status",
    )
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in records or []:
        writer.writerow(
            {
                "Category": row.get("category") or "",
                "Keyword": row.get("keyword") or "",
                "Type": row.get("page_type") or "",
                "Priority": row.get("priority") or "",
                "Notes": row.get("notes") or "",
                "Clicks": row.get("clicks", ""),
                "Impressions": row.get("impressions", ""),
                "CTR": row.get("ctr", ""),
                "Position": row.get("average_position", ""),
                "Target URL": row.get("target_url") or "",
                "Status": row.get("mapping_status") or "",
            }
        )
    return output.getvalue().encode("utf-8-sig")


def records_csv_bytes(records, fields):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(fields))
    writer.writeheader()
    for row in records or []:
        writer.writerow({field: row.get(field, "") for field in fields})
    return output.getvalue().encode("utf-8-sig")


def create_blog_brief_from_keyword(state, keyword, *, actor=None):
    keyword = dict(keyword or {})
    if not keyword.get("keyword"):
        raise SEOValidationError("Select a keyword before creating a blog brief.")
    record = upsert_record(
        state,
        "blog_records",
        {
            "article_title": "",
            "sport_topic": keyword.get("sport_player") or "",
            "primary_keyword": keyword.get("keyword") or "",
            "search_intent": keyword.get("buyer_intent") or "Needs Review",
            "target_market": keyword.get("target_market") or "Australia",
            "status": "Brief",
            "source_keyword_id": keyword.get("id") or "",
            "product_url_omitted": True,
        },
        actor=actor,
    )
    keyword["mapping_status"] = "Mapped"
    upsert_record(state, "keywords", keyword, actor=actor, record_id=keyword.get("id"))
    return record


def overview_metrics(state):
    blogs = active_records(state, "blog_records")
    keywords = active_records(state, "keywords")
    citations = active_records(state, "citations")
    outreach = active_records(state, "outreach_records")
    return {
        "Blog Posts in Progress": sum(
            str(row.get("status") or "") not in {"Published", "Archived"} for row in blogs
        ),
        "Keywords Mapped": sum(str(row.get("mapping_status") or "") == "Mapped" for row in keywords),
        "Citations Live": sum(str(row.get("status") or "") == "Live" for row in citations),
        "Outreach Pending": sum(
            str(row.get("status") or "") in {"Outreach Draft", "Sent", "Follow-up Due", "Replied"}
            for row in outreach
        ),
        "Backlinks Live": sum(str(row.get("status") or "") == "Live" for row in outreach),
    }


def duplicate_primary_keyword_warning(records, primary_keyword, *, excluding_id=""):
    clean = str(primary_keyword or "").strip().casefold()
    if not clean:
        return ""
    for row in records or []:
        if str(row.get("id") or "") == str(excluding_id or ""):
            continue
        if str(row.get("primary_keyword") or "").strip().casefold() == clean and not row.get("archived_at"):
            return "This primary keyword is already assigned to another blog record."
    return ""


def mapping_conflicts(mappings):
    by_keyword = {}
    by_target = {}
    conflicts = set()
    for row in mappings or []:
        row_id = str(row.get("id") or "")
        keyword = str(row.get("primary_keyword") or "").strip().casefold()
        target = str(row.get("target_page") or "").strip().casefold()
        if keyword and keyword in by_keyword:
            conflicts.update({row_id, by_keyword[keyword]})
        if target and target in by_target:
            conflicts.update({row_id, by_target[target]})
        if keyword:
            by_keyword[keyword] = row_id
        if target:
            by_target[target] = row_id
    return conflicts


def internal_link_opportunities(state):
    plans_by_blog = {
        str(row.get("source_blog_id") or row.get("source_blog") or "").strip().casefold(): row
        for row in active_records(state, "link_plans")
    }
    opportunities = []
    for blog in active_records(state, "blog_records"):
        key = str(blog.get("id") or blog.get("article_title") or "").strip().casefold()
        plan = plans_by_blog.get(key, {})
        missing = []
        if not plan.get("homepage_url"):
            missing.append("Homepage link")
        if not plan.get("collection_url"):
            missing.append("Collection link")
        if blog.get("product_url") and not plan.get("product_url"):
            missing.append("Verified product link")
        if not plan.get("collection_anchor_text"):
            missing.append("Anchor text")
        if str(plan.get("verification_status") or "") == "Not Checked":
            missing.append("Verification")
        if missing:
            opportunities.append(
                {
                    "Blog Article": blog.get("article_title") or "Untitled blog",
                    "Status": blog.get("status") or "",
                    "Missing": ", ".join(missing),
                }
            )
    return opportunities
