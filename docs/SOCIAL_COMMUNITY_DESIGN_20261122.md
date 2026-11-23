# Social Media styling and reliability — 22 November 2026

Task: `20261122-5ec2485e`, owner `codex/social-media-design-20261122-01a20091`.
Developed in its assigned worktree, based on current main `544d0c85`.

## Presentation

All four tabs share a scoped white, black and gold presentation: compact controls,
fine borders, consistent table rows, restrained status badges and a right detail
panel. The header retains all five existing social profile links. Facebook and
Instagram remain together. No shared app navigation or other page is restyled.

- Inbox: combined table, search/unread filter, dated message bubbles, detail
  header and reply composer. Closed reply windows still explain the restriction.
- Comments: dated expanding summaries on the left, selected comment's context,
  reply and moderation on the right. Only one reply form is constructed, even
  with multiple rows open. Secondary actions are grouped under More.
- Collaborations: creator/stage/next-action table, profile details, invitation
  editor and recorded timestamps. Empty states explain the next step. The UI
  uses actual stored information; no invented creators, editions or deliveries.
- Connection: explicit read-only checks, feature results, account detail card
  and concise troubleshooting. Opening this tab does not issue provider calls.

The implementation uses native controls and a small local stylesheet. It adds
no browser JavaScript framework, iframe, remote font, image asset or dependency.
The supplied reference guides the layout and styling; a pixel-exact browser
comparison has not been completed.

## Performance and reliability

- Newest pages retain the existing 60-second cache/refresh. Loaded older pages
  use a five-minute session cache. Manual Refresh and successful writes invalidate
  reads. Failed reads cache for 15 seconds, preventing repeated requests while
  allowing recovery sooner than the history cache.
- Creator filters and invitation editing reuse a 30-second, account/user-scoped
  list cache; discovery, saving and Refresh invalidate it.
- A send verifies conversation ownership once, then checks fresh inbound
  messages and the recipient before its single POST. Writes are never retried.
- Malformed provider pages become recoverable section errors, not false empty
  results. Unexpected fragment errors are contained and logged by view/type only;
  raw provider data and credentials are not logged.
- Changing accounts/users clears cached diagnostics, selections, pagination and
  drafts. Access checks still run before cache reads and every provider request.
- Existing token selection and live-only ad filtering are preserved. No token,
  database schema, ad, CRM integration or customer automation was changed.

## Validation and release state

Synthetic Streamlit AppTest and mocked-provider checks cover all tabs, both
channels, public replies, moderation, unread filtering, history pagination,
history-cache expiry, failure recovery, user/draft isolation, malformed pages
and a three-request send budget (ownership GET, messages GET, one POST).
The collaboration ledger regression suite uses disposable local PGlite only.
No production credentials or customer data were used in development.

Result: 120 tests and 68 subtests passed; eight opt-in legacy database tests
skipped. The Render topology validator and `git diff --check` passed.

The full focused command is:

```
python -m pytest tests/test_instagram_ad_comments.py tests/test_meta_social.py tests/test_social_community_feed.py tests/test_social_community_live_regressions.py tests/test_social_community_store.py tests/test_social_community_design.py tests/test_social_wall_inbox.py tests/test_social_media_reporting.py tests/test_workspace_route_isolation.py -q --tb=short --disable-warnings
```

Local previews remain disabled by repository policy. Edge computer-use review is
also unavailable because the helper reports an existing active request. Browser
appearance and production latency must therefore not be described as verified.
The user authorized committing and publishing this styling release to GitHub and
the existing Render service on 22 November. Deployment IDs, live revision and
health results are recorded in the task's local release receipt after rollout.
No production service configuration or credentials are changed by this release.
