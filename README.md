# Sports Cave OS

Private Streamlit operations app for Sports Cave staff. Phase 3 combines the
existing Image Factory with a practical Product Command Centre and a link-based
Google Drive asset workflow.

## Active Workflows

- Dashboard priorities for product readiness, missing files, and asset review
- Product creation, filtering, editing, archiving, links, edition data, and VA notes
- Product File Hub with grouped Drive links and asset approval statuses
- Files dashboard for missing, connected, review, and approved asset packs
- Product Upload workflow board grouped by VA stage
- CSV product backup/export including file links and asset statuses
- Local limited-edition tracking and edition calculations
- Existing mockup generation, previews, prompts, and ZIP downloads

The sidebar also includes placeholders for Orders, Certificates, Marketing
Factory, and VA Training. Those systems are intentionally deferred.

## Database

Product, asset status, and limited-edition records are stored in SQLite at
`data/sports_cave_os.db`. Override this location with `SPORTS_CAVE_DB_PATH`.

Render's normal filesystem is ephemeral. Attach a Render persistent disk and
point `SPORTS_CAVE_DB_PATH` to that mounted path if records must survive a
redeploy. Database migrations only add missing tables and columns; they do not
delete existing products, edition records, or output folders.

## Local Run

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the app:

```bash
python -m streamlit run app.py
```

You can also use `start-app.bat` on Windows.

## Google Drive Link-Based Mode

Phase 3 stores Google Drive file and folder URLs on each product record. It does
not require Google OAuth, a Drive Picker, or full Drive API sync. VAs open the
connected links from Product Detail or the Files dashboard and manually save
generated ZIPs into the correct product folder.

Recommended structure:

```text
Sports Cave Products
└── [Product Name]
    ├── 01 PSD
    ├── 02 Final JPG
    ├── 03 Shopify Images WebP
    ├── 04 Mockups
    ├── 05 Lifestyle ChatGPT
    ├── 06 Prompt Pack
    ├── 07 Certificates
    └── 08 Ads Social
```

Full Drive API sync, OAuth, and a Drive Picker are intentionally deferred until
the link-based file workflow is stable.

## Mockup Workflow

1. Open `Mockups`.
2. Upload the finished artwork.
3. Confirm the product name and sport category.
4. Generate the five core Shopify images.
5. Review lightweight previews or load full resolution only when needed.
6. Download the final ZIP.
7. Save the ZIP into the correct Google Drive product folder.
8. Add the Drive folder or ZIP URL to the product File Hub.

Mockup generation continues to use local `output/runs/...` working folders and
does not call the Phase 3 asset database while images are being generated.

## Notes

- Never commit credentials to GitHub.
- `.env`, OAuth files, `output/`, and local database files are ignored by git.
- Full-resolution mockups and ZIP generation remain separate from the link-based File Hub.
