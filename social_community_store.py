"""Small server-only collaboration ledger. Inbox content stays at Meta."""
from meta_social import require_access, username

STATES = ("discovered", "shortlisted", "sending", "sent", "unknown", "agreed", "declined")


def _backend():
    import supabase_backend
    return supabase_backend


def _query(user, sql, args=(), *, write=False):
    require_access(user)
    with _backend().connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='4000ms'")
            cur.execute(sql, args)
            rows = [dict(row) for row in cur.fetchall()] if cur.description else []
        if write:
            conn.commit()
        return rows


def list_creators(user):
    return _query(user, "SELECT * FROM public.social_collaborators ORDER BY score DESC, username LIMIT 200")


def save_creator(user, profile):
    return _query(user, """INSERT INTO public.social_collaborators
        (username,followers,engagement,fit,score,reason,draft)
        VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (username) DO UPDATE SET
        followers=EXCLUDED.followers,engagement=EXCLUDED.engagement,fit=EXCLUDED.fit,
        score=EXCLUDED.score,reason=EXCLUDED.reason,updated_at=now() RETURNING *""",
        (username(profile['username']), profile['followers'], profile['engagement'],
         profile['fit'], profile['score'], profile['reason'], profile['draft']), write=True)


def update_creator(user, handle, state, draft):
    if state not in STATES or state in ("sending", "sent", "unknown"):
        raise ValueError("Choose a collaboration pipeline status.")
    if not str(draft).strip() or len(draft) > 1000:
        raise ValueError("Write an invitation between 1 and 1,000 characters.")
    return _query(user, """UPDATE public.social_collaborators SET state=%s,draft=%s,updated_at=now()
        WHERE username=%s AND state NOT IN ('sending','unknown') RETURNING *""",
        (state, draft, username(handle)), write=True)


def claim_invitation(user, handle):
    # Atomic durable claim before the external send. Ambiguous results are never
    # retried automatically, even if a process stops between send and completion.
    rows = _query(user, """UPDATE public.social_collaborators SET state='sending',updated_at=now()
        WHERE username=%s AND state IN ('discovered','shortlisted') AND fit=TRUE
        AND sent_at IS NULL RETURNING *""", (username(handle),), write=True)
    return rows[0] if rows else None


def finish_invitation(user, handle, *, state, message_id=""):
    if state not in ("sent", "unknown"):
        raise ValueError("Invalid delivery result.")
    _query(user, """UPDATE public.social_collaborators SET state=%s,message_id=%s,
        sent_at=CASE WHEN %s='sent' THEN now() ELSE sent_at END,updated_at=now()
        WHERE username=%s AND state='sending' RETURNING username""",
        (state, str(message_id)[:200], state, username(handle)), write=True)


def automation(user, enabled=None):
    if enabled is not None:
        import os_accounts
        if not os_accounts.is_admin(user):
            raise PermissionError("Only an administrator can change automatic invitations.")
        return _query(user, """INSERT INTO public.social_community_settings(id,automation_enabled) VALUES (1,%s)
            ON CONFLICT(id) DO UPDATE SET automation_enabled=EXCLUDED.automation_enabled RETURNING *""",
            (bool(enabled),), write=True)[0]
    rows = _query(user, "SELECT * FROM public.social_community_settings WHERE id=1")
    return rows[0] if rows else {"automation_enabled": False}
