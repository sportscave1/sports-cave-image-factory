# Phase 3: professional inbox experience

25 November 2026. Implemented and tested **locally**. This candidate includes
the uncommitted Phase 2 speed improvements and released Phase 1 recovery
(`58d8446f42f831cb792c84644575bb4cb2d45df6`). Nothing in Phases 2 or 3 has been
committed, pushed, deployed or activated in production. Developer Studio task:
`20261125-email-polish`, owner `codex-email-polish-20261125`.

## Behavior

- Connection feedback distinguishes Connected, Syncing, Reconnecting, Needs
  attention and Not connected. Normal queued reads appear as syncing. The last
  successful sync remains visible; transient failures show the automatic retry
  countdown using server-provided relative delays. Credential/configuration/TLS
  problems retain the existing manual recovery path. The countdown adds no
  mailbox calls and does not replay mail actions.
- A single polite live region announces status changes without announcing each
  countdown tick. Loading messages have a status label and decorative skeleton;
  animation respects reduced-motion preferences. Text and icon-only controls
  have accessible labels. Selected conversation buttons use `aria-current`.
- Up/Down and Home/End move keyboard focus through conversations without opening
  or modifying mail. Enter opens the focused conversation and moves focus to its
  heading; focus survives the later arrival of the message body. Escape returns
  to the selected row and slash focuses search. Text fields, editors, dialogs
  and existing menus retain their keyboard controls.
- Background refreshes preserve focus, the draft subject caret, open draft
  recovery disclosures and sent receipt disclosures. An inactive inbox does not
  claim focus from another page or control. Temporary Working feedback clears
  when its operation is acknowledged, even when the status markup is unchanged.
- At phone widths the reader shows Back, Reply, Reply all, Forward and More.
  Archive, move, copy, flag, read/unread, junk and trash remain in More. Status
  text wraps and the reader stays inside the component viewport.
- The companion owner panel formats the authoritative outbox outcome. An
  accepted automatic reply says **✓ Companion sent**, without repeating its
  older queued explanation. Queued, sending, uncertain delivery, rejected and
  review outcomes remain distinct. An uncertain delivery warns against
  resending. A manually answered request does not receive a Companion sent tick.

The public My Collection certificate reply, framing sentence, review request,
saved Nathan signature, durable send protection, existing customer automation
settings and Phase 1/2 recovery behavior remain unchanged. Phase 2 source was
compared with its saved candidate: all twelve files outside the intentionally
extended component and release-gate lists have identical normalized text (three
tracked files differ only in CRLF/LF bytes after patch transfer).

## Validation and limits

All evidence below is in `C:/Dev/SportsCaveWorktrees/.studio/runtime/`.

| Check | Result | Evidence |
| --- | --- | --- |
| Release-gate EMAIL list plus reply prompts and release-gate harness | 345 passed, 17 subtests passed, zero skipped; 46.65 s | `20261125-email-polish-required.log` |
| Broader inbox/support email/certificate Python suites | 636 passed, 63 subtests passed; 45 opt-in disposable/native SQL tests skipped; 77.41 s | `20261125-email-polish-inbox-broad.log` |
| Focused component, autosave, reader, sent attribution, reconnect, prompts, timing and navigation Node suites | 10 suites passed, zero skipped | `20261125-email-polish-node-focused.log` |
| Wider Node audit | 18 passed, 2 failed; both failures reproduced against released Phase 1 source | `20261125-email-polish-node.log`, `20261125-email-polish-baseline/baseline.log` |
| Wider filename sweep including campaign editor and wall preview | 716 passed, 76 subtests passed; 7 failures outside inbox scope, 79 skipped | `20261125-email-polish-broad.log` |
| Render topology and whitespace | Passed; no infrastructure changes | Studio verification / `git diff --check` |

The two wider Node failures are old shared-header fixtures: an obsolete
`ORDER_STATUS_REFRESH_MS = 60000` assertion and a sliced VM fixture missing
`parentWindow`. The wider Python failures are campaign navigation's invalid
fixture UUID, campaign preview/placeholder/catalogue contract expectations and
wall-preview permission display. These modules and tests were not changed by
Phase 3; they remain unresolved outside this inbox change. This report does not
claim that the entire repository passes or that the full production release
gate has run for this uncommitted candidate.

Browser checks used the **real component** in the allowlisted static workbench
`tests/profile_email_phase3_browser.py`. Its messages, replies and status models
are synthetic. The host acknowledges selections after 80 ms, has no mailbox or
SMTP API and cannot send or modify live mail. No application preview or
production credentials/customer records were used. The loopback helper and
temporary browser tab were closed after testing; the viewport override was reset.

Observed browser checks: arrows/Home/End did not change the selected message or
emit mail actions; Enter retained heading focus after body arrival; Escape
restored the selected row; slash entered search; typing r/f stayed in search;
background refresh retained row focus, open draft controls and draft subject
caret (position 16 in `Draft focus check`). A confirmed fixture reply updated
both row and message ticks without changing the mailbox revision. At 375 CSS
pixels, client and scroll width were both 375 and all secondary actions remained
available in More. Connected/syncing/reconnecting/attention and loading states
were inspected. No browser errors were observed. Native screen-reader speech
and real-device/production latency were not measured.

Review images: `20261125-email-polish-desktop.jpg` and
`20261125-email-polish-mobile.jpg`. They show synthetic data, not a live send.

## Release boundary

Retain both task worktrees for review. Obtain explicit authorization to commit
and push Phases 2 and 3, run the complete release gate for the committed revision,
then release through the canonical `sports-cave-os` service. No duplicate primary
service or Blueprint synchronization is required. After an authorized release,
verify the deployed revision and read-only health/worker evidence; do not resend
the already answered customer request as a test.
