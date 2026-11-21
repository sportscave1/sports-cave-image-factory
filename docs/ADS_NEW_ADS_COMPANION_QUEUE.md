# New Ads companion queue — local implementation

Task: `20261118-87270961`; owner: `codex-ads-queue-20261118-01a1ec26`.
The user explicitly approved advancing this new task branch from the Studio
November 2 base to existing committed companion revision `3040285d` on November
18, 2026. No other task was edited. The user confirmed scope: any product using
the existing Meta Instant Experience automation, not additional campaign formats.

## Existing flow reviewed

Design Studio Publish + Ad creates a durable ad request alongside its upload job.
After publication and Edition Ops mapping, the paired companion obtains the
verified black-frame original, sends the New Ads prompt into the Meta Ads ChatGPT
project, waits for three named JPEG covers and ad_copy.csv in the job's Dropbox
folder, validates those files, selects targeting, and submits the existing Meta
Posting job. Ads are created paused for review. The queue retains failure details,
posting receipts, account permission checks, one active slot and pause/play state.

## New entry point

New Ads now shows Add to queue beside Submit. Both execute the existing form
validation and result builder. Submit remains manual. Add to queue freezes that
same result, including optional campaign details, and inserts a standalone job in
the existing queue; it does not manufacture or repeat a product upload.

The selected catalog product must have a Shopify ID and matching product URL.
Before generation the worker verifies the Edition Ops record, active Shopify
listing and original Black-frame image. Existing products use the verified Shopify
original image URL; Design Studio jobs retain their exact Dropbox reference.
Missing mapping or reference is reported as a failed job without substituting art.
Both routes reuse the same delivery prompt, output validation and Meta posting code.

Repeated enqueue of an identical saved draft returns its existing job, including
completed or failed jobs, without restarting it. A changed brief or Fresh pack
produces a new draft. Progress appears in Developer → Companion Queues → Ads queue.
Offline or paused queues retain requests until the companion is available and
playing. Carousel and Single Image/Video keep manual Submit; their queue button
is disabled. Google and Creative Refresh are unchanged.

No schema migration or desktop extension update is required: standalone jobs use
the existing app_settings storage and ad-tick protocol.

## Validation

Synthetic PostgreSQL via PGlite; mocked provider calls and Streamlit AppTest, with
outbound provider HTTP forbidden in the new tests. No live preview, account data,
ChatGPT prompt, Dropbox upload or Meta campaign was used for acceptance.

`python -m pytest tests/test_ads_companion_queue.py tests/test_design_publish_ad.py tests/test_ads_auto_post.py tests/test_ads_direct_post.py tests/test_ads_product_url_autofill.py -q --disable-warnings --maxfail=1`

Result: 39 passed and 17 subtests passed. The PGlite fixture uses
AUTO_EDITIONS_TEST_PGLITE pointing to an installed local PGlite dist/index.js.
Tests cover mixed design/direct queue scheduling, durable duplicate protection,
pause/play, account revocation, blocked references, completion receipts, exact
manual-brief reuse and the two rendered form actions.

`node --test tests/test_morning_design_companion.cjs`: 6 passed, including the
existing ad queue's background-project dispatch and matching receipt contract.
Studio Verify passed syntax, infrastructure, changed-file secret-pattern and
diff checks. Live end-to-end ChatGPT/Meta execution remains untested locally.

## Release authorization

On November 18 the user explicitly requested pushing this change to GitHub and
Render for testing. The task was advanced to the latest production revision
`31e6f20f` before release, preserving the newer Design Studio prompt changes.
Release uses the existing primary service's automatic deployment from main;
no Blueprint sync, service creation, production configuration change or desktop
companion installation is required. Live ad generation is left to the user's test.


## Status-bar reliability update — 21 November 2026

Ads rows retain their buttons while progress and timestamps change. Stop displays
its pending state immediately; Delete removes the row immediately and restores it
if rejected. Confirmed action receipts override older header snapshots. Delete
remains authoritative if a late Cancel arrives. Errors stay inline so a toast
cannot cover the retry controls. Action requests have a 15-second timeout and
release their buttons without waiting for the next status poll. Existing chats,
files and Posting receipts remain available; stopping automation cannot reverse
Meta operations already accepted.

Quick Add keeps the typed query while products load, shares one in-flight read,
and supports Reload products after an error or empty result. Search normalizes
spacing, punctuation and accents, accepts words in any order and renders at most
80 matching options at once. Selecting a result preserves its exact product ID;
duplicate display names are never silently substituted. The dropdown overlays the
form instead of moving Add to queue during a click. Retries after an uncertain
submission reuse the same request ID to avoid duplicate jobs.

The header version changes when its markup changes, including Reload products.
On a same-version Streamlit rerun, retained Ads buttons are rebound, pending reads
from the old controller cannot update the new panel, and the account-scoped typed
query/selected product survives reopening. Browser coverage exercises both the
retained shell and upgrading an open older header.

Catalog records have a bounded, account-scoped 45-second cache shared by the picker
and submission. Successful live catalog reads retain their existing five-minute
cache; failed reads are no longer cached as empty results. Reload explicitly
refreshes the live catalog. Logs `ads_picker_catalog` and `ads_queue_control` record
read duration/count and committed action IDs without product/customer content.

Regression coverage includes `test_ads_status_reliability_browser.py`,
`test_ads_companion_controls.py`, `test_ad_quick_picker_browser.py`,
`test_ads_queue_popup_browser.py` and `test_ads_popup_delete.cjs`, using synthetic
endpoints or disposable PostgreSQL.

## Prompt regression follow-up — 21 November 2026

The follow-up suite covers the current production contract rather than the
superseded three-line footer, manual New Ads Submit action, automatic saved-pack
upgrades and old description-style bank. The approved two-line footer is 160px
high, preserves its assigned headline/second-line split, and uses the unused line
as the written Meta headline. Existing saved output stays verbatim. New Ads uses
Add to queue; saved-draft renderer tests explicitly seed an existing draft.

Snapshot fixtures were reconciled with production revision `5073a051` and the
approved current prompt policies. They remain exact hashes/structure assertions;
the test run does not auto-accept new snapshots. Public builders additionally run
across every selectable sport and market, checking the image count, footer,
standalone briefs and persisted copy assignments. Historical seasonal substitution
has its own synthetic legacy template; current two-line prompts stay unchanged.

Two functional regressions were corrected: shared racing-copy instructions now
precede the final CSV instead of becoming extra CSV rows, and refresh packages
validate uploaded image uniqueness even
across locally edited and reused original cards, preserving their saved notes.
Saved copy-only IE variants may intentionally share the verified original bytes;
this exception requires both an explicit reuse declaration and the exact source
hash. Edited outputs and separate Carousel cards retain duplicate checks.
Optional copy review is tested directly as a compatibility component while
current generation retains its integrated review.
Current Carousel records now return immediately on reopen, avoiding repeated
prompt rebuilds and preserving their creation timestamp and saved copy. Shared
editor, upload and Carousel fixtures were also aligned with their deployed
interfaces and current physical-scale/publication wording.

Run the complete Ads and queue checks with:

```powershell
$env:AUTO_EDITIONS_TEST_PGLITE = '<local @electric-sql/pglite/dist/index.js>'
python scripts/run_ads_regression.py
```

The runner strips inherited production credentials, refuses unmocked provider
HTTP/database access, runs Python prompt/UI/queue tests and then the Node status,
request, navigation and download checks. Browser fixtures use synthetic endpoints;
no real advertising, uploads or customer automations are executed.
The standalone prompt editor runs in a separate test process from legacy upload
modules so their imported application adapters cannot pollute its Streamlit state.
