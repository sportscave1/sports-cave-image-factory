import os
import time
from dataclasses import dataclass


MASKED_PASSWORD = "••••••••••••"
REVEAL_SECONDS = 20
REVEAL_STATE_KEY = "sports_cave_revealed_credentials"
FIELD_USERNAME = "username"
FIELD_PASSWORD = "password"

ACTION_PERMISSION_GRANTED = "credential_permission_granted"
ACTION_PERMISSION_REVOKED = "credential_permission_revoked"
ACTION_USERNAME_COPIED = "credential_username_copied"
ACTION_PASSWORD_REVEALED = "credential_password_revealed"
ACTION_PASSWORD_COPIED = "credential_password_copied"
ACTION_ACCESS_DENIED = "credential_access_denied"


@dataclass(frozen=True)
class CredentialSpec:
    key: str
    display_name: str
    username_env: str
    password_env: str
    permission_key: str


CREDENTIAL_REGISTRY = (
    CredentialSpec(
        key="prodigi",
        display_name="Prodigi",
        username_env="PRODIGI_USERNAME",
        password_env="PRODIGI_PASSWORD",
        permission_key="credential_prodigi",
    ),
    CredentialSpec(
        key="adobe",
        display_name="Adobe",
        username_env="ADOBE_USERNAME",
        password_env="ADOBE_PASSWORD",
        permission_key="credential_adobe",
    ),
    CredentialSpec(
        key="chatgpt",
        display_name="ChatGPT",
        username_env="CHATGPT_USERNAME",
        password_env="CHATGPT_PASSWORD",
        permission_key="credential_chatgpt",
    ),
)
CREDENTIAL_PERMISSION_KEYS = tuple(spec.permission_key for spec in CREDENTIAL_REGISTRY)
_CREDENTIAL_BY_KEY = {spec.key: spec for spec in CREDENTIAL_REGISTRY}
_CREDENTIAL_BY_PERMISSION = {spec.permission_key: spec for spec in CREDENTIAL_REGISTRY}
_VALID_FIELDS = {FIELD_USERNAME, FIELD_PASSWORD}


class CredentialAccessError(RuntimeError):
    pass


class CredentialAccessDenied(PermissionError):
    pass


class CredentialAccessUnavailable(CredentialAccessError):
    pass


def credential_specs():
    return CREDENTIAL_REGISTRY


def credential_spec(service_key):
    clean_key = str(service_key or "").strip().casefold()
    spec = _CREDENTIAL_BY_KEY.get(clean_key)
    if not spec:
        raise ValueError("Unknown shared credential.")
    return spec


def credential_spec_for_permission(permission_key):
    return _CREDENTIAL_BY_PERMISSION.get(str(permission_key or "").strip().casefold())


def credential_permission_keys(values):
    selected = {str(value or "").strip().casefold() for value in values or ()}
    return tuple(spec.permission_key for spec in CREDENTIAL_REGISTRY if spec.permission_key in selected)


def _field_env_name(spec, field):
    clean_field = str(field or "").strip().casefold()
    if clean_field == FIELD_USERNAME:
        return spec.username_env
    if clean_field == FIELD_PASSWORD:
        return spec.password_env
    raise ValueError("Unknown shared credential field.")


def _stable_user_id(user):
    user = user or {}
    return str(
        user.get("id")
        or user.get("email")
        or user.get("username")
        or ""
    ).strip()


def _active_user(user):
    user = user or {}
    account_status = str(user.get("account_status") or "active").strip().casefold()
    return bool(
        user
        and bool(user.get("is_active", True))
        and account_status != "removed"
        and not user.get("removed_at")
    )


def resolve_user_for_permission_check(user, *, store=None):
    user = dict(user or {})
    if not user:
        return {}
    if user.get("legacy"):
        return user
    user_id = str(user.get("id") or "").strip()
    if not user_id:
        return {}
    try:
        import os_accounts

        fresh = (store or os_accounts.DEFAULT_STORE).get_user(user_id)
    except Exception as error:
        raise CredentialAccessUnavailable(
            "Credential access could not be verified right now."
        ) from error
    return dict(fresh or {})


def _can_access_checked_user(user, spec):
    if not _active_user(user):
        return False
    import os_accounts

    if os_accounts.is_admin(user):
        return True
    return spec.permission_key in os_accounts.permission_keys(user)


def can_access_credential(user, service_key, *, fresh=False, store=None):
    spec = credential_spec(service_key)
    checked_user = resolve_user_for_permission_check(user, store=store) if fresh else dict(user or {})
    return _can_access_checked_user(checked_user, spec)


def accessible_credential_specs(user, *, fresh=False, store=None):
    checked_user = resolve_user_for_permission_check(user, store=store) if fresh else dict(user or {})
    if not _active_user(checked_user):
        return ()
    import os_accounts

    if os_accounts.is_admin(checked_user):
        return CREDENTIAL_REGISTRY
    selected = os_accounts.permission_keys(checked_user)
    return tuple(spec for spec in CREDENTIAL_REGISTRY if spec.permission_key in selected)


def can_manage_credential_permissions(actor):
    if not _active_user(actor):
        return False
    import os_accounts

    return os_accounts.is_admin(actor)


def credential_field_is_configured(user, service_key, field, *, environ=None, fresh=True, store=None):
    spec = credential_spec(service_key)
    checked_user = resolve_user_for_permission_check(user, store=store) if fresh else dict(user or {})
    if not _can_access_checked_user(checked_user, spec):
        record_credential_audit(
            ACTION_ACCESS_DENIED,
            user,
            spec.key,
            allowed=False,
            field=field,
            requested_action="configuration_check",
        )
        raise CredentialAccessDenied("Credential access is not approved for this account.")
    env = os.environ if environ is None else environ
    return bool(str(env.get(_field_env_name(spec, field), "") or ""))


def read_credential_value(user, service_key, field, *, environ=None, fresh=True, store=None, requested_action=""):
    spec = credential_spec(service_key)
    try:
        checked_user = resolve_user_for_permission_check(user, store=store) if fresh else dict(user or {})
    except CredentialAccessUnavailable:
        record_credential_audit(
            ACTION_ACCESS_DENIED,
            user,
            spec.key,
            allowed=False,
            field=field,
            result="permission_check_unavailable",
            requested_action=requested_action or "credential_read",
        )
        raise
    if not _can_access_checked_user(checked_user, spec):
        record_credential_audit(
            ACTION_ACCESS_DENIED,
            checked_user or user,
            spec.key,
            allowed=False,
            field=field,
            requested_action=requested_action or "credential_read",
        )
        raise CredentialAccessDenied("Credential access is not approved for this account.")
    env = os.environ if environ is None else environ
    return str(env.get(_field_env_name(spec, field), "") or "")


def read_credential_for_action(
    user,
    service_key,
    field,
    action_type,
    *,
    environ=None,
    store=None,
):
    value = read_credential_value(
        user,
        service_key,
        field,
        environ=environ,
        fresh=True,
        store=store,
        requested_action=action_type,
    )
    if value:
        record_credential_audit(
            action_type,
            user,
            service_key,
            allowed=True,
            field=field,
        )
    return value


def _actor_label(user):
    user = user or {}
    return (
        str(user.get("display_name") or "").strip()
        or str(user.get("email") or "").strip()
        or str(user.get("username") or "").strip()
        or "sports_cave_os"
    )


def _audit_message(action_type, service_name):
    label = {
        ACTION_PERMISSION_GRANTED: "Permission granted",
        ACTION_PERMISSION_REVOKED: "Permission revoked",
        ACTION_USERNAME_COPIED: "Username copied",
        ACTION_PASSWORD_REVEALED: "Password revealed",
        ACTION_PASSWORD_COPIED: "Password copied",
        ACTION_ACCESS_DENIED: "Denied credential-access attempt",
    }.get(str(action_type or "").strip(), "Credential access")
    return f"{label}: {service_name}"


def record_credential_audit(
    action_type,
    actor,
    service_key,
    *,
    allowed,
    target_user=None,
    field="",
    result="",
    requested_action="",
):
    spec = credential_spec(service_key)
    actor = dict(actor or {})
    target_user = dict(target_user or {})
    metadata = {
        "actor_id": actor.get("id") or "",
        "actor_email": actor.get("email") or "",
        "actor_role": actor.get("role") or "",
        "service_key": spec.key,
        "service_name": spec.display_name,
        "permission_key": spec.permission_key,
        "credential_action": str(action_type or "").strip(),
        "requested_action": str(requested_action or "").strip(),
        "field": str(field or "").strip() if str(field or "").strip() in _VALID_FIELDS else "",
        "allowed": bool(allowed),
        "result": str(result or ("allowed" if allowed else "denied")),
        "status": "success" if allowed else "denied",
    }
    if target_user:
        metadata.update(
            {
                "target_account_id": target_user.get("id") or "",
                "target_account_display": target_user.get("display_name") or "",
                "target_account_role": target_user.get("role") or "",
            }
        )
    metadata = {key: value for key, value in metadata.items() if value not in ("", None)}
    try:
        from activity_log import record_activity_log

        record_activity_log(
            str(action_type or "").strip() or ACTION_ACCESS_DENIED,
            "Accounts & Access",
            _audit_message(action_type, spec.display_name),
            entity_type="os_user" if target_user else "shared_credential",
            entity_id=target_user.get("id") or spec.key,
            metadata=metadata,
            actor=_actor_label(actor),
        )
    except Exception:
        pass


def mark_credential_revealed(state, user, service_key, *, now=None):
    spec = credential_spec(service_key)
    now = time.monotonic() if now is None else float(now)
    reveals = dict(state.get(REVEAL_STATE_KEY) or {})
    reveals[spec.key] = {
        "user_id": _stable_user_id(user),
        "expires_at": now + REVEAL_SECONDS,
    }
    state[REVEAL_STATE_KEY] = reveals


def clear_revealed_credential(state, service_key=None):
    if service_key is None:
        state.pop(REVEAL_STATE_KEY, None)
        return
    clean_key = str(service_key or "").strip().casefold()
    reveals = dict(state.get(REVEAL_STATE_KEY) or {})
    reveals.pop(clean_key, None)
    if reveals:
        state[REVEAL_STATE_KEY] = reveals
    else:
        state.pop(REVEAL_STATE_KEY, None)


def expire_revealed_credentials(state, user=None, *, now=None):
    now = time.monotonic() if now is None else float(now)
    expected_user_id = _stable_user_id(user) if user is not None else ""
    changed = False
    active = {}
    for service_key, reveal in dict(state.get(REVEAL_STATE_KEY) or {}).items():
        spec = _CREDENTIAL_BY_KEY.get(str(service_key or "").strip().casefold())
        expires_at = float((reveal or {}).get("expires_at") or 0)
        reveal_user_id = str((reveal or {}).get("user_id") or "")
        if not spec or expires_at <= now or (expected_user_id and reveal_user_id != expected_user_id):
            changed = True
            continue
        active[spec.key] = {"user_id": reveal_user_id, "expires_at": expires_at}
    if active:
        state[REVEAL_STATE_KEY] = active
    elif state.get(REVEAL_STATE_KEY):
        state.pop(REVEAL_STATE_KEY, None)
        changed = True
    return changed


def credential_is_revealed(state, user, service_key, *, now=None):
    spec = credential_spec(service_key)
    now = time.monotonic() if now is None else float(now)
    expire_revealed_credentials(state, user, now=now)
    reveal = dict((state.get(REVEAL_STATE_KEY) or {}).get(spec.key) or {})
    return bool(
        reveal
        and str(reveal.get("user_id") or "") == _stable_user_id(user)
        and float(reveal.get("expires_at") or 0) > now
    )


def reveal_remaining_seconds(state, user, service_key, *, now=None):
    spec = credential_spec(service_key)
    now = time.monotonic() if now is None else float(now)
    if not credential_is_revealed(state, user, spec.key, now=now):
        return 0
    reveal = dict((state.get(REVEAL_STATE_KEY) or {}).get(spec.key) or {})
    return max(0, int(float(reveal.get("expires_at") or 0) - now))
