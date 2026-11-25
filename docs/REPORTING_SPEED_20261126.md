# Reporting normalization repair — 26 November 2026

Task `20261125-4cf57044`, owner `codex-speed-20261126-reporting`.
Approved Studio source `2938186a21758a75ff461bef59e755c53c944b4d`;
initial main/live `ec9f28de7f775e3b9018f9254950cb8cf35e9694`.
No approved-base registry change. All unrelated owner work retained.

## Diagnosis and selection

Fresh discovery, nested source/test changes, real Reporting route and shared
dashboard dependencies inspected. Initial isolated populated full report:
84 sheets / 1,260 tasks / 1,260 timers, 12 weeks and 84 day rows. Five baseline
samples 167.817,171.748,168.305,173.691,170.058 ms. The unchanged comparison
confirms noise only. cProfile: 756 normalizations, 0.372 of 0.569 profiled seconds
(65%); named-task iteration normalizes twice per summary, summary repeats it,
and weekly/daily summaries repeat it again. This is CPU/allocation work, not
provider latency, queue wait, network transfer or a database query regression.
Initial fake-backend profile includes copying populated fixtures and is diagnosis
only; final acceptance must use real isolated PostgreSQL and browser interaction.

Ranking by actionable evidence:
1. Reporting twelve-week progress: proven repeated CPU work and unreviewed
   interactive planning/report coverage; selected. Shared weekly helper affects
   Home/weekly reporting, so test those contracts too.
2. Upload cold enqueue: historical 168.72 ms first call; independent cold-process
   evidence/root cause absent. Current queue read path is bounded to 20 rows.
3. SEO storage: largest tables 254,345,216 and 81,428,480 bytes unchanged; no waste
   proved and no deletion justified.
4. Orders/editions: high operational impact, fresh companion QA repair released
   today by another owner; no independent new speed failure observed.
5. Inbox: extensive same-day speed/reliability release and active separate owners;
   do not duplicate that objective.
6. Website/Reviews: separate unfinished parity owners; preserve their work.
7. Marketplace/status/recovery hashing: completed cooldowns through 1 Dec/29 Nov/
   2 Dec; no new failure in their selected runtime sources.

## Phases and budgets

1. Complete populated CPU profile and establish repeated baseline. Complete.
2. Normalize each sheet once within report evaluation. Private helpers consume
   normalized rows; public entry points continue accepting raw rows. Keep all
   date filtering, carry chains, deduplication, timer outcomes and copies. No
   persistent cache, TTL, new dependency, worker or database write.
3. Complete real PostgreSQL read contracts, 5 comparable before/after full report
   samples (target >=25% median CPU-path reduction), desktop/mobile complete
   report -> week -> day interaction (three samples each, no >10% regression),
   exact output/visual parity. Test legacy/blank/malformed/future/carry data,
   paused/running/failed timer handling, permissions/ownership, DB failure and
   retry, concurrent calls and bounded repeat soak. No customer/provider writes.
4. Commit focused source, tests and harness under standing scoped authority.
   Integrate exact current main in a separate owned RELEASE task if necessary;
   retest exact candidate, normal release gates and current-main fence. Push
   through speed_release only if gates pass. Verify GitHub, three existing
   active Render services, health and relevant read-only live workflow. Keep
   cron suspended. Revert is the focused runtime diff; no durable data change.

## Constraints and storage

UI source/design/controls, query/row limits, authorization, historical outcomes,
timer/retry semantics and ownership must remain identical. Memory is temporary
per call, bounded by existing fetched rows; no global cache or extra source-byte
retention. Aggregate audit growth 107,741,184/29,161 -> 111,157,248/30,089 estimated
bytes/rows is not evidence of waste. No operational record/history deletion.
Speed reports alone keep their existing 90-day namespace retention.

Initial candidate has 84 instead of 756 normalizations and identical full output;
five fake-backend samples median173.483 ->64.214 ms (62.99%). This is preliminary,
not final release evidence or a production speed claim.

## Populated acceptance before exact release integration

`output/reporting-speed/browser6/acceptance.json`: actual existing Supabase read
functions against private PostgreSQL, 84 owner sheets + 1 other-owner sheet,
1,260 tasks/timers. Five full reports median193.348 ->80.131 ms, 113.217 ms /58.56%
faster; CPU171.592 ->64.413 ms. SQL50statements across5reports unchanged;
normalizations756 ->84 per report. No data cache, extra DB write or artifact.

Actual Streamlit Reporting renderer and Chromium, three comparable sessions each:
full-report ready median2107.734 ->1632.013 ms; week+day drawer1291.805 ->691.523 ms.
Both desktop and mobile PNGs match exactly in this run. An earlier desktop
comparison differed by two canvas-border pixels; visually inspected and recorded.
The acceptance budget permits at most8 unmasked pixels, not omitted regions.
Three concurrent calls, three browser tabs, eight-report soak,40 seeded raw/
legacy/carry/future/status/timer parity comparisons, input immutability, real
other-owner detail denial, owner permissions and timeout/retry recovery pass.
57 focused pytest pass. Wider existing200tests have10failures/190passes128subtests
on BOTH unchanged source and candidate. They concern existing design/Home rendering
and an outdated activity-route assertion; no failures newly introduced or hidden.
Normal release gate includes the57focused contracts and remains mandatory.

## Live prerequisite found by read-only inspection

Existing live Reporting renders its normal sections, but Twelve Week Progress
shows a pre-existing storage-unavailable message. Authoritative Supabase project
`ceyzbfpuwuuxaiqwiltz` metadata confirms the cycle/weekly/monthly planner tables
are absent and estimates0saved daily sheets/timers. The similarly named project
is not authoritative; an initial metadata-only lookup there returned no rows.
No database configuration/credentials or migrations were changed. The separate
cycle migration is a backlog dependency, not fixed by this performance patch.
Human Work Records also shows an existing read error; no cause is asserted.
Three existing-live complete Reporting reads through final controls:
14974,14714,14581 ms. These include unrelated database/network/schema-failure
time and do NOT measure populated planner readiness or a production speed gain.
Release verification must distinguish unchanged live failure/empty state from
the demonstrated populated synthetic computational/interactive improvement.
