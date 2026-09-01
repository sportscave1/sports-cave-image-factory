"""Persistent, permission-scoped repair and improvement requests."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import uuid

import os_accounts


TABLE_NAME = "os_repair_requests"
MIGRATION_NAME = "20260901_os_repair_requests.sql"
PROMPT_VERSION = "2"
RECENT_LIMIT = 5
DISPLAY_TIMEZONE = ZoneInfo("Australia/Sydney")

STATUS_SUBMITTED = "submitted"
STATUS_COMPLETE = "complete"
SCOPE_SECTION_ONLY = "section_only"
SCOPE_RELATED_SECTIONS = "related_sections"
SCOPE_NOT_SURE = "not_sure"
SCOPE_LABELS = {
    SCOPE_SECTION_ONLY: "Yes — this section only",
    SCOPE_RELATED_SECTIONS: "No — related sections also need changes",
    SCOPE_NOT_SURE: "Not sure",
}


CHATGPT_CODEX_HANDOFF_PREFIX = """==================================================
CHATGPT — CREATE THE FINAL CODEX PROMPT
==================================================

This is a Sports Cave OS repair / improvement handoff.

Read the entire request below before responding.

Your job is NOT to implement the code change yourself.

Create one complete, production-quality prompt for Codex to carry out the requested repair or improvement in the Sports Cave OS repository. Use the submitted request as the source of truth.

The Codex prompt you create must:

- preserve the exact reported problem and expected result
- preserve the stated scope / isolation boundary
- tell Codex to inspect the current repository implementation before editing
- tell Codex to identify and explain the root cause
- tell Codex to fix the underlying issue rather than only the visible symptom
- tell Codex to reuse existing Sports Cave OS architecture, helpers and UI patterns
- protect all currently working unrelated behaviour
- include likely files or code paths only when supported by the supplied request or context
- require focused regression tests where appropriate
- require syntax/compile checks and relevant tests for every changed file
- prohibit destructive production actions
- prohibit exposing secrets
- prohibit pushing or deploying unless the request explicitly authorises it
- require Codex to stop after local implementation and report the result

Improve and expand the implementation instructions where necessary so Codex receives an unambiguous engineering task, but DO NOT change the user's intended behaviour or broaden the requested scope.

If screenshots, files, error messages or additional context are supplied with this request, incorporate them into the Codex prompt where relevant.

Return ONLY the final Codex prompt, ready for Nathan to copy directly into Codex.

Do not give Nathan an explanation before or after it.

==================================================
ORIGINAL SPORTS CAVE OS REPAIR REQUEST
==================================================""".strip()


class RepairRequestError(RuntimeError):
    """Base error for this lightweight workflow."""


class RepairRequestValidationError(RepairRequestError):
    """The submitted form payload is invalid."""


class RepairRequestStorageUnavailable(RepairRequestError):
    """Durable repair-request storage cannot currently serve the request."""


class RepairRequestStorageMissing(RepairRequestStorageUnavailable):
    """The additive repair-request table or one of its required columns is missing."""


class RepairRequestStorageTemporary(RepairRequestStorageUnavailable):
    """The database is configured but temporarily unavailable."""


def _single_line(value, *, limit):
    return " ".join(str(value or "").split()).strip()[:limit]


def _multiline(value, *, limit):
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()[:limit]


def _identity_id(identity):
    return _single_line((identity or {}).get("sub") or (identity or {}).get("id"), limit=160)


def _identity_name(identity):
    return _single_line(
        (identity or {}).get("display_name") or (identity or {}).get("username"),
        limit=160,
    )


def _identity_role(identity):
    return _single_line((identity or {}).get("role"), limit=40).casefold()


def normalise_submission(payload):
    payload = dict(payload or {})
    section = _single_line(payload.get("section"), limit=160)
    problem = _multiline(payload.get("problem_description"), limit=6000)
    desired = _multiline(payload.get("desired_result"), limit=6000)
    scope_choice = _single_line(payload.get("scope_choice"), limit=60).casefold()
    scope_notes = _multiline(payload.get("scope_notes"), limit=4000)
    if not section:
        raise RepairRequestValidationError("Choose the affected Sports Cave OS section.")
    if not problem:
        raise RepairRequestValidationError("Describe what is happening.")
    if not desired:
        raise RepairRequestValidationError("Describe what should happen instead.")
    if scope_choice not in SCOPE_LABELS:
        raise RepairRequestValidationError("Choose a scope / isolation answer.")
    return {
        "section": section,
        "request_type": "repair_improvement",
        "problem_description": problem,
        "desired_result": desired,
        "scope_choice": scope_choice,
        "scope_notes": scope_notes,
    }


def _as_datetime(value):
    if isinstance(value, datetime):
        result = value
    else:
        clean = str(value or "").strip()
        if not clean:
            return None
        try:
            result = datetime.fromisoformat(clean.replace("Z", "+00:00"))
        except ValueError:
            return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result


def format_sydney_date(value):
    parsed = _as_datetime(value)
    return parsed.astimezone(DISPLAY_TIMEZONE).strftime("%d/%m/%Y") if parsed else ""


def summarise_request(request, *, limit=120):
    text = _single_line(
        (request or {}).get("problem_description")
        or (request or {}).get("desired_result"),
        limit=2000,
    )
    if len(text) <= limit:
        return text
    shortened = text[: max(limit - 1, 1)].rsplit(" ", 1)[0].strip()
    return f"{shortened or text[: max(limit - 1, 1)].strip()}…"


def build_repair_prompt(request):
    request = dict(request or {})
    section = _single_line(request.get("section"), limit=160)
    problem = _multiline(request.get("problem_description"), limit=6000)
    desired = _multiline(request.get("desired_result"), limit=6000)
    scope = SCOPE_LABELS.get(
        _single_line(request.get("scope_choice"), limit=60).casefold(),
        _single_line(request.get("scope_choice"), limit=160) or "Not sure",
    )
    scope_notes = _multiline(request.get("scope_notes"), limit=4000) or "None provided."
    submitted_date = format_sydney_date(request.get("created_at")) or "Not recorded"
    return f"""{CHATGPT_CODEX_HANDOFF_PREFIX}

==================================================
SPORTS CAVE OS — REPAIR / IMPROVEMENT REQUEST
==================================================

Work from the repository root.

Inspect the current implementation before editing anything.

SECTION:
{section}

SUBMITTED:
{submitted_date} (Australia/Sydney)

REPORTED PROBLEM / IMPROVEMENT:
{problem}

REQUIRED RESULT:
{desired}

SCOPE / ISOLATION:
{scope}

SCOPE NOTES:
{scope_notes}

IMPORTANT BOUNDARY:

Preserve all currently working behaviour outside the requested scope.

Investigate the root cause before changing code. Do not patch only the visible symptom if the underlying issue is elsewhere.

Reuse existing Sports Cave OS architecture, helpers and UI patterns rather than creating duplicate systems.

Do not alter unrelated workflows. Do not expose secrets. Do not perform destructive production actions.

Do not push or deploy until explicitly requested.

REQUIRED PROCESS:

1. Inspect the current implementation and identify the exact code path responsible.
2. Explain the root cause before or while implementing the repair or improvement.
3. Implement the smallest reliable change that achieves the required result.
4. Preserve all unrelated behaviour.
5. Add or update focused regression tests where appropriate.
6. Run syntax/compile checks and relevant tests for every changed file.
7. Stop after local implementation and report; do not perform production actions.

DEFINITION OF DONE:

The requested behaviour works exactly as described.

CURRENT / REPORTED:
{problem}

EXPECTED:
{desired}

SCOPE:
{scope}

SCOPE NOTES:
{scope_notes}

FINAL RESPONSE:

Report:

1. Root cause.
2. Files changed.
3. Exact repair or improvement made.
4. Confirmation unrelated functionality was preserved.
5. Tests and checks run, with results.
6. Whether it is safe for Nathan to test locally.

DO NOT PUSH.
DO NOT DEPLOY.
STOP AFTER LOCAL IMPLEMENTATION AND REPORT.
""".strip()


def _base_mirror(request):
    request = dict(request or {})
    return {
        "id": str(request.get("id") or ""),
        "section": _single_line(request.get("section"), limit=160),
        "summary": summarise_request(request),
        "status": (
            STATUS_COMPLETE
            if str(request.get("status") or "").casefold() == STATUS_COMPLETE
            else STATUS_SUBMITTED
        ),
        "submitted_date": format_sydney_date(request.get("created_at")),
        "completed_date": format_sydney_date(request.get("completed_at")),
    }


def request_mirror_for_user(request, identity):
    """Return only fields the authenticated role is permitted to receive."""

    mirror = _base_mirror(request)
    if not os_accounts.is_admin(identity):
        return mirror
    request = dict(request or {})
    mirror.update(
        {
            "problem_description": _multiline(request.get("problem_description"), limit=6000),
            "desired_result": _multiline(request.get("desired_result"), limit=6000),
            "scope_choice": _single_line(request.get("scope_choice"), limit=60),
            "scope_label": SCOPE_LABELS.get(
                _single_line(request.get("scope_choice"), limit=60).casefold(),
                "Not sure",
            ),
            "scope_notes": _multiline(request.get("scope_notes"), limit=4000),
            "submitted_by_name": _single_line(request.get("submitted_by_name"), limit=160),
            "submitted_by_role": _single_line(request.get("submitted_by_role"), limit=40),
            "admin_notes": _multiline(request.get("admin_notes"), limit=4000),
            "repair_prompt": build_repair_prompt(request),
            "generated_prompt_version": _single_line(
                request.get("generated_prompt_version") or PROMPT_VERSION,
                limit=20,
            ),
        }
    )
    return mirror


def repair_prompt_for_user(request, identity):
    if not os_accounts.is_admin(identity):
        raise PermissionError("Only an administrator can receive a repair prompt.")
    return build_repair_prompt(request)


class PostgresRepairRequestStore:
    """Small durable repository that uses the application's configured Postgres."""

    _SELECT_FIELDS = """
        id, section, request_type, problem_description, desired_result,
        scope_choice, scope_notes, submitted_by, submitted_by_name,
        submitted_by_role, status, created_at, completed_at, completed_by,
        completed_by_name, admin_notes, generated_prompt_version
    """

    @staticmethod
    def _backend():
        import supabase_backend

        if not supabase_backend.is_configured():
            raise RepairRequestStorageTemporary(
                "Repair request storage is not configured."
            )
        return supabase_backend

    @staticmethod
    def _storage_error(error):
        if isinstance(error, RepairRequestStorageUnavailable):
            return error
        sqlstate = str(
            getattr(error, "sqlstate", "")
            or getattr(error, "pgcode", "")
            or ""
        ).upper()
        if sqlstate in {"42P01", "42703"}:
            return RepairRequestStorageMissing(
                "Repair request storage is not ready. Apply migration "
                f"{MIGRATION_NAME}, then retry."
            )
        return RepairRequestStorageTemporary(
            "Repair requests are temporarily unavailable. Please retry."
        )

    def create(self, values):
        request_id = str(uuid.uuid4())
        try:
            backend = self._backend()
            with backend.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        INSERT INTO {TABLE_NAME} (
                            id, section, request_type, problem_description,
                            desired_result, scope_choice, scope_notes,
                            submitted_by, submitted_by_name, submitted_by_role,
                            status, generated_prompt_version
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s
                        )
                        RETURNING {self._SELECT_FIELDS}
                        """,
                        (
                            request_id,
                            values["section"],
                            values["request_type"],
                            values["problem_description"],
                            values["desired_result"],
                            values["scope_choice"],
                            values["scope_notes"],
                            values["submitted_by"],
                            values["submitted_by_name"],
                            values["submitted_by_role"],
                            STATUS_SUBMITTED,
                            PROMPT_VERSION,
                        ),
                    )
                    row = dict(cur.fetchone() or {})
                conn.commit()
            if not row:
                raise RepairRequestStorageTemporary(
                    "Repair request storage did not return the stored request."
                )
            return row
        except Exception as error:
            raise self._storage_error(error) from error

    def recent(self, *, submitted_by=None, limit=RECENT_LIMIT):
        safe_limit = max(1, min(int(limit or RECENT_LIMIT), RECENT_LIMIT))
        try:
            backend = self._backend()
            with backend.connect() as conn:
                with conn.cursor() as cur:
                    if submitted_by:
                        cur.execute(
                            f"""
                            SELECT {self._SELECT_FIELDS}
                            FROM {TABLE_NAME}
                            WHERE submitted_by = %s
                            ORDER BY created_at DESC
                            LIMIT %s
                            """,
                            (str(submitted_by), safe_limit),
                        )
                    else:
                        cur.execute(
                            f"""
                            SELECT {self._SELECT_FIELDS}
                            FROM {TABLE_NAME}
                            ORDER BY created_at DESC
                            LIMIT %s
                            """,
                            (safe_limit,),
                        )
                    return [dict(row or {}) for row in cur.fetchall()]
        except Exception as error:
            raise self._storage_error(error) from error

    def complete(self, request_id, *, completed_by, completed_by_name, admin_notes=""):
        try:
            backend = self._backend()
            with backend.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        UPDATE {TABLE_NAME}
                        SET status = %s,
                            completed_at = now(),
                            completed_by = %s,
                            completed_by_name = %s,
                            admin_notes = %s
                        WHERE id = %s AND status = %s
                        RETURNING {self._SELECT_FIELDS}
                        """,
                        (
                            STATUS_COMPLETE,
                            completed_by,
                            completed_by_name,
                            _multiline(admin_notes, limit=4000),
                            str(request_id),
                            STATUS_SUBMITTED,
                        ),
                    )
                    row = dict(cur.fetchone() or {})
                    if not row:
                        cur.execute(
                            f"""
                            SELECT {self._SELECT_FIELDS}
                            FROM {TABLE_NAME}
                            WHERE id = %s
                            """,
                            (str(request_id),),
                        )
                        row = dict(cur.fetchone() or {})
                conn.commit()
            return row
        except Exception as error:
            raise self._storage_error(error) from error


def submit_request(payload, identity, *, store=None):
    user_id = _identity_id(identity)
    if not user_id:
        raise PermissionError("A signed-in Sports Cave OS account is required.")
    values = normalise_submission(payload)
    values.update(
        {
            "submitted_by": user_id,
            "submitted_by_name": _identity_name(identity),
            "submitted_by_role": _identity_role(identity),
        }
    )
    row = (store or PostgresRepairRequestStore()).create(values)
    return request_mirror_for_user(row, identity)


def recent_requests(identity, *, store=None, limit=RECENT_LIMIT):
    user_id = _identity_id(identity)
    if not user_id:
        raise PermissionError("A signed-in Sports Cave OS account is required.")
    admin = os_accounts.is_admin(identity)
    rows = (store or PostgresRepairRequestStore()).recent(
        submitted_by=None if admin else user_id,
        limit=min(max(int(limit or RECENT_LIMIT), 1), RECENT_LIMIT),
    )
    rows = sorted(
        (dict(row or {}) for row in rows),
        key=lambda row: _as_datetime(row.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )[:RECENT_LIMIT]
    return [request_mirror_for_user(row, identity) for row in rows]


def mark_request_complete(request_id, identity, *, admin_notes="", store=None):
    if not os_accounts.is_admin(identity):
        raise PermissionError("Only an administrator can complete a repair request.")
    clean_id = _single_line(request_id, limit=160)
    if not clean_id:
        raise RepairRequestValidationError("Choose a repair request to complete.")
    row = (store or PostgresRepairRequestStore()).complete(
        clean_id,
        completed_by=_identity_id(identity),
        completed_by_name=_identity_name(identity),
        admin_notes=_multiline(admin_notes, limit=4000),
    )
    if not row:
        raise RepairRequestValidationError("Repair request not found.")
    return request_mirror_for_user(row, identity)
