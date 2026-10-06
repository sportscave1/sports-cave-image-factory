# Wall Preview CRM V2

## Storefront rollout (theme source is outside this repository)

The production Shopify visualizer/theme has **not** been edited by this backend deployment.
Paste `docs/storefront/wall-preview-crm-v2.js` into the existing theme integration. Keep its
calibration, artwork/frame/size rendering, cart drawer, spinner and cart refresh/open code.
Remove the old name/email gate and social permission checkbox. Use this adapter in place of
the identity-gated archive call; retain existing branded Save/Share output.

Create `SportsCaveWallPreviewCRM(hooks)` with these callbacks:

- `metadata()`: existing verified product/variant fields, frame/size/unit/product URL;
  optional Liquid-provided logged-in customer email/name/ID with `identity_source=logged_in`;
  UTM/referrer/landing fields. Never invent identity or subscribe consent.
- `compositeBlob(branded)`: existing `buildCompositeCanvas(branded)` then canvas JPEG
  re-encoding. `false` is the clean finished composite, `true` retains the existing watermark.
- `showConfirm(visible)`: small dark/gold **Looks right? / CONFIRM PLACEMENT** control anchored
  inside the visualizer near the rendered frame's bottom-right. Show immediately after drag end.
- `showActions(visible)`: Save Your Preview / Share Preview / Email My Preview after confirmation.
  Keep the existing sticky Add To Cart available even during upload/failure.
- `archiveStatus(text)`: small truthful status; never call queued email “sent”.
- `downloadBlob(blob)`: existing branded download behavior.

Call `newWallPhoto()` only when selecting a completely new wall photo. Call
`placementChanged()` on drag end/frame/size changes; this does not upload. Bind Confirm to
`confirm()`, Save to `download()`, Share to `share()`. Email uses the existing logged-in email
or reveals one email field; bind to `emailPreview(email)`. Augment the existing cart line's
properties through `cartProperties(existingProperties)` without replacing variant/cart behavior;
call `addedToCart()` after the existing successful add. Keep the visualizer below the cart drawer.
Do not upload on moves/drags. Do not upload raw wall photos. No advertising pixel is fired by
this adapter; DOM events contain IDs only, and any downstream advertising tracking still needs consent.

## API contract

`POST /api/wall-previews` accepts bounded binary JPEG/PNG + query metadata (same transport as
the existing theme). V2 requires random UUID v4 `client_preview_id` and `session_id`,
`product_url` on the allowlisted shop `/products/` route; other product/frame/size fields optional.
Identity is optional. Reconfirmation reuses the client ID and session. `preview_id` is optional
and must match. Response includes `ok`, `preview_id`, `preview_token`, `version`, `duplicate`,
and `share_url`. The random session doubles as a first-party write capability: keep it private,
send it only to the private first-party backend, never to dataLayer, third-party analytics, URLs, logs or share payloads. Preview/customer IDs confer no auth.
Legacy email/name query requests remain accepted during rollout, with their original permission semantics.

`POST /api/wall-previews/{preview_id}/events` takes `{event_name,event_id}` and
`X-Wall-Preview-Token`. Public events: Downloaded, Shared, AddedToCart. Started, Confirmed and
EmailCaptured are emitted by authoritative server actions; Purchased only by verified Shopify ingestion.
All names use the `WallPreview` prefix. Random UUID `event_id` deduplicates retries. Arbitrary metadata rejected.

`POST /api/wall-previews/{preview_id}/email` takes `{email}` and the same capability header.
Optional `product_url`/`requested_at` are accepted for rollout but never override canonical data/time.
Response reports durable `email_status=queued|processing|sent|failed|uncertain`, never fake sent success.
One request/recipient per preview prevents tap storms. Reserved `.invalid/.test/.example` addresses
are rejected before queue insertion/transport (safe production endpoint validation).

`GET /wall-preview/{unguessable-token}` and `/image`: minimal public finished preview/product CTA.
90-day expiry, noindex/nofollow/noarchive, no-referrer, no-store; admin can revoke in Details.
No customer/session/Dropbox/internal metadata is rendered. No public Dropbox sharing links.

## Delivery, consent and correlation

The existing `sports_cave_worker.py` supervisor runs `crm_worker.py`; its 30-second cycle
claims one durable Wall Preview email job with `SKIP LOCKED`. Browser closure cannot stop it.
Requested emails use existing Resend credentials/sender/adapter and do not require marketing opt-in.
Flow: **See It On Your Wall Follow Up**. +4h/+24h jobs check existing marketing gates, fresh exact
Shopify email/consent, native unsubscribe URL, local/provider suppression and CRM smart sending.
Unknown eligibility fails closed. No subscription/consent writes occur. Any newer customer order
conservatively suppresses reminders. Correlated purchase suppresses queued follow-ups immediately.
Timeout/interrupted submission becomes `uncertain` and is never blindly resent. Known 429 rejection
has bounded retry; safe structured logs contain only preview/job IDs and outcome categories.

The existing HMAC-verified `/webhooks/shopify/orders-paid` path correlates canonical preview/client
properties with the purchased variant **before** order-receipt deduplication. It never alters Edition
Ops allocation. Order webhook retries repair correlation idempotently. Existing registration is reused.

## Storage and deployment

Exact root: `/Sportscave Team Folder/03_ASSETS/11 Wall Preview Inbox`.
Anonymous previews: `Anonymous/<client-uuid>.jpg`. Initially identified previews retain per-email
folders. Later email capture updates CRM identity without moving the existing archive. Reconfirmation
replaces the same stable file, increments version only when image/product data changes. Re-encoding
removes EXIF/GPS and bounds the image to 2400px. A new wall photo uses a new client ID.

Migration `20261005_wall_preview_crm_v2.sql` retains existing rows, extends the existing identity enum,
keeps the legacy byte uniqueness index intact for rolling-deploy compatibility, and adds client/share
indexes plus server-only events and email jobs (RLS, no anon/authenticated grants).
Startup uses the existing reviewed-SHA migration runner; no Render service topology change.
V2 stores the actual clean composite hash in `archive_sha256`; its legacy `image_sha256` field is
an owner-scoped fingerprint so two anonymous clients can independently archive identical images.
