# Design Studio upload queue feedback and dispatch

Task: 20261119-0d8d1411
Owner: codex-queue-20261119-01a1f2f2

Implemented locally, without committing or deploying.

## Findings

The card's first click could reveal a missing-sport selector without completing
the request when a sport was selected. Enqueue outcomes were routed through the
header notice instead of remaining beside the design. Re-enqueueing a failed or
completed source revision returned its existing ID as though new work was queued.
Desktop claims ran on a 30-second alarm, with no enqueue wake-up signal.

These are verified code paths, not a confirmed diagnosis of the individual
Unshaken click: no live job records were queried or changed. The approved local
base still called the card button Publish now; the supplied screenshot calls it
Add to queue. Release integration must reconcile the deployed revision.

## Changes

- Isolate each card in a Streamlit fragment to avoid gallery listing and intake
  reads on card interaction.
- Name the action Add to queue, consume a pending missing-sport selection once,
  and display persistent success/error feedback beside the design.
- Preserve revision-based deduplication and explicit Restart semantics. Report
  failed/completed jobs instead of falsely reporting them as newly queued.
- Send a small wake message through the existing authenticated-origin companion
  bridge after persistence. Keep the periodic alarm as recovery for disconnection
  or older extensions. No extra polling loop or worker is created.
- Package companion version 1.5.5. Immediate wake requires that version to be
  installed/reloaded in the paired desktop profile after an authorized release.

Paused queues remain paused; offline desktops retain durable pending requests.
A different staff computer cannot wake the paired desktop remotely; its next
periodic check will claim work. No claim promises completion of external services.

## Validation

Offline Streamlit and disposable PGlite tests: 55 cases across
test_design_review_selection.py, test_design_review_selection_layout.py,
test_design_review_gallery.py, test_product_upload_staff_queue.py and
test_design_publish_ad.py passed (54 together, corrected card-selector test
passed separately). Selection tests passed again after consuming failed pending
clicks. No production credentials or live publishing were used.

Node companion-origin/instant-wake test completed, including duplicate-tick
protection. Four cancellation and worker-lifetime cases passed. JavaScript syntax
checks and git diff --check passed. The origin harness now supplies worker timer
APIs and a watchdog, preventing a pending promise from falsely exiting as success.
