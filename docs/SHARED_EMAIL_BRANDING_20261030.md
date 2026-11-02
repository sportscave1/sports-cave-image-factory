# Shared email branding release evidence

Task: `20261030-0952e68d`, owner `codex-email-branding-20261030-01a18b94`.

## Confirmed cause

`with_email_defaults` used `setdefault('html_sections', ...)`. A saved document's
copied sections therefore won over the successfully persisted singleton settings.
Published flow preview loaders also returned frozen publication settings, and
campaign dispatch consumed rendered queue snapshots. Saving a global default
refreshed only a composer fragment whose settings argument could remain stale.
The HTML importer discarded the approved header's Outlook conditional markup.

Read-only production inspection on 30 October found header version 4 with the
approved HTML and footer version 2 with the user's current footer. Nine published
native flow snapshots and four campaign drafts contained copied sections. The
six recorded campaigns were all SENT. No scheduled campaign existed at inspection.
The active Post Checkout and Abandoned Checkout flows use native delivery.
The older legacy Abandoned Checkout flow is paused. No detected campaign-body
logo/unsubscribe embeds required destructive body extraction.

## Change and preservation

Shared settings resolve into a render copy, including older copied section slots.
Original documents, bodies, publications, template versions and sent messages are
retained. The exact approved header source is a repository asset; its safe,
known Outlook markup survives rendering. Footer source/design is not rewritten.
Successful saves use the returned database revision, clear preview cache and
rerun the full app. Database/concurrency failures remain errors.

Campaign branding is pinned in existing runtime storage under a campaign lock.
Queued frozen messages are refreshed only at verified renderer envelope boundaries;
body bytes, subjects, recipient personalisation and tracking survive. Unrecognised
envelopes fail closed. Campaigns already submitted before this release keep their
historical branding for retry and campaign consistency. Flow branding is pinned
per future send; already-submitted jobs keep historical settings. No job is recreated.
Published flow previews resolve current branding and thumbnails include it in keys.

The explicit release SQL backs up shared settings, authored drafts/templates and
flow definitions inside existing private runtime storage before installing the
header. It preserves the footer, campaign delivery snapshots and sent history.
Its migration marker prevents reruns overwriting subsequent edits.

## Scope and exceptions

Campaign authoring, preview, test transport, scheduled/queued campaign assembly,
batch dispatch, single-send worker, personalised/catalogue payloads, native flow
preview and future native automation sends share this policy. Existing market,
consent, timing, unsubscribe, size and provider-idempotency guards remain active.

Support mailbox signatures, direct transactional messages and the separate
customer-requested wall-preview delivery service have independent purpose-specific
templates. They do not use the CRM shared-branding editor and were not converted.
Plain-text alternatives and intentionally plain messages retain their send paths.
The paused legacy automation is not activated or republished.

## Validation

Two offline regressions reproduced the old missing-header/footer behaviour before
the renderer fix. Disposable PostgreSQL and mocked transports cover save/reload,
revision conflicts, source history, existing/new previews, queued-before-edit
delivery, campaign version pinning, payload equality and idempotent backup migration.
Synthetic final production JSON and HTML were inspected, not just a browser canvas.

The saved production header/footer with a synthetic body measured 11,287 HTML bytes
(11.02 KB), below the 97,280-byte send ceiling. Chromium measurements at 320, 390,
600 and 1000 pixels showed a centred 180 × 54 logo and no horizontal overflow.
Exactly one logo and one unsubscribe link were verified. Source retains Outlook
fallback, but native Outlook client execution was not available.

Commands and raw results are retained in the task's Studio runtime evidence folder.
No customer campaign, internal test email, flow activation or customer job was sent.
Render topology validation preserves the sole canonical `sports-cave-os` service.
