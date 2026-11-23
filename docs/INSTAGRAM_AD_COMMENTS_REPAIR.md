# Instagram advertising comments — 22 November 2026

## Final scope: live ads only

The three investigated ads all return `effective_status=DISAPPROVED`, despite
their configured `status=ACTIVE`. Their media failures do not establish a
connection failure for live ads. At the user's direction, the advertising
comment feed now requests only effective `ACTIVE` ads and defensively excludes
other returned statuses. Organic post and inbox reads are unchanged.

The new Sports Cave Community login configuration (`2009683517103204`) issued
a valid Facebook User token with all five requested permissions, including
`instagram_manage_comments`. It can read the linked account's published media
and comments, but the three disapproved media still reject both comment edges.
No community token was saved to Render: the guarded environment update stopped
at service inspection before any write. Existing ads, Page and CRM credentials
were not replaced. Further token changes are unnecessary for these rejected ads
and have been stopped as requested. No customer reply or moderation was sent.

The old reader expanded ordinary media metadata and comments together. A media
node failure discarded the post before its advertising comments edge was tried.

For creatives returned by the configured ad account, tied to the configured
Facebook Page and naming the exact connected Instagram actor, read
`ordered_comments` directly. This includes other media used by placement asset
customization. Fall back to `comments` for Story/carousel child media, retaining
the chosen edge for pagination. Never transfer a cursor between edges. If the
advertising User token cannot read an ad's comments, try the linked Page token;
retain that token choice for pagination and reverified moderation. For boosted
posts, also try the original `source_instagram_media_id` from the verified
creative when the effective ad media is unavailable.

Reply/moderation requests carry the ad ID as untrusted context. Before acting,
re-read the ad and verify its account, Page, Instagram actor and effective media
ID, then verify comment membership. Writes use the advertising User token and
are never retried. Creatives without an explicit matching actor retain the
existing media-owner verification. Organic posts and messages are unchanged.

Failures retain the existing notice and log only media/ad IDs and sanitized
provider diagnostics, allowing exact production failures to be investigated
without logging credentials or customer comment text.

Reference: https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-media/comments

Offline validation: 105 tests passed, 8 legacy opt-in database tests skipped,
68 subtests passed; Render topology validator passed. No real replies,
moderation actions, ad changes or customer automations were sent during tests.
Live availability must be verified after deployment; offline tests do not prove
that Meta grants access to each production media object.

## Production token audit

Read-only `debug_token` checks on 22 November confirmed:

- Both deployed tokens belong to Sports Cave OS, app `1490062765695248`.
- `META_ACCESS_TOKEN` is a valid `SYSTEM_USER` token with expiry `0`.
- `META_PAGE_ACCESS_TOKEN` is a valid `PAGE` token for `116001074739884`,
  also with expiry `0`.
- Both include `instagram_basic`, `instagram_manage_comments`,
  `instagram_manage_messages`, `pages_read_engagement`, `ads_read` and
  `ads_management`. Returned granular scopes contain no target restrictions.
- Business Settings shows the system user has full access to the app, Page
  and Instagram account. No existing token was revoked or replaced.

The Facebook Login ad-comment API documents a Facebook User token. A separate
`META_SOCIAL_ACCESS_TOKEN` can now be configured for the community module;
absence preserves its existing token fallback. This key is not consumed by
ad posting, review sync, reporting or CRM, which retain `META_ACCESS_TOKEN`.
Page messaging retains `META_PAGE_ACCESS_TOKEN`. Isolation is tested offline.

The separate User-token route remains a proposed recovery until the three
production media have been read successfully. Valid scopes alone do not prove
media availability. No new credential value is stored in Git or this report.
