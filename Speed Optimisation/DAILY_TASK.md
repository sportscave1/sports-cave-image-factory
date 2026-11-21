# Nightly operating instructions

Scope: improve speed only, one measured section per Sydney calendar day. Preserve
all operations, permissions, data, designs, layouts, actions and visible features.
The user authorizes focused commits, GitHub publication and the existing Render
deployment for proven performance-only improvements. That authority does not cover
unrelated unfinished work, feature changes, provider writes during testing, a new
Render service, blind merges, force pushes or bypassing failed checks.

1. Verify the actual repository root, branch, Studio task ID/owner and cleanliness
   before edits. Read AGENTS.md and the Studio procedures. This coordination
   folder is not permission to reuse another active task. Allocate each new coding
   task with Studio New (CORE, unique speed owner). Record any dependencies on
   unfinished marketplace/website work without modifying those owners' worktrees.
   Consult GitHub and existing Render service read-only to establish the exact
   current revisions. If access is missing, record it; never infer a successful
   connection. Reconcile the approved Studio base with the live source before
   attempting releases. Do not silently change the approved-base registry.
2. Run `python scripts/speed_daily.py begin` from the coordination task worktree.
   Use its returned ID and date in the report. If already_reported, retry only
   publication of that report. The active.json claim prevents overlapping runs;
   interrupted claims require inspection, never blind expiry or lock deletion.
   Inspect today's report and outstanding Speed tasks
   before starting. If another run is active, stop. Resume an unfinished owned
   speed task instead of creating duplicates. A retry of a finished daily review
   republishes its existing immutable report ID, not a second coding task.
3. Read OS history at /api/speed/reports using the existing owner browser session.
   Merge any locally queued reports. Run python scripts/speed_review.py and inspect
   new modules, route definitions and recent Git changes, including changes to
   deeper directories and shared dependencies that static discovery may miss.
   Enrol the marketplace and website after verifying their actual repo, domain
   and ownership. Never invent external URLs or assume they share OS deployment.
   Prioritise unreviewed/new/changed sections, then repeat regressions, then oldest
   reviewed sections. Missing workflows are onboarding work, not proof of speed.
4. Use comparable samples (at least three) tied to exact revisions. For Orders,
   measure navigation until all expected rows are usable and time to open an
   order; HTML response time alone is insufficient. Distinguish browser, server,
   network and provider latency. Read-only live checks must not submit orders,
   send email, allocate editions, publish ads or trigger customer automations.
   Use synthetic data with enforced isolation for behavioural tests. Do not start
   the application while Studio's Phase 1 preview restriction remains in force.
5. Write phases for the selected section. Prepare at most one focused improvement
   if a repeatable bottleneck is demonstrated. No speculative rewrite, removed
   feature, arbitrary cache freshness change or reduced row count. Add appropriate
   regression coverage, compare baseline/candidate timings under the same workload,
   and verify unchanged appearance, outputs, permissions and actions. A section
   with no justified improvement should produce a no_change report.
6. Publish automatically only when exact candidate tests, measured improvement,
   synthetic functional/browser parity and release readiness all pass. Current
   Phase 1 restrictions or missing parity evidence mean blocked, not approved.
   Use the existing manifest-based deployment process, an isolated release
   checkout and only selected Speed files. Inspect helper requirements before
   invoking it; it expects main and must never be run in someone else's checkout.
   Check origin/main has not advanced, validate Render topology and preserve the
   canonical sports-cave-os ID srv-d8kl4on7f7vs73dvavv0 and supporting services.
   No Blueprint changes are required. If one is ever needed, inspect its preview
   before syncing and reject duplicate primary services. Do not disable CI or
   provider verification. After push, verify GitHub SHA, Render deployed SHA and
   health, then repeat the same live workflow timings. A health check by itself
   does not establish unchanged app behaviour or improved speed. Stop further
   releases after a failed release and report the exact failure; no blind retry.
7. Produce one daily JSON report using speed_optimisation.validate_report. Include
   id (UUID), Sydney date, section, source fingerprint, base_sha, honest status,
   summary, phases, tests, blockers, files and measurements (workflow, environment
   live/baseline/candidate, revision, samples_ms). Add candidate_sha and live_sha
   only when actually known. Never fabricate measurements. Include the source of
   each test/measurement in the summary or tests. Do not claim released unless
   Render verification AND post-release workflow checks succeeded. No secrets,
   customer identifiers, raw orders or logs containing personal data in reports.
8. Save the payload in a temporary file, then use
   `python scripts/speed_daily.py complete --run-id <id> --report <payload-file>`
   in the coordination worktree to save .local-data/speed/YYYY-MM-DD.json atomically
   and release only the matching run claim. Publish only
   that report using the signed-in owner form /ops/speed/publish (or same-origin
   JSON POST) and verify the ID via /api/speed/reports. If the endpoint/session is
   unavailable, retain the exact payload for retry and report publication blocked.
   Never overwrite or guess successful publication. Record tests/status in Studio.
   The daily result belongs in Developer → Speed Optimisation; no duplicate email
   or ChatGPT scheduled report is necessary. End with a concise factual result.
