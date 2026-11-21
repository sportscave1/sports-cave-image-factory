# Speed Optimisation

Daily review/coding runs at **01:00 Australia/Sydney**, using **GPT-6.1 Sol / Medium**.
Automation: `speed-optimisation-daily-1am-sydney`. It uses the existing Codex project
entry and explicitly selects this isolated coordination worktree. The computer
and Codex must be available for local scheduled execution.

Read DAILY_TASK.md on every run. Allocate one Studio task per improvement and
preserve unrelated work. The user authorizes automatic releases of verified speed
and code-cleanliness improvements, preserving operations, data, permissions,
functionality and existing designs. Work on one section per day, prioritising
new/changed areas, including Marketplace and Website.

## Companion

`python scripts/speed_companion.py start` starts a hidden singleton supervisor
and report publisher, using Studio process locking and Windows DPAPI encryption.
The supervisor recovers an exited worker. The native daily run ensures it starts;
a Windows logon shortcut also starts it. No clipboard copying is necessary.
The companion queues/retries reports, validates publication receipts and retrieves
history plus aggregate Supabase table statistics. It cannot execute code or deploy.
Its credential is encrypted in ignored `.local-data/speed/publisher.json`; only
its digest is configured on the canonical Render primary. Requests use the exact
canonical HTTPS URL, with redirects disabled. `review`, `queue --report <file>`
and `flush` support unattended handoff. Create `.local-data/speed/stop-companion`
to stop it; explicit Start resumes it.

## Safe checks and release

`python scripts/verify_speed_preview.py --id <task> --owner <owner>` runs the real
Streamlit app in the existing hardened Docker boundary: network none, no host
mounts/ports/secrets, read-only root, non-root user, dropped capabilities, bounded
resources and pinned seccomp. Cache, temp files and synthetic PostgreSQL live in
private container tmpfs. Provider writes, workers and migrations are denied. The
exact source manifest/commit, browser frames and PostgreSQL/API contracts are
recorded under `.local-data/speed/preview/`. Containers are removed afterwards.
This is scoped Speed acceptance; other workflows need their own populated fixtures.
General uncontained previews remain disabled. Production authentication is unchanged.

For the Meta Review overview, add `--meta-baseline <previous-full-Git-SHA>` to
the verifier. It compares the actual prior Git object's reader against the
candidate using a 20-campaign, two-page synthetic provider fixture, nine cold
reads and five complete Streamlit refreshes per revision. It checks identical
request multisets, metrics, tables, search/sort controls and desktop/mobile
visual parity inside the same Docker boundary. The JPEG transport permits at most
two channel levels of noise in 0.05% of pixels; content must match exactly.
These artificial request delays
demonstrate the scheduling improvement; they are never production speed claims.
The preview-only provider overrides are recorded in the acceptance evidence and
are never exported back to application source or the live service. Live Meta
verification must use the existing account connection and GET-only refresh.

The image refresh supports current static navigation, existing services source
and the current connection-pool dependency. Speed.Dockerfile pins the original
local base and hash-checks the dependency wheel; build from a minimal source context.
`scripts/speed_release.py` exports the exact committed candidate and reuses normal
offline release validation, with a final GitHub main revision fence. It publishes
from the owned Studio branch without touching another local main checkout.
The installation exception is limited to the initial task/base; nightly fixes
require repeated workflow timings and behaviour/visual parity. Verify exact
GitHub/Render revisions and relevant live checks after the normal auto-deploy.
Never create or rename a primary service; sports-cave-os remains canonical.

## Code and Supabase cleanliness

`scripts/speed_code_review.py` reports unused-import candidates without executing
or deleting code. Confirm dynamic references, exports, registration effects and
tests before removal. Retain infrequent features, recovery paths, migrations and
regression evidence. Record actual removals or reduced payload/memory/import cost.

Reports include cleanup_checks and storage_checks. Storage review uses aggregate
metadata, not customer rows. Only the speed_report:v1: namespace expires: 90 days,
at most five immutable reports per date (normally one, with correction allowance),
96KB maximum per report. Retries reuse the same ID. Raw logs, screenshots, customer
data and code dumps stay out of Supabase. No new table or migration is required.
Never automatically drop application tables/indexes or delete orders, editions,
financial/customer records or shared provider history based on size alone.
