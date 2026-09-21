# Google Demand Gen Beta in New Ads

New Ads defaults to Meta. Google adds one Demand Gen Image + Products campaign
with a shared pool of five headlines, five descriptions and nine images. It does
not create nine ads. Google posting is disabled; the final package is uploaded
manually in Google Ads. This change is local and does not change Render topology.

## Operator workflow

1. Select Google, the product, category, country, product URL and optional Campaign Moment.
2. Submit, copy the prompt, and use the CSV popover to download the blank Google template.
3. Give ChatGPT the prompt, exact product image and template. Import its completed CSV through that same popover.
4. Generate and upload the nine images to their matching slots. Every group has a
   1200 × 1200 square, 1200 × 628 landscape and 960 × 1200 vertical composition.
5. Save campaign, select the usual Files/Dropbox destination, and save there.
   Saving before copy import or before all nine images exist is supported.
6. Use **Open saved Google campaign** to browse back to the saved campaign folder.
   **Open folder** also opens that folder in the existing Files page.

## Implementation and record format

- `ads_google_demand_gen.py`: `GOOGLE_DEMAND_GEN_PROMPT_V1`, product context,
  nine-slot contract, CSV validation/import/export, JPEG validation, save/load.
- `prompts/google_demand_gen_v1.txt`: supplied master prompt plus the supplied
  ChatGPT CSV contract. Runtime injection reuses the existing product/category,
  country-language and image-realism helpers. Meta's Baseball-only fallback
  edition claim does not count as verified Google product evidence.
- `ads_google_ui.py`: Google rendering, form snapshots, shared copy display,
  CSV popover, upload/replace/remove, Files picker and disabled posting control.
- `ads_page.py`: additive platform selector/dispatch; existing Meta widget keys,
  prompts, campaign types, copy/CSV schemas and image counts stay in place.
- `ads_posting_handoff.py` and `ads_posting_page.py`: explicit guards against
  passing Google campaigns into Meta posting.
- Tests: `test_ads_google_demand_gen.py`, the pre-change Meta prompt hash fixture,
  and updated JPEG/established export expectations in `test_ads_image_workflow.py`,
  `test_ads_page.py` and `test_posting_import_csv.py`.

No database migration is required: New Ads currently uses session records and
Dropbox packages. The additive `platform` field is `meta` or `google`; missing or
null means Meta. New Meta saved posting packages explicitly carry `platform`.
Google state uses separate session keys, never the Meta result or image keys.

Each Google campaign folder contains:

- `google-campaign.json`, schema version 1: platform, campaign ID, product identity,
  category, country, type `demand_gen`, URL, Campaign Moment, verified metadata,
  generated prompt, timestamps, completion state and `google_config`.
- `google_config`: imported setup/audience fields, the shared copy pools, search
  terms, and exactly nine `image_slots` with prompt, dimensions, filename, saved
  path, MIME type and SHA-256 when an image exists.
- `sports-cave-google-demand-gen.csv` and `google-prompt.txt`.
- `assets/<content hash>/01-right-square.jpg` through `09-left-vertical.jpg` for
  uploaded assets. Revision folders retain the original requested filenames and
  keep the previous manifest usable if a later save fails partway through.

The JSON manifest is committed last, after successful asset and text uploads.
Reopening validates the platform, schema, nine-slot mapping, approved folder
boundaries and saved image hashes before replacing the active draft. Removing an
asset clears its next manifest reference; it does not delete historical files.
Image filenames imported in CSV are references, never automatic downloads or
evidence that an image exists.

## JPEG behavior

`ads_image_workflow.prepare_new_ads_package_jpeg` decodes, applies EXIF orientation,
flattens transparency onto white, converts to sRGB RGB and writes an optimized
quality-95 JPEG with an sRGB profile. It preserves the oriented dimensions.
Google rejects incorrect slot dimensions rather than cropping or resizing.

New Ads uses this conversion for both Meta and Google, including historical PNG
bytes saved as a new package. Existing stored PNGs remain readable and are not
migrated or deleted. Creative Refresh retains its existing export behavior.
The old PNG converter remains available for those flows.

## Verification

Run with the repository virtual environment:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_ads*.py'
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

`test_ads_google_demand_gen.py` covers the form, CSV controls and invalid imports,
shared copy and slot counts, product changes, platform isolation, JPEG format and
dimensions, incomplete and complete save/reopen, failed saves and Meta publishing
guards. A fixture records 78 Meta prompt hashes captured before implementation.
The JPEG tests preserve the explicit Creative Refresh PNG checks.

Four pre-existing test expectations were stale at baseline: the old dropdown
order, superseded carousel prompt wording, and a no-URL fixture with a valid
Shopify handle, plus a posting test that still expected nested copy-file paths
after the existing export had changed to flat filenames. These were aligned with
the existing implementation; Meta product
behavior and prompt text were not changed to make them pass.

Local verification on 21 September 2026:

- The ads-focused discovery run passed 393 tests.
- The final Google/image/handoff/CSV/Meta posting run passed 263 tests, including
  all 16 Google tests and all 78 pre-change Meta prompt hash comparisons.
- Save/reopen and upload failures were exercised using an in-memory Dropbox
  adapter; image decoding/encoding used the real Pillow implementation. No live
  Dropbox, Meta, Google or deployment writes were made.
- The full discovery run executed 3,016 tests, with 130 failures, 36 errors and
  36 skips. An untouched HEAD archive executed 3,000 tests, with 132 failures,
  33 errors and 36 skips. Both reproduce a shared Streamlit form-context failure
  across many UI tests and existing unrelated assertion failures. The four new
  Google UI tests hit the same polluted context in full discovery and pass in
  both focused runs. The full suite is therefore not green.

Detailed local logs and the HEAD comparison are under
`output/google-demand-gen-checks/` (ignored by Git).

Beta limitations: no Google API publishing, no Merchant Center feed connection or
live Google preview/eligibility validation. CSV copy and prompts come from the
operator's ChatGPT session. Uploaded creatives must already have the exact native
slot dimensions. Dropbox availability and existing Files permissions are required
for durable saving and reopening.
