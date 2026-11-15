# Email performance pass — 27 September 2026

## Scope and checkout provenance

This pass changes only the Email frontend's redundant reading-pane work. No CSS,
markup templates, labels, routing, mailbox actions, SMTP, signatures, cache policy,
polling interval or persistence behaviour was changed by this pass.

The starting checkout included uncommitted connection-recovery work on `332acc9`.
That work was preserved. During validation, another process committed `ffbe809`
(`Harden live email connection recovery`), including this pass's edits to mail.js.
This task issued no commit, push, deployment or production commands. Consequently,
`git diff HEAD` is not a complete representation of this task's changes.

## Profile and findings

The existing cached controller path was already inexpensive: initial profiling
measured 0.02 ms for cached reopen and 0.12 ms to prepare its model. There were zero
provider calls, order queries or HTML conversions. A fixture with a deliberate
240 ms body delay and two 180 ms historical-header delays confirmed that these
costs occur only on uncached content/history, not cached reopen. These are simulated
delays, not measurements of VentraIP.

The frontend had two confirmed redundant DOM replacement paths:

1. After normal rendering, any disabled reading-pane button triggered a second
   forced paint. A legitimately unavailable action therefore caused unchanged
   updates to replace the reading pane, bypassing the existing render stamp.
2. An uncached selection rendered empty message content immediately before
   replacing it with the existing loading markup.

The counting DOM benchmark executes the production render/selection functions
against identical data. It deliberately includes a legitimately disabled button.

| Render-path measurement | Before | After |
|---|---:|---:|
| Initial reading-pane replacements | 2 | 1 |
| Replacements over 1,000 unchanged updates | 1,000 | 0 |
| Uncached selection replacements before response | 2 | 1 |
| Cached selection replacements | 1 | 1 |
| Selection acknowledgement repaint when needed | 1 | 1 |
| Mean adapter render CPU time | 0.0152 ms | 0.0102 ms |

The adapter does not measure real browser layout/paint time. The replacement counts
are the useful repeatable result; microsecond CPU differences are not a production
latency claim. No claim is made that every normal message previously repainted:
the extra repaint depended on the presence of a disabled action.

## Exact changes

- Track whether selection temporarily disabled reading controls. Only that state
  requires the acknowledgement repaint; permanent disabled buttons do not.
- Clear this state whenever the reading pane has already been rebuilt, preventing
  a second repaint after a normal model change.
- On an uncached selection, create the existing loader directly. Cached selection
  still paints its cached content immediately, with writes disabled until validated.

The final markup and styling are identical. No optimistic mailbox mutation or
early send completion was introduced. No control is enabled before acknowledgement.

## Controller benchmark

`python -m tests.profile_email_interactions` uses 75 fabricated messages, the current
workspace/controller and mocked provider, persistence and audit entry points.
Provider method timings exclude network latency. Values below include operation
and model preparation. Backend code was unchanged by this pass, so differences
between runs are measurement variation, not claimed improvements.

| Flow | Run 1 ms | Run 2 ms | Provider calls |
|---|---:|---:|---|
| Initial mailbox | 4.163 | 3.449 | folders + headers |
| Uncached open, including automatic read | 2.343 | 1.523 | body + flag |
| Cached open | 0.070 | 0.064 | none |
| Thread-history resolution | 0.250 | 0.213 | related headers for two folders |
| Reply composer | 0.489 | 0.444 | none |
| New Mail composer | 0.095 | 0.110 | none |
| Mark unread | 0.529 | 0.503 | flag |
| Mark read | 0.531 | 0.468 | flag |
| Flag | 0.488 | 0.466 | flag |
| Folder switch, uncached empty folder | 0.138 | 0.121 | headers |
| Cached folder switch | 0.100 | 0.077 | none |
| Submitted search | 1.755 | 1.528 | headers |
| Live check | 0.494 | 0.472 | live metadata |

Additional CPU measurements, 100 repetitions: header parsing 0.504 ms; sanitizing
100 short HTML paragraphs 0.880 ms; real provider MIME/BODYSTRUCTURE parsing through
a fake wire 14.022 ms (includes local connection setup/cleanup scaffolding); matching
1,000 fabricated orders 0.305 ms. Matching remains drawer-only; normal selections
performed zero order loads.

The JSON bridge payload is approximately 30.6 KB on initial list render, 31.5 KB
with selected content, 60.5 KB for Reply including inline logo, and 7.3 KB for an
empty folder. It is unchanged. A delta protocol would add risk without evidence
that these bounded payloads are the dominant delay.

## Preserved performance contracts

- No IMAP commands or Streamlit reruns were removed by this frontend-only fix.
  Cached reopen still performs zero provider calls. Unread open still fetches the
  missing body and performs the real flag update; read/unread/flag use one provider
  action each. Connections and their limits remain unchanged.
- Session MIME/render-ready body, thread membership and header caches remain as
  implemented. Cached reopen performs no parsing/sanitization or order reload.
- Attachments remain lazy. No email content or attachment persistence was added.
- Context menu and scrolling remain frontend-only; composer typing does not emit
  Python requests per keystroke. Existing editor wiring guards prevent duplicate
  listeners. Signature rebuilding remains explicit, not per keystroke.
- No additional cache or retained DOM representation was added. One boolean tracks
  temporary selection controls; avoiding DOM replacements reduces transient DOM
  work. Heap reduction was not measured or claimed.
- Prior recovery timing is preserved: 30-second shell heartbeat, 55-second local
  guard and 60-second coordinated IMAP snapshots. This pass does not change it.

## Validation

- 225 targeted Python Email/provider/cache/live/recovery/notification/signature/send
  tests passed.
- Seven existing JavaScript suites passed: live/context, connection status,
  notifications, send status, component/cache, composer/search focus, app search.
- New production render benchmark assertions pass for unchanged updates, cached
  and uncached selection and acknowledgement repaint.
- Full Python suite: 3,267 tests, 131 failures, 36 errors, 36 skips. Failure/error
  identities exactly match the previous recovery validation's 167 failing cases;
  no new failing identity. The repository-wide suite is not green.
- Python compile, JavaScript syntax and `git diff --check` passed.

Browser fixtures at 1440×900 and 1920×1080 exercised selection, read state, Reply,
typing, context menu, read/unread, folder switching and long-message scrolling.
Ten different messages were opened in the 75-message fixture, followed by cached
reopen. The three-pane layout, toolbar, Nathan signature and loading design were
unchanged. A browser-control timeout interrupted one repeat compose check; a fresh
fixture tab successfully opened New Mail and accepted recipient/subject/body input.
In that tab a simulated incoming message appeared automatically (four to five
conversations), while the compose draft and typed text remained intact and Live.
No real email was sent. Browser timings below 50/100 ms, pixel-diff equality, archive/
trash end-to-end timing and context-menu paint latency were not instrumented, so
those targets are not claimed. Existing action regression tests remain passing.

## Files attributable to this pass

- `components/support_email/mail.js`: two redundant-render optimisations.
- `tests/profile_email_render.cjs`: repeatable frontend counting benchmark and tests.
- `tests/profile_email_interactions.py`: offline controller/parse/matching benchmark.
- `docs/EMAIL_PERFORMANCE_PASS.md`: evidence, limits and validation report.

Raw measurements and the exact pre-edit mail.js snapshot are under ignored
`output/email-performance-*`. Before/after render comparison can be repeated with:

```text
node tests/profile_email_render.cjs output/email-performance-before/mail.js
node tests/profile_email_render.cjs
python -m tests.profile_email_interactions
```

This is a small, locally validated performance change suitable for deployment
review. It does not establish production latency or resolve the unrelated full-suite
failures. Review the concurrent commit boundary before deployment. No deployment
is authorised or performed by this task; Nathan's approval remains required.
