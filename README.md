# Sports Cave Image Factory

Private Streamlit app for Sports Cave staff to:

- upload one finished artwork
- generate the base mockup assets
- download one final ZIP with the selected WEBP and JPG assets
- upload finished ChatGPT lifestyle mockups back into the same run
- automatically sync each finished run to Google Drive

## App Sections

The sidebar now includes:

1. `Mockups`
2. `Google Drive`
3. `Limited Editions`
4. `Product Uploads`
5. `Settings`

Only `Mockups` and `Google Drive` are active right now. The other sections are placeholders for the wider Sports Cave backend.

## Local Run

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Add a local `.env` file with your Google Drive settings if you want Drive sync while developing.
4. Start the app:

```bash
python -m streamlit run app.py
```

You can also use `start-app.bat` on Windows.

## Google Drive Setup

This app now uses OAuth credentials from environment variables on Render.

Your Drive root folder is:

`https://drive.google.com/drive/folders/13g4jx3R0JuBZRggf9pI_mVh43s4oStoU`

The folder ID is:

`13g4jx3R0JuBZRggf9pI_mVh43s4oStoU`

### Local Helper Script

1. Copy your downloaded Desktop OAuth client JSON into the repo root.
2. Rename it to `client_secret.json`.
3. Run:

```bash
python get_google_drive_refresh_token.py
```

4. Sign in with the Vernaclean Google account in the browser window that opens.
5. Copy the printed value:

```text
GOOGLE_OAUTH_REFRESH_TOKEN=...
```

The helper script also writes a local `token.json` cache file. Both `client_secret.json` and `token.json` are gitignored.

### Render Environment Variables

Set these on Render:

```text
GOOGLE_DRIVE_ROOT_FOLDER_ID=13g4jx3R0JuBZRggf9pI_mVh43s4oStoU
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...
GOOGLE_OAUTH_REFRESH_TOKEN=...
```

### Render Deployment Steps

1. Create a Google Cloud project.
2. Enable the Google Drive API.
3. Create a Desktop OAuth client in Google Cloud.
4. Download the client JSON.
5. Use `client_secret.json` locally with `get_google_drive_refresh_token.py`.
6. Sign in with the Vernaclean Google account.
7. Copy the refresh token into Render as `GOOGLE_OAUTH_REFRESH_TOKEN`.
8. Copy the client ID and client secret into Render as `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET`.
9. Set `GOOGLE_DRIVE_ROOT_FOLDER_ID=13g4jx3R0JuBZRggf9pI_mVh43s4oStoU`.
10. Redeploy the app.

### Recommended Drive Structure

```text
Sports Cave Image Factory
├── Mockups
├── Limited Editions
├── Product Uploads
└── System Logs
```

Each generated run is uploaded under `Mockups`.

## Mockup Workflow

1. Open the `Mockups` page.
2. Upload the finished artwork file.
3. Confirm or edit the product name.
4. Choose the sport category.
5. Click `Generate Images`.
6. Download the final ZIP directly from the app.
7. Use the prompt pack for ChatGPT lifestyle generations if needed.
8. Upload finished ChatGPT lifestyle images back into the matching prompt cards.
9. Tick only the images you want included in the ZIP packages.

The app keeps using local `output/runs/...` folders as working storage, then syncs the full run to Google Drive after a successful generation.

## Output Behavior

Each run keeps:

- generated review previews
- Shopify-ready WebP assets
- social JPG assets
- ChatGPT prompt files
- one final ZIP package
- `manifest.json`

If Google Drive is configured, the full run folder is uploaded automatically after generation. If Drive is not configured, the app still works locally and shows that files were saved locally only.

## Notes

- Never commit credentials to GitHub.
- `.env`, `client_secret.json`, `token.json`, `output/`, `credentials.json`, and `service-account.json` are ignored by git.
- If Google Drive upload fails, local generation and ZIP downloads still succeed.
