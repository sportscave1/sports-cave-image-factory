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

Edge follow-up: after the owner enabled Instagram connected-tools message
access, the unified inbox loaded 60 Facebook/Instagram conversations without the
previous rejection. No token replacement or new permission grant was performed
by the agent. The advertising root multi-ID expansion returned error 100 in
production; replaced it with direct, ownership-checked reads for at most five
ads per page. An unavailable ad post no longer discards readable posts.

The direct Facebook advertising reads exposed recent November 2026 customer
comments in Edge. Instagram advertising media needs the existing Facebook
User/Business token with advertising access, as specified in Meta's IG Media
reference, rather than the Page messaging token. Updated this read path and
added a verified-owner read fallback before Instagram moderation chooses its
credential. A moderation write is issued once; no write is automatically retried.
Reference: https://developers.facebook.com/documentation/instagram-platform/reference/instagram-media
Focused validation: 86 passed, 8 legacy database opt-in skips, 68 subtests.

Final bounded ad-read correction omits caption/permalink metadata that Meta
does not support on carousel child media, and excludes advertising creatives
explicitly assigned to a different Instagram actor before making media reads.
Remaining provider failures retain safe numeric/permission diagnostics rather
than only an unreadable-post count. No raw provider messages or secrets are
returned. Focused validation: 87 passed, 8 skips, 68 subtests.

Edge verified the remaining Instagram advertising failures as Meta 100/33,
without affecting the restored inbox or regular comments. Added two read-only
diagnostic probes on that failure path to distinguish missing User-token grants
from inability to read the linked account or unavailable individual media. These
probes expose permission names/status only and never change Meta access.
Focused validation: 89 passed, 8 legacy database opt-in skips, 68 subtests.

`python -m pytest tests/test_meta_social.py tests/test_social_community_feed.py
tests/test_social_community_live_regressions.py tests/test_social_community_store.py
tests/test_social_wall_inbox.py tests/test_social_media_reporting.py
tests/test_workspace_route_isolation.py -q --tb=short --disable-warnings`

Result: 78 passed, 8 legacy database opt-in skips, 68 subtests passed.
Topology validator and whitespace checks passed. No Blueprint sync or Render
service/configuration changes are part of this repair.
