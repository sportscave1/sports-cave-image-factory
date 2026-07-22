import os
import threading
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import sc_auth


ROLE_ADMIN = "admin"
ROLE_WORKER = "worker"
VALID_ROLES = {ROLE_ADMIN, ROLE_WORKER}
ADMIN_TIMEZONE = "Australia/Sydney"
WORKER_TIMEZONE = "Asia/Manila"

PAGE_REGISTRY = (
    {"key": "dashboard", "route": "Dashboard", "label": "Home", "worker_assignable": True},
    {"key": "orders", "route": "Orders", "label": "Orders", "worker_assignable": True},
    {"key": "prodigi", "route": "Prodigi", "label": "Prodigi", "worker_assignable": True},
    {"key": "edition_ops", "route": "Edition Ops", "label": "Edition Ops", "worker_assignable": True},
    {"key": "mockups", "route": "Mockups", "label": "Mockups", "worker_assignable": True},
    {
        "key": "social_media_reels_studio",
        "route": "Social Media Reels Studio",
        "label": "Social Media Reels Studio",
        "worker_assignable": True,
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
        "key": "va_training",
        "route": "VA Training",
        "label": "VA Training",
        "worker_assignable": True,
    },
    {"key": "dropbox", "route": "Dropbox", "label": "Dropbox", "worker_assignable": True},
    {
        "key": "accounts_access",
        "route": "Accounts & Access",
        "label": "Accounts & Access",
        "worker_assignable": False,
    },
    {"key": "developer", "route": "Developer", "label": "Developer", "worker_assignable": False},
    {"key": "files", "route": "Files", "label": "Files", "worker_assignable": False},
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


def worker_assignable_pages():
    return tuple(page for page in PAGE_REGISTRY if page["worker_assignable"])


def default_timezone_for_role(role):
    return ADMIN_TIMEZONE if str(role or "").strip().casefold() == ROLE_ADMIN else WORKER_TIMEZONE


def timezone_for_user(user):
    user = user or {}
    return str(user.get("timezone") or "").strip() or default_timezone_for_role(user.get("role"))


def permission_keys(user):
    return {
        str(key or "").strip()
        for key in (user or {}).get("page_permissions", ())
        if str(key or "").strip()
    }


def is_admin(user):
    return str((user or {}).get("role") or "").strip().casefold() == ROLE_ADMIN


def can_access_page(user, route_or_key):
    if not user or not bool(user.get("is_active", True)):
        return False
    if is_admin(user):
        return True
    page = PAGE_BY_KEY.get(str(route_or_key or "").strip())
    if page is None:
        page = PAGE_BY_ROUTE.get(normalise_route(route_or_key))
    if not page or not page.get("worker_assignable"):
        return False
    return page["key"] in permission_keys(user)


def allowed_navigation_routes(user):
    return tuple(
        page["route"]
        for page in worker_assignable_pages()
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
    row["timezone"] = str(row.get("timezone") or default_timezone_for_role(row["role"])).strip()
    row["is_active"] = bool(row.get("is_active", True))
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
                                timezone TEXT NOT NULL DEFAULT 'Asia/Manila',
                                is_active BOOLEAN NOT NULL DEFAULT TRUE,
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
                        cur.execute("ALTER TABLE os_users ADD COLUMN IF NOT EXISTS timezone TEXT")
                        cur.execute(
                            """
                            UPDATE os_users
                            SET timezone = CASE
                                WHEN role = 'admin' THEN %s
                                ELSE %s
                            END
                            WHERE timezone IS NULL OR timezone = ''
                            """,
                            (ADMIN_TIMEZONE, WORKER_TIMEZONE),
                        )
                        cur.execute("ALTER TABLE os_users ALTER COLUMN timezone SET DEFAULT 'Asia/Manila'")
                        cur.execute("ALTER TABLE os_users ALTER COLUMN timezone SET NOT NULL")
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
                cur.execute("SELECT * FROM os_users WHERE role='admin' ORDER BY created_at LIMIT 1")
                row = cur.fetchone()
                return _clean_user(row, self._permissions(cur, row["id"]) if row else ())

    def get_user(self, user_id):
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM os_users WHERE id=%s LIMIT 1", (str(user_id),))
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
                    WHERE lower(username)=%s OR lower(COALESCE(email, ''))=%s
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
                    SELECT id, username, email, display_name, role, timezone, is_active,
                           created_at, updated_at, last_login_at
                    FROM os_users
                    ORDER BY CASE WHEN role='admin' THEN 0 ELSE 1 END, display_name, username
                    """
                )
                rows = []
                for row in cur.fetchall():
                    rows.append(_clean_user(row, self._permissions(cur, row["id"])))
                return rows

    @staticmethod
    def _replace_permissions(cur, user_id, page_keys):
        valid_keys = {page["key"] for page in worker_assignable_pages()}
        selected = sorted({str(key) for key in page_keys or () if str(key) in valid_keys})
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

    def create_user(self, *, username, email, display_name, password_hash, role, page_keys=()):
        self.ensure_schema()
        clean_role = str(role or ROLE_WORKER).casefold()
        if clean_role not in VALID_ROLES:
            raise ValueError("Invalid account role.")
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO os_users(username, email, display_name, password_hash, role, timezone)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING *
                        """,
                        (
                            str(username or "").strip(),
                            str(email or "").strip() or None,
                            str(display_name or "").strip(),
                            str(password_hash or ""),
                            clean_role,
                            default_timezone_for_role(clean_role),
                        ),
                    )
                    row = cur.fetchone() or {}
                    selected = self._replace_permissions(cur, row.get("id"), page_keys) if clean_role == ROLE_WORKER else []
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
    ):
        self.ensure_schema()
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    if password_hash:
                        password_sql = ", password_hash=%s"
                        params = [
                            str(username or "").strip(),
                            str(email or "").strip() or None,
                            str(display_name or "").strip(),
                            bool(is_active),
                            str(password_hash),
                            str(user_id),
                        ]
                    else:
                        password_sql = ""
                        params = [
                            str(username or "").strip(),
                            str(email or "").strip() or None,
                            str(display_name or "").strip(),
                            bool(is_active),
                            str(user_id),
                        ]
                    cur.execute(
                        f"""
                        UPDATE os_users
                        SET username=%s, email=%s, display_name=%s, is_active=%s,
                            updated_at=now(){password_sql}
                        WHERE id=%s AND role='worker'
                        RETURNING *
                        """,
                        params,
                    )
                    row = cur.fetchone()
                    if not row:
                        raise ValueError("Worker account was not found.")
                    selected = self._replace_permissions(cur, user_id, page_keys)
                conn.commit()
            return _clean_user(row, selected)
        except Exception as error:
            if getattr(error, "sqlstate", "") == "23505":
                raise ValueError("That username or email is already in use.") from error
            raise

    def update_last_login(self, user_id):
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE os_users SET last_login_at=now(), updated_at=now() WHERE id=%s RETURNING *",
                    (str(user_id),),
                )
                row = cur.fetchone()
                permissions = self._permissions(cur, user_id) if row else ()
            conn.commit()
        return _clean_user(row, permissions)


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


def bootstrap_first_admin(username, password, *, display_name="Sports Cave Admin", store=None):
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
    if not user.get("is_active"):
        return None, "inactive"
    if not verify_password(password, user.get("password_hash")):
        return None, "invalid"
    return store.update_last_login(user["id"]), "ok"


def create_worker_account(
    *, username, email="", display_name, password, page_keys=(), store=None
):
    clean_username = str(username or "").strip()
    clean_name = str(display_name or "").strip()
    if not clean_username or not clean_name or not password:
        raise ValueError("Username, display name and password are required.")
    return (store or DEFAULT_STORE).create_user(
        username=clean_username,
        email=str(email or "").strip(),
        display_name=clean_name,
        password_hash=hash_password(password),
        role=ROLE_WORKER,
        page_keys=page_keys,
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
    store=None,
):
    clean_username = str(username or "").strip()
    clean_name = str(display_name or "").strip()
    if not clean_username or not clean_name:
        raise ValueError("Username and display name are required.")
    password_hash = hash_password(new_password) if new_password else ""
    return (store or DEFAULT_STORE).update_worker(
        user_id,
        username=clean_username,
        email=str(email or "").strip(),
        display_name=clean_name,
        is_active=bool(is_active),
        page_keys=page_keys,
        password_hash=password_hash,
    )


def reset_account_cache():
    global _PREPARED
    _PREPARED = False
    DEFAULT_STORE._schema_ready = False
