# Visible comment feed — 22 November 2026

Task `20261122-614a3f07`, owner `codex/social-comments-scroll-20261122-01a20091`.
The user authorized GitHub/Render release of this change.

## Behavior

- Comment cards show the author returned by Meta, date in Sydney time, complete
  text, available attachment, post context and visible action buttons. There are
  no comment expanders, side detail pane or More dropdown.
- Results combine live ads (`effective_status=ACTIVE`) and organic posts from
  Facebook/Instagram, sorted newest first among the loaded results. Rejected
  and paused ads remain excluded. No claim is made to have scanned all history.
- The first render checks one organic batch per channel. A small inline
  IntersectionObserver requests another bounded batch near the bottom. It
  waits for further downward scrolling before requesting again, deduplicates
  request tokens and disconnects on cleanup. It pauses when hidden or when
  errors are present. A normal Load older comments button remains as fallback.
- Up to 40 more already-loaded cards are displayed per request; when necessary,
  the backend reads the next organic/ad/comment pages. Earlier cached pages are
  retained. Only one reply editor is created, and deletion requires an explicit
  inline confirmation. No framework, iframe, external script or polling is added.
- Facebook comments request newest-first ordering, attachment, current like
  status and hidden status. Instagram comments also request hidden status.
  Boosted-post merging fills omitted text/attachment fields without discarding
  ad context, cross-placement comments or the correct pagination edge.
- If Meta omits the text/name, the card states that rather than inventing a
  customer name or showing a misleading `[Comment]` placeholder. Attachment
  images are escaped, HTTPS only and lazy-loaded in the browser.

## Mutations and verification limits

Reply, hide/unhide and delete retain account/post/comment membership checks and
the verified advertising token context. Facebook Like toggles to Unlike when
Meta returns `user_likes`. Reply success requires a returned reply ID; other
mutations require `success=true` (or boolean true). Ambiguous results are not
reported as success and writes are never retried automatically.

Instagram comment likes remain an explicit **Like in Instagram** link. The
existing integration does not expose API liking; no additional permission or
credential was silently requested. Official IG Comment reference lists replies
and hide/delete, with no supported likes edge for this integration:
https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-comment

Synthetic Streamlit interactions cover the visible cards, single reply editor,
deletion confirmation, paging and cached edits. A Node unit test mocks viewport
events to verify observer cleanup, no repeated loading and hidden/error pauses.
Provider contract tests check ownership, token routing, one write per action
and negative/absent mutation acknowledgements. Local ledger tests use PGlite.
No real customer message, comment, like or deletion is sent during testing.

Validation: 130 focused tests and 68 subtests passed, with eight legacy opt-in
database skips. Render topology and `git diff --check` passed.

Edge visual verification is unavailable because its computer-use helper reports
an existing active request. Local server previews remain disabled by AGENTS.md.
Deployment health and logs are verified separately after Render reports LIVE.
