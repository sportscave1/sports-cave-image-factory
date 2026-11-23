# Unified Social Media workspace refinement

Studio task: 20261122-62a4cf78.
Owner: codex/social-unified-ui-20261122-01a20091.
Started from production main 6996ce40. The user authorized committing, pushing
and deploying this revision with "PUSH LIVE" on 22 November 2026. The release
integrates the latest production main before final validation. No production
settings or schema changes are required.

## Changes

- Restored the exact original Instagram, Facebook, Pinterest, TikTok and YouTube
  shortcuts and SVG icons.
- Removed the custom community strapline/header markup. The heading is now a
  native compact Social Media title, which avoids the indented HTML rendering
  as a code block seen in the user's screenshot.
- Combined Facebook and Instagram conversations into one searchable table and
  reply pane. A Channel column identifies the source. Selection retains the
  platform and scoped ID, so equal provider IDs cannot route replies incorrectly.
- Combined comments into a searchable, dated list. Each comment is an expandable
  row with its author, source, preview, Sydney date and time. Reply and moderation
  forms render only while that row is open. Facebook like/unlike stays in-app;
  the existing Instagram-like fallback opens the original Instagram post.
- Added incremental comment/post pagination through Show more comments instead
  of the old post/comment selectors and thirty-notification cutoff. All loaded
  comments remain reachable. Initially renders forty lightweight row summaries.
- Reworked Collaborations into a compact searchable table, stage filter and
  selected-creator detail pane. No fictional editions, avatars, delivery dates
  or deliverables were added.
- Added a scoped white/gold layout and compact profile links based on the supplied
  reference. Existing global navigation, store, permissions and write checks remain.

## Performance and safety

The comment feed uses field expansion to load eight owned posts and their first
twenty comments per platform in one request each. Initial comment summaries
therefore need two provider reads instead of one post query and repeated
ownership/comment requests for each post. Older comment/post edges load only
when explicitly requested.

A sixty-second cache lives in the authenticated Streamlit session and is scoped
to OS user, Page, Instagram account and API version. It stores only returned
read data and sanitized errors, never tokens or client objects. Search, opening
rows and editing drafts reuse that cache. Refresh and successful actions
invalidate it. Each read still checks OS access, and every send/moderation action
uses the existing fresh provider ownership/recipient checks.

Partial failure on either channel shows a warning while retaining the other
channel. Dates are converted from provider timestamps to Australia/Sydney;
missing dates are explicitly unavailable. Failed sends preserve the draft.

No real messages, likes, replies, deletions, invitations or customer automations
were used for validation. No development server or live preview was started.
AppTest validates the actual Streamlit layout with synthetic providers.

## Verification

Focused tests cover the merged scoped identities, actual dataframe-selection
events, channel-correct inbox/comment replies, dates/DST, cache expiry and
invalidation, permission revocation, partial failures, older post/comment
pagination, all ninety synthetic comments reachable across display pages,
lazy closed-row forms, confirmation before delete, and preservation of failed
reply drafts. Existing API, collaboration ledger, Wall Preview, reporting and
route-isolation contracts run alongside these.

The new tracked-expander widget is supported by the installed Streamlit API.
AppTest's tree does not yet serialize its bool state, so tests send the actual
browser-equivalent widget state explicitly when opening a row.
