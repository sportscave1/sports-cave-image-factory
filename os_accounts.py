import os
import threading
import uuid
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import sc_auth
from shared_credentials import CREDENTIAL_PERMISSION_KEYS
import social_media
import seo_navigation as seo_workspace


ROLE_ADMIN = "admin"
ROLE_WORKER = "worker"
VALID_ROLES = {ROLE_ADMIN, ROLE_WORKER}
ACCOUNT_STATUS_ACTIVE = "active"
ACCOUNT_STATUS_REMOVED = "removed"
VALID_ACCOUNT_STATUSES = {ACCOUNT_STATUS_ACTIVE, ACCOUNT_STATUS_REMOVED}
ADMIN_TIMEZONE = "Australia/Sydney"
WORKER_TIMEZONE = "Asia/Manila"
COUNTRY_AUSTRALIA = "Australia"
COUNTRY_PHILIPPINES = "Philippines"
COUNTRY_TIMEZONES = {
    COUNTRY_AUSTRALIA: ADMIN_TIMEZONE,
    COUNTRY_PHILIPPINES: WORKER_TIMEZONE,
}
COUNTRY_OPTIONS = tuple(COUNTRY_TIMEZONES)
FILES_DELETE_CAPABILITY = "delete_files"
ACTIVITY_LOG_CAPABILITY = "view_activity_log"
EDIT_PROMPTS_CAPABILITY = "edit_prompts"
REPORTING_PAGE_KEY = "reporting"
DAILY_PLANNER_PAGE_KEY = "daily_planner"
DAILY_PLANNER_ROUTE = "Daily Planner"
WEEKLY_REVIEW_PAGE_KEY = "weekly_review"
WEEKLY_REVIEW_ROUTE = "Weekly Review"
ACTION_USER_REMOTE_LOGOUT = "account_remote_logout"
ACTION_ACCOUNT_PERMANENTLY_REMOVED = "account_permanently_removed"
ACTION_ADMIN_ACCOUNT_ACTION_DENIED = "account_admin_action_denied"
ACTION_ACCOUNT_REMOVAL_FAILED = "account_removal_failed"
REPORTING_OWNER_ENV_KEYS = (
    "SPORTS_CAVE_REPORTING_OWNER_EMAIL",
    "SPORTS_CAVE_ADMIN_EMAIL",
)

PAGE_REGISTRY = (
    {"key": "dashboard", "route": "Dashboard", "label": "Home", "worker_assignable": True},
    {"key": "orders", "route": "Orders", "label": "Orders", "worker_assignable": True},
    {"key": "prodigi", "route": "Prodigi", "label": "Fulfilment", "worker_assignable": True},
    {"key": "edition_ops", "route": "Edition Ops", "label": "Edition Ops", "worker_assignable": True},
    {"key": "mockups", "route": "Mockups", "label": "Mockups", "worker_assignable": True},
    {
        "key": social_media.SOCIAL_MEDIA_PAGE_KEY,
        "route": social_media.SOCIAL_MEDIA_ROUTE,
        "label": social_media.SOCIAL_MEDIA_ROUTE,
        "worker_assignable": True,
    },
    {
        "key": social_media.AI_REELS_PAGE_KEY,
        "route": social_media.AI_REELS_ROUTE,
        "label": social_media.AI_REELS_ROUTE,
        "worker_assignable": False,
        "parent_key": social_media.SOCIAL_MEDIA_PAGE_KEY,
        "navigation_child": True,
    },
    {
        "key": "product_uploads",
        "route": "Product Uploads",
        "label": "Product Uploads",
        "worker_assignable": True,
    },
    {
        "key": "design_studio",
        "route": "Design Studio",
        "label": "Design Studio",
        "worker_assignable": True,
    },
    {"key": "ads", "route": "Ads", "label": "Ads", "worker_assignable": True},
    {
        "key": seo_workspace.SEO_PAGE_KEY,
        "route": seo_workspace.SEO_OVERVIEW_ROUTE,
        "label": "SEO",
        "worker_assignable": True,
    },
    *(
        {
            "key": f"seo_{route.casefold().replace(' & ', '_').replace(' ', '_')}",
            "route": route,
            "label": seo_workspace.SEO_NAV_LABELS[route],
            "worker_assignable": False,
            "parent_key": seo_workspace.SEO_PAGE_KEY,
            "navigation_child": True,
        }
        for route in seo_workspace.SEO_ROUTES[1:]
    ),
    {
        "key": "va_training",
        "route": "VA Training",
        "label": "VA Training",
        "worker_assignable": True,
    },
    {"key": "files", "route": "Files", "label": "Files", "worker_assignable": True},
    {
        "key": REPORTING_PAGE_KEY,
        "route": "Reporting",
        "label": "Reporting",
        "worker_assignable": False,
        "top_level": True,
        "sensitive": True,
    },
    {
        "key": DAILY_PLANNER_PAGE_KEY,
        "route": DAILY_PLANNER_ROUTE,
        "label": DAILY_PLANNER_ROUTE,
        "worker_assignable": False,
        "parent_key": REPORTING_PAGE_KEY,
        "navigation_child": True,
    },
    {
        "key": WEEKLY_REVIEW_PAGE_KEY,
        "route": WEEKLY_REVIEW_ROUTE,
        "label": WEEKLY_REVIEW_ROUTE,
        "worker_assignable": False,
        "parent_key": REPORTING_PAGE_KEY,
        "navigation_child": True,
    },
    {
        "key": "accounts_access",
        "route": "Accounts & Access",
        "label": "Accounts & Access",
        "worker_assignable": False,
    },
    {"key": "developer", "route": "Developer", "label": "Developer", "worker_assignable": False},
    {"key": "products", "route": "Products", "label": "Products", "worker_assignable": False},
    {
        "key": "product_assets",
        "route": "Product Assets",
        "label": "Product Assets",
        "worker_assignable": False,
    },
    {
        "key": "webhook_events",
        "route": "Webhook Events",
        "label": "Webhook Events",
        "worker_assignable": False,
    },
    {"key": "sync_runs", "route": "Sync Runs", "label": "Sync Runs", "worker_assignable": False},
    {"key": "app_errors", "route": "App Errors", "label": "App Errors", "worker_assignable": False},
    {
        "key": "persistence_check",
        "route": "Persistence Check",
        "label": "Persistence Check",
        "worker_assignable": False,
    },
)

PAGE_ALIASES = {
    "Settings": "Developer",
    "Marketing Factory": "Ads",
    "Dropbox": "Files",
    social_media.LEGACY_REELS_ROUTE: social_media.AI_REELS_ROUTE,
}
PAGE_KEY_ALIASES = {
    "dropbox": "files",
    social_media.LEGACY_REELS_PAGE_KEY: social_media.SOCIAL_MEDIA_PAGE_KEY,
}
PAGE_BY_KEY = {page["key"]: page for page in PAGE_REGISTRY}
PAGE_BY_ROUTE = {page["route"]: page for page in PAGE_REGISTRY}
DATABASE_URL_ENV_KEYS = (
    "DATABASE_URL",
    "SUPABASE_DATABASE_URL",
    "SUPABASE_DB_URL",
    "POSTGRES_URL",
    "POSTGRES_PRISMA_URL",
    "POSTGRES_URL_NON_POOLING",
    "DATABASE_PRIVATE_URL",
    "DATABASE_PUBLIC_URL",
    "RENDER_DATABASE_URL",
)


class AccountStorageError(RuntimeError):
    pass


class AccountActionError(RuntimeError):
    pass


class AccountActionDenied(PermissionError):
    pass


def hash_password(password):
    return sc_auth.hash_password(password)


def verify_password(password, stored_hash):
    return sc_auth.verify_password(password, stored_hash)


def normalise_login(value):
    return str(value or "").strip().casefold()


def normalise_route(route):
    clean_route = str(route or "").strip()
    return PAGE_ALIASES.get(clean_route, clean_route)


def page_key_for_route(route):
    page = PAGE_BY_ROUTE.get(normalise_route(route))
    return page["key"] if page else ""


def normalise_page_key(page_key):
    clean_key = str(page_key or "").strip().casefold()
    return PAGE_KEY_ALIASES.get(clean_key, clean_key)


def worker_assignable_pages():
    return tuple(page for page in PAGE_REGISTRY if page["worker_assignable"])


def navigation_pages():
    return tuple(
        page
        for page in PAGE_REGISTRY
        if page.get("worker_assignable") or page.get("top_level")
    )


def default_timezone_for_role(role):
    return ADMIN_TIMEZONE if str(role or "").strip().casefold() == ROLE_ADMIN else WORKER_TIMEZONE


def default_country_for_role(role):
    return COUNTRY_AUSTRALIA if str(role or "").strip().casefold() == ROLE_ADMIN else COUNTRY_PHILIPPINES


def timezone_for_country(country):
    return COUNTRY_TIMEZONES.get(str(country or "").strip(), "")


def normalise_country(country, *, role=ROLE_WORKER):
    clean_country = str(country or "").strip()
    return clean_country if clean_country in COUNTRY_TIMEZONES else default_country_for_role(role)


def timezone_for_user(user):
    user = user or {}
    return (
        str(user.get("timezone") or "").strip()
        or timezone_for_country(user.get("country"))
        or default_timezone_for_role(user.get("role"))
    )


def password_strength_error(password):
    value = str(password or "")
    if len(value) < 10:
        return "Password must be at least 10 characters."
    if not any(char.isupper() for char in value):
        return "Password must include an uppercase letter."
    if not any(char.islower() for char in value):
        return "Password must include a lowercase letter."
    if not any(char.isdigit() for char in value):
        return "Password must include a number."
    return ""


def permission_keys(user):
    return {
        normalise_page_key(key)
        for key in (user or {}).get("page_permissions", ())
        if normalise_page_key(key)
    }


def account_status(user):
    clean_status = str((user or {}).get("account_status") or ACCOUNT_STATUS_ACTIVE).strip().casefold()
    return clean_status if clean_status in VALID_ACCOUNT_STATUSES else ACCOUNT_STATUS_ACTIVE


def account_is_removed(user):
    user = user or {}
    return bool(account_status(user) == ACCOUNT_STATUS_REMOVED or user.get("removed_at"))


def account_is_active(user):
    return bool(user and bool((user or {}).get("is_active", True)) and not account_is_removed(user))


def is_admin(user):
    return bool(account_is_active(user) and str((user or {}).get("role") or "").strip().casefold() == ROLE_ADMIN)


def reporting_owner_email(environ=None):
    environ = os.environ if environ is None else environ
    for key in REPORTING_OWNER_ENV_KEYS:
        value = normalise_login(environ.get(key, ""))
        if value:
            return value
    return ""


def is_reporting_owner(user, *, environ=None):
    user = user or {}
    owner_email = reporting_owner_email(environ)
    return bool(
        owner_email
        and account_is_active(user)
        and is_admin(user)
        and normalise_login(user.get("email")) == owner_email
    )


def can_manage_reporting_permission(actor, target):
    actor = actor or {}
    target = target or {}
    return bool(
        actor.get("id")
        and str(actor.get("id")) == str(target.get("id") or "")
        and is_reporting_owner(actor)
        and is_reporting_owner(target)
    )


def can_access_reporting(user):
    return bool(
        is_reporting_owner(user)
        and REPORTING_PAGE_KEY in permission_keys(user)
    )


def can_access_page(user, route_or_key):
    if not account_is_active(user):
        return False
    page = PAGE_BY_KEY.get(normalise_page_key(route_or_key))
    if page is None:
        page = PAGE_BY_ROUTE.get(normalise_route(route_or_key))
    if page and page["key"] == REPORTING_PAGE_KEY:
        return can_access_reporting(user)
    if page and page["key"] in {DAILY_PLANNER_PAGE_KEY, WEEKLY_REVIEW_PAGE_KEY}:
        return is_admin(user)
    if page and page["key"] in {
        social_media.SOCIAL_MEDIA_PAGE_KEY,
        social_media.AI_REELS_PAGE_KEY,
    }:
        if is_admin(user):
            return True
        return social_media.SOCIAL_MEDIA_PAGE_KEY in permission_keys(user)
    if page and (
        page["key"] == seo_workspace.SEO_PAGE_KEY
        or page.get("parent_key") == seo_workspace.SEO_PAGE_KEY
    ):
        if is_admin(user):
            return True
        return seo_workspace.SEO_PAGE_KEY in permission_keys(user)
    if page and page["key"] == "accounts_access":
        return True
    if is_admin(user):
        return True
    if not page or not page.get("worker_assignable"):
        return False
    return page["key"] in permission_keys(user)


def can_delete_files(user):
    """Return whether the account may remove items from the shared Files root."""
    if not account_is_active(user):
        return False
    if is_admin(user):
        return True
    return bool(
        can_access_page(user, "Files")
        and FILES_DELETE_CAPABILITY in permission_keys(user)
    )


def can_view_activity_log(user):
    """Return whether the account may view the Home page activity log."""
    if not account_is_active(user):
        return False
    if is_admin(user):
        return True
    return bool(
        can_access_page(user, "Dashboard")
        and ACTIVITY_LOG_CAPABILITY in permission_keys(user)
    )


def can_edit_prompts(user):
    """Return whether the signed-in account may edit persistent prompts."""
    if not account_is_active(user):
        return False
    if is_admin(user):
        return True
    return EDIT_PROMPTS_CAPABILITY in permission_keys(user)


def can_manage_credential_permissions(actor):
    """Return whether the account may grant or revoke shared credential access."""
    return bool(account_is_active(actor) and is_admin(actor))


def credential_permission_keys(page_keys):
    selected = permission_keys({"page_permissions": page_keys or ()})
    return tuple(key for key in CREDENTIAL_PERMISSION_KEYS if key in selected)


def _credential_permissions_requested(page_keys):
    return set(credential_permission_keys(page_keys))


def _credential_permission_write_allowed(actor, page_keys):
    requested = _credential_permissions_requested(page_keys)
    if requested and not can_manage_credential_permissions(actor):
        raise PermissionError("Password access can only be changed by an administrator.")
    return bool(requested)


def safe_account_label(user):
    user = user or {}
    return (
        str(user.get("display_name") or "").strip()
        or str(user.get("email") or "").strip()
        or str(user.get("username") or "").strip()
        or str(user.get("id") or "").strip()
        or "Account"
    )


def safe_account_identifier(user):
    user = user or {}
    return (
        str(user.get("email") or "").strip()
        or str(user.get("username") or "").strip()
        or str(user.get("id") or "").strip()
        or "unknown"
    )


def _safe_reason(reason):
    return (
        str(reason or "")
        .strip()
        .casefold()
        .replace(" ", "_")
        .replace(".", "")
        .replace(",", "")
    )[:120]


def _account_action_message(action_type, target_user):
    target_label = safe_account_label(target_user)
    if action_type == ACTION_USER_REMOTE_LOGOUT:
        return f"User remotely logged out: {target_label}"
    if action_type == ACTION_ACCOUNT_PERMANENTLY_REMOVED:
        return f"Account permanently removed: {target_label}"
    if action_type == ACTION_ADMIN_ACCOUNT_ACTION_DENIED:
        return f"Denied account action: {target_label}"
    if action_type == ACTION_ACCOUNT_REMOVAL_FAILED:
        return f"Failed removal attempt: {target_label}"
    return f"Account action: {target_label}"


def record_account_access_audit(action_type, actor, target_user=None, *, result, reason=""):
    actor = dict(actor or {})
    target_user = dict(target_user or {})
    metadata = {
        "actor_id": actor.get("id") or "",
        "actor_email": actor.get("email") or "",
        "actor_role": actor.get("role") or "",
        "target_account_id": target_user.get("id") or "",
        "target_account_display": target_user.get("display_name") or "",
        "target_account_identifier": safe_account_identifier(target_user),
        "account_action": str(action_type or "").strip(),
        "result": str(result or "").strip(),
        "safe_reason": _safe_reason(reason),
        "status": str(result or "").strip() or "unknown",
    }
    metadata = {key: value for key, value in metadata.items() if value not in ("", None)}
    try:
        from activity_log import record_activity_log

        record_activity_log(
            str(action_type or "").strip() or "account_action",
            "Accounts & Access",
            _account_action_message(action_type, target_user),
            entity_type="os_user",
            entity_id=target_user.get("id") or "",
            metadata=metadata,
            actor=safe_account_label(actor),
        )
    except Exception:
        pass


def allowed_navigation_routes(user):
    return tuple(
        page["route"]
        for page in navigation_pages()
        if can_access_page(user, page["key"])
    )


def run_authorized(user, route_or_key, renderer):
    if not can_access_page(user, route_or_key):
        return False
    renderer()
    return True


def _clean_user(row, permissions=None):
    row = dict(row or {})
    if not row:
        return {}
    row["id"] = str(row.get("id") or "")
    row["username"] = str(row.get("username") or "")
    row["email"] = str(row.get("email") or "")
    row["display_name"] = str(row.get("display_name") or row.get("username") or "")
    row["role"] = str(row.get("role") or ROLE_WORKER).casefold()
    row["country"] = normalise_country(row.get("country"), role=row["role"])
    row["timezone"] = str(
        row.get("timezone") or timezone_for_country(row["country"]) or default_timezone_for_role(row["role"])
    ).strip()
    try:
        row["session_version"] = max(1, int(row.get("session_version") or 1))
    except (TypeError, ValueError):
        row["session_version"] = 1
    row["account_status"] = account_status(row)
    row["removed_by"] = str(row.get("removed_by") or "")
    row["removed_at"] = row.get("removed_at")
    row["is_active"] = bool(row.get("is_active", True)) and not account_is_removed(row)
    if permissions is not None:
        row["page_permissions"] = sorted(set(permissions))
    else:
        row["page_permissions"] = sorted(set(row.get("page_permissions") or ()))
    return row


class PostgresAccountStore:
    def __init__(self):
        self._schema_ready = False
        self._schema_lock = threading.Lock()

    def is_configured(self):
        return any(str(os.getenv(key, "") or "").strip() for key in DATABASE_URL_ENV_KEYS)

    def _database_url(self):
        for key in DATABASE_URL_ENV_KEYS:
            value = str(os.getenv(key, "") or "").strip()
            if value:
                parsed = urlparse(value)
                query = dict(parse_qsl(parsed.query, keep_blank_values=True))
                query.setdefault("sslmode", "require")
                query.setdefault("connect_timeout", "4")
                return urlunparse(parsed._replace(query=urlencode(query)))
        raise AccountStorageError("Account storage is not configured.")

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:
            raise AccountStorageError("Postgres support is not installed.") from error
        try:
            return psycopg.connect(
                self._database_url(),
                row_factory=dict_row,
                connect_timeout=4,
                prepare_threshold=None,
                options="-c statement_timeout=4000 -c idle_in_transaction_session_timeout=4000",
            )
        except Exception as error:
            raise AccountStorageError("Accounts could not connect right now.") from error

    def ensure_schema(self):
        if self._schema_ready:
            return
        if not self.is_configured():
            raise AccountStorageError("Account storage is not configured.")
        with self._schema_lock:
            if self._schema_ready:
                return
            try:
                with self._connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
                        cur.execute(
                            """
                            CREATE TABLE IF NOT EXISTS os_users (
                                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                                username TEXT NOT NULL,
                                email TEXT,
                                display_name TEXT NOT NULL,
                                password_hash TEXT NOT NULL,
                                role TEXT NOT NULL DEFAULT 'worker'
                                    CHECK (role IN ('admin', 'worker')),
                                country TEXT NOT NULL DEFAULT 'Philippines',
                                timezone TEXT NOT NULL DEFAULT 'Asia/Manila',
                                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                                session_version INTEGER NOT NULL DEFAULT 1,
                                account_status TEXT NOT NULL DEFAULT 'active'
                                    CHECK (account_status IN ('active', 'removed')),
                                removed_at TIMESTAMPTZ,
                                removed_by UUID,
                                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                                last_login_at TIMESTAMPTZ
                            )
                            """
                        )
                        cur.execute(
                            """
                            CREATE TABLE IF NOT EXISTS os_user_page_permissions (
                                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                                user_id UUID NOT NULL REFERENCES os_users(id) ON DELETE CASCADE,
                                page_key TEXT NOT NULL,
                                can_access BOOLEAN NOT NULL DEFAULT TRUE,
                                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                                UNIQUE (user_id, page_key)
                            )
                            """
                        )
                        cur.execute("ALTER TABLE os_users ADD COLUMN IF NOT EXISTS country TEXT")
                        cur.execute("ALTER TABLE os_users ADD COLUMN IF NOT EXISTS timezone TEXT")
                        cur.execute("ALTER TABLE os_users ADD COLUMN IF NOT EXISTS session_version INTEGER DEFAULT 1")
                        cur.execute("ALTER TABLE os_users ADD COLUMN IF NOT EXISTS account_status TEXT DEFAULT 'active'")
                        cur.execute("ALTER TABLE os_users ADD COLUMN IF NOT EXISTS removed_at TIMESTAMPTZ")
                        cur.execute("ALTER TABLE os_users ADD COLUMN IF NOT EXISTS removed_by UUID")
                        cur.execute(
                            """
                            UPDATE os_users
                            SET session_version = 1
                            WHERE session_version IS NULL OR session_version < 1
                            """
                        )
                        cur.execute(
                            """
                            UPDATE os_users
                            SET account_status = 'active'
                            WHERE account_status IS NULL
                               OR account_status NOT IN ('active', 'removed')
                            """
                        )
                        cur.execute(
                            """
                            UPDATE os_users
                            SET country = CASE
                                WHEN role = 'admin' THEN %s
                                ELSE %s
                            END
                            WHERE country IS NULL OR country = ''
                            """,
                            (COUNTRY_AUSTRALIA, COUNTRY_PHILIPPINES),
                        )
                        cur.execute(
                            """
                            UPDATE os_users
                            SET timezone = CASE
                                WHEN country = %s THEN %s
                                WHEN country = %s THEN %s
                                WHEN role = 'admin' THEN %s
                                ELSE %s
                            END
                            WHERE timezone IS NULL OR timezone = ''
                            """,
                            (
                                COUNTRY_AUSTRALIA,
                                ADMIN_TIMEZONE,
                                COUNTRY_PHILIPPINES,
                                WORKER_TIMEZONE,
                                ADMIN_TIMEZONE,
                                WORKER_TIMEZONE,
                            ),
                        )
                        cur.execute("ALTER TABLE os_users ALTER COLUMN country SET DEFAULT 'Philippines'")
                        cur.execute("ALTER TABLE os_users ALTER COLUMN country SET NOT NULL")
                        cur.execute("ALTER TABLE os_users ALTER COLUMN timezone SET DEFAULT 'Asia/Manila'")
                        cur.execute("ALTER TABLE os_users ALTER COLUMN timezone SET NOT NULL")
                        cur.execute("ALTER TABLE os_users ALTER COLUMN session_version SET DEFAULT 1")
                        cur.execute("ALTER TABLE os_users ALTER COLUMN session_version SET NOT NULL")
                        cur.execute("ALTER TABLE os_users ALTER COLUMN account_status SET DEFAULT 'active'")
                        cur.execute("ALTER TABLE os_users ALTER COLUMN account_status SET NOT NULL")
                        cur.execute(
                            """
                            DO $$
                            BEGIN
                                ALTER TABLE os_users
                                ADD CONSTRAINT os_users_account_status_check
                                CHECK (account_status IN ('active', 'removed'));
                            EXCEPTION WHEN duplicate_object THEN NULL;
                            END $$;
                            """
                        )
                        cur.execute(
                            "CREATE UNIQUE INDEX IF NOT EXISTS idx_os_users_username_unique "
                            "ON os_users (lower(username))"
                        )
                        cur.execute(
                            "CREATE UNIQUE INDEX IF NOT EXISTS idx_os_users_email_unique "
                            "ON os_users (lower(email)) WHERE email IS NOT NULL AND email <> ''"
                        )
                        cur.execute(
                            "CREATE UNIQUE INDEX IF NOT EXISTS idx_os_users_single_admin "
                            "ON os_users (role) WHERE role='admin'"
                        )
                        cur.execute(
                            "CREATE INDEX IF NOT EXISTS idx_os_user_permissions_user "
                            "ON os_user_page_permissions (user_id, can_access)"
                        )
                        cur.execute(
                            "CREATE INDEX IF NOT EXISTS idx_os_user_permissions_page_key "
                            "ON os_user_page_permissions (page_key, can_access)"
                        )
                        cur.execute(
                            "CREATE INDEX IF NOT EXISTS idx_os_users_active_accounts "
                            "ON os_users (account_status, is_active, role)"
                        )
                    conn.commit()
            except AccountStorageError:
                raise
            except Exception as error:
                raise AccountStorageError("Accounts could not connect right now.") from error
            self._schema_ready = True

    @staticmethod
    def _permissions(cur, user_id):
        cur.execute(
            """
            SELECT page_key
            FROM os_user_page_permissions
            WHERE user_id=%s AND can_access IS TRUE
            ORDER BY page_key
            """,
            (str(user_id),),
        )
        return [row.get("page_key") for row in cur.fetchall() if row.get("page_key")]

    def first_admin(self):
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM os_users
                    WHERE role='admin'
                      AND is_active IS TRUE
                      AND account_status <> 'removed'
                    ORDER BY created_at
                    LIMIT 1
                    """
                )
                row = cur.fetchone()
                return _clean_user(row, self._permissions(cur, row["id"]) if row else ())

    def get_user(self, user_id, *, include_removed=False):
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                if include_removed:
                    cur.execute("SELECT * FROM os_users WHERE id=%s LIMIT 1", (str(user_id),))
                else:
                    cur.execute(
                        """
                        SELECT * FROM os_users
                        WHERE id=%s
                          AND account_status <> 'removed'
                        LIMIT 1
                        """,
                        (str(user_id),),
                    )
                row = cur.fetchone()
                return _clean_user(row, self._permissions(cur, row["id"]) if row else ())

    def find_user_by_login(self, login):
        self.ensure_schema()
        clean_login = normalise_login(login)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM os_users
                    WHERE (lower(username)=%s OR lower(COALESCE(email, ''))=%s)
                      AND account_status <> 'removed'
                    ORDER BY created_at
                    LIMIT 1
                    """,
                    (clean_login, clean_login),
                )
                row = cur.fetchone()
                return _clean_user(row, self._permissions(cur, row["id"]) if row else ())

    def list_users(self):
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, username, email, display_name, role, country, timezone, is_active,
                           session_version, account_status, removed_at, removed_by,
                           created_at, updated_at, last_login_at
                    FROM os_users
                    WHERE account_status <> 'removed'
                    ORDER BY CASE WHEN role='admin' THEN 0 ELSE 1 END, display_name, username
                    """
                )
                rows = []
                for row in cur.fetchall():
                    rows.append(_clean_user(row, self._permissions(cur, row["id"])))
                return rows

    @staticmethod
    def _replace_permissions(cur, user_id, page_keys, *, allow_credential_permissions=False):
        valid_keys = {page["key"] for page in worker_assignable_pages()}
        valid_keys.add(FILES_DELETE_CAPABILITY)
        valid_keys.add(ACTIVITY_LOG_CAPABILITY)
        valid_keys.add(EDIT_PROMPTS_CAPABILITY)
        if allow_credential_permissions:
            valid_keys.update(CREDENTIAL_PERMISSION_KEYS)
        normalised_keys = {
            normalise_page_key(key)
            for key in page_keys or ()
            if normalise_page_key(key)
        }
        if normalised_keys.intersection(CREDENTIAL_PERMISSION_KEYS) and not allow_credential_permissions:
            raise PermissionError("Password access can only be changed by an administrator.")
        selected = sorted(key for key in normalised_keys if key in valid_keys)
        cur.execute("DELETE FROM os_user_page_permissions WHERE user_id=%s", (str(user_id),))
        for page_key in selected:
            cur.execute(
                """
                INSERT INTO os_user_page_permissions(user_id, page_key, can_access)
                VALUES (%s, %s, TRUE)
                """,
                (str(user_id), page_key),
            )
        return selected

    def create_user(
        self,
        *,
        username,
        email,
        display_name,
        password_hash,
        role,
        page_keys=(),
        country="",
        allow_credential_permissions=False,
    ):
        self.ensure_schema()
        clean_role = str(role or ROLE_WORKER).casefold()
        if clean_role not in VALID_ROLES:
            raise ValueError("Invalid account role.")
        clean_country = normalise_country(country, role=clean_role)
        timezone_name = timezone_for_country(clean_country) or default_timezone_for_role(clean_role)
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO os_users(username, email, display_name, password_hash, role, country, timezone)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        RETURNING *
                        """,
                        (
                            str(username or "").strip(),
                            str(email or "").strip() or None,
                            str(display_name or "").strip(),
                            str(password_hash or ""),
                            clean_role,
                            clean_country,
                            timezone_name,
                        ),
                    )
                    row = cur.fetchone() or {}
                    selected = (
                        self._replace_permissions(
                            cur,
                            row.get("id"),
                            page_keys,
                            allow_credential_permissions=allow_credential_permissions,
                        )
                        if clean_role == ROLE_WORKER
                        else []
                    )
                conn.commit()
            return _clean_user(row, selected)
        except Exception as error:
            if getattr(error, "sqlstate", "") == "23505":
                raise ValueError("That username or email is already in use.") from error
            raise

    def update_worker(
        self,
        user_id,
        *,
        username,
        email,
        display_name,
        is_active,
        page_keys,
        password_hash="",
        country="",
        allow_credential_permissions=False,
    ):
        self.ensure_schema()
        clean_country = normalise_country(country, role=ROLE_WORKER)
        timezone_name = timezone_for_country(clean_country) or WORKER_TIMEZONE
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    if password_hash:
                        password_sql = ", password_hash=%s"
                        params = [
                            str(username or "").strip(),
                            str(email or "").strip() or None,
                            str(display_name or "").strip(),
                            clean_country,
                            timezone_name,
                            str(password_hash),
                            str(user_id),
                        ]
                    else:
                        password_sql = ""
                        params = [
                            str(username or "").strip(),
                            str(email or "").strip() or None,
                            str(display_name or "").strip(),
                            clean_country,
                            timezone_name,
                            str(user_id),
                        ]
                    cur.execute(
                        f"""
                        UPDATE os_users
                        SET username=%s, email=%s, display_name=%s,
                            country=%s, timezone=%s,
                            updated_at=now(){password_sql}
                        WHERE id=%s
                          AND role='worker'
                          AND account_status <> 'removed'
                        RETURNING *
                        """,
                        params,
                    )
                    row = cur.fetchone()
                    if not row:
                        raise ValueError("Worker account was not found.")
                    selected = self._replace_permissions(
                        cur,
                        user_id,
                        page_keys,
                        allow_credential_permissions=allow_credential_permissions,
                    )
                conn.commit()
            return _clean_user(row, selected)
        except Exception as error:
            if getattr(error, "sqlstate", "") == "23505":
                raise ValueError("That username or email is already in use.") from error
            raise

    def update_profile(self, user_id, *, display_name, country):
        self.ensure_schema()
        clean_name = str(display_name or "").strip()
        if not clean_name:
            raise ValueError("Display name is required.")
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT role FROM os_users
                    WHERE id=%s
                      AND account_status <> 'removed'
                    LIMIT 1
                    """,
                    (str(user_id),),
                )
                current = cur.fetchone() or {}
                if not current:
                    raise ValueError("Account was not found.")
                role = str(current.get("role") or ROLE_WORKER).casefold()
                clean_country = normalise_country(country, role=role)
                timezone_name = timezone_for_country(clean_country) or default_timezone_for_role(role)
                cur.execute(
                    """
                    UPDATE os_users
                    SET display_name=%s, country=%s, timezone=%s, updated_at=now()
                    WHERE id=%s
                      AND account_status <> 'removed'
                    RETURNING *
                    """,
                    (clean_name, clean_country, timezone_name, str(user_id)),
                )
                row = cur.fetchone()
                permissions = self._permissions(cur, user_id) if row else ()
            conn.commit()
        return _clean_user(row, permissions)

    def update_password(self, user_id, *, current_password, new_password):
        self.ensure_schema()
        strength_error = password_strength_error(new_password)
        if strength_error:
            raise ValueError(strength_error)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM os_users
                    WHERE id=%s
                      AND account_status <> 'removed'
                    LIMIT 1
                    """,
                    (str(user_id),),
                )
                row = cur.fetchone()
                if not row:
                    raise ValueError("Account was not found.")
                if not verify_password(current_password, row.get("password_hash")):
                    raise ValueError("Current password is incorrect.")
                cur.execute(
                    """
                    UPDATE os_users
                    SET password_hash=%s, updated_at=now()
                    WHERE id=%s
                      AND account_status <> 'removed'
                    RETURNING *
                    """,
                    (hash_password(new_password), str(user_id)),
                )
                updated = cur.fetchone()
                permissions = self._permissions(cur, user_id) if updated else ()
            conn.commit()
        return _clean_user(updated, permissions)

    def update_last_login(self, user_id):
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE os_users
                    SET last_login_at=now(), updated_at=now()
                    WHERE id=%s
                      AND is_active IS TRUE
                      AND account_status <> 'removed'
                    RETURNING *
                    """,
                    (str(user_id),),
                )
                row = cur.fetchone()
                permissions = self._permissions(cur, user_id) if row else ()
            conn.commit()
        return _clean_user(row, permissions)

    @staticmethod
    def _clean_uuid(value):
        try:
            return str(uuid.UUID(str(value or "").strip()))
        except (TypeError, ValueError, AttributeError):
            return ""

    @staticmethod
    def _active_admin_count(cur, *, exclude_user_id=""):
        params = []
        exclude_clause = ""
        clean_exclude = PostgresAccountStore._clean_uuid(exclude_user_id)
        if clean_exclude:
            exclude_clause = "AND id <> %s"
            params.append(clean_exclude)
        cur.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM os_users
            WHERE role='admin'
              AND is_active IS TRUE
              AND account_status <> 'removed'
              {exclude_clause}
            """,
            tuple(params),
        )
        return int((cur.fetchone() or {}).get("count") or 0)

    @staticmethod
    def _fetch_action_actor(cur, actor):
        clean_actor_id = PostgresAccountStore._clean_uuid((actor or {}).get("id"))
        if not clean_actor_id:
            raise AccountActionDenied("Only an active administrator can perform this account action.")
        cur.execute(
            """
            SELECT *
            FROM os_users
            WHERE id=%s
              AND is_active IS TRUE
              AND account_status <> 'removed'
            LIMIT 1
            FOR UPDATE
            """,
            (clean_actor_id,),
        )
        row = cur.fetchone()
        clean_actor = _clean_user(row, PostgresAccountStore._permissions(cur, clean_actor_id) if row else ())
        if not is_admin(clean_actor):
            raise AccountActionDenied("Only an active administrator can perform this account action.")
        return clean_actor

    @staticmethod
    def _fetch_action_target(cur, target_user_id):
        clean_target_id = PostgresAccountStore._clean_uuid(target_user_id)
        if not clean_target_id:
            return clean_target_id, {}
        cur.execute(
            """
            SELECT *
            FROM os_users
            WHERE id=%s
            LIMIT 1
            FOR UPDATE
            """,
            (clean_target_id,),
        )
        row = cur.fetchone()
        permissions = PostgresAccountStore._permissions(cur, clean_target_id) if row else ()
        return clean_target_id, _clean_user(row, permissions)

    def remote_logout_user(self, actor, target_user_id):
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                clean_actor = self._fetch_action_actor(cur, actor)
                clean_target_id, target = self._fetch_action_target(cur, target_user_id)
                if not target:
                    conn.commit()
                    return {
                        "changed": False,
                        "actor": clean_actor,
                        "target": {"id": clean_target_id or str(target_user_id or "")},
                        "reason": "target_not_found",
                    }
                if account_is_removed(target):
                    conn.commit()
                    return {
                        "changed": False,
                        "actor": clean_actor,
                        "target": target,
                        "reason": "already_removed",
                    }
                cur.execute(
                    """
                    UPDATE os_users
                    SET session_version = GREATEST(COALESCE(session_version, 1), 1) + 1,
                        updated_at = now()
                    WHERE id=%s
                      AND account_status <> 'removed'
                    RETURNING *
                    """,
                    (clean_target_id,),
                )
                row = cur.fetchone()
                permissions = self._permissions(cur, clean_target_id) if row else ()
            conn.commit()
        return {
            "changed": bool(row),
            "actor": clean_actor,
            "target": _clean_user(row, permissions) if row else target,
            "reason": "logged_out" if row else "target_not_found",
        }

    def remove_account(self, actor, target_user_id):
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                clean_actor = self._fetch_action_actor(cur, actor)
                clean_target_id, target = self._fetch_action_target(cur, target_user_id)
                if not target:
                    conn.commit()
                    return {
                        "changed": False,
                        "actor": clean_actor,
                        "target": {"id": clean_target_id or str(target_user_id or "")},
                        "reason": "target_not_found",
                    }
                if account_is_removed(target):
                    cur.execute("DELETE FROM os_user_page_permissions WHERE user_id=%s", (clean_target_id,))
                    conn.commit()
                    return {
                        "changed": False,
                        "actor": clean_actor,
                        "target": {**target, "page_permissions": []},
                        "reason": "already_removed",
                    }
                if str(clean_actor.get("id") or "") == str(target.get("id") or ""):
                    raise AccountActionDenied("You cannot remove your own active account.")
                if str(target.get("role") or "").casefold() == ROLE_ADMIN and self._active_admin_count(
                    cur,
                    exclude_user_id=clean_target_id,
                ) < 1:
                    raise AccountActionDenied("The final active administrator account cannot be removed.")
                tombstone_username = f"removed-{clean_target_id}"
                cur.execute("DELETE FROM os_user_page_permissions WHERE user_id=%s", (clean_target_id,))
                cur.execute(
                    """
                    UPDATE os_users
                    SET username=%s,
                        email=NULL,
                        password_hash='removed-account',
                        is_active=FALSE,
                        account_status='removed',
                        removed_at=COALESCE(removed_at, now()),
                        removed_by=%s,
                        session_version = GREATEST(COALESCE(session_version, 1), 1) + 1,
                        updated_at=now()
                    WHERE id=%s
                    RETURNING *
                    """,
                    (tombstone_username, clean_actor.get("id"), clean_target_id),
                )
                row = cur.fetchone()
            conn.commit()
        return {
            "changed": bool(row),
            "actor": clean_actor,
            "target": _clean_user(row, ()) if row else target,
            "previous_target": target,
            "reason": "removed" if row else "target_not_found",
        }

    def set_reporting_permission(self, actor, target_user_id, enabled):
        actor = _clean_user(actor)
        clean_target_id = str(target_user_id or "").strip()
        if not clean_target_id or str(actor.get("id") or "") != clean_target_id:
            raise PermissionError("Reporting access can only be changed for the signed-in owner account.")
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM os_users
                    WHERE id=%s
                      AND account_status <> 'removed'
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (clean_target_id,),
                )
                target = cur.fetchone()
                permissions = self._permissions(cur, clean_target_id) if target else ()
                clean_target = _clean_user(target, permissions)
                if not can_manage_reporting_permission(actor, clean_target):
                    raise PermissionError("Reporting access is restricted to the configured owner account.")
                old_value = REPORTING_PAGE_KEY in permission_keys(clean_target)
                new_value = bool(enabled)
                if old_value != new_value:
                    if new_value:
                        cur.execute(
                            """
                            INSERT INTO os_user_page_permissions(user_id, page_key, can_access)
                            VALUES (%s, %s, TRUE)
                            ON CONFLICT (user_id, page_key)
                            DO UPDATE SET can_access=TRUE, updated_at=now()
                            """,
                            (clean_target_id, REPORTING_PAGE_KEY),
                        )
                    else:
                        cur.execute(
                            """
                            DELETE FROM os_user_page_permissions
                            WHERE user_id=%s AND page_key=%s
                            """,
                            (clean_target_id, REPORTING_PAGE_KEY),
                        )
                    cur.execute(
                        "UPDATE os_users SET updated_at=now() WHERE id=%s RETURNING *",
                        (clean_target_id,),
                    )
                    target = cur.fetchone() or target
                    permissions = self._permissions(cur, clean_target_id)
                updated = _clean_user(target, permissions)
            conn.commit()
        return {
            "changed": old_value != new_value,
            "old_value": old_value,
            "new_value": new_value,
            "user": updated,
            "event_key": (
                f"reporting-permission:{clean_target_id}:"
                f"{int(old_value)}:{int(new_value)}:{updated.get('updated_at') or ''}"
            ),
        }


DEFAULT_STORE = PostgresAccountStore()
_PREPARE_LOCK = threading.Lock()
_PREPARED = False


def prepare_account_system(store=None):
    global _PREPARED
    store = store or DEFAULT_STORE
    if store is DEFAULT_STORE and _PREPARED:
        return {"available": True, "admin": store.first_admin()}
    if not store.is_configured():
        return {"available": False, "admin": {}, "reason": "not_configured"}
    with _PREPARE_LOCK:
        store.ensure_schema()
        admin = bootstrap_first_admin_from_environment(store=store)
        if store is DEFAULT_STORE:
            _PREPARED = True
        return {"available": True, "admin": admin or store.first_admin(), "reason": "ok"}


def bootstrap_first_admin(
    username,
    password,
    *,
    display_name="Sports Cave Admin",
    country=COUNTRY_AUSTRALIA,
    store=None,
):
    store = store or DEFAULT_STORE
    existing = store.first_admin()
    if existing:
        return existing
    clean_username = str(username or "").strip()
    if not clean_username or not password:
        return {}
    email = clean_username if "@" in clean_username else ""
    try:
        return store.create_user(
            username=clean_username,
            email=email,
            display_name=str(display_name or "").strip() or "Sports Cave Admin",
            password_hash=hash_password(password),
            role=ROLE_ADMIN,
            country=country,
        )
    except ValueError:
        return store.first_admin()


def bootstrap_first_admin_from_environment(*, store=None):
    email = str(os.getenv("SPORTS_CAVE_ADMIN_EMAIL", "") or "").strip()
    password = str(os.getenv("SPORTS_CAVE_ADMIN_PASSWORD", "") or "")
    if not email or not password:
        return (store or DEFAULT_STORE).first_admin()
    display_name = str(os.getenv("SPORTS_CAVE_ADMIN_NAME", "Sports Cave Admin") or "").strip()
    return bootstrap_first_admin(email, password, display_name=display_name, store=store)


def authenticate_user(login, password, *, store=None):
    store = store or DEFAULT_STORE
    user = store.find_user_by_login(login)
    if not user:
        return None, "invalid"
    if not account_is_active(user):
        return None, "inactive"
    if not verify_password(password, user.get("password_hash")):
        return None, "invalid"
    updated = store.update_last_login(user["id"])
    if not account_is_active(updated):
        return None, "inactive"
    return updated, "ok"


def create_worker_account(
    *,
    username,
    email="",
    display_name,
    password,
    page_keys=(),
    country=COUNTRY_PHILIPPINES,
    store=None,
    actor=None,
):
    clean_username = str(username or "").strip()
    clean_name = str(display_name or "").strip()
    if not clean_username or not clean_name or not password:
        raise ValueError("Username, display name and password are required.")
    allow_credential_permissions = _credential_permission_write_allowed(actor, page_keys)
    return (store or DEFAULT_STORE).create_user(
        username=clean_username,
        email=str(email or "").strip(),
        display_name=clean_name,
        password_hash=hash_password(password),
        role=ROLE_WORKER,
        page_keys=page_keys,
        country=country,
        allow_credential_permissions=allow_credential_permissions,
    )


def update_worker_account(
    user_id,
    *,
    username,
    email="",
    display_name,
    is_active,
    page_keys=(),
    new_password="",
    country=COUNTRY_PHILIPPINES,
    store=None,
    actor=None,
):
    clean_username = str(username or "").strip()
    clean_name = str(display_name or "").strip()
    if not clean_username or not clean_name:
        raise ValueError("Username and display name are required.")
    password_hash = hash_password(new_password) if new_password else ""
    allow_credential_permissions = _credential_permission_write_allowed(actor, page_keys)
    return (store or DEFAULT_STORE).update_worker(
        user_id,
        username=clean_username,
        email=str(email or "").strip(),
        display_name=clean_name,
        is_active=bool(is_active),
        page_keys=page_keys,
        password_hash=password_hash,
        country=country,
        allow_credential_permissions=allow_credential_permissions,
    )


def update_my_profile(user_id, *, display_name, country, store=None):
    return (store or DEFAULT_STORE).update_profile(
        user_id,
        display_name=display_name,
        country=country,
    )


def change_my_password(user_id, *, current_password, new_password, store=None):
    return (store or DEFAULT_STORE).update_password(
        user_id,
        current_password=current_password,
        new_password=new_password,
    )


def update_reporting_permission(actor, *, enabled, store=None):
    actor = actor or {}
    return (store or DEFAULT_STORE).set_reporting_permission(
        actor,
        actor.get("id"),
        bool(enabled),
    )


def remote_logout_user(actor, target_user_id, *, store=None):
    store = store or DEFAULT_STORE
    try:
        result = store.remote_logout_user(actor or {}, target_user_id)
    except PermissionError as error:
        record_account_access_audit(
            ACTION_ADMIN_ACCOUNT_ACTION_DENIED,
            actor or {},
            {"id": str(target_user_id or "")},
            result="denied",
            reason=str(error),
        )
        raise
    except Exception:
        record_account_access_audit(
            ACTION_USER_REMOTE_LOGOUT,
            actor or {},
            {"id": str(target_user_id or "")},
            result="failed",
            reason="account_action_unavailable",
        )
        raise
    target = result.get("target") or {"id": str(target_user_id or "")}
    record_account_access_audit(
        ACTION_USER_REMOTE_LOGOUT,
        result.get("actor") or actor or {},
        target,
        result="success" if result.get("changed") else result.get("reason") or "unchanged",
        reason=result.get("reason") or "",
    )
    return result


def remove_user_account(actor, target_user_id, *, store=None):
    store = store or DEFAULT_STORE
    try:
        result = store.remove_account(actor or {}, target_user_id)
    except PermissionError as error:
        record_account_access_audit(
            ACTION_ADMIN_ACCOUNT_ACTION_DENIED,
            actor or {},
            {"id": str(target_user_id or "")},
            result="denied",
            reason=str(error),
        )
        raise
    except Exception:
        record_account_access_audit(
            ACTION_ACCOUNT_REMOVAL_FAILED,
            actor or {},
            {"id": str(target_user_id or "")},
            result="failed",
            reason="account_action_unavailable",
        )
        raise
    target = result.get("previous_target") or result.get("target") or {"id": str(target_user_id or "")}
    if result.get("changed"):
        record_account_access_audit(
            ACTION_ACCOUNT_PERMANENTLY_REMOVED,
            result.get("actor") or actor or {},
            target,
            result="success",
            reason=result.get("reason") or "removed",
        )
    else:
        record_account_access_audit(
            ACTION_ACCOUNT_REMOVAL_FAILED,
            result.get("actor") or actor or {},
            target,
            result=result.get("reason") or "failed",
            reason=result.get("reason") or "failed",
        )
    return result


def reset_account_cache():
    global _PREPARED
    _PREPARED = False
    DEFAULT_STORE._schema_ready = False
