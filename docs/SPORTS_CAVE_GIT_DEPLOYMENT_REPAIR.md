# Sports Cave OS Git and PowerShell deployment repair

11 October 2026, Australia/Sydney.

## Root causes and repair

The original local `main` was `b526c1d0`, one commit ahead and fourteen commits behind GitHub `main`. GitHub and all four canonical Render services were already on `d1b3eecb4ae9e1e91feee0ab82a147b3dfcce4b6`, containing Email Automation Expansion and Automations V6. The upstream configuration was correct; its tracking reference and the local branch were stale.

`.tmp-full-system-release` is a separate Git repository with its own object database, not a registered worktree of the main repository. Its release commits were not originally resolvable in the main checkout. Historical release helpers assumed particular base commits and exact pre-release file contents. Consequently, a release already deployed could fail their history/content guards. The local analytics file originally lacked V6's aggregate query even while the separate release checkout contained it. Reapplying those historical bundles is no longer appropriate.

The earlier general helper could implicitly select all dirty/untracked files when nothing was staged, normalize files during validation, and stop verification at Git push. That was unsuitable for the current shared checkout with active Inbox development. The new entry point uses exact, hash-bound manifests and verifies an isolated candidate. Native Git arguments are passed by Python arrays, avoiding PowerShell quoting and stderr-as-failure pitfalls.

The following local history repair was performed without a commit, push, deployment or application-file write:

1. Fetched GitHub and verified the live Render SHA.
2. Computed `git merge-tree main origin/main`. Its tree exactly matched `origin/main` (`91adb4f213eaa9d21be9a0e830f7bc57a816038d`), proving the unique old local commit had no additional committed source to retain in current main.
3. Preserved the old commit on `codex/local-main-before-sync-20261011` and copied the old index to `.tmp-git-deployment-repair/index-before`.
4. Atomically aligned `main` to the verified GitHub SHA, with an expected-old-SHA guard, and loaded that tree into the index **without updating working files**. This was not a hard reset, checkout overwrite or force push.
5. Verified 2,503 existing source/document files remained byte-identical. Untracked/ignored directories and all existing worktrees were retained. The main branch now has a normal relationship with GitHub; remaining local differences represent actual unfinished work.

Audit records are local under `.tmp-git-deployment-repair/`. Earlier reconciliation backups remain under `.tmp-combined-release-reconcile/`.

## Release scope and Inbox preservation

Email Automation Expansion and Automations V6 were already live and are retained. The remaining approved non-Inbox application update is the completed Abandoned Checkout status projection and removal of recipient timeline panels, described in `docs/checkout-email-status-upgrade.txt`. It changes `crm_checkout_analytics.py`, `crm_checkout_progress.py` and `crm_flow_page.py`, together with their focused regression tests. It reads existing tracking evidence; no migration, provider call, scheduler change or activation is introduced.

Active Inbox Phase 2A/subsequent work is excluded: `app.py`'s account-change draft-journal edit, `support_email*`, `components/support_email/*`, Inbox tests/fixtures and Inbox audit/evidence. A release candidate starts from committed Git blobs, so the uncommitted Inbox implementation cannot leak into tests or deployment through shared local files. The entire `app.py` local delta is Inbox-only and is excluded. No attempt was made to interrupt or message the other task.

The helper explicitly holds Inbox paths. Completion of the other task never triggers automatic deployment. Only a later user-approved preparation with `-IncludeCompletedInbox` can approve those files for a manual release. All source files must also match their recorded hashes at deployment time. The helper never watches another task or publishes a completed manifest automatically.

Other local archives, historic reports, temporary release scripts, generated evidence, Supabase CLI scratch metadata, benchmark outputs and nested repositories remain local. Their presence is not release approval.

## One-command manual deployment

From the VS Code PowerShell terminal:

```powershell
.\scripts\deploy-sports-cave.ps1
```

The script resolves its own repository root, regardless of the terminal's current directory. The ordinary entry point consumes `deploy/normal.json`. The checked-in initial manifests are empty deliberately: no unfinished current work is implicitly approved.

During a development task, have Codex prepare the manifest for the exact completed and approved files, include relevant offline regression tests and safe import checks, and show the selection. For example:

```powershell
.\scripts\deploy-sports-cave.ps1 -Prepare -Paths crm_checkout_progress.py,tests/test_crm_checkout_progress.py -Tests tests.test_crm_checkout_progress.Projection -Imports crm_checkout_progress -Message 'Improve checkout status display'
```

`-Prepare` records exact file paths, SHA256 contents, commit message, test names and current GitHub base. It does not commit or push. Invoke it only for reviewed, production-ready files; it is the explicit release selection, not a readiness detector. A file edited afterward invalidates its approval. Directories/globs are not accepted. A deletion must be explicitly listed and already tracked.

After that preparation, the user needs only the ordinary one-command invocation. It validates, commits the exact selection, pushes `main`, and waits for configured Render auto-deployment. There is no second deploy command or temporary release worktree to reconcile.

Useful options:

```powershell
.\scripts\deploy-sports-cave.ps1 -DryRun
.\scripts\deploy-sports-cave.ps1 -Mode Full
.\scripts\deploy-sports-cave.ps1 -VerifyOnly
```

`Full` uses `deploy/full.json`, prepared with `-Prepare -Mode Full` and an explicit list of every approved file. It never means all local files. Both modes apply identical safety gates; Full additionally requires explicit regression tests. `-Manifest path/to/release.json` supports a separately reviewed manifest. Do not include a manifest in its own file list.

For a future completed Inbox release, the user can explicitly authorize `-Prepare -IncludeCompletedInbox` with that release's reviewed paths/tests/imports. The resulting manifest permits the ordinary command to deploy it. This authorization has **not** been granted or prepared for the current Inbox work.

The general historical entry points `scripts/deploy.ps1`, `scripts/deploy_render.ps1` and the `scripts/deploy.py` CLI route to the guarded workflow. The old task-specific bundle helpers are preserved as historical local work; do not use them to replay already-deployed releases.

## Safety and failure behavior

- Exact canonical repository, `main`, fetch/push URLs and upstream configuration are verified. Missing local tracking references are restored by fetch. Missing GitHub branches/authentication, divergent/unapproved history, active Git operations and unresolved conflicts stop with guidance.
- A remote advance never causes an automatic merge or rebase. Review incoming commits and re-prepare the manifest. An existing rejected-push commit can be retried with the same manifest only if its entire tree matches the approved candidate; unrelated local commits cannot be pushed accidentally.
- Existing staged changes stop deployment and remain staged. A private index selects files. A real index lock protects against concurrent staging during commit; working files are never replaced. Hooks run against the candidate; failed hooks stop before push. A hook-altered tree is not pushed.
- The candidate is exported from committed Git blobs plus exact selected contents. Local virtual environments, nested worktrees, secrets, temporary/generated data and evidence bundles cannot be selected. Git objects created during a dry-run are harmless; branch, real index and working files are unchanged.
- Changed Python is compiled without execution, changed JavaScript is checked with Node, JSON is parsed, and the candidate runs topology, draft-lock, ten-email, disabled Win Back email 4 and aggregate-cache checks. Manifest-specific imports and unittest cases run in the isolated candidate with network/HTTP denied and without production credentials. Failures and skipped tests stop the release. A fast smoke is not a substitute for pre-release SQL/browser verification of affected behavior.
- Database migrations, production configuration/dependencies, infrastructure, Shopify theme changes and sensitive automation/sender changes require a separate reviewed workflow; this routine script refuses them. It does not execute SQL or change Shopify/Render settings. There is no force-push, blanket `git add -A`, deploy hook call, or automatic activation.
- No helper can infer whether arbitrary business logic is finished. The manifest and human review remain the approval boundary. Source sharing a file with unfinished work must be separated/reviewed before preparing that path.

## Render verification and credentials

The four existing services were verified on branch `main`, with commit-triggered auto-deploy enabled:

| Service | Immutable ID |
|---|---|
| sports-cave-os | srv-d8kl4on7f7vs73dvavv0 |
| sports-cave-os-webhooks | srv-d9146onlk1mc739nrm7g |
| sports-cave-seo-worker | srv-d9ujm9navr4c73amurgg |
| sports-cave-seo-daily-sync | crn-d9ujqvvqj5pc73fpe0ag |

No topology repair, Blueprint sync or duplicate service is needed. A normal Git push triggers their existing auto-deploy once. The helper never starts the cron job.

When `RENDER_API_KEY` is available in the terminal environment, the helper uses only read-only Render API calls to validate configuration and poll the **expected commit SHA** on all four services. Success requires `live`, primary health HTTP 200 and webhook health HTTP 200 with the same SHA. Build/update/pre-deploy failures, cancellation, superseding/deactivation, API errors and timeouts cannot become deployment success. See [Render deploy status API](https://api-docs.render.com/reference/list-deploys) and [Render service configuration](https://api-docs.render.com/reference/retrieve-service).

Codex connector authentication is not automatically available to a VS Code terminal. Set `RENDER_API_KEY` securely in your terminal environment once if you want the command to verify Render itself; never put the key in a manifest or source file. Without it, the command still performs the approved Git push and allows existing auto-deploy, but clearly returns **exit 2 / RENDER UNVERIFIED**. It does not claim completion. `-PushWithoutRenderVerification` explicitly selects the same push-only outcome. With credentials later available, `-VerifyOnly` verifies the current GitHub SHA without a new commit, push or deployment.

Exit codes: `0` = no changes, successful dry-run, or verified live deployment (read the printed result); `1` = stopped/failed; `2` = pushed, Render unverified. A failed push leaves the local commit for review/retry and never prints a Render success message.

## Verification and status

The Git repair was verified byte-for-byte and against the existing release. PowerShell parsing and an empty-manifest dry-run passed in the real checkout without staging or deployment. The disposable-repository suite covers clean/up-to-date, modified/new/deleted selections, stale/missing references, remote advances, staged/unmerged work, concurrent changes, stale worktrees, temporary files, failed tests/hooks/auth/push, retry, Render failure/wrong SHA/timeout/missing credentials, unsafe paths/migrations and Inbox exclusion.

Final pre-release verification:

- **30 deployment-workflow tests passed** against disposable local Git origins and fake Render responses, including explicit deletion and failed import checks. Windows line-ending/attribute tests also passed: candidate blobs honor committed `.gitattributes`, while working-file bytes remain unchanged. Uncommitted attributes stop deployment.
- **172 application regression/integration tests passed, zero skips**, against an isolated PGlite/PostgreSQL fixture. Shopify/Resend data were fabricated; external HTTP was blocked. Optional thumbnail prewarming was mocked so browser installation does not contaminate backend validation.
- **Chrome checkout component passed** at 1440/1024/750/390/320px: status progression/reload, selection/details, countdown, bounded polling, DOM retention, sticky scrolling and dynamic columns.
- **Mocked shared Flow page passed** at 1440/390/320px: removed timeline UI remains absent, checkout panel opens, no exceptions or horizontal overflow.
- PowerShell entry points parse, the real empty-manifest dry-run passes, and canonical topology validation passes.

The candidate was built from committed production code plus the exact eleven checkout source/test/report files, excluding every working Inbox change. Raw results remain local in `.tmp-git-deployment-repair/`. The release also adds the deployment helper, empty default manifests and this documentation; the full approved selection is hash-bound in the local release manifest. Actual post-rollout status is appended locally after Render confirms it, rather than creating another deployment solely to record its own commit SHA.
