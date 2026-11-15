# Sports Cave OS latest updates release

The owner explicitly authorised committing, pushing, deployment to the existing
Render services and updating the Windows Companion on 17 October 2026.

The release starts from origin/main ef87511b and adds the completed Product Uploads
workflow. Earlier Bulk Review, Worker Health, reset cancellation, colour recovery,
automatic technical processing, Orders, email, Settings V2 and Design Studio V4
updates are already incorporated. Historical task copies and the original dirty
checkout are preserved. The independent in-progress PSD repair is excluded.

## Product Uploads integration

Durable account-owned PSD intake, bounded/resumable chunks, stored Dev Mode prompts,
clipboard fallback, Files navigation, exact Shopify title/URL lookup including
drafts, canonical product registration, mapping conflicts, queue handoff, cached
preview and terminal status are included. Linking does not create a Shopify product.

When AUTO_EDITIONS_TECHNICAL_FLOW_ENABLED=true, the intake reuses the released
asynchronous Technical worker. It cannot issue a separate intake approval before
that worker validates source, asset bytes, profiles and durable receipts. Technical
retries reuse retained preparations. Existing global status/policy checks determine
Cloud Ready. The intake-scoped fallback remains available when the global flow is
off. No duplicate native preparation pipeline is introduced.

The private product_upload_intakes migration was applied to the verified production
project. RLS is enabled; anon/authenticated have no SELECT access; service_role has
the required privileges. The automatic route is enabled through its explicit Render
environment flag after publication. Native scripts, shared templates, existing
colour policies, allocations, certificates and source artwork are not changed.

## Verification

- 284 combined intake, technical-worker, recovery, status, quality, visual, Files,
  prompt and upload-mode tests passed; 34 subtests passed. One optional native
  PostgreSQL benchmark was skipped. The new global-worker scenario uses real SQL
  and generated fixture assets and proves no early intake approval is created.
- Real Chromium tested the release branch's actual HTTP component with the released
  technical worker enabled, including clipboard fallback, resumable uploads, source
  recovery, manual modes, Files navigation, duplicate submissions, technical
  completion, preview reuse, narrow layouts, scaling and iframe height handshake.
  Shopify, Dropbox and Photoshop producer boundaries are local test doubles.
- Migration manifest safety, topology, Python compilation and JavaScript syntax
  checks passed. No Blueprint sync or replacement service is needed.
- Windows device tests passed 30 cases. A broader legacy Studio suite passed 49
  cases and reported six failures plus one cleanup error in existing preview/source
  navigation fixtures. Studio runtime code is unchanged from the released baseline;
  those results are retained rather than described as a passing full Studio suite.

## Deployment and Windows verification

The canonical primary sports-cave-os, existing sports-cave-os-webhooks and existing
sports-cave-seo-worker deploy from main. Verify their exact new commit and runtime
health, rather than treating a push/build trigger as deployment completion. Owner-
suspended legacy resources and unrelated repositories remain untouched.

The installed native worker started this release at ef87511b in Recovering state,
with a retained processor safety lock and no active cloud preparation lease or
pending local upload. Software handoff must preserve that lock and all job journals,
and must not terminate Photoshop or Dropbox. The Dev Mode Companion uses the same
existing task/owner, trust store, port and Windows startup identity when its runtime
is updated. A software update does not certify cleanup of the prior native failure.

Exact commits, deploy IDs, installed paths/hashes, startup backup, protected-process
checks, job hashes, health responses and final status belong in the ignored local
`output/release-all/` evidence. The source report's native template-size and
Photoshop validation limitations still apply. No new production design is submitted
for testing, and no supplier/order fulfilment is enabled.
