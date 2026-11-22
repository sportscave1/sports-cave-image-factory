# Instagram advertising comments — 22 November 2026

The old reader expanded ordinary media metadata and comments together. A media
node failure discarded the post before its advertising comments edge was tried.

For creatives returned by the configured ad account, tied to the configured
Facebook Page and naming the exact connected Instagram actor, read
`ordered_comments` directly. This includes other media used by placement asset
customization. Fall back to `comments` for Story/carousel child media, retaining
the chosen edge for pagination. Never transfer a cursor between edges.

Reply/moderation requests carry the ad ID as untrusted context. Before acting,
re-read the ad and verify its account, Page, Instagram actor and effective media
ID, then verify comment membership. Writes use the advertising User token and
are never retried. Creatives without an explicit matching actor retain the
existing media-owner verification. Organic posts and messages are unchanged.

Failures retain the existing notice and log only media/ad IDs and sanitized
provider diagnostics, allowing exact production failures to be investigated
without logging credentials or customer comment text.

Reference: https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-media/comments

Offline validation: 100 tests passed, 8 legacy opt-in database tests skipped,
68 subtests passed; Render topology validator passed. No real replies,
moderation actions, ad changes or customer automations were sent during tests.
Live availability must be verified after deployment; offline tests do not prove
that Meta grants access to each production media object.
