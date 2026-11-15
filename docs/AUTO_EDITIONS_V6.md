# Auto Editions V6

Additive onboarding and private cloud TEST downloads on the existing Sports Cave
OS service. Existing mappings, allocation logic, certificates and Photoshop
downloads remain authoritative. No catalogue rescan or historical migration.

Administrators select an allocated Orders unit (completed units are supported),
open Auto Editions setup, and reuse Add if its PSD is unlinked. Inspect transfers
only that immutable Dropbox revision to the existing trusted companion. Confirm
the design's actual visible number, plaque and matting layers. Preparation uses
Photoshop once, without saving the original PSD. Review the assigned-number
preview before approving the exact product variant for TEST downloads.

The registered reference is `data/auto_editions_template.json`. Its standard
layer names define structure, never coordinates. Legacy roles require explicit
selection. Nested or ambiguous roles and unavailable fonts fail closed.

Persistent assets use authenticated Dropbox under
`03_ASSETS/Auto Editions/Prepared`: one lossless master plus small number patches,
not 100 full-size JPGs. The server independently checks checksums, three Photoshop
reference composites and the untouched image outside the number region. Cloud
generation fetches the master and one patch. No Photoshop, companion pairing or
Developer Studio access is used during the cloud download.

Apply `migrations/20261014004209_auto_editions_v6.sql` explicitly; it creates five
new RLS-protected tables only. Enable `SPORTS_CAVE_AUTO_EDITIONS_V6=true` on the
existing canonical service. Default is disabled. Disable that flag to return
Orders to its existing V4 behavior; no mapping rollback is required. A single
serial worker uses durable leases, bounded retries and deterministic identities.
Generated cache outputs expire after 24 hours. Old/invalid source revisions,
revoked access, altered allocations and changed assets block downloads.

There is no PRINT READY transition in this release. Prodigi credentials and
authenticated SKU specifications are unavailable. Native-resolution TEST masters
are limited to 12 megapixels on the verified worker budget. Production dimensions,
effective DPI, bleed, safe areas, colour and size sharing remain uncertified.
No claim of added source detail is made; no supplier order is submitted.

Pre-release evidence on 14 October 2026: SC3287 native 2835 × 2004 #005/100
rendered on the actual Render Linux host in 5.66 seconds with approximately
130 MiB peak RSS. Its JPG SHA-256 was
`9764dc84320165a51e30908f6768fca3064c053f3260fa80cd42380d27d614ac`,
byte-identical to the locally verified render. SC3284 #002 was pixel-identical
to its existing approved V4 PNG. This compositor evidence alone is not live
OS onboarding or VA acceptance; record those separately after deployment.

Focused checks: 86 Python tests passed, including disposable PostgreSQL queue,
RLS and approval tests; browser cloud-download, existing companion handshake,
Add picker and compact Orders checks passed. The compact fixture now resolves
shared CSS from the application root. The old canonical-line test already fails
on the unchanged base because it expects a generic Files link for an unlinked
PSD. A separate legacy snapshot test requires a missing local CSV; it was not
reported as passed. Studio's broad verification also reports whitespace in
inherited files; the scoped V6 diff passes `git diff --check`.
