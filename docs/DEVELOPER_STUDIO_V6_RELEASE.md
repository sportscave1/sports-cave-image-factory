# Developer Studio V6 — RELEASE handoff

CORE approval: `bdc46c292a9a4213a21b861184c35186820a16be`.
RELEASE task: `20261012-e9bca758`, owner `me/studio-v6-release`.
Integrated live/main baseline: `a1f8c3c55778aa27ff21310cbcf5383810992b48`.
This is a local candidate awaiting hosted acceptance and final owner deployment approval.
Real Publish stays disabled. No production push, deployment or migration is authorised.

## Content and preservation

The native RELEASE merge retains all current-main application, worker, CRM,
Design Studio, navigation and deployment files. Eleven reviewed conflicts were
already-deployed V5 files superseded by the approved V6 implementation. They were
resolved to the exact approved CORE blobs. Only 36 Studio implementation/test/doc
files plus this handoff document differ from main. No unrelated draft was included.
The original, UI/UX, V5 and other worktree files are not edited by this integration.

The existing 18762 companion now uses the clean approved CORE implementation,
with its existing task 20261011-7192d493 and owner me/os-uiux-v1. Four protected
trust identities and their generations/expiry were preserved; the protected file
remained byte-identical. Scheduled-task triggers, limited privilege, duplicate
prevention and crash recovery are retained. The idle service was stopped via its
authenticated local API and restarted without browser popups or active previews.
No owner reassignment or broader access was granted. The previous scheduled-task
XML is retained privately for rollback. Never import it over a newer configuration
without checking its identity and the current task first.

## Combined local acceptance

- 130 focused unittest executions: editor, owner access, HTTP restrictions,
  preview/export isolation, V6 mappings/grants, companion and release gates.
- Three Node suites: exact-origin pairing, trusted renewal/revocation and selected
  task routing, locks and recorded evidence. Canonical Render topology check passed.
- Actual RELEASE draft in network-isolated Docker: synthetic login and OS navigation,
  mapped inspection, visual/source Save, preview refresh, Undo/recovery, stale-save
  and path rejection, synthetic database preservation, Desktop/Tablet/Mobile.
  All edited application source restored byte-for-byte; only that preview stopped.
- Disposable Edge 155.0.4283.45 local embedded UI: Save, Undo, Restore, Discard,
  history, tests, unsaved reconnect and 1440/1100/390 layouts; zero JavaScript errors.
  This is local browser evidence, not hosted/personal-profile acceptance.
- Combined preview cold startup 25.379s; save refresh 4.746s. Previous recorded
  baseline was 18.472s / 14.482s. Refresh improved about 67%; no startup improvement
  is claimed. Local embedded open 0.698s. These are single-run measurements.

Exact external evidence: .studio/v6-integration-plan-e9bca758.json,
v6-release-runtime-e9bca758.json, v6-release-ui-e9bca758.json,
v6-release-node-topology-e9bca758.json, v6-companion-upgrade-before.json and
v6-companion-upgrade-after.json. Machine paths, credentials and runtime records
remain outside source control. Original CORE acceptance evidence remains intact.

## Outstanding hosted gate and release procedure

The existing temporary HTTPS service srv-db5m140473hc73bkpi50 currently serves
V5 staging cc49cc46d4597091e9e735a48c914b8f34f4eb95, with auto-deploy off.
Its old three-asset wrapper cannot certify V6: the editor requires its four static
module/style assets and a narrowly scoped blob-module CSP allowance. Keep the
host authenticated, expiring and limited to static UI; connect-src remains none.
Do not add local filesystem, Git, Docker or provider endpoints to the hosted service.
A staging update and representative hosted browser checks remain pending.
Existing owner-reported V5 browser acceptance is preserved, not relabelled V6.

Before production: complete V6 hosted acceptance, confirm main has not advanced,
obtain owner approval for the exact tested RELEASE SHA, then use the existing
RELEASE procedure and canonical Render services. If main advances, integrate/test
a new immutable candidate before approval. Preserve worker configuration and
verify exact deployed app/worker revisions and owner-only Studio access afterwards.
Do not enable Real Publish or claim simulation receipts are production evidence.

## Hosted acceptance follow-up

Actual HTTPS testing found a timing defect: editor inputs were not locked while
an authorised file/selection reload was pending. A fast edit could be replaced
by the late response. Selection now uses the existing busy/disabled guard until
loading completes. The disposable UI acceptance holds a real file-open response
and verifies the fields stay disabled, then verifies Save/Undo/recovery and all
existing UI checks. No authentication, file scope or preview boundary changed.
The final candidate supersedes the first local merge; hosted acceptance must use
its exact updated editor bundle. Test-harness recovery additionally checks that
an editor journal entry was created by that test before attempting restoration.
