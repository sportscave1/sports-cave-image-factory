# Auto Editions V15 — final local acceptance

Status: **implemented and tested locally; not live**. 15 October 2026.

Worktree: `C:/Dev/SportsCaveWorktrees/sports-cave-integrations-auto-editions-v15-automatic-product-mappin-20261014-1aae0e49`.
Task `20261014-1aae0e49`, owner `codex/v15-20261015-01a13cc7`, branch
`codex/task/integrations-auto-editions-v15-automatic-product-mappin-20261014-1aae0e49`.
HEAD remains the owner-approved V14 prerequisite `ca9ff5c2`. Both preceding phases
are retained. No commit, push, merge, deployment, production write, live allocation,
Shopify publication, supplier order or companion installation was performed.

## Final repairs and acceptance evidence

Successful mapping, queue, companion, preparation, approval and TEST download
components were reused. Phase 3 repairs two confirmed diagnostic defects:

- A malformed legacy preparation source now becomes Failed without raising during
  the batch status projection. Other products retain their authoritative statuses.
- Legacy receipts without byte counts now report missing size evidence, instead
  of falsely claiming that the current Dropbox file differs.

An explicit offline metadata audit supports batches of at most 200 supplied
Masters entries. It reports unknown identities, discrepancies and missing files
only when the supplied inventory is complete. It has no cloud writes, source
discovery, automatic relinking, approval or page/worker polling integration.
Example: `python auto_editions_asset_audit.py --export metadata-export.json`.
The JSON contains `records` (hash, mapped, receipts), `entries` (Dropbox metadata)
and `complete`; follow `next_offset` with `--offset`. Do not include credentials.

The lifecycle regression uses real disposable PostgreSQL and synthetic images:
eligible registration -> durable waiting -> late PSD discovery -> one audited
mapping -> one queue checkpoint -> companion lease -> generated archive import ->
all 101 immutable PNG uploads/metadata checks -> stored pixel proofs -> Review ->
explicit existing approval endpoint -> Cloud Ready -> existing synthetic ledger
number 36 -> durable idempotent numbered TEST JPG job. Source bytes, existing JPG
bytes, manifest geometry/hash, product cursor, allocations, ownership and
certificates are unchanged. Photoshop output and Dropbox transport are synthetic;
this is not a claim that a live Photoshop run occurred.

| Acceptance case | Local evidence |
| --- | --- |
| PSD before product; product before PSD; new PSD | Discovery SQL tests, incremental cursor and late-PSD lifecycle |
| Manual Add; existing verified mapping; repeated events/requests | Existing transactional mapping/queue tests, one audit/mapping and retained lease/checkpoint |
| Ambiguous title, handle, filename, ownership or location | Fail closed; no mapping, fuzzy match or prepared-folder source candidate |
| Interrupted Photoshop; failed/lost upload | Companion exception/lease/source-preservation tests; recovery ZIP retained, reconnect and lost-success receipt tests |
| Render/process restart; discovery/queue lease recovery | Recreated durable stores, expired leases, fenced old workers, atomic rollback and concurrent PostgreSQL claims |
| Correct product/file/revision/limit/geometry | Manifest/source fences, all patch checksums, original-outside-number and reference pixel proofs; changed identities rejected |
| Review and current Cloud Ready | Existing approval endpoint plus scoped status SQL; stale source, proof/hash, limit and approval cases fail closed |
| Number authority | Existing allocation-only renderer plus integrity regressions; duplicate jobs reuse identity; no allocation creation API used |
| Permissions | Existing active-account, page, administrator, same-origin, host revocation/session and RLS denial cases |
| Table/edit/save/scroll | Real Streamlit and browser fixtures at 1440/390px; native cell edit deferred/committed, manual Refresh retains dirty edit and scroll |

Logs and measurements are retained under ignored `output/v15-phase3/`. The broader
suite initially passed 246 tests/17 subtests; additional runtime, allocation,
cache and rollout regressions passed 15 tests/8 subtests. After the final audit
repair and three added cases, the focused suite passed 80 tests. Existing
FastAPI/Starlette deprecations and the deliberate duplicate-ZIP test warning are
unrelated. The final consolidated suite passed **264 tests and 25 subtests** in
72.13 seconds: `output/v15-phase3/final-consolidated.log`. Static verification
passed all 27 checks against the approved V14 prerequisite; topology passed.

Browser acceptance: two compact status/review layouts, two real native grid
layouts, two existing onboarding layouts and nine PSD modal/File scenarios pass.
The performance harness additionally exercises 12 native sessions and 60 simulated
visible 25-second intervals per V15 session. Every interval makes one batch;
unchanged responses cause no full-page or table reconstruction. Actual screenshots
are `output/v15-phase3/native-1440.png` and `native-390.png`.

## Performance, same 334-product synthetic baseline

V14 table modules are extracted directly from committed `ca9ff5c2` into ignored
output. Both loopback fixtures use identical synthetic products, the real native
Streamlit editor and no production startup hooks, credentials or remote catalogue.
Three fresh browser sessions per width/version measure navigation-to-grid time.
These small samples include local bootstrap/scheduling noise; they are neither
hosted latency nor an assertion of faster production rendering.

| Measurement | V14 baseline | V15 |
| --- | --- | --- |
| Desktop median navigation-to-grid | 1,110 ms | 1,068 ms |
| Mobile median navigation-to-grid | 1,006 ms | 1,026 ms |
| Native grid viewport / row height | 600px / 28px | 600px / 28px |
| Desktop initial JS heap median | 13.88 MB | 14.79 MB |
| Mobile initial JS heap median | 13.90 MB | 14.63 MB |
| Extra status database queries | 0 | 1 scoped batch per visible 25s interval |
| Status per-row Dropbox/Shopify calls | 0 | 0 |
| Full-page reruns on status refresh | 0 | 0 |

V15 heap after 30 unchanged polls was 15.32 MB desktop / 15.16 MB mobile median;
30 further polls added no retained heap (approximately -392 bytes per session
after GC). This bounds observed retained growth in the synthetic page, not a
full browser-process or Render RSS guarantee. No expanded row heights or extra
page/table viewport was introduced. Mobile retains the existing compact toolbar
with horizontal access to its controls.

Native PostgreSQL, 334 products and 6,680 audit rows: simple synthetic product
listing median **19.86 ms**, authoritative status median **36.94 ms**, signed
response **75,793 bytes**, one query, zero Dropbox/catalogue API calls. Latest
checkpoint lookup uses the Phase 2 additive index. Edits, scrolling, hidden tabs
and open dialogs pause/defer refresh application; unchanged polling never rerenders.

## Read-only existing asset audit

At approximately **00:57 UTC, 15 October 2026**, connector-only SELECT/metadata
inspection used the repository-documented authoritative Supabase project
`ceyzbfpuwuuxaiqwiltz`. No credentials were imported into previews or tests, and
no customer/order content or pixel downloads were requested. The similarly named
`sports-cave-image-factory` project was checked for schema presence only; it had
none of the preparation tables and was not used as authority.

All 50 immediate Masters folders and their bounded child listings completed
without pagination remaining. Their 4,976 files were compared with 48 preparation
records containing 4,848 receipts:

- All **4,848 recorded file IDs/names** were present in the correct hash folder.
- All **2,929 recorded byte counts** matched. **1,919 legacy receipts lack byte
  counts**; these remain evidence gaps, not inferred mismatches or approvals.
- All 48 recorded hash folders exist and retain their recorded product/file mapping.
- Nine sampled metadata reads (master, number 1 and number 100 for one active
  preparation and the two unreferenced preparations) matched recorded revisions.
  The other 4,839 revisions and all pixel hashes were not freshly revalidated.
- Two folders are **unrecorded**: `3f64e368452aa47c5338a69751896c62e9ac97742bfd6f4829e5abc658b6ca54`
  has 104 files; `d9717124f857a72a1f3182f7d61f105fa29249ffb8d62ab278e7d3bf459b0c13`
  has 24 files. They are not eligible for automatic source discovery or approval.
- Two recorded preparations have **no current checkpoint or layout approval**:
  `d685d19de22148e9aad4af4ac5ebd3e9f229a2b80311ea0a16f16f113447cc23`
  and `e5126d7e2e02e695a8dec3448493c40b6ac340c5d8c6f4bd78f5d8887d9e5b6e`.
  Their mapping still exists; they may be retained historical attempts, not
  proven corrupt or safe to remove.

Machine-readable evidence: [AUTO_EDITIONS_V15_ASSET_AUDIT.json](AUTO_EDITIONS_V15_ASSET_AUDIT.json).
Preserve all four flagged identities. Owner review should correlate their original
import/audit/package provenance and current product/source/geometry. If recovery
is appropriate, use the existing authorised preparation/review workflow after
verification; never silently attach by folder name, overwrite a master, delete
history or infer approval. Check legacy missing-size evidence against an exact
recorded revision and package before any separately approved receipt repair.
Root Packages/Reports/Cache and the two root ZIPs were observed but are not Masters
receipts; no orphan/expiry or deletion claim is made for them.

## Compact operator guide

1. **Automatic:** eligible Shopify create/update enters the existing authenticated
   registration path. Exact unique original PSD identity is verified and audited,
   then queued. A late PSD stays durably waiting and is picked up incrementally.
   Existing Add/Save queues automatically; existing mappings/checkpoints survive.
2. **Preparation computer:** Windows signed-in desktop, existing authorised
   companion, Photoshop exposing `Photoshop.Application.200`, required fonts,
   internet, adequate Photoshop resources and at least 8 GiB free local disk.
   The computer must be awake. Python and the installed runtime remain required;
   Codex, VS Code and an open Edition Ops tab are not required for processing.
   The existing companion's approved Windows sign-in startup must be installed;
   local source alone does not install or update that runtime.
3. **Connect/reconnect:** start the existing owned companion using its installed
   launcher (or its already approved sign-in task). In existing Auto Editions
   onboarding, use **Connect preparation computer** and approve the local
   connection. The preparation-only capability is DPAPI-protected for that Windows
   user, renewed on authorised use, expires after 30 idle days and is revocable.
   Password/session changes or revocation require explicit reconnection. Never
   paste capabilities into logs or provide Shopify/Dropbox credentials locally.
4. **Administrator approval:** open Review, inspect the prepared artwork/plaque,
   numbering, faces/borders and enlargement quality; confirm visual quality using
   existing controls. Approval is mandatory and TEST-only. A green Cloud Ready
   tick is neither Shopify sync completion nor supplier print certification.
5. **Needs Repair:** correct the actual PSD through the established artwork process
   after checking fonts, editable number/plaque layers and geometry. Preserve the
   verified mapping. Use safe Retry where offered. A retained immutable or stale
   preparation requires administrator source/approval review; never reset its hash.
6. **Failed:** read the compact reason, check internet, disk, Photoshop dialogs and
   companion connection. Retry only when offered; Prepare Now promotes an awaiting
   or deferred job. Connect recovers older valid mappings missing a checkpoint;
   it never remaps or allocates numbers.
7. **Recovery:** polls occur every 30 seconds locally. Successful packages reconnect
   and resume upload without reopening Photoshop; lost success responses reuse
   the completed receipt. Server preparation leases expire after 45 minutes and
   allow three interrupted attempts before blocking for review. Old workers cannot
   publish under a replacement lease. Durable discovery survives worker restarts.
8. **Hard kill caveat:** the shared legacy `Documents/SportsCavePrintJobs/processor.lock`
   is intentionally not stolen or age-deleted. A killed companion can leave it.
   Stop owned processing, close/check Photoshop and verify every print/preparation
   owner has exited before an administrator recovers that exact stale lock. Restart
   the companion and allow lease recovery. If ownership is unclear, retain the lock
   and escalate. Routine work is automatic; this exceptional recovery is manual.
9. **Verify a new artwork:** confirm File still opens the mapped PSD, then Queued /
   Preparing / Review / Cloud Ready in Auto Editions. Open the status for its latest
   checkpoint. Use Refresh without discarding edits. For a numbered TEST download,
   select an existing authorised allocated unit; never create an allocation to test.

Discovery cycles every 60 seconds, idle Dropbox deltas at most every five minutes,
and waiting retries every 15 minutes or when new metadata wakes them. Initial
inventory and historical deferred bootstrap can take multiple bounded cycles.
Prepare Now/order urgency retain precedence. Preparing represents a valid lease,
not a Photoshop heartbeat; external availability still requires the computer.

## Owner-approved release checklist and unresolved limits

No production integration steps below have been executed:

- Review the complete uncommitted diff against `ca9ff5c2`, plus both preceding
  reports. Resolve Studio's older registry base comparison separately; inherited
  V14 whitespace failures remain intact. Static verification against the approved
  prerequisite, task diff and Render topology pass. Tested does not mean committed
  Ready for Review; a commit requires separate authorisation.
- In an authorised release candidate apply **20261014234210_auto_editions_v15_discovery.sql**
  and **20261015000124_auto_editions_status_audit_index.sql**, after existing PSD
  mapping/V6/V11 schemas. Verify server grants, RLS/browser denial and index use.
  Phase 3 adds no migration, dependency, service, cron or allocation change.
- Include the Phase 1 worker/registration and Phase 2 status routes/assets in the
  existing architecture. Enable `AUTO_EDITIONS_V15_ENABLED=true` consistently on
  existing registration/webhook/worker processes; retain the existing cloud TEST
  gate `SPORTS_CAVE_AUTO_EDITIONS_V6`. Use the canonical Sports Cave OS service;
  validate topology and inspect any authorised Blueprint preview for zero extra
  primary services before applying it.
- Verify the actual installed Windows companion includes the prerequisite V11–V14
  host/transfer/cleanup code and approved startup. Do not overwrite another Studio
  task, change its owner or install this task automatically. Pair the actual
  preparation computer and run one authorised test-only staging artwork through
  real Photoshop, network interruption, host/server restart and visual approval.
- Review the four asset identities and legacy evidence gaps above without deletion
  or automatic relinking. Complete any required full revision/pixel verification
  in bounded batches separately; this audit is metadata evidence only.
- Perform hosted authenticated multi-user/browser/load acceptance and verify real
  server RSS/latency. Local synthetic memory/timing does not establish hosted
  capacity or real fonts/Photoshop quality. Source changes and stale preparations
  continue to block readiness/download; safe Retry never resets an immutable hash.
- Only after owner approval, release through the established process. Monitor
  waiting, leases, failures and Review. For rollback disable V15 discovery, preserve
  additive records and assets, and review queued work; never reset the ledger,
  certificates, ownership, metafields or archived JPGs.

Exact changed-file inventory accompanies this report in
[AUTO_EDITIONS_V15_CHANGED_FILES.txt](AUTO_EDITIONS_V15_CHANGED_FILES.txt).
Phase 1 and Phase 2 reports explain each earlier implementation change. Phase 3
adds the audit helper/report, lifecycle and audit tests, V14 baseline/performance
fixtures, two companion regressions, the two diagnostic repairs and this guide.
