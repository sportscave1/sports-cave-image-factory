# Product Uploads PSD performance and deferred handoff — 19 October 2026

Task `20261019-91c418c4`, owner `codex-01a1533c-psd-performance-20261019`.
Worktree `C:/Dev/SportsCaveWorktrees/sports-cave-products-product-uploads-psd-performance-and-defer--20261019-91c418c4`.
Branch `codex/task/products-product-uploads-psd-performance-and-defer--20261019-91c418c4`.
Verified clean before edits and advanced the new task to the verified live commit
`f5d925e84affe788d965f3b8c256e369acf8b098`. The previous task and unrelated checkouts
were not edited. The user explicitly requested direct GitHub/Render publication.

## Confirmed cause and scope

The manifest release (`fc73bd37`, deployed in `f5d925e8`) removed the server-side
condition around the final handoff component. A second workflow iframe therefore
mounted as soon as a PSD was selected. Its hidden upload area still loaded PSD
thumbnails/previews, polled state and requested mapping status. This was measurable
extra work, even though no final prompt or WEBP originals were being retrieved.

The previous release `e0a5419b` and current release were compared by loading their
actual Git object source into an isolated harness, without resetting any checkout.
The PSD selection/decoder and shared image engine files are byte-identical across
all three versions; the harness asserts this. There was one source selection, one
prepare request and one original PSD download per run in every version, including
subsequent mockup generation. No duplicate full PSD decode/upload was found.

The fix restores the server-side mount condition and additionally checks the
current receipt version and active prepare/generate/save jobs. No final component
is mounted for initial, manual, incomplete, failed or outdated workflows. The
post-save component also stops loading a hidden PSD preview. The disabled panel
and its Save All first helper are removed. The upper controls remain intact.

The authoritative saved manifest, exact folder path/optional ID, collision handling,
save tokens and on-click prompt generation are unchanged. Rendering/copying does
not discover folders or retrieve originals. The existing single exact-folder ID
lookup occurs only after a complete save when the receipt lacks that metadata;
an already recorded folder ID is reused. No PSD validation, ICC conversion,
resolution, encoding, generation or Save All implementation was changed.

## Repeatable measurements

Representative file supplied by the user: `peter-brock-king-of-the-mountain.psd`,
217,337,232 bytes (207.27 MiB), 2835 × 2004 RGB8 with embedded profile. Only read
the local synced original; all derivatives went into disposable local directories.

Five runs per version, rotating version order, no concurrent test suites in the
final measurement run. Windows Chrome headless, Python 3.12, actual HTTP routes,
disposable PGlite SQL, warm OS file cache and a cold application derivative cache
per run. Dropbox is replaced by a local disk replay and a synthetic early thumbnail.
Real Pillow decoding, existing ICC handling, prepared preview and all five core
mockups use the same source and repository templates. Actual page mount decisions
are executed with the upper Streamlit renderer stubbed in the benchmark shell.
The full Streamlit entrypoint is tested separately.

Median milliseconds:

| Stage | Previous `e0a5419b` | Manifest release `f5d925e8` | Fix |
| --- | ---: | ---: | ---: |
| Selection to metadata bound | 14 | 14 | 14 |
| Selection request to original transfer starting | 34.39 | 32.65 | 35.02 |
| Original transfer (local disk replay) | 102.34 | 115.64 | 99.40 |
| PSD decode, ICC conversion and PNG output | 1161.88 | 1154.28 | 1149.51 |
| Complete server preparation | 1641 | 1641 | 1625 |
| Selection to artwork-ready UI | 2304 | 2332 | 2301 |
| Selection to decoded usable artwork preview | 2329 | 2350 | 2328 |
| Five core mockup generation | 3603.06 | 3617.11 | 3619.35 |
| Selection to five mockup files ready | 5934.04 | 5975.91 | 5957.94 |
| Browser frame-gap p95 | 7 | 7 | 7 |

This does **not** establish a meaningful end-to-end speed improvement: the measured
preview difference is 22 ms and core mockup completion differs by 18 ms. Small
local transfer differences must not be presented as Dropbox bandwidth improvements.
The significant verified reduction is request work: state requests drop from
8 to 4 per selection, preview requests from 3–4 to 2, and early mapping-status
requests from 1 to 0. Those match the previous release. No final prompt or saved
WEBP requests occur during selection/preparation in any version. The fixed page
has zero final component mounts before saving.

All 15 runs produced identical prepared RGB pixels (2000 × 1414, the existing
working-image limit), with SHA-256
`0892805bc6f7eec570b10094ab41c4cdf1557a86c0181cea62137cb144922d7a`.
ICC profile creation timestamps can differ; comparison deliberately uses pixels,
dimensions and mode, rather than assuming encoded PNG bytes are identical.

The current workflow chooses an existing Dropbox PSD: there is no browser PSD
upload transfer. The timed transfer is original retrieval on the server. Local
server time is predominantly image processing; UI polling adds time before ready
is displayed. Live network/database latency was not replayed or measured under
matched Render conditions, so its remaining contribution is unknown.

Read-only production logs showed an attempt starting at 08:46:15.396 UTC and its
217,337,232-byte download verified at 08:46:28.132 UTC. That same instance began
shutdown at 08:46:26.290 UTC. There is no completed preparation timing for that
attempt, so it cannot serve as a clean before/after sample or establish that the
final section caused all of the reported delay. A prior cold preparation logged
20.92 s and cache reuse logged 10.69 s, but these are unmatched observations.

## Verification

- 163 focused Python cases passed across the source/receipt, package, server PSD,
  jobs, loading, recovery, Dropbox selection/download, outputs, mockups, modes,
  gallery and deferred-component suites. One older opt-in test for a different
  PSD is skipped; the supplied Peter Brock PSD is covered by the benchmark.
- Seven actual Streamlit entrypoint cases passed, including the upper five
  previews, lifestyle actions/uploaders, Save All and absence of an unsaved final
  component. Test fixtures were adjusted for Windows asyncio loopback and the
  existing sport-selector/container API; no production networking rules changed.
- Five JavaScript suites passed: complete prompt, upload state, copy feedback,
  mapping and focus. Clipboard success feedback resets at exactly two seconds;
  source changes, late responses and unmount cleanup are covered. A post-save
  handoff with a preview URL must not fetch it.
- Real Chrome and Edge clipboard checks passed for Draft/Live/Update, editable
  template content, exact numbered WEBP folder/ID, clipboard denial, feedback
  reset, invalidation, narrow layout and no image downloads/helper calls.
- Complete, partial, failed, missing-destination, changed-source/image and
  overlapping/late-save cases are covered. Existing save tests exercise numbered
  collision handling, actual count/order, retries and confirmed-file reuse.
- Render topology validation and `git diff --check` passed. No Blueprint change
  or sync, new primary service, Companion invocation or Shopify write is involved.

Evidence: ignored `output/product-upload-psd-performance/benchmark.json`,
`benchmark-run.txt`, test logs, and
`output/product-upload-dropbox-prompt/browser-checks.json`.
To reproduce the opt-in benchmark, set `PRODUCT_UPLOAD_BENCHMARK_PSD` to the local
representative file and `AUTO_EDITIONS_TEST_PGLITE` to the existing fixture runtime,
then run `python -m pytest tests/benchmark_product_upload_psd.py -q -s` in this task.

Runtime changes: `product_upload_mockups_ui.py`,
`components/product_uploads/app.js`, `components/product_uploads/index.html`.
Supporting changes: component README, this report, the benchmark and deferred
handoff tests, entrypoint/recovery/clipboard/state tests, and the clipboard browser
verification script. No unrelated production modules were modified.

The exact released SHA/deploy/health result is recorded in Studio and ignored
release evidence after publication. Live logged-in PSD performance, full Streamlit
websocket latency, and Dropbox → ChatGPT → Shopify transfer are not claimed tested.
