# Email composer / global search focus fix

## Diagnosis and scope

The global keydown handler did **not** contain type-to-search or ordinary-letter
activation. The unsafe activation path was the search input's `focus` listener:
tabbing to the input or restored focus called `openSearch()` without a click or
shortcut. Its `input` listener could also open a closed palette. Panel close
logic returns focus to its trigger, so focus was incorrectly treated as intent.

Before editing, the actual local OS shell reproduced search opening on Tab from
the refresh button, without a click or shortcut. Ordinary typing in the local
Email iframe did not reproduce Nathan's precise deployed symptom. No evidence
was found of Email reruns explicitly autofocusing global search. Consequently,
this fixes a demonstrated unsafe focus path and hardens keyboard isolation; the
precise production trigger still needs a smoke test in Nathan's browser.

## Changes

- `components/sports_cave_top_bar/index.html`: open desktop search on click,
  never passive focus; input updates only an already-open panel. Closed search
  cannot navigate cached results. Ctrl/Cmd+K remains explicit, excluding consumed,
  composing, repeated, Alt-modified and Shift-modified events.
- Editable detection uses `composedPath()` plus ancestor lookup for inputs,
  textareas, selects, buttons, contenteditable descendants, textbox/combobox
  roles and composer wrappers. A focused iframe remains responsible for its
  keyboard events. Escape within OS panels retains existing close behavior.
- `components/support_email/mail.js`: broaden the existing R/F shortcut typing
  guard to the same editable contexts and shadow paths. Existing Ctrl+Enter send
  and Escape composer-close behavior is unchanged.
- `tests/test_composer_search_focus.cjs`: executable production-listener tests.
- `tests/test_top_bar.py`: update the lazy-load contract from focus to click.
- `tests/fixtures/email_notifications_preview.py`: fabricated search results for
  browser navigation verification; no external I/O.

No app styling, search ranking, signatures, transport, recipient logic, draft
persistence, attachments, notifications, order matching or caching was changed
by this focused fix. Earlier notification edits were preserved.

## Validation

- New JavaScript suite: **2,404 checks passed**, including normal characters,
  punctuation, @, navigation keys, editable descendants, shadow targets, iframe
  guard, focus restoration, Ctrl/Cmd+K, Escape and Email Ctrl+Enter/R/F behavior.
- Existing Email component and notification badge suites: **42 checks passed**.
- Python Email, V2, performance, signatures, notifications, top-bar and order
  notification suites: **228 tests, 225 passed, 3 previously known failures**:
  - sidebar source contract expects removed `resetInitialSidebarScroll`;
  - order-status suite cache contamination expects 1 instead of cached 15;
  - source contract expects a literal 30-second timer rather than existing
    named 60-second interval.
- Navigation performance, startup scope and sidebar cleanup: **34 passed**.
- JS syntax checks for Email and extracted top-bar script passed.
- Python compilation for changed test/fixture files passed.
- `git diff --check` passed.

## Actual shell/browser checks

Using the production shell and Email components with fabricated mailbox data:

- Before: ordinary New Mail To/Subject/body typing stayed in Email; passive Tab
  focus into global search incorrectly opened the palette.
- After: the same passive focus leaves search closed.
- To, CC, BCC, Subject and contenteditable body verified in New Mail, Reply,
  Reply All and Forward, with addresses, numbers, punctuation and spaces.
- New Mail focus remained in each edited field. Formatting and mocked draft-save
  rerender left search closed. Saved draft reopened through Drafts / Edit mailbox
  draft, and body typing left search closed.
- Ctrl+K within the editor did not open OS search. Ctrl+K outside editable fields
  on Orders opened it; Cmd+K equivalent is covered by executable listener tests.
- Search click opened it, filtering found Orders, and Enter navigated to Orders.
- Escape closed search without losing composer content; Email Escape closed the
  composer. Ctrl+Enter was tested at the actual listener boundary, not by sending
  real mail.
- Screenshot: `output/EMAIL_COMPOSER_FOCUS_FIXED.png`.

No new Email performance work or server operations were introduced. No real mail,
IMAP, SMTP or database connection was used. No commit, push or deployment command
was run by this task. A concurrent repository commit appeared during validation;
its contents were preserved.

Suitable for a controlled deployment smoke test after approval. Verify Nathan's
original typing sequence in his deployed browser before declaring that exact
production symptom resolved. This task stops here.
