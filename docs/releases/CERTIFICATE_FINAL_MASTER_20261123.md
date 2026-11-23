# Final certificate master and centred typography

The user explicitly authorized publishing this template replacement, then supplied a newer border adjustment and instructed continuation with that revision. Scope is newly generated certificates; there is no regeneration, customer backfill or order/allocation change. Phase 1 remains in its separate local worktree; Phase 2 is not part of this release.

## Source and rendering

- Dropbox master: `/Sportscave Team Folder/03_ASSETS/certificate-of-authenticity-template.jpg`, saved 2026-11-23 10:10:26 UTC, revision `01660eecd80ddc6000000036d367e13`, 2,576,437 bytes. SHA-256: `79111749098b2ad30c24dfcc7e6f13619565ddb5874f8abcf860c69a72366f2e`.
- The production JPG is copied byte-for-byte into assets. The user's inset borders, texture, logos, body copy and signature are retained. The PSD remains the editable source and is not required by production.
- The existing PIL image-to-PDF/JPG/WebP generation flow remains in use. The print JPG remains 3508×2480 with 300dpi metadata. A lightweight blank WebP background matches the new master aspect ratio.
- Source Serif 4 Semibold renders the title; Source Serif 4 Regular renders `No. 030 of 100`. Both unmodified fonts and their SIL Open Font License are bundled from Adobe's official source-serif repository, so production does not depend on Windows fonts or Adobe activation. Designer: Frank Grießhammer.
- `certificate_typography.py` centres the combined text block in the protected band between the body ornament and the Handcrafted line. Titles wrap to at most two lines and fit their width. Trailing `Wall Art` is removed only for display and existing spaced dashes are normalized. Names are not guessed or rewritten.
- Display formatting reads the existing edition number and total. Allocation, certificate IDs, filenames and stored `#030/100` metadata are unchanged. Existing Ready certificates still bypass generation.

## Verification

51 tests pass with disposable PGlite enabled. Coverage includes exact display values 001, 027, 030, 100 and 1000; long names and title wrapping; geometric centring at master/preview/print sizes; unchanged pixels outside the text area; PDF/JPG/WebP output; reuse of previously issued certificates; order route access; framing and download behaviour. No real customer order or supplier write was used.

The rendered PDF and existing frame-placement proof were visually reviewed. Evidence and sample outputs are in Studio runtime `20261123-13720924`. Render topology validation passes; only the existing canonical primary service is used. There are no infrastructure or database changes.

Font provenance: https://github.com/adobe-fonts/source-serif/tree/release/TTF
