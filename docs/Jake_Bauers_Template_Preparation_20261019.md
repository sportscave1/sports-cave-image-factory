# Jake Bauers template preparation — local investigation, 19 October 2026

## Result and scope

The demonstrated failure is a worker enlargement defect. Jake's saved native PSD
is opaque and structurally valid. Photoshop 27.10.0's existing 4x layered resize
introduces alpha at the canvas boundary when the full-canvas artwork is a normal
smart-object layer rather than an opaque Photoshop Background. No source, template,
colour policy, edition allocation, mapping or production record was changed.

The local fix preserves and verifies the native artwork, prepares its independently
opaque bottom artwork as a Background on the disposable staged document, then
uses the existing enlargement and editable edition/plaque pipeline. It does not
choose a fill colour, turn on hidden matting, flatten the source PSD, substitute a
font, convert colours, or relax output validation. Native artwork pixels before
and after Background promotion must match exactly. A separately measured test
upscale remains TEST ONLY, not supplier certification or permission to print.

**Production remains unchanged.** Installing/releasing the corrected companion and
server, then explicitly retrying only Jake's existing checkpoint, remains pending.
Real uploads were not attempted. Local server archive import checks simulate the
transfer/cloud boundary; they do not establish production Cloud Ready.

## Workspace evidence

Original repository inspected at
`C:\Users\hello\Documents\sports-cave-image-factory`: local main `7b84f2c5`, with
many unrelated modified and untracked files. All were preserved.

Native `git worktree list --porcelain` identifies the INTEGRATIONS category folder
at `C:\Dev\SportsCaveWorktrees\sports-cave-integrations`, branch
`codex/category/integrations`, clean at `2a0bf7b7`. It is an idle, outdated category
entry point. Its AGENTS.md requires a separate Studio task. The newer companion
recovery and PSD intake tasks also contain unfinished changes; neither was edited.

Studio created task `20261019-9cee8802`, owner `codex-jake-template-20261019`, in
`C:\Dev\SportsCaveWorktrees\sports-cave-integrations-jake-bauers-template-preparation-failure-i-20261019-9cee8802`.
Branch: `codex/task/integrations-jake-bauers-template-preparation-failure-i-20261019-9cee8802`.
Its initial registry base `59b60972` was stale. While this new checkout was clean,
its task branch was advanced directly to verified current `origin/main`
`8ee2aa687d04f5bb276a926b0d9e58b7ad1d2e4c`. No merge or commit was made. This
contains current mapping and automatic companion handoff code. No existing task
branch or files were reset. AGENTS.md local-only/isolation rules were followed.

## Exact product, source, template and job

| Identity | Evidence |
|---|---|
| Product/design | `gid://shopify/Product/15427775824179`, Jake Bauers — The Eleventh Pitch |
| Authoritative mapping | `product_psd_mappings` SELECT: `id:u1tYiAa2O-AAAAAAAABw6g` |
| Failed PSD revision | `0165e2e9786d4d3000000036d367e13`, 285,917,086 bytes |
| Dropbox content hash | `9ec05aa80b19006a0f4c7a6fa03a07d259fc4247230c019a43a06c1668d9199c` |
| Source SHA-256 | `161708de41a0b41a64bcbb9707ec066c61033d3996140e575c7a29d609e9b677` |
| Companion local job | `dc6c69b085907f8db07c9245d5adcc9b3983cf7c86015a17` |
| Queue identity | `auto_edition_onboarding` is keyed by product_gid; no separate queue-job UUID |
| Claim audit | id `5550`; same lease beginning `aaec6bb7` in local job and queue audit |
| Actual template | User confirmed `03_ASSETS/designs-canvas.psd` |
| Template Dropbox ID/revision | `id:u1tYiAa2O-AAAAAAAAAALQ` / `0165dfeceb5e463000000036d367e13` |
| Template bytes/local SHA-256 | 162,221,634 / `deb8eed2a958168389acc7863418895cf17e13941df4923471c16f49541320e9` |
| Template local Dropbox hash | `99d9972578e61ae0fca89735019a0670b964ffeb486da852068789a3622c9b8e` |

Read-only Dropbox metadata still identifies the pinned Jake revision. Template
metadata was read separately; the connector omits its server content hash, so the
local template hash is recorded independently. No separately embedded template
version/cryptographic parent-child lineage was established. The user identified
the authoring template; names alone were not used as lineage proof.

The other files `sportscave-new-designs-template.psd` and
`SC_Auto_Editions_Base_Template_V1.psd` were inspected only while locating the
canonical file. They are different assets and are not recommended substitutes.
The former lacks the recognised plaque role; the latter is untagged. Existing
historical documentation about an untagged designs-canvas revision predates the
current tagged 17 October revision and is not evidence against this source.

## Running revisions and warning

Read-only Render deployment verification in the user-confirmed Nathan's workspace:

- OS application: `8ee2aa68`, deploy `dep-dbaue4gae00c73a5r09g`, live at
  `2026-10-19T09:50:10Z`.
- Background worker: `8ee2aa68`, deploy `dep-dbaue4gae00c73a5r220`, live at
  `2026-10-19T09:48:45Z`.
- Running Windows companion: process command line uses
  `.studio/installed-releases/approved-eb74083066591d0dd5ff652059afdb1615614ae3/scripts/studio/companion.py`;
  installed marker and Jake diagnostic both identify `eb740830`.
- Native Photoshop: `27.10.0`, recorded in inspection and native preparation.

`git diff eb740830 8ee2aa68` is empty for `auto_editions_local.py`,
`prepare_auto_editions.py`, and `prepare_auto_editions.jsx`. The Worker Health
warning compares release revisions as well as the companion module hash. A
revision mismatch exists, but there is no demonstrated preparation compatibility
change between these installed/cloud revisions. The warning was not suppressed,
and the live companion was not updated. The local correction still needs normal
version alignment before production recovery.

## Correlated attempt history and exact failure

Read-only Supabase SELECTs against the repository-documented authoritative project
`ceyzbfpuwuuxaiqwiltz` confirm one queue attempt, still Blocked with no preparation
hash. Relevant audit events (Sydney time is UTC+11):

| UTC time on 19 October | Sydney time | Audit/stage |
|---|---|---|
| 10:01:31.949 | 21:01:31.949 | `5549 mapping_confirmed` |
| 10:01:33.988 | 21:01:33.988 | `5550 claimed` |
| 10:01:38.126 | 21:01:38.126 | `5551 Preparing` |
| 10:05:26.832 | 21:05:26.832 | `5554 ARTWORK_ALPHA`, recovery not attempted |
| 10:05:39.778 | 21:05:39.778 | `5555 Blocked`, `5556 ARTWORK_ALPHA`, attempt 1 |

Application logs include Jake's exact product status GET at 10:01:44Z. The
companion's retained input, inspection, preparation.json, native-status.json,
job-state.json and failure-detail.json all identify this source/job. Native status
records all 100 number exports completed and the owned document closed. Last
successful stage: native Photoshop export. First failed stage: local independent
pixel/reference verification in Preparation. No upload stage, preparation hash,
cloud receipt or completion claim exists for Jake.

Exact retained ValueError:

> Saved artwork exports RGBA with non-opaque alpha (222-255). An approved opaque composition is required; no background was guessed or painted.

The original failure-detail.json records the exception type and message, but no
historical traceback. Local reproduction of the exact retained failed exports
records the stack in `tmp/jake-template/original-failure-reproduced.txt`:
`auto_editions.compose`, `auto_editions.py:183`, raises this ValueError while
reading master.png (the caller in normal preparation is reference comparison).
This is a reproduced stack, not an invented historical traceback.

The failed original.png, master.png and reference-1.png are RGBA 11340x8016,
alpha 222–255, with 77,400 non-opaque pixels at the outer canvas boundary. The
number-1.png patch is RGB. A fresh native-size Photoshop export from the pinned
source is RGB 2835x2004, completely opaque. Repeating only the existing layered
resize reproduces the exact alpha range. Promoting the independently opaque
native artwork to a Background on the disposable copy removes the introduced
alpha; hidden matting remains hidden. The corrected native composite is pixel
exact before enlargement.

This was not template-role inspection, layer ambiguity, edition/plaque editing,
font, colour/profile assignment, upload or completion verification failure.

A separate retained upload/checkpoint HTTPError exists for Blue Heaven,
product `10377381577011`, local job `1efb2c8ac1b0e00ec0ad939288f135da5e10ef7bda68513e`.
It is a different source/job. No screenshot attachment was available in this chat
to prove which historical upload row its warning referred to. It was not treated
as Jake evidence or retried.

## PSD comparison

Current designs-canvas and Jake are RGB/8, tagged `sRGB IEC61966-2.1`, 2835x2004
at 72 dpi. Both have top-level editable `SC_EDITION_NUMBER`, content `001 / 100`,
installed `Cinzel-Medium`, and visible `SC_EDITION_PLAQUE` smart object. Their
source-specific positions differ and are retained. No duplicate role, nested role,
font substitution or broken number/plaque containment was observed. Matting is
visible in the canonical template and hidden in Jake; Jake instead has full-canvas
opaque `Generative Fill` artwork. Enabling hidden matting would change the source
and is not the fix. Smart-object artwork/plaque contents are not searched for
alternative numbering targets.

Previously successful control: The King of Football Pelé Wall Art, product
`8148468793651`, source `id:u1tYiAa2O-AAAAAAAAAYdQ`, revision
`0165da24823563f000000036d367e13`, hash
`9caf6ad093a88a4ad3f600ec31687ce8f46889d53bbe5ed9fa9f33b6caa5dc1a`.
Its exact source has a retained Cloud-assets-independently-verified receipt. Its
7016x4961 tagged RGB source is prepared at native size. It is a historical
successful control, not another failed Jake attempt.

## Changes and recovery contracts

- `auto_editions_preflight.py`: reuses onboarding detect/role/font/geometry rules;
  verifies native PNG opacity and the proposed background plane; verifies exact
  native pixels after promotion and opaque full-size original/master outputs.
- `scripts/photoshop/prepare_auto_editions.jsx`: read-only-source native preflight,
  exact layer identity pinning, isolated bottom artwork export with visibility
  restored, disposable Background promotion, existing editable number/plaque and
  export logic. No guessed backing or hidden layer activation.
- `scripts/prepare_auto_editions.py`: validates source identity before expensive
  work, runs preflight, preserves native proof/ICC checks and strict composition
  checks, records versioned resize evidence. Each native dispatch invalidates the
  previous cleanup receipt, preventing preflight evidence from releasing an
  uncertain later Photoshop call's processor lock.
- `scripts/studio/auto_editions_local.py`: only transient transport/408/429/5xx
  failures retry; waits of 1 and 2 seconds between the three inner attempts are
  cancellation-aware. Existing outer recovery remains bounded at three cycles.
  Reconnect checks for already-imported completion before retransmission.
  Deterministic HTTP validation failures stop. Exact redacted server validation
  reasons, stage-specific diagnostics, traceback and append-only local failure
  history are retained. No bulk retry, queue seeding or allocation code changed.
- `tests/test_auto_editions_template_preflight.py`: regression coverage for native
  opacity, the demonstrated 222 alpha, incorrect/duplicate/nested roles, missing
  fonts, wrong totals/identity, changed native pixels, deterministic/transient
  retry behaviour, retained intermediates, cleanup evidence and diagnostic
  redaction.

Existing exact-source input/inspection cache and verified completed-package reuse
remain intact. Packages are tied to pinned source revision/hash, edition total,
roles and preparation geometry; imported output is independently rechecked by
the server. A partial invalid alpha export is not reusable. Queue uniqueness,
lease fences, content hashes and reconnect completion checks remain distinct
from product mapping success. No edition allocation is performed by this change.

## Local verification

Acceptance results and artifact paths are recorded in the accompanying
`tmp/jake-template/*-result.json`, `sandbox-results.json`, manifests, source/pixel
proofs, native cleanup receipts and PNG/JPEG previews. Final measured results are
listed below after verification. Cloud checks are simulated local archive import,
using the actual server unpack/validation function and test doubles for network
retry tests; no production upload or live technical-review completion was run.

## Authoring instructions for future designs

1. Continue using the current **designs-canvas.psd**. A replacement template is not
   required by this failure. No corrected template was created or installed.
2. Save a new PSD; preserve the original template. Keep one visible, unlocked,
   top-level editable `SC_EDITION_NUMBER`, with its exact installed font and
   enough digits for the full edition limit (`001 / 100` for 100). Do not rasterise,
   duplicate, group or embed this number target inside a smart object.
3. Keep one visible, top-level `SC_EDITION_PLAQUE`; keep every rendered edition
   number within its plaque. Preserve intended text styling, plaque placement
   and layout. Artwork and plaque may remain smart objects.
4. Keep the approved background/matting visible, or supply an independently
   opaque full-canvas bottom artwork layer. Hide matting only when the visible
   artwork already covers the canvas. Transparent output requires explicit
   authoring review; the worker will not fill or enable a background for you.
5. Preserve the embedded approved colour profile, RGB mode and 8-bit depth. The
   current template is tagged sRGB. Do not silently assign/convert another
   profile, flatten the source or substitute fonts to bypass validation.
6. Preserve canvas proportions. The current 2835x2004 template follows the
   existing 4x TEST path to 11340x8016. Enlarged pixel dimensions do not certify
   source detail or print suitability; existing quality/supplier review remains.
7. A successful PSD mapping is not prepared/cloud completion. Require opaque
   exports, every numbered patch/checksum, exact independent reference and
   outside-number proofs, verified package import, then the existing cloud
   technical/visual readiness decision. Keep any actionable failure visible.

## Pending production work

Review/install/deploy the local correction through the normal approved release
process and align the companion with the application. Afterwards authorise a
scoped retry of Jake's existing blocked preparation against the same current PSD
revision (re-check source revision first). Do not remap, reset editions, allocate
new numbers, overwrite the live template or bulk-retry unrelated failures.
External network, storage, fonts, disk, Photoshop and source changes can still
fail; the checks preserve a specific stage/cause and bounded safe recovery.

### Final acceptance results

| Local input | Real Photoshop | Required numbered assets | Pixel and colour checks | Simulated import |
|---|---|---|---|---|
| Exact Jake source (`jake-fixed`) | PASS, 27.10.0 | 100, 11340x8016 master | Native Background promotion pixel exact; original/master opaque; exact 001/100 and outside-number proofs; ICC preserved | PASS, 139,779,129-byte archive, all 101 master/patch assets verified |
| Newly authored design from current designs-canvas (`fresh-authored-fixed`) | PASS, 27.10.0 | 100, 11340x8016 master | New editable gold title, unobstructed original template plaque; exact 001/100 and outside-number proofs; native pixels and ICC preserved | PASS, 11,657,557-byte archive, all 101 master/patch assets verified |
| Previously completed Pelé source (`pele-fixed`) | PASS, 27.10.0 | 100, native 7016x4961 master | Exact 001/100 and outside-number proofs; ICC preserved | PASS, 139,231,727-byte archive, all 101 master/patch assets verified |
| Deliberately transparent template variant (`transparent-rejected`) | Correctly rejected in native preflight | **0 numbered exports** | Specific alpha 0–255 / full-canvas requirement; no guessed backing; owned Photoshop document closed | Not submitted |

Final local preparation hashes:

- Jake: `fa79abee29baf8cf5a5821263e107cb272a48d69b8f2486c8e77fba4309fc7ec`
- Fresh template design: `5e2b3baf2a3d179c55533886673c6c0a8f252c2d69224affc8f9c910bef03f0e`
- Pelé control: `509ec1adfd817a71b26383c03e1cde1730b139b1b6e4eaaad7b5e53da890e674`

All three acceptance runs produced source-proof.json, proofs.json, manifest.json,
numbered PNGs, original/master PNGs, native cleanup evidence and TEST JPEGs.
001 and 100 full-canvas previews were visually inspected: required numbering,
plaque placement, artwork and intended colour appearance were retained. The new
fixture intentionally uses new editable test typography on the canonical template;
it is not a new Shopify product or a manufactured Dropbox file/revision. Its
schema-conforming source ID/revision are explicitly local test doubles. The
initial exploratory Jake-art/template composite and malformed test-revision run
are retained as experiments, not counted as acceptance designs.

`final-source-and-cleanup-checks.json` re-hashes original retained Jake, the actual
Dropbox designs-canvas file, and the historical Pelé source after all runs.
All are unchanged. All acceptance native runs completed and closed their owned
documents. The final negative test exercised the current dispatch cleanup guard
and rejected the incompatible file before costly enlargement/numbered export.

Final regression command (production credentials were not loaded):

```powershell
$env:AUTO_EDITIONS_TEST_PGLITE='C:\Dev\SportsCaveWorktrees\.studio\release-evidence\ov20\pgtest\node_modules\@electric-sql\pglite\dist\index.js'
& C:\Users\hello\Documents\sports-cave-image-factory\.venv\Scripts\python.exe -m pytest tests/test_auto_editions_native_v19.py tests/test_auto_editions_onboarding.py tests/test_auto_editions_reliability.py tests/test_auto_editions_template_preflight.py tests/test_auto_editions_preparation_host.py tests/test_auto_editions_package.py tests/test_auto_editions_bulk_reliability.py -q
```

**98 passed, 0 skipped, 43.05 seconds.** One expected zipfile warning is emitted
by the test deliberately constructing duplicate manifest entries. Native benchmark
safety tests are offline unit tests; real Photoshop runs are separately identified
above. `git diff --check` passes. No production job was claimed by these scripts,
no Shopify/Supabase records were written, no production replacement was uploaded,
and no commit, push, merge, deployment or live companion installation was done.

The local fix is tested and retained uncommitted in its isolated task. There is
no remaining local Photoshop/source availability blocker. Production recovery and
real cloud readiness remain pending the separately authorised release/alignment
and scoped retry described above.
