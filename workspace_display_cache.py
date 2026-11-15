"""Session-local, bounded display snapshots. Never use for authorising a mutation.

Reuses the email display cache's TTL, copy isolation and memory bounds. Ownership
includes the account revision and permissions, not just the user's name.
"""
from crm_cache import DisplayCache


def user_scope(user):
    user = user or {}
    return (str(user.get("id") or ""), user.get("session_version"), user.get("role"),
            user.get("is_active"), user.get("account_status"), user.get("timezone"),
            tuple(sorted(str(p) for p in user.get("page_permissions") or ())))


def session_cache(state, name, user):
    scope = user_scope(user)
    saved = state.get(name)
    if not saved or saved[0] != scope:
        saved = (scope, DisplayCache(limit=32, byte_limit=4 * 1024 * 1024))
        state[name] = saved
    return saved[1]


def read_display(cache, key, loader, *, ttl=30):
    value = cache.get(key)
    if value is not None:
        return value
    # Exceptions are deliberately not cached. An unavailable service is retryable.
    value = loader()
    cache.put(key, value, ttl=ttl if value else min(ttl, 3))
    return value


def home_weekly_snapshot(state, user, local_now, loader):
    cache = session_cache(state, "home-weekly-display-cache", user)
    return read_display(cache, (local_now.date().isoformat(),), lambda: loader(user, local_now))


def invalidate_home(state):
    state.pop("home-weekly-display-cache", None)
