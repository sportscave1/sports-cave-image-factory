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
