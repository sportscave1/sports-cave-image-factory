# Social Media community replacement — local implementation

Studio task: 20261122-c8142d5f. Owner: codex/social-rebuild-20261122-01a20091.

The existing Social Media destination now contains Inbox, Comments, Collaborations
and Connection. Its Instagram icon and original @sportscaveshop link remain.
The content creator, planner/tasks, playbook, tracking forms, AI Reels renderer
and its paste component have been removed. Old reel bookmarks and staff
permissions resolve to Social Media. Wall Preview Inbox and its SEO placement
are preserved. Historical activity reports retain their aggregate shape, but
no longer query or initialize the old social task tables.

## Runtime setup

This work is uncommitted, local and not deployed. No production tokens were read,
customer data fetched, real messages sent or storage deleted.

Use Facebook Login with an existing Facebook Page and its linked Instagram
professional account. The transport uses the existing Meta API version setting,
defaulting to v26.0. This does not create a Meta app or change Render services.

Server configuration:

- META_FACEBOOK_PAGE_ID (existing META_PAGE_ID/FACEBOOK_PAGE_ID aliases work).
- META_INSTAGRAM_ACTOR_ID (existing account ID aliases work).
- META_PAGE_ACCESS_TOKEN: a Page token for the selected Page.
- META_SOCIAL_DISCOVERY_TOKEN: separate Facebook User token for Business Discovery.
- META_API_VERSION, optional.
- META_SOCIAL_WRITES_ENABLED=0 by default. Set to 1 only in an authorized environment.
- META_SOCIAL_AUTOMATION_ENABLED=0 by default. Automatic invitations also need the
  saved administrator opt-in on Collaborations.

Required permissions depend on the operation: pages_messaging,
pages_manage_metadata, pages_read_engagement, pages_read_user_content,
pages_manage_engagement, instagram_basic, instagram_manage_messages and
instagram_manage_comments. Business Discovery requires instagram_basic and
pages_read_engagement on the Facebook User token; a Business Manager assigned
role can additionally require ads_read or ads_management. Meta business
verification, appropriate Page tasks, App Review/advanced access and conversation
routing must be satisfied for the real connection. Existing advertising
permissions alone do not establish inbox access.

Run scripts/social_community_schema.sql explicitly against an isolated test DB
first. It creates two small tables with RLS and denies browser-role access. The
existing server PostgreSQL role must have access. This file is deliberately
outside startup migrations; production provisioning belongs to an approved
release. No new Supabase browser SDK or service key is introduced.

## Behavior and practical limits

Inbox reads Meta directly and refreshes every 60 seconds while open. Conversations
and messages have cursor pagination. Text replies use the verified conversation
recipient. Attachments are indicated, with Business Suite as the viewing fallback.
Only the standard 24-hour inbound reply window is implemented. Expanded ad-entry
or Human Agent windows are not used. Meta can further restrict sending based on
conversation routing or app permissions.

Comments show recent activity across the first ten posts in the selected page,
up to thirty comments each, with separate post/comment pagination. This is polling
while the page is open, not a complete webhook notification archive. Actions
revalidate ownership before reply, delete, hide or unhide. Facebook comment
like/unlike is implemented. Instagram comment likes are not enabled in this
integration; the original-post link is the fallback. Instagram top-level comments
are supported; this version does not provide a separate nested reply browser.
This is a focused community workspace, not full Business Suite feature parity.

Creator discovery uses usernames on Sports Cave's recent Instagram comments,
plus optional manually supplied usernames, to fetch professional account profiles
through Business Discovery. It does not scrape personal accounts or provide
unrestricted global account search. Fit uses 1,000–50,000 followers and sports
keywords in bios/captions. Engagement uses up to twelve returned posts and is
unknown when no data is returned. Audience location, authenticity, interest in a
collaboration and willingness to own an Edition still need human assessment.

Discovery saves a ranked prospect and an editable invitation. Repeat discovery
updates measurements without overwriting the saved invitation or pipeline state.
The pipeline supports shortlisting, agreed and declined statuses. Sending requires
an eligible inbound Instagram conversation with a verified matching username.
Replies appear in the same API Inbox. There is no unsolicited automated cold DM.

Opted-in automation runs every five minutes while Collaborations is open.
It assesses at most thirty usernames and checks the top twenty pending prospects,
with at most five invitations per run. It is not an always-running background
service. Every send claims a durable ledger row first; another process cannot
claim the same creator. Sent creators never receive a repeat invitation.
Interrupted or ambiguous sends remain sending/unknown and require operational
reconciliation against the Inbox before an administrator changes that ledger
state. Never reset these states automatically or retry an ambiguous request.

## Retired data and storage cleanup

Keep the historical migration file for audit history. run_migrations.migration_files
excludes it, and the retired store no longer initializes it, so removed tables
will not be recreated by this application.

scripts/retire_social_workspace.py defaults to a read-only inventory and accepts
only an explicitly selected loopback test PostgreSQL URL. It never discovers
production credentials or loads .env. Set SOCIAL_CLEANUP_TEST_DSN to a disposable
local database and run:

    python scripts/retire_social_workspace.py
    python scripts/retire_social_workspace.py --apply

It inventories row counts and generated destination paths, then drops only the
nine retired social planner/content tables in dependency order, without CASCADE.
It also removes prompt templates with exact module social_reels and their
associated prompt versions. Unexpected shared foreign keys stop the transaction.
The new collaboration tables and other OS data remain intact. Dropping the
retired tables releases their relation storage; prompt-row deletion may leave
reusable space until normal database maintenance.

Production retirement needs separate authorization and an operator-reviewed
execution of those exact operations against the intended database after the
replacement release is ready. The local cleanup CLI deliberately cannot target
production. Review the generated destination manifest before deleting external
assets. Old content output may be in Dropbox under 04_OUTPUT/social-media;
AI Reels local packs use output/runs/social-media-reels-studio-<token>.
Those directories can contain independently valuable work. No shared Dropbox
folder, Supabase Storage bucket, general output/runs directory, task belonging
to another OS module, historical activity audit or shared prompt library is
deleted by this change. External generated files have not been removed.

Before an authorized release, inventory/approve the exact assets to retire,
provision the new tables, verify Meta permissions with test accounts, then release
the tested application and retire the old data. Validate the existing canonical
Render topology; do not create another primary application.

## Validation

Focused API and Streamlit AppTest contracts use synthetic profiles/messages and
mock transports. Database contracts run actual SQL on disposable in-memory
PostgreSQL (PGlite), including RLS/grants, upserts, claims, terminal send states,
and cleanup preserving unrelated data. No app server or live preview is started.

Final focused run: 115 passed, 8 skipped, 169 subtests passed. The eight skips
are legacy Wall Preview tests requiring their separate opt-in database fixture.
The new collaboration database tests all ran against PGlite. The focused command
covered test_meta_social, test_social_community_store, test_social_wall_inbox,
test_social_media_reporting, test_sports_categories,
test_ads_instant_experience_footer, test_workspace_route_isolation,
test_order_source_attribution and the affected account prompt-permission test.
Render topology validation passed; its configuration was not changed.

The broader physical-frame tests contain three existing Ads Refresh failure
subcases across two tests. The exact unchanged HEAD tests reproduce those
failures with the unchanged Ads Refresh implementation. They are outside this
replacement and are not repaired or hidden.

## Reference documentation

- [Meta Page Conversations API](https://developers.facebook.com/docs/graph-api/reference/page/conversations/)
- [Meta Instagram messaging changelog and reply windows](https://developers.facebook.com/documentation/business-messaging/instagram-messaging/changelog/)
- [Meta IG User and Business Discovery](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/v21.0/)
- [Meta Facebook object likes](https://developers.facebook.com/docs/graph-api/reference/object/likes/)
- [Supabase API security](https://supabase.com/docs/guides/api/securing-your-api)
