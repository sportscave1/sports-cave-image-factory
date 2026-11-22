# Social Media live failure repair

Task: `20261122-878e415f`.
Owner: `codex/social-live-repair-20261122-01a20091`.
Base: production main `f4c4820b`.

## Observed in Edge on 22 November 2026

The production Inbox loaded 30 Facebook conversations but rejected Instagram
conversation access. Comments initially showed “No comments yet” with more post
pages still available. Clicking Show more comments produced a Facebook API error.
No messages, likes, moderation actions or invitations were sent during inspection.

## Repairs

- Preserve Meta pagination cursors in full. The former 500-character truncation
  corrupts longer opaque cursors; a regression now checks a 1,442-character cursor.
  The live Facebook pagination error is consistent with this defect; its original
  provider message was discarded by the released error handler, so that cause
  cannot be established conclusively from the old alert alone.
- Scan up to four initial post batches per channel when recent posts have no
  comments. Keep reads cached and wait for explicit Search older posts before
  extending an unsuccessful search. Preserve comments when a later page fails.
- Distinguish an incomplete history search from an exhausted provider feed.
  Display posts checked, dates, merged channels and older-history controls.
- Include numeric Meta error/subcodes and allowlisted permission names without
  echoing raw provider text, credentials or URLs.
- Check Facebook messages, Facebook comments, Instagram messages and Instagram
  comments independently. A working Page identity no longer implies every feature
  works. Identity failures do not produce a false connection-success notice.
- Use the shared compact presentation, correct Streamlit ButtonGroup selectors,
  white secondary actions, gold selection and smaller spacing. Replace bot avatars
  with escaped message bubbles. Convert Messenger comment-referral system messages
  into short context plus a link. Explain closed response windows specifically.
- Keep the five original social profile URLs and existing scoped reply/moderation
  checks. Instagram likes still open the original post because the connected API
  does not provide that operation.

## External dependency and verification limits

Instagram conversation access was rejected by the existing production Meta
connection. No credentials were copied into development and no permission grants
were changed. The precise missing scope/account setting is not yet verified.
Meta documents a Page token from an administrator with the Messaging task,
`instagram_basic`, `instagram_manage_messages`, `pages_manage_metadata`, and
verified business ownership for this endpoint:
https://developers.facebook.com/docs/graph-api/reference/page/conversations/

Reauthorization, account messaging access or App Review may be needed. The code
cannot grant these permissions. Available Facebook and Instagram comment reads
remain independent from a failed Instagram messages check. Read checks do not
prove write permission. Meta's 24-hour standard response window still applies.

The revised layout has passed synthetic Streamlit interaction checks. It has not
yet been visually verified in production Edge. Repository Phase 1 rules disable
local app preview startup. The user explicitly authorized committing, pushing and deploying this repair on
22 November 2026 with YES PUSH LIVE GIT / RENDER THEN CHECK IT IN EDGE AND FIX
THE INSTAGRAM CONNECTION AS WELL. Production verification follows deployment.

## Validation

## Production follow-up

The first repair (`dc88249b`) reached live on all three active Render services.
Main and webhook health endpoints returned HTTP 200. Edge confirmed gold tab
selection, compact message bubbles, seven historical Facebook comments after
scanning 120 posts, and working expansion into Reply/Like/Hide controls. These
controls were inspected without sending or moderating real customer content.

The new capability checks verified the Sports Cave Page and @sportscaveshop,
Facebook messages, Facebook comments and Instagram comments. Instagram messages
returned Meta code 200/subcode 2534041. Business Suite independently showed
Instagram with a Confirm access badge and no available messages. The next repair
maps this subcode to the connected-tools message access setting explicitly.

The organic feed misses unpublished advertising posts. Added read-only discovery
from the configured advertising account's ad creative effective post IDs, with
the existing advertising token; Page-token reads and returned ownership checks
restrict exposed comments to the configured Page/Instagram account. Ads and
organic comments merge with scoped deduplication and independent pagination.
No ads are created or changed. Official creative field reference:
https://developers.facebook.com/documentation/ads-commerce/marketing-api/reference/ad-creative

Focused validation after this follow-up: 83 passed, 8 legacy database opt-in
skips, 68 subtests passed. This follow-up still requires live verification.

`python -m pytest tests/test_meta_social.py tests/test_social_community_feed.py
tests/test_social_community_live_regressions.py tests/test_social_community_store.py
tests/test_social_wall_inbox.py tests/test_social_media_reporting.py
tests/test_workspace_route_isolation.py -q --tb=short --disable-warnings`

Result: 78 passed, 8 legacy database opt-in skips, 68 subtests passed.
Topology validator and whitespace checks passed. No Blueprint sync or Render
service/configuration changes are part of this repair.
