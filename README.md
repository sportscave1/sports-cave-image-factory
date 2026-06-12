# Sports Cave OS

Private Streamlit operations app for Sports Cave staff. Phase 1 combines the
existing Image Factory with a lightweight product operations foundation:

- Dashboard priorities and product counts
- Product creation, editing, readiness, links, and VA notes
- Local limited-edition tracking and edition calculations
- Existing mockup generation and product upload workflows
- Placeholder areas for later Orders, Certificates, Files, and Marketing phases

## App Sections

The sidebar includes:

1. `Dashboard`
2. `Products`
3. `Mockups`
4. `Product Uploads`
5. `Limited Editions`
6. `Orders`
7. `Certificates`
8. `Files`
9. `Marketing Factory`
10. `VA Training`
11. `Settings`

Phase 1 activates Dashboard, Products, Mockups, Product Uploads, Limited
Editions, and Settings. The remaining sections are clearly marked placeholders.

## Phase 1 Database

Product and limited-edition records are stored in SQLite at
`data/sports_cave_os.db`. Override this location with `SPORTS_CAVE_DB_PATH`.

Render's normal filesystem is ephemeral. Attach a Render persistent disk and
point `SPORTS_CAVE_DB_PATH` to that mounted path if records must survive a
redeploy. The database layer is isolated in `db.py` so it can be replaced by a
hosted database in a later phase.

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
