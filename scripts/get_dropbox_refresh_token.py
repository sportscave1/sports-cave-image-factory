import os
from urllib.parse import urlencode

import requests


AUTHORIZE_URL = "https://www.dropbox.com/oauth2/authorize"
TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"


def env_value(name):
    return str(os.getenv(name, "") or "").strip()


def main():
    app_key = env_value("DROPBOX_APP_KEY")
    app_secret = env_value("DROPBOX_APP_SECRET")
    redirect_uri = env_value("DROPBOX_REDIRECT_URI")
    missing = [
        name
        for name, value in (
            ("DROPBOX_APP_KEY", app_key),
            ("DROPBOX_APP_SECRET", app_secret),
            ("DROPBOX_REDIRECT_URI", redirect_uri),
        )
        if not value
    ]
    if missing:
        raise SystemExit("Missing env vars: " + ", ".join(missing))

    params = {
        "client_id": app_key,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "token_access_type": "offline",
    }
    print("Open this Dropbox authorisation URL:")
    print(f"{AUTHORIZE_URL}?{urlencode(params)}")
    code = input("Paste the returned code: ").strip()
    if not code:
        raise SystemExit("No code supplied.")

    response = requests.post(
        TOKEN_URL,
        data={
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        auth=(app_key, app_secret),
        timeout=20,
    )
    if not 200 <= response.status_code < 300:
        raise SystemExit(response.text)
    refresh_token = str(response.json().get("refresh_token") or "").strip()
    if not refresh_token:
        raise SystemExit("Dropbox did not return a refresh token.")
    print(refresh_token)


if __name__ == "__main__":
    main()
