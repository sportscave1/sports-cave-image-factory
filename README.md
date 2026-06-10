# Sports Cave Image Factory

Private Streamlit app for Sports Cave staff to:

- upload one finished artwork
- generate the base mockup assets
- download Shopify, social, prompt, and complete package ZIPs
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

This app uses a Google service account only. It does not use user OAuth.

Required environment variables:

```text
GOOGLE_DRIVE_ROOT_FOLDER_ID=your_drive_folder_id_here
GOOGLE_SERVICE_ACCOUNT_JSON_BASE64=your_base64_encoded_service_account_json_here
```

Fallback if you do not want to base64-encode the JSON:

```text
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account",...}
```

The app reads `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64` first, then falls back to `GOOGLE_SERVICE_ACCOUNT_JSON`.

### Render Deployment Steps

1. Create a Google Cloud project.
2. Enable the Google Drive API.
3. Create a service account.
4. Download the service account JSON key.
5. Base64-encode the JSON file.
6. Add `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64` to Render.
7. Add `GOOGLE_DRIVE_ROOT_FOLDER_ID` to Render.
8. Create or choose the Drive folder `Sports Cave Image Factory`.
9. Share that Drive folder with the service account email as `Editor`.
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
6. Download any of the ZIP outputs directly from the app.
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
- ZIP packages
- `manifest.json`

If Google Drive is configured, the full run folder is uploaded automatically after generation. If Drive is not configured, the app still works locally and shows that files were saved locally only.

## Notes

- Never commit credentials to GitHub.
- `.env`, `output/`, `credentials.json`, and `service-account.json` are ignored by git.
- If Google Drive upload fails, local generation and ZIP downloads still succeed.
