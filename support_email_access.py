"""Current account authorization for private Email utility transports."""


def current_email_claims(request):
    import os_accounts
    from top_bar_api import _claims
    claims = _claims(request)
    if not claims or 'Email' not in claims.get('allowed_routes', ()):
        return {}
    try:
        user = os_accounts.DEFAULT_STORE.get_user(claims['sub'])
        if (not os_accounts.can_access_page(user, 'Email')
                or int(claims.get('sv', 0)) != int(user.get('session_version', 1))):
            return {}
    except Exception:
        # A failed account lookup cannot extend a revoked permission snapshot.
        return {}
    return claims
