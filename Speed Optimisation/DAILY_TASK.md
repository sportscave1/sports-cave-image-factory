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
   Start/ensure `python scripts/speed_companion.py start` first. Its authenticated
   report publisher and crash-recovering supervisor are separate from coding.
   Use its returned ID and date in the report. If already_reported, retry only
   publication of that report. The active.json claim prevents overlapping runs;
   interrupted claims require inspection, never blind expiry or lock deletion.
   Inspect today's report and outstanding Speed tasks
   before starting. If another run is active, stop. Resume an unfinished owned
   speed task instead of creating duplicates. A retry of a finished daily review
   republishes its existing immutable report ID, not a second coding task.
3. Read OS history at /api/speed/reports using the existing owner browser session.
   Prefer `python scripts/speed_companion.py review` for unattended history and
   read-only aggregate Supabase table sizes/estimated rows/dead rows. It uses a
   Speed-only credential, not production database credentials in the preview.
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
   Use synthetic data with enforced isolation for behavioural tests. Use the
   reviewed Docker preview verifier; host app/server startup remains prohibited.
   Extend synthetic fixtures for the selected section before claiming parity.
5. Write phases for the selected section. Prepare at most one focused improvement
   if a repeatable bottleneck is demonstrated. No speculative rewrite, removed
   feature, arbitrary cache freshness change or reduced row count. Add appropriate
   regression coverage, compare baseline/candidate timings under the same workload,
   and verify unchanged appearance, outputs, permissions and actions. A section
   with no justified improvement should produce a no_change report.
   Review code cleanliness in that same section using
   `python scripts/speed_code_review.py <selected-source-files>`. Its unused-import
   output is candidate evidence only. Search repository references, dynamic imports,
   configuration, route registration, exports, CLI entry points and side effects.
   Remove code/assets/dependencies only when lack of use is established and the
   focused checks prove preserved behaviour. Retain tests, migrations, recovery
   paths, access controls, audit evidence and features that are merely infrequent.
   Record deleted files/lines or reduced payload/memory/import cost. Never delete
   a working feature to achieve a speed score. Cleanup-only work must demonstrate
   smaller code/payload and no measured workflow regression, plus behaviour parity.
   Review Supabase storage growth, unnecessary repeated writes, duplicate generated
   artefacts and retention in the selected section. Use aggregate metadata first.
   Speed reports expire after 90 days and contain no raw logs, screenshots, code
   dumps or customer records. No automatic SQL/table/index drops, VACUUM FULL,
   customer/order/edition/financial deletion, retention changes for shared data or
   bulk cleanup based only on table size. Report such candidates with dependencies
   and a reversible plan; optimise writes/queries without changing operational data.
6. Publish automatically only when exact candidate tests, measured improvement,
   synthetic functional/browser parity and release readiness all pass. Missing
   isolation or parity evidence means blocked, not approved.
   Use the existing manifest-based deployment process, an isolated release
   checkout and only selected Speed files. Inspect helper requirements before
   invoking it. The normal helper expects main and must never run in someone
   else's checkout. The owned-branch path is scripts/speed_release.py; it reuses
   normal offline validation and fences main before push. Its initial installation
   exception cannot be reused by nightly improvements.
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
   Include cleanup_checks and storage_checks in the report, even when there is
   nothing proven safe to remove. Run `python scripts/speed_companion.py flush`
   after completion. The companion retains failed publications and retries them;
   its publisher endpoint cannot execute code, modify the app or release anything.
   The daily result belongs in Developer → Speed Optimisation; no duplicate email
   or ChatGPT scheduled report is necessary. End with a concise factual result.
