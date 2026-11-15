import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow


CLIENT_SECRET_PATH = Path("client_secret.json")
TOKEN_PATH = Path("token.json")
SCOPES = ["https://www.googleapis.com/auth/drive"]


def main():
    if not CLIENT_SECRET_PATH.exists():
        raise SystemExit(
            "client_secret.json was not found in the current folder. "
            "Copy your downloaded Desktop OAuth client JSON here and rename it to client_secret.json."
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CLIENT_SECRET_PATH),
        SCOPES,
    )
    credentials = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
        authorization_prompt_message=(
            "Sign in with your Vernaclean Google account in the browser window that opens."
        ),
        success_message=(
            "Google Drive authentication is complete. You can close this tab and return to the terminal."
        ),
    )

    if not credentials.refresh_token:
        raise SystemExit(
            "No refresh token was returned. Re-run the script, approve with the Vernaclean account, "
            "and make sure consent is granted."
        )

    token_payload = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
    }
    TOKEN_PATH.write_text(json.dumps(token_payload, indent=2), encoding="utf-8")

    print(f"GOOGLE_OAUTH_REFRESH_TOKEN={credentials.refresh_token}")


if __name__ == "__main__":
    main()
