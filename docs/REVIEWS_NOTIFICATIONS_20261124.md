# Reviews arrival notifications

User authorised this focused change and Git/Render production release on 24 November 2026.

Reviews uses the existing Orders sidebar badge styling and global 30-second notification schedule, with no separate polling timer, media queries, provider calls or customer emails. The bell combines Orders actions and unread Reviews, with separate entries. Hidden tabs retain the existing suspend behaviour.

Unread receipts belong to each signed-in account. New database inserts receive a server arrival timestamp, including native submissions, CSV imports and incoming Shop reviews. Updates and duplicate imports do not restamp the arrival. Archived/spam reviews are excluded. All pre-existing rows retain a null arrival timestamp and start seen.

Opening Overview acknowledges only the actual successfully loaded page (maximum 25 rows). Detail clicks are unnecessary; filters and pagination leave undisplayed reviews unread. The acknowledgement runs in the existing bounded read pool and sends its count directly to the shared header. Failed/stale loads do not acknowledge reviews. A generation guard prevents an earlier in-flight status response from restoring a cleared badge. New arrivals refresh an already open Overview once per new arrival timestamp. The private Overview sorts by arrival, so newly imported historical reviews remain discoverable; public review ordering is unchanged.

Schema: migration `supabase/migrations/20261124051302_review_notifications.sql`. `sc_review_seen` is server-only, RLS enabled, with all PUBLIC/anon/authenticated privileges revoked. The timestamp trigger uses invoker privileges and an empty search path. Supabase security advisory reports no policies for this intentionally private table; public access remains denied.

Validation:

- 65 focused tests passed for receipt semantics, browser behaviour, Orders recovery and Shop ingestion; the receipt/API tests were expanded afterward and passed again.
- All three Reviews browser scenarios passed: combined badge/clear, failure and delayed response handling, and Reviews-only permissions using the shared poll and refreshing the open list.
- 48 review/API/account/widget/SQL tests passed, one optional SQL test skipped; native deferred upload suite passed separately (3 tests) on a fresh disposable database. Its first combined-suite attempt encountered an existing queued-media fixture collision; the isolated rerun passed. No production uploads or emails were used.
- Navigation Node regression and Python compilation passed. Render topology validator passed. No infrastructure manifest or Shopify/theme changes.
- Production migration verified: 209 published reviews preserved, zero historical arrivals, zero receipts, one enabled arrival trigger, private table RLS enabled and anon/authenticated SELECT denied.

Release acceptance: verify existing Render services are Live at the release commit and the deployed notification endpoint denies unauthenticated reads. No fake public review is needed for release verification. A future genuine submission will populate the production badge; synthetic receipt and browser tests cover its increase and automatic clear.
