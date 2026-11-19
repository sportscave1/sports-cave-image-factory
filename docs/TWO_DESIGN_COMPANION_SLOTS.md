# Two concurrent design jobs

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
