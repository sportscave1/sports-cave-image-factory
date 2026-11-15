# Sports Cave deployment workflow

## One command

Run from the repository in VS Code PowerShell, after reviewing the intended diff:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy.ps1
```

Optionally supply `-Message "Describe your change"`. The wrapper uses the local
`.venv` Python when present, otherwise `python` on PATH. Python 3.10+ and Git are
required. It does not import or start the application.

- `-CheckOnly`: normalize/check/stage selected changes; **no commit or push**.
- `-Paths app.py,tests/test_example.py`: explicitly select changed files or
  directories. Without this option, an existing staged selection is authoritative;
  otherwise all changed/untracked, non-ignored files are selected and listed.
- Partially staged files stop the helper before rewriting/staging anything. Finish
  staging or unstage those files first; the helper never overwrites a partial selection.
- A clean working tree prints `Working tree clean — nothing new to commit.` and
  `NOTHING TO DEPLOY`, exits 0 and never commits or pushes. It reports whether
  local HEAD matches origin/main.
- If a previous push failed after a successful commit, review the commit and use
  the same command with `-PushExisting`. This requires a clean tree, performs the
  branch/remote/ancestor/syntax checks, and pushes the existing commit without an
  empty or duplicate commit. The ordinary clean-tree command still does nothing.

The local `git deploy` alias has been redirected to this tracked entry point.
For another checkout, optional one-time alias setup is:

```powershell
git config --local alias.deploy '!powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/deploy.ps1'
```

Do not chain another commit/push after the helper. The old `.git/deploy.ps1` is no
longer used. `scripts/deploy_render.ps1` is a compatibility wrapper, **not** a
separate deploy-hook path. Its old `-ValidateOnly` maps to the staging/check-only
mode with an explicit message; `-AllowDirty` is rejected. No hook secrets are read.

## Checks and failure semantics

The helper verifies the checkout, exact Sports Cave origin fetch/push URLs, main
branch, no unfinished merge/rebase/cherry-pick, and no conflicts. It fetches
origin/main and refuses to overwrite remote history or auto-merge it. Filenames
use NUL-delimited Git output and literal pathspecs, including spaces/brackets.

Before commit it repairs syntax-proven harmless Python/JSON whitespace, stages
only the selection, runs `git diff --cached --check`, and compiles changed Python
without executing it. Already-committed changes ahead of origin/main also receive
syntax checks. Real fetch/stage/check/compile/hook/commit/push/verification errors
stop the workflow with nonzero status. Normal Git hooks are preserved.

Successful native command exit codes decide success; LF/CRLF stderr warnings do
not. Results are `COMMITTED`, `PUSHED`, `NOTHING TO DEPLOY`, or `CHECKS PASSED`.
`PUSHED` verifies local HEAD against freshly fetched origin/main. It does **not**
claim Render is live. Inspect all four Render deployments separately.

No direct Render API call, Blueprint sync, migrations, mail send, Shopify write,
marketing toggle or flow activation exists in this helper. Existing production
startup migrations and auto-deploy settings are unchanged.

## Whitespace and line endings

There was no repository `.gitattributes`, `.editorconfig` or VS Code whitespace
policy. Generated edits could retain extra final blank lines; the private helper
only trimmed some EOF cases, and manual command chains still ran commits after a
successful clean-tree return. The evidence does not identify a particular model
or formatter as the source of every extra blank line.

The repository now uses LF for source/text and CRLF for `.bat`/`.cmd`, with binary
files excluded. No repository-wide `git add --renormalize` was run. Previously
checked-out CRLF files may produce a one-time normalization warning when touched;
that is not a build error. Git's repository representation is predictable.

VS Code inserts a final newline and removes extra final blank lines. Literal
trailing spaces are retained by default; JSON can safely trim them. EditorConfig
provides matching newline rules and preserves literal source/Markdown whitespace.
Other editors need EditorConfig support to apply those settings.

Deployment normalization touches **only selected changed Python/JSON files**,
preserves encoding/BOM and newline style, skips binary/symlink files, protects
Python strings, and compares parsed values/ASTs before writing. It cannot alter
embedded email HTML, Markdown hard breaks, or multiline string values. Ambiguous
HTML/JS/other whitespace failures remain visible with the Git file/line diagnostic
for manual review; they are never suppressed. No blanket formatter is run.

## September 28, 2026 Render incident

Read-only inspection covered Nathan's workspace and the four existing services.
The affected repository HEAD was `5258dd4265a6dd9545fd66ddaeabf5440806c729`.
No production configuration, database or deployment was changed during repair.

All four used repository root (empty `rootDir`), native Python, and the same build
command: **`pip install -r requirements.txt`**. None runs tests, compilation or
migrations as part of that build command.

| Service / ID | Type | Start command | Release/runtime migrations |
| --- | --- | --- | --- |
| sports-cave-os / srv-d8kl4on7f7vs73dvavv0 | Web, standard | `python sports_cave_server.py` | Existing predeploy `python run_migrations.py --only 20260901_os_repair_requests.sql`; existing startup deployment/SEO migrations |
| sports-cave-os-webhooks / srv-d9146onlk1mc739nrm7g | Web, free | `python webhook_server.py` | No predeploy command |
| sports-cave-seo-worker / srv-d9ujm9navr4c73amurgg | Background worker, starter | `python google_seo_import.py worker --poll-seconds 15` | No predeploy command; existing SEO repository `ensure_schema` at runtime |
| sports-cave-seo-daily-sync / crn-d9ujqvvqj5pc73fpe0ag | Cron, starter; `30 18 * * *` UTC | `python google_seo_import.py daily` | No predeploy command; same existing SEO storage setup |

The shared first meaningful error was a PyPI index read timeout fetching the
**Svix dependency python-dateutil**, not a CRM Python import or whitespace error:

```text
ReadTimeoutError: HTTPSConnectionPool(host='pypi.org', port=443): Read timed out. (read timeout=15)
/simple/python-dateutil/
ERROR: Could not find a version that satisfies the requirement python-dateutil (from svix) (from versions: none)
ERROR: No matching distribution found for python-dateutil
```

| Service | First observed timeout, UTC | First fatal dependency error, UTC |
| --- | --- | --- |
| sports-cave-os | 10:36:19 | 10:37:42 |
| sports-cave-os-webhooks | 10:36:17 | 10:37:40 |
| sports-cave-seo-worker | 10:36:13 | 10:37:36 |
| sports-cave-seo-daily-sync | 10:36:14 (first build recovered) | 10:42:05 (next build) |

The preceding “Ignored ... 0.55.2 ... Python <3.5” pip message was resolver noise,
not evidence that python-dateutil is unavailable for modern Python. The cron
successfully built `c162961` and installed python-dateutil 2.9.0.post0 and Svix
1.99.1; the later `54e6a9b` and empty trigger `5258dd4` failed across all four.
That is direct evidence of the shared dependency-fetch failure.

`c162961` contains the brand-template/rendering/VA-removal work. `54e6a9b` reused
the same commit subject but actually contains the Product Upload pricing revert
and tests. Neither changed requirements. Svix was added earlier in `f9978b0`.
No CRM code was rolled back or build validation disabled to fix this incident.

## Build repair

1. `requirements.txt` now references the official universal python-dateutil
   **2.9.0.post0** wheel directly, with SHA-256 verification. This bypasses the
   failing `/simple/python-dateutil/` index lookup while preserving Svix and webhook
   verification. The artifact/version is the same one confirmed in the successful
   cron build. It still requires HTTPS access to PyPI's file host; no local change
   can guarantee builds during a general network outage.
2. All observed builds chose **Python 3.14.3 (default)**. The existing
   `runtime.txt` declared 3.12.8 but was not controlling Render. `.python-version`
   now explicitly declares **3.12.8**, matching that existing repository intent.
   [Render's version-selection rules](https://render.com/docs/python-version)
   use `PYTHON_VERSION` first, then `.python-version`, then the service default.
   No runtime environment variables were changed.
3. The Blueprint remains unchanged and owns only the webhook service. The
   canonical primary stays externally managed; no duplicate service is created.

The wheel SHA-256 is
`a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427`, verified by pip
against [the official release metadata](https://pypi.org/pypi/python-dateutil/2.9.0.post0/json).

## Local verification

Files changed for this repair:

- Runtime/dependency: `.python-version`, `requirements.txt`.
- Workflow: `scripts/deploy.ps1`, `scripts/deploy.py`,
  `scripts/deploy_render.ps1` (compatibility wrapper).
- Editor/line endings: `.gitattributes`, `.editorconfig`, `.vscode/settings.json`.
- Documentation: `README.md`, `docs/DEPLOY_WORKFLOW.md`.
- Tests: `tests/test_deploy_workflow.py`, `tests/test_render_build_contract.py`,
  `tests/test_crm_html_workspace.py`, `tests/test_seo_workspace.py`,
  `tests/test_sports_cave_pricing.py`.

The local Git alias was updated separately; it is not a committed configuration
file. No application module, migration, price source, navigation registry, mail
transport or CRM delivery switch was modified. Product Upload Small/Medium
framed prices remain A$169/A$209 across Black/Oak/White; existing RRPs are intact.
The Email navigation, campaign editor, saved brand templates, safe HTML/image
rendering, and VA Training removal remain present in the unchanged application.

- Fresh isolated Python 3.12.8 environment: `pip install -r requirements.txt`
  succeeded; `pip check` found no broken requirements.
- Linux x86_64 / CPython 3.12 wheel-resolution dry run succeeded for requirements.
  This is dependency validation, not execution on Render/Linux. Windows is the
  available host; neither Docker nor a WSL distribution is installed.
- Entry-point and changed CRM-module imports passed with network access blocked;
  application entry points were **not started** against production.
- CRM suites run sequentially against the disposable PGlite PostgreSQL fixture,
  because their existing setup truncates fixture tables. Parallel CRM fixture
  tests interfere with one another and are not a valid regression run.
- Three stale tests were corrected: obsolete disabled Email menu expectation,
  12-vs-16 pricing fixture count (four sizes times four finishes), and AppTest's
  current session-state mapping API. No corresponding application logic changed.
- Deployment tests use temporary local bare Git origins only. They cover clean
  tree, normal change, EOF repair, syntax/hook/fetch/push failures, CRLF warnings,
  partial staging, explicit paths, literal filenames, remote-ahead protection,
  clean-ahead recovery and PowerShell exit-code propagation.

Final validation: **875 tests collected, 873 passed, 2 skipped** across 60 suites
(CRM 164; Email 319; Product Upload/pricing 59; SEO 226; webhook 19;
navigation/startup/sidebar 68, including six also counted under Email; topology 3;
deploy helper/build contract 23). All **440 Python files** compiled without
execution. Git whitespace checks passed, including the new tracked-intended
files. The two optional SEO tests needing a separate localhost PostgreSQL server
are skipped; their SQL parser and mocked runtime tests are included. No live
credentials, Shopify writes, email sends or production migrations are used.

After approval, run the single command above and inspect all four Render builds.
Confirm logs select 3.12.8 and complete dependency installation, then verify their
normal health/runtime checks. A successful local build is not proof of a future
Render deployment; this repair intentionally did not trigger one.
