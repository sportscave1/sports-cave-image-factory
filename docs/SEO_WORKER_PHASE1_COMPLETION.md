# SEO Phase 1 completion and release verification

20 October 2026. Studio task `20261020-57995487`, branch
`codex/task/growth-seo-worker-phase-1-consolidated-workspace-20261020-57995487`.
The verified task worktree is
`C:\Dev\SportsCaveWorktrees\sports-cave-growth-seo-worker-phase-1-consolidated-workspace-20261020-57995487`.

This completion supersedes the remaining-work list in the initial
[implementation report](SEO_WORKER_PHASE1_LOCAL_IMPLEMENTATION.md), which retains
the feature migration map and original verification history. The continuation
authorized finishing local verification and pushing/deploying to Git/Render.

The release incorporates production revision
`87c6eec5426981221c283ce62b76af4453e0ee02`, including the recorder browser-focus
correction. Recorder source, its separate worktree, preview and database were
preserved. No recorder files differ from that integrated revision.

## Completed remaining work

- Shared persistence now adapts existing JSON state and legacy tables through
  `seo_phase1_store.SharedSEOStore`. Interactive loading checks existing storage;
  it does not apply migrations. No new production SQL table or migration is needed.
- Plan edits and legacy status changes save in one PostgreSQL transaction with a
  workspace lock, source row locks, version checks and conflict rejection.
  Disjoint edits merge; duplicate-open-task races and conflicting edits roll back.
- Legacy task/proposal changes appear in Plan on reload. Source IDs, evidence,
  draft content, mappings and history are retained. Source mutations require an
  administrator in the backend as well as the UI.
- Editing an approved proposal clears its approval metadata and returns it to
  awaiting approval. Plan never grants proposal approval or publishes to Shopify.
- Deferred items remain deduplicated but leave the actionable queue. Original
  task validators support the additive deferred/review values.
- Plan opens its exact linked draft in both the existing editor and review
  control. Revision-bound decisions persist through database reloads.
- Render selects shared storage by default; local execution remains local unless
  explicitly configured. Existing Google connections are reused.

| Plan | Legacy growth task | Legacy recommendation |
|---|---|---|
| Open | approved | draft; existing unchanged approvals are preserved |
| In progress | in_progress | in_progress |
| Ready for review | ready_for_review | awaiting_approval |
| Deferred | deferred | snoozed, with a 14-day snooze |
| Done | completed | completed |
| Dismissed | cancelled | rejected |

Source assigned maps to In progress. Measuring/measured map to Done without
changing those source states during unrelated saves. These source tables already
use text status fields, so this requires no SQL enum change.

## Isolated shared data and full app

Separate container: `sports-cave-seo-phase1-pg-57995487`, loopback port **55447**,
database `seo_phase1`. It does not reuse the recorder database on 55439.

`scripts/seo_phase1_devdata.py` validates the exact loopback host, port and database
before preparing the established schema chain and synthetic records. The
development-only marker/call-record tables are never imported by production code.

`scripts/seo_phase1_preview.py` launches actual `app.py`, account sign-in, sidebar,
route dispatch and existing same-origin handlers. It sanitizes the environment,
disables dotenv, uses empty isolated Streamlit secrets, blocks external sockets
and subprocesses, and confines file writes to its runtime directory. It excludes
the production server launcher, provider credentials and scheduled workers.

Google integration tests run unchanged `GoogleReports` and `CanonicalGA4Client`
against deterministic raw API responses. They verify exact Google-organic,
all-organic and all-channel scopes, compatible market/device filters, privacy
differences between property/query totals, source metrics and cache reuse. This
verifies the integration contracts; it does not claim reconciliation of live
Google property values using production credentials.

The authenticated browser walkthrough passed:
login -> Analytics -> persisted Plan task -> bidirectional legacy transitions ->
health import -> exact linked draft -> existing editor save -> internal review ->
combined History -> bounded Worker scan. All additional report views were opened.
View switching reused cached source requests.

Widths verified: 1440px, 1920px, 1280px with CSS zoom 1.25, and a 1280 physical-pixel
/ 125% equivalent context (1024 CSS pixels, device scale 1.25). No document
overflow or Streamlit exceptions were observed. The zoom check is an emulation;
the user's browser zoom setting was not changed.

Evidence: [acceptance results](seo-phase1-evidence/acceptance.json),
[1440px screenshot](seo-phase1-evidence/analytics-1440.png),
[125% equivalent screenshot](seo-phase1-evidence/analytics-1280-125.png).

## Reproduce

Run the existing full application Python runtime against
`scripts/seo_phase1_preview.py --root .local/seo-dev --port 18977`.
Open `http://127.0.0.1:18977/?page=seo`. Synthetic credentials and the dedicated
database setup are contained in the preview script; no real account is used.

Set `SEO_PHASE1_TEST_POSTGRES=1` to opt into the loopback execution tests, then run
`tests/test_seo_phase1.py`, `tests/test_seo_phase1_ui.py` and
`tests/test_seo_phase1_shared.py` with pytest. The authenticated walkthrough is
`node tests/seo_phase1_full_browser.cjs` and requires the isolated app to be running.

## Verification

- **25 Phase 1 model/UI/shared-Postgres tests passed** on the full runtime with
  Streamlit **1.58.0** and Python 3.14. These cover atomic rollback, concurrent
  edits, duplicate races, permissions, all legacy statuses in both directions,
  approval invalidation, source scopes/cache and persistence.
- **69 canonical reporting, blog, audit, recorder-navigation and retired-Mockups checks passed**, with six subtests, in a clean process. These checks
  run in a separate clean process. Some legacy tests import/render `app.py` during
  collection and leave a Streamlit form context that contaminates unrelated
  AppTests; those collections are not used to assess new UI behavior.
- A wider combined run returned 194 passes and 20 failures/subfailures, including
  that collection contamination and old refresh/source-string and Ads/product
  prompt/pricing expectations. It is not reported as green. The initial checkpoint
  separately reproduced five reporting/navigation and five account/source-string
  failures on its approved base. Ads/Products services, prompts and pricing were
  not changed by SEO.
- Python compilation, whitespace checks and Render topology validation passed.
  No Blueprint was changed or synced.

## Recorder and execution boundary

The integrated Task Recorder has authenticated device relay, ownership checks,
command receipts, fencing and revision-bound local browser recording/playback.
Those capabilities are preserved. SEO links to the real Task Recorder page but
does not silently bind or start a recorded task. The older top-bar WebM capture
also remains unchanged.

A later SEO execution handoff can carry the stable Plan ID, proposal revision,
target/evidence, explicitly permitted scope and existing recorder device/task
revision/operation references. Recorded content remains evidence, not authority.
Autonomous SEO execution, automatic proposal generation and live Shopify
publishing remain outside Phase 1. No email/ad send, live theme edit or new
schedule is part of this release.

## Files completing the work

- Transactional persistence/status synchronization: `seo_phase1_store.py`,
  `seo_phase1.py`, `seo_growth_intelligence.py`, `seo_workspace.py`.
- Workflow/editor integration: `seo_phase1_ui.py`, `seo_page.py`.
- Isolated environment: `scripts/seo_phase1_devdata.py`,
  `scripts/seo_phase1_preview.py`.
- Verification: `tests/test_seo_phase1_shared.py`, new model regression,
  `tests/seo_phase1_full_browser.cjs`, and `docs/seo-phase1-evidence/`.

Deployment targets the existing primary `sports-cave-os`
(`srv-d8kl4on7f7vs73dvavv0`) in the user-confirmed Nathan's workspace. Its
Git-backed auto-deploy path is retained; no replacement primary is created.
