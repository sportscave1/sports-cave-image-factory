import os
import sys
from urllib.parse import parse_qs, urlencode, urlparse

import requests


AUTHORIZE_URL = "https://www.dropbox.com/oauth2/authorize"
TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"


def env_value(name):
    return str(os.getenv(name, "") or "").strip()


def mask_token(value, *, visible=6):
    clean = str(value or "")
    if not clean:
        return ""
    if len(clean) <= visible:
        return "*" * len(clean)
    return clean[:visible] + "..." + "*" * 8


def code_from_input(value):
    clean = str(value or "").strip()
    if not clean:
        return ""
    if "://" not in clean:
        return clean
    parsed = urlparse(clean)
    query = parse_qs(parsed.query)
    code_values = query.get("code") or query.get("oauth_token")
    return str(code_values[0] if code_values else "").strip()


def sanitized_response(response):
    try:
        payload = response.json()
    except Exception:
        payload = {"raw_response": str(getattr(response, "text", "") or "").strip()}

    if not isinstance(payload, dict):
        payload = {"response": payload}

    safe = {}
    for key, value in payload.items():
        key_text = str(key)
        if key_text in {"access_token", "refresh_token", "id_token"}:
            safe[key_text] = mask_token(value)
        elif key_text in {"app_secret", "client_secret"}:
            safe[key_text] = "[hidden]"
        else:
            safe[key_text] = value
    return safe


def print_dropbox_error(response, message):
    payload = sanitized_response(response)
    print(f"ERROR: {message}", file=sys.stderr)
    print(f"HTTP status: {response.status_code}", file=sys.stderr)
    print(f"Dropbox response: {payload}", file=sys.stderr)

    joined = " ".join(str(value) for value in payload.values()).casefold()
    if "invalid_grant" in joined or "expired" in joined or "code" in joined:
        print(
            "The Dropbox code may be expired or already used. Generate a fresh code from the authorisation URL and paste it once.",
            file=sys.stderr,
        )


def validate_env(app_key, app_secret):
    missing = [
        name
        for name, value in (
            ("DROPBOX_APP_KEY", app_key),
            ("DROPBOX_APP_SECRET", app_secret),
        )
        if not value
    ]
    if missing:
        print("ERROR: Missing env vars: " + ", ".join(missing), file=sys.stderr)
        return False
    return True


def main():
    app_key = env_value("DROPBOX_APP_KEY")
    app_secret = env_value("DROPBOX_APP_SECRET")

    if not validate_env(app_key, app_secret):
        return 1

    # Omitting redirect_uri makes Dropbox display a one-time code directly on
    # its authorization page. The token exchange must omit it as well.
    params = {
        "client_id": app_key,
        "response_type": "code",
        "token_access_type": "offline",
        "force_reapprove": "true",
    }
    print("Open this Dropbox authorisation URL:", file=sys.stderr)
    print(f"{AUTHORIZE_URL}?{urlencode(params)}", file=sys.stderr)
    print(file=sys.stderr)
    print(
        "Dropbox will display a one-time authorization code after approval.",
        file=sys.stderr,
    )
    print(
        "Paste that newest code below. Codes expire quickly and can be used only once.",
        file=sys.stderr,
    )
    print("Authorization code: ", end="", file=sys.stderr, flush=True)

    code = code_from_input(input())
    if not code:
        print("ERROR: No code supplied.", file=sys.stderr)
        return 1

    try:
        response = requests.post(
            TOKEN_URL,
            data={
                "code": code,
                "grant_type": "authorization_code",
            },
            auth=(app_key, app_secret),
            timeout=20,
        )
    except requests.RequestException as exc:
        print(
            f"ERROR: Could not contact Dropbox: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1
    if not 200 <= response.status_code < 300:
        print_dropbox_error(response, "Dropbox token exchange failed.")
        return 1

    try:
        payload = response.json()
    except Exception:
        print_dropbox_error(response, "Dropbox returned a non-JSON response.")
        return 1

    refresh_token = str(payload.get("refresh_token") or "").strip()
    if not refresh_token:
        print_dropbox_error(response, "Dropbox did not return a refresh_token.")
        return 1

    print(f"DROPBOX_REFRESH_TOKEN={refresh_token}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
