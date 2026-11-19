# Design queue capacity: one at a time

The owner reverted admission to **one active design** on 19 November 2026.
The server enforces this under the shared paired-desktop claim lock even when
an already installed companion advertises capacity 2. New Designs, refreshes
and edits share that single limit. The next design starts only after the active
one completes or releases its slot through the existing failure/timeout handling.

Two jobs admitted before this rollback may finish and report their progress;
no additional job starts while either remains active. Preserve their saved chats,
send journals and output receipts rather than cancelling or replaying them.
The retained slot column/index supports those existing records and does not
authorize two new admissions. No database migration or installed-extension
update is required for the server limit. Companion 1.7.1 also requests only one
slot and will not open two new chats from an older two-job response.

Validation covers competing capacity-2 clients receiving the same single claim,
automatic progression after completion, draining existing two-job records,
late receipts, restart safety and no duplicate sends.

## Historical two-slot implementation (superseded)

The design companion advertises capacity 2. The server claims only free slots
under its existing paired-desktop lock; a partial unique index and a 1–2 slot
constraint independently cap active jobs at two. Older companions retain the
single-slot request protocol. Refreshes, edits and new designs share these two
slots. Upload and ad admission are unchanged.

Each design retains its own tab, progress report, source/output receipt and send
journal. Pasting and submitting still use the shared browser mutex; generation
can then run in both chats. Completion or timeout releases only the affected
slot. Uncertain submissions are never automatically replayed.

The existing Design card shows the number working and the selected job number.
It alternates active titles, stage text and progress every five seconds, with a
short fade unless reduced motion is requested. Rotation does not fetch status,
rebuild the popup or touch the Uploads or Ads cards. Both designs remain listed
in the popup.

## Release order

After explicit release approval:

1. Apply `20261119063000_two_design_slots.sql` before deploying server code. The
   default slot 1 keeps older server/companion claims safe during rollout.
2. Deploy the server and header to the existing canonical service.
3. Update the installed browser companion to 1.7.0, retaining its pairing and
   send journals. Only the updated companion requests the second slot.
4. Verify two distinct active jobs, each submitted once, and both status phases.

Local verification: 53 queue tests, 8 companion tests and 2 header browser tests
passed, including concurrent claims, the database cap, slot replacement, stalled
job isolation, restart safety, rotation and reduced motion. Live operation is not
verified by these synthetic tests.
