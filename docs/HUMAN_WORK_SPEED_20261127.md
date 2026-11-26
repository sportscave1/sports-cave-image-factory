# Human Work reader repair — 27 November 2026

Task 20261126-3dc8ffb3, owner codex-speed-20261127-human-work.
Reviewed source/main/live: ebcc7bd37f64f8bd24678a0625c0c31db44cf9ea.
Studio approved base 2938186a retained; only this owned task fast-forwarded to main.

The existing Human Work warning outranks unproved upload cold-start cost, unchanged
SEO storage sizes, and completed/other-owned Marketplace, Orders, Inbox and design
work. Daily seven-area ranking and nested route/source inventory are retained in
the automation ledger and output/human-work-speed/daily-scan.json.

## Diagnosis and phases

1. Reproduce the actual missing ZoneInfo import: three isolated attempts fail
   before reaching PostgreSQL. A diagnostic baseline injects ONLY that import to
   measure the intended working reader; it is never described as deployed success.
   Real private PostgreSQL has 6,000 synthetic events and the production page reader
   returns 25 rows plus its next-page sentinel. Five baseline reads median 3.071ms;
   connection setup consumes 8.788ms of 16.7ms total. No provider/queue/transfer work.
2. Import ZoneInfo and reuse the existing read transport (maximum three exclusive
   connections, eight waiting callers, existing idle/lifetime bounds). Run the
   unchanged SELECT and SET LOCAL 2500ms inside an explicit transaction because
   pooled connections use autocommit. No row/data cache, schema, dependency,
   index, UI, write, retry, freshness or access policy change.
3. Verify at least five comparable reads per revision, cold/warm separately and
   repeated filter/page workflows; target >=20% median working-reader improvement
   and fewer new transports. Verify full output equality, own/all-user access,
   inactive denial, Sydney DST boundaries, query timeout and recovery, concurrent
   reads and bounded soak. Actual Streamlit Human Work controls, paging/filter
   usability, three tabs and desktop/mobile frames must match the diagnostic
   import-only baseline. No deployed-baseline speed percentage is possible because
   the shipped workflow fails. Report browser overhead separately.
4. Commit only focused files, repeat exact candidate acceptance and normal release
   gates in an owned release task fenced against current main. Publish through
   speed_release.py only when gates pass; verify existing Render identities,
   health and read-only workflow. Rollback is a scoped revert under normal gates.

No operational records are removed. Aggregate growth is evidence only: onboarding
audit 114655232B/30999 estimated rows, prior111157248B/30089. SEO details254345216B
and snapshots81428480B unchanged. Only compact Speed reports retain existing90day
expiry. Missing planner tables remain a separate prerequisite; no migrations.

Final measured results and executed checks belong in exact acceptance/report
artifacts. Preliminary diagnostics above are not final release evidence.

## Pre-release evidence

Actual deployed Reporting still warns in three live reloads:11984/11905/12217ms
through Sent Reports; these are failed-view timings, never a successful baseline.
First complete isolated acceptance: working reader median3.250->0.879ms,
2.371ms/72.95% faster. Initial pool setup9.074ms is included in candidate samples.
Three recreated-pool cold reads median3.117->3.905ms:0.788ms overhead; no cold gain.
Browser readiness1991->2107ms and next-page/filter337->339ms show no meaningful UI
speed gain, within the predeclared15% nonregression budget. Desktop/mobile0changed
pixels. The gain is restored functionality plus reduced repeated transport work.

54 focused pytest and9subtests pass, including shared daily digest/reporting,
Human Work tracking, permissions, DST23/25hour days and read-pool tests. Actual
SQL timeout/rollback/recovery and default timeout restoration pass;9reads across
3threads plus20read soak, transport disconnection recovery, all/own-user scopes,
filtered/empty/page navigation pass. Browser3sessions/revision and3tabs pass.
The first harness failure was a read-only SHOW probe omitted from the fixture
allowlist; the second an ambiguous2canvas selector. Both corrected in the harness,
with no production workaround. Source audit has no unused-import candidates after
removing unused imports from newly added harness/test files. No feature/code/asset
or dependency removal; all6000synthetic records retained. Pause/resume/idempotent
writes are inapplicable to this read-only workflow; no new retries or jobs.

Exact committed release artifacts supersede these preliminary numbers. New-pool
cold samples are not independent fresh interpreter samples and are labelled as such.
