# Wall Inbox image notifications

Implemented in the existing notification bell, notification centre, sidebar badge helper, authenticated top-bar endpoint, and 30-second notification heartbeat. No separate menu, notification framework, polling timer, dependency, or database migration was added.

## Behavior

New captures from both the current and legacy upload paths record a `wall_inbox_image_received` event in the existing `audit_logs` table. The event commits in the same transaction as the capture. Existing records and historical upload retries do not generate events. Repeated new-capture requests and concurrent notification writes are deduplicated by preview identity under a transaction lock.

The notification centre shows “New image received in Wall Inbox.” and links directly to the corresponding preview, even if it is outside the current filters or page. The sidebar displays the complete unread count; the centre loads at most ten Wall Inbox items per refresh alongside existing notifications.

Opening the page, polling, selecting cards, or loading a thumbnail does not mark an image seen. The full-image viewer acknowledges successful image loading, after which the server stores a per-user receipt in the existing `app_sync_state` table. Only that image is cleared for that user. Receipts survive browser refreshes, logout, and device changes. The existing shell refreshes immediately after the receipt is committed. Failed image loads stay unread; a receipt write failure leaves the notification available for retry.

The existing route permissions and private-image visibility rules apply. Deleted or deletion-pending previews are excluded. No Dropbox requests are needed for notification polling. Pending archive images can be viewed from their already-persisted job payload; a later archive failure does not fabricate a second arrival event.

## Files changed for this feature

- `wall_preview_notifications.py`: transactional event creation, unread query, per-user seen receipts.
- `wall_preview_crm_store.py`, `wall_preview_store.py`: new-capture hooks.
- `top_bar.py`, `top_bar_api.py`, `components/sports_cave_top_bar/index.html`: permission-scoped configuration, existing endpoint response, heartbeat, sidebar badge and notification links.
- `wall_preview_inbox.py`, `components/wall_preview_gallery/index.html`: direct-image opening and successful-load acknowledgement.
- `tests/test_wall_preview_notifications.py`, `tests/wall_inbox_notifications_ui.cjs`: persistence, deduplication, permissions, failure cases, shared shell and responsive acceptance tests.
- `tests/social_inbox_preview_app.py`, `tests/test_wall_preview_feature.py`: synthetic UI and existing notification-table fixtures.
- `tests/test_email_notification_component.cjs`, `tests/test_order_action_notifications.py`, `tests/test_top_bar.py`: shared heartbeat assertions and isolation of the existing Orders cache; removed an obsolete sidebar-scroll assertion.
- This document.

Existing bulk-delete and unpublished Shopify theme work in the workspace was preserved.

## Verification and deployment

176 backend/regression tests passed, along with the shared badge and navigation JavaScript checks, Python compilation, JavaScript syntax, whitespace checks, and Render topology validation.

Backend coverage includes capture/event atomicity, both ingest paths, historical exclusion, deduplication, concurrent receipts, three unread becoming two, independent users, fresh-session persistence, visibility permissions, pagination-sized counts, deleted previews, and shared API failure isolation. Browser checks cover the real 30-second heartbeat, notification deep links, immediate 3 → 2 → 1 → 0 clearing, zero badge removal, unchanged Orders badge, failed image loading, and desktop/tablet/mobile sizes. Existing inbox browser regressions also cover 14 viewport sizes and the bulk-delete workflow.

Deploy the updated application code through the normal existing service release process. No new service, schema migration, environment variable, or data backfill is needed. The existing operational tables and indexes used by Email/Orders must already be present. No production customer data was changed and no deployment was performed during development.
