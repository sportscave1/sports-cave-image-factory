# Prodigi page recovery — Companion 1.7.56

SC3551's stored history on 25 November 2026 (Sydney) identifies two pre-Save
failures. The image picker first timed out waiting for the uploaded image. Its
existing empty-item recovery then encountered an unresponsive previous content
script. After waking that tab, `prodigiWaitForPage` threw “The woken order page
did not expose its identity” before the caller could use its fresh-tab fallback.
The server's upload recovery allowlist also omitted that exact error, leaving
the order in Needs review. The generic finish message conflated an unused Save
permit with a changed supplier order.

The stored Save permit was unused, the business-field difference list was empty,
product selection had passed verification, and no submission was recorded. The
live supplier tab was still displaying the image picker with “Uploading…”. This
evidence establishes the application recovery failure; it does not establish
why the supplier's original upload stopped progressing.

The Companion now treats a missing previous document identity as bounded page
unavailability. It preserves that old tab and opens one fresh context only for
an already authorised product, empty-item, full-Reset or saved-order QA handoff.
It checks the original owned tab ID before replacement and checks current
ownership and destination immediately before an ordinary refresh. Failed fresh
pages cannot create a tab loop. Working responsive pages keep their existing
reload, upload and QA paths.

The server recognises the old missing-identity failure, allowing affected
orders to recover through the existing independent source, item, empty-slot,
business-state and unused-permit checks. It retires the previous token and keeps
the receipt history. Changed drafts, used Save permits, submissions and unknown
errors remain blocked. The pre-Save readiness message describes an unchanged
draft only after those saved-state checks succeed. No payment, submission,
edition allocation, customer messaging or infrastructure behaviour changes.

Offline coverage is included in `scripts/check_orders_release.py`, including
the frozen/missing/unidentified content-script cases, exhausted fresh context,
ownership/navigation/sign-in races, legacy receipt recovery, source/order
changes, and used-permit rejection. PostgreSQL cases use disposable PGlite and
synthetic orders; live orders must never be used as failure fixtures.
