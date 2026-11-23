# Revised certificate badge and title spacing — local only

Task `20261123-f044eb6e`, owner `codex-certificate-spacing-20261123`.
Based on the existing certificate release `daec97e570fb6abcbff7a9245c798a64ff6f92e9`.

## Master

The latest `/Sportscave Team Folder/03_ASSETS/certificate-of-authenticity-template.jpg` is copied byte-for-byte to `assets/certificates/certificate-authenticity-master.jpg`. Dropbox revision `01660ef133e3a32000000036d367e13`, modified 23 November 2026 at 10:29:56 UTC (21:29:56 Sydney), size 2,715,252 bytes, dimensions 2835×2004. SHA-256: `201a2020f1f8920d547aec2743bdb94606af8543d0c878726c16fae15e6f2ded`.

Metadata was checked again after the work; the revision was unchanged. The updated badge, borders and lower Handcrafted line come directly from this source. The PSD and Dropbox original are untouched. The matching lightweight 1200×848 blank WebP was refreshed from the JPG.

## Placement

The lower body ornament ends at y=1292 and Handcrafted starts at y=1740 in the master. The combined title and edition block is centred at y=1516, with equal 24px protective margins inside these landmarks. Relative coordinates scale the same layout to preview and 3508×2480 printing.

Source Serif 4 Semibold title and Regular edition-number text retain their existing styling. For two-line titles, the divider (dash, colon or semicolon) is replaced by a line break. The edition name is Semibold; the athlete line uses Regular at 80% of its size in a slightly lighter charcoal (RGB 45/45/45). Hyphenated athlete names retain their internal hyphens. Each line fits the protected width and is horizontally centred. The complete text block remains vertically centred with the existing line and number gaps. One-line titles are unchanged.

Number formatting, allocation, IDs, filenames, the generation pipeline and print DPI are unchanged. No previously issued certificate or customer record is regenerated. This candidate only affects newly generated certificates after a future authorized release. The separate local Phase 1/2 performance worktrees are untouched.

## Checks

67 tests and 3 subtests passed:

```
AUTO_EDITIONS_TEST_PGLITE=C:/Users/hello/.codex/tmp/design-queue-tests/node_modules/@electric-sql/pglite/dist/index.js
python -m pytest -q tests/test_certificate_typography.py tests/test_certificate_engine.py tests/test_certificate_print_download.py tests/test_collector_collection_offers.py tests/test_certificate_frame_fulfilment.py tests/test_orders_certificate.py --tb=short
```

Coverage includes exact 001/027/030/100/1000 formatting; independent measured-landmark centring for one/two-line text at master, preview and print sizes; separator removal, smaller/lighter subtitles and preserved hyphenated names; title integrity and fitting; unchanged pixels outside the text band; PDF/JPG/WebP generation; reuse of already-issued certificates; existing framing and downloads. Disposable PGlite and synthetic certificates were used, without real customer or supplier writes.

One-line, two-line and long-title proofs were visually inspected. Evidence is retained in `C:/Dev/SportsCaveWorktrees/.studio/runtime/20261123-f044eb6e/`.

No commit, push or deployment was performed. Production remains on the previously released master until a separately authorized release.
