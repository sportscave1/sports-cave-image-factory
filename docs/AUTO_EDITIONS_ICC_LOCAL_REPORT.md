# Auto Editions ICC correction — local implementation, 16 October 2026

Task `20261015-65dad529`, owner `codex-icc-20261016-01`. Uncommitted local work.
This is the initial implementation report. The owner subsequently approved the
sRGB template policy and the current catalogue audit was completed; see
[the follow-up catalogue review](AUTO_EDITIONS_ICC_CATALOGUE_REVIEW_20261016.md)
for current approval status, scoped legacy proposals and the held recovery plan.
Studio allocated the task from `1a41ca3e`; the new clean task branch was then
fast-forwarded by rebase to its verified descendant Worker Health release
`8a9b87baaf0e9d7a5e76e4e8cdb25486e436777a`. No new commit, push, production merge,
deployment, configuration change or provider write was performed. Other task
worktrees, V17, Worker Health controls and release changes are retained.

## Confirmed causes and evidence

1. **Genuine missing source profiles.** Read-only PSD resource inspection confirms
   Verry Elleegant, AFC Supremacy and designs-canvas are untagged RGB/8, each
   2835 × 2004. They are not classified as corrupt. The two catalogue sources took
   0.30/0.26 ms to inspect locally; only bounded metadata was read. Photoshop also
   reopened the staged template as untagged. The old onboarding code raised
   `NeedsRepair` for missing profiles and the companion set `repair=True` for
   colour decisions. Those routes now distinguish colour review from PSD repair.
2. **Export omission reproduced.** Photoshop saved a PNG from the tagged template
   candidate without ICC metadata. The previous restoration required
   `original.png` to already contain ICC bytes, so it could not recover when that
   export also lost its profile. Preparation now reads exact ICC bytes from the
   PSD resource, corroborates Photoshop's document state and every export, then
   restores metadata without decoding/recompressing IDAT data.
3. **Inspection failures are separate.** Photoshop inspection now records tagged,
   untagged and inspector-failure states. The ExtendScript enum is `ColorProfile`,
   as verified against the installed Photoshop DOM. Getter exceptions do not
   become proof of an absent profile. Binary resource inspection is independent
   of machine working-space defaults.
4. **Source/export disagreement remains blocking.** A tiny disposable Photoshop
   PSD witness embeds the profile actually in use. Its ICC bytes must equal the
   source bytes before number exports begin; Python independently checks it too.
   This detects same-label/different-byte profiles and automatic profile changes.
   Existing conflicting PNG ICC data is never overwritten.
5. **Compatibility, scratch and transfer failures remain distinct.** RGB/8 is the
   existing supported preparation mode. Other modes/depths require review and
   separate conversion approval. Scratch disk, connection, upload, source change,
   numbering and plaque errors do not become colour-policy recovery candidates.

## Recommended policy and supplier evidence

Recommend **sRGB IEC61966-2.1 for the new template**, subject to owner approval.
Preserve other valid embedded RGB profiles exactly. No blanket sRGB assignment
to legacy untagged artwork is approved or configured.

Two historical Sports Cave edition JPEGs were inspected read-only:
`#001-At Last Dale EarnHardt Sr.jpg` and
`#001-The Intimidator vs The Wonder Boy Dale Earnhardt Sr and Jeff Gordon.jpg`.
Both are 11340 × 8016 and embed sRGB IEC61966-2.1. Their presence in edition-output
folders establishes prior export practice, **not verified physical-print or
fulfilment acceptance**. The AFC storefront JPEG is untagged and therefore cannot
establish colour intent. These observations support a proposed standard, not an
assertion that every historical source was authored in sRGB.

Prodigi's [official colour guide](https://www.prodigi.com/blog/beginners-guide-to-colour-profiles/)
specifies RGB editing and treats its product ICC files as destination profiles
for soft proofing, which should not be embedded as document profiles. Its
[printing FAQ](https://www.prodigi.com/faq/printing/) describes proofing support.
Neither establishes a universal sRGB requirement or the historical intent of an
untagged Sports Cave PSD. Preserve the distinction between document RGB profiles
and supplier/paper proof profiles. Existing SKU-specific V16 certification,
visual approval, dimensions, bleed and safe-margin requirements remain mandatory.

Adobe's [PSD specification](https://www.adobe.com/devnet-apps/photoshop/fileformatashtml/)
defines ICC resource 1039 and intentionally-untagged resource 1041. Its
[profile guidance](https://helpx.adobe.com/photoshop/desktop/adjust-color/color-profiles/color-profiles.html)
explains why a working-space display of untagged RGB is not embedded-profile
evidence. No printer profile, monitor profile or machine default is guessed.

## Concrete template candidate

Local artifacts are under `output/icc-review/` in this task worktree:

- `designs-canvas-sRGB-CANDIDATE-AWAITING-APPROVAL.psd`
- `template-acceptance.json`, `photoshop-template-reopen.json`
- `template-original-UNTAGGED.png`, `template-candidate-sRGB.png`
- `template-policy-PENDING.json`, `proposed-sRGB.icc`
- `photoshop-preparation-result.json`, `template-local-preparation/`

The candidate was made from the pinned downloaded template by changing ICC
resources only. Original SHA-256:
`fb24e209f3fb6013e38cef2a8603728fa7eb30411584745a3779c3b584cd77a0`.
Candidate SHA-256:
`deb8eed2a958168389acc7863418895cf17e13941df4923471c16f49541320e9`.
The proposed ICC SHA-256 is
`2b3aa1645779a9e634744faf9b01e9102b0c9b88fd6deced7934df86b949af7e`.

Canvas stays 2835 × 2004 with original 72 ppi metadata. Layer/pixel tail hash is
unchanged; merged composite pixels are identical. Photoshop reopens the candidate
as sRGB. The complete inspected layer surface is unchanged, including
`SC_EDITION_NUMBER` (`001 / 100`), `SC_EDITION_PLAQUE`, `SC_EDITION_MATTING`, text
style, effects and geometry. No font substitution, layer rasterisation, resizing,
pixel conversion or original-template save was used to create the candidate.
Equal raw pixels alone cannot establish the intended appearance of untagged art;
the thumbnail comparison is explicitly a proposed interpretation.

The complete local preparation test, at native scale 1 (TEST only), generated all 100 number patches and exact
references for editions 1/100, preserved pixels outside the number region, retained
ICC through the TEST JPG and reported `source_unchanged=true`, `print_ready=false`.
It took 77.674 seconds (68.438 s numbering assets; 6.570 s master preparation).
Metadata-only candidate creation and integrity hashing took 0.858 s. The final
early ICC witness byte check was additionally exercised in installed Photoshop.
No catalogue design or the 45 existing packages was regenerated.

## Reusable approval and recovery

`scripts/review_auto_editions_colour.py` offers offline inspect/propose/approve/
template/audit commands. A proposal records the exact ICC bytes and hash, trusted
reference/comparison artifact hashes, source group and pinned members, each with
provenance. Approval requires an identified owner and the exact reviewed proposal
fingerprint. Changed or conflicting policies fail closed. Registry configuration
is empty by default; no approval was created in this task.

`template-policy-PENDING.json` fingerprint:
`904bb099537bfeb0a1059a442116ba210fa9f4dd3223122ecf78d2765c064f02`.
It covers the template only. After approval and separately authorised publication,
future designs that retain its embedded ICC follow the normal tagged path without
another colour-policy decision. Existing untagged catalogue groups need verified
membership and a one-time scoped decision; filenames, folders and matching layer
names are insufficient provenance. Pinned members reuse the policy automatically.
Changed/unverified future untagged sources stay pending membership review; the
implementation deliberately does not infer ancestry from matching artwork layout.

Install the same reviewed policy registry on server and companion via
`AUTO_EDITIONS_COLOUR_POLICIES_FILE`. Only after a separately authorised release,
`AUTO_EDITIONS_COLOUR_RECOVERY_ENABLED=true` enables bounded automatic recovery.
`auto_editions_colour_recovery.recover(..., dry_run=True)` is the default planning
operation. The recovery flag is independent of owner colour approval.

Recovery selects only exact approved missing-profile sources, preserves existing
priority/source identity, respects Pause and serializes with claims. It excludes
prepared checkpoints **and any stored preparation for that product**, active
replacement/reset operations, current leases, changed mappings and uncertain
inspection/export/supplier conflicts. Each product gets one audited automatic
colour retry, avoiding a recurring failure loop. Source revision is rechecked by
the existing authoritative grant flow. Paid priority remains highest; failed
policy loading cannot block unrelated queue claims. Existing retained verified
packages and source/edition identity checks remain in place.

After import and independent package verification, `colour_recovered` records the
exact preparation hash. This grants no visual or supplier approval. No edition,
certificate, allocation, approval, order or mapping is reset by recovery.

## Audit and Worker Health

Most recent retained companion journals cover 139 product identities: 52 missing
profile, 3 ICC mismatch, 11 number-layer, 5 plaque, 1 number-format, 49 historical
source-change and 18 undetermined records. This is **local retained history**, not
the authoritative current mapped-catalogue total or a live failure count. The
connected browser had no authenticated Sports Cave tab; production credentials
were not loaded into a development process. A current server snapshot/audit is
still required before live recovery. The audit primitive and read model do not
download or process the catalogue to count failures.

Worker Health adds explicit missing-profile, inspector failure, ICC mismatch,
policy-pending, approved-correction and recovered diagnostics, plus affected /
recovered / unresolved design counts. Recovered counts require both the matching
audit hash and current verified uploaded status. No provider calls were added to
page reads. Existing 25-row paging, lazy diagnostics, 20-second refresh and bounded
SQL reads remain. Browser tests at 1280/390 px passed, with 25 rendered rows and
350 DOM nodes after repeated refreshes; measured first paint 173/71 ms in the
synthetic browser fixture (the final rerun measured 89/71 ms). These are local
measurements, not production latency.

## Tests and remaining authorisation

Focused backend run: **204 passed, 1 skipped** (native PostgreSQL performance
fixture), 1 warning, in 160.98 seconds, using disposable PGlite and synthetic
identities. The final colour-specific rerun passed **26 tests** in 20.76 seconds, including
tagged/untagged preparation, same-label ICC conflict, metadata-only assignment,
original integrity, PNG IDAT preservation, JPG ICC, policy reuse/tamper rejection,
bounded recovery, unrelated failures, preservation of 45 prepared designs, paid
priority, staged-copy corruption rejection and Worker Health diagnostics. These
runs overlap; their counts must not be added. Run logs are in `output/icc-review/`.

Node JSX inspection/witness contracts, Worker Health desktop/mobile browser
contracts and V17 desktop/mobile contracts passed. Studio static/syntax, secret
pattern checks and Render topology validation passed. No application startup
smoke test or development preview used production credentials/customer records.
Later edits are rechecked and recorded in Studio before handoff.

Remaining decisions: approve the sRGB template proposal and verified legacy
source cohorts after reviewing their evidence; authorise a specific tested
release/idle companion update and recovery enablement separately; authorise any
Dropbox template publication separately. Unverified colour intent and supplier
certification remain pending. No production deployment or actual catalogue
recovery has happened, and no physical print match is claimed.

## Changed implementation

- `auto_editions_colour_source.py`, `auto_editions_colour_policy.py`,
  `auto_editions_colour_recovery.py`: resource inspection, staged assignment,
  scoped policy and recovery.
- `auto_editions_colour.py`, `auto_editions.py`, `auto_editions_package.py`:
  ICC restoration and PNG/JPG/package validation.
- `scripts/photoshop/inspect_psd_editions.jsx`,
  `scripts/photoshop/prepare_auto_editions.jsx`, `scripts/prepare_auto_editions.py`,
  `scripts/studio/auto_editions_local.py`: independent Photoshop evidence and
  companion orchestration.
- `auto_editions_onboarding.py`, `auto_editions_onboarding_api.py`,
  `auto_editions_onboarding_store.py`, `auto_editions_status.py`,
  `worker_diagnostics.py`, `worker_health.py`, `components/worker_health/index.html`:
  colour review, opt-in retry, audit and lightweight diagnostics.
- `scripts/review_auto_editions_colour.py`, new colour Python/JSX tests and updated
  existing expectations. Disposable SQL test transport now supports migrations
  with multiple statements and psycopg-compatible top-level timestamps; JSONB
  remains JSON.
