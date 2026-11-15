# Product Uploads master prompt V6 — 19 October 2026

User authorised integration and production deployment in this chat.
Release base: current production main `42e661f3ed4002e71326719f1249b562249c6eba`.

Product Uploads now uses the supplied SPORTS CAVE ULTIMATE 3-MOCKUP MASTER V6
in full. Its existing output renderer imports the updated master automatically.
The V6 prompt key prevents an old saved V1 master from masking the replacement;
saved individual room/camera customisations remain unchanged. The three upload
cards remain Man Cave, Office and Living Room. Per-card requirements now use V6's
source-preserving compositing, verified scale, glazing, framing and output rules.

Validation: 75 focused tests plus 48 subtests passed across master composition,
saved settings, output/export lifecycle, gallery, mockups, original retrieval,
upload validation and prompt storage. Exact attachment comparison, changed Python
syntax, Product Uploads JavaScript state checks and Render topology passed.
Desktop Chrome browser verification passed: full 128,280-character resolved
prompt copied, full V6 master and three complete per-card contracts present,
original image copy pixel checks, three uploads, mocked save of all 16 outputs,
stale action revocation and zero JavaScript errors. Clipboard comparison normalises
Windows line endings. The harness uses a synthetic RGB8 PSD and disposable
SQL/provider doubles; no customer artwork, production writes or Companion jobs.

Deploy by pushing only this tested change on current main. The canonical existing
sports-cave-os service auto-deploys main. No infrastructure or environment-variable
change is required. Verify the exact resulting commit is live, health is successful
and recent runtime logs show no new errors before reporting completion.
