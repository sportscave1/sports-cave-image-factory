# Ads companion interruption and recovery — 23 November 2026

Task: `20261123-71e91205`; owner: `codex-companion-offline-20261123-01a20263`.

## Observed outcome

Bound in Gold — Sam Kerr & Mary Fowler finished at 13:11 AEDT. The posting receipt
and queue checkpoint both read `COMPLETE`; all three ad receipts are `PAUSED`.
The Ads dashboard shows Companion online, Queue playing, zero running and zero
waiting. The existing campaign and ad set were retained:

| Object | ID |
| --- | --- |
| Queue job | d52a5d43-3f5d-5349-9f94-818e3ed6e55c |
| Posting submission | 5f123db0-3718-5513-ba3f-25f55e72048a |
| Campaign | 120251137439630554 |
| Ad set | 120251137440040554 |
| Existing ad 1 | 120251137443450554 |
| Existing ad 2 | 120251137450330554 |
| Completed ad 3 | 120251137660240554 |

The operation did not activate ads or change budgets. It used the canonical
Render service `sports-cave-os` (`srv-d8kl4on7f7vs73dvavv0`).

## Diagnosis

- The Edge companion was installed at version 1.7.48 and continued polling every
  30 seconds. Render logs showed repeated Ads poll 503 responses. A successful
  queue transaction was required to commit its heartbeat, so contention could
  display a connected browser as offline. The shared desktop credential row was
  also locked while claiming unrelated queue work. Long browser transfers could
  suppress the regular poll and its heartbeat.
- Render deployed 9021302 at 12:38 AEDT while this posting run was starting. The
  old instance stopped advancing after two confirmed paused ads; its posting
  lease expired at 12:42:57. Every provider write intent had a confirmed outcome.
  This is consistent with interruption during the deployment, rather than a
  disconnected Windows Photoshop worker.
- Both queue and reservation logic imposed a 30-minute delay on an interrupted
  nonterminal posting receipt, even after its lease expired.
- Recovery then failed deterministically in `SupabasePostingStore.reserve`.
  Its parameterized SQL contained literal `%` wildcards. The real psycopg driver
  rejected the query before PostgreSQL could run it. The previous disposable SQL
  adapter did not apply psycopg's placeholder parser and missed this defect.
- Resuming the saved ads exposed the previously diagnosed optional `enhance_cta`
  omission. Live read-back confirmed this enhancement was absent on both saved
  creatives, with every required feature passing. The earlier local fix had not
  been deployed.

## Permanent local changes

Authenticated Ads contact commits independently of queue claims and uses short
transaction timeouts. A contact-only poll cannot claim work, and an alarm can
send it while a long browser transfer is in progress. Actual queue claims retain
their durable Ads lease. Temporary 503 responses receive bounded, staggered
retries of the same checkpoint; unknown network outcomes retain the existing
reconciliation path.

An expired posting lease can resume confirmed operations promptly. A reservation
that has not yet received a lease retains a two-minute grace period. Running
workers, active leases, unknown write outcomes and terminal receipts remain
protected. The two SQL wildcard patterns are bound as parameters. Only omission
of the optional CTA enhancement is tolerated; explicit conflicting values and
every required artwork-protection flag still fail verification.

The prepared companion package is version 1.7.49. Its production candidate is
based on `2914f4e7555163005d23c59a83266f3fb59984e6`, preserving the newer order
companion files, manifest permissions and production queue concurrency limiter.
The isolated task branch itself started from Studio's older approved base; use
the reviewed production patch to integrate these changes, rather than replacing
production files with the entire older checkout. Recheck current production HEAD
before an authorized release.

## Operational safeguards and evidence

A guarded SQL operation first saved a full before-image, then made only this
expired submission eligible for the existing recovery path. Recovery snapshots
remain in `app_settings` under `companion_recovery:20261123-71e91205`, with `:shell`
and `:optional-cta` records for the two reviewed shell attempts. The first attempt
stopped at creative verification. The second used process-local versions of the
two confirmed fixes, verified the existing IDs, and finished the saved campaign.
No production source files were patched by these scripts.

Local operational scripts, the production patch, a complete extension archive,
test logs and the completion screenshot are in `output/companion-recovery/`.
Those artifacts contain no production credentials. The operational scripts are
specific to this job and reject changed identities, active leases, cancellation,
unknown writes and repeat recovery attempts.

Validation completed:

- Task checkout: 230 Python tests and 25 subtests passed.
- Candidate on the current production lineage: 231 Python tests and 25 subtests
  passed, including extension package completeness.
- 15 JavaScript tests passed, covering polling, long-transfer contact, uncertain
  sends, deadlines, worker lifetime and queue wake behavior.
- Real psycopg query adaptation ran before the disposable PostgreSQL retry tests.
- The production patch applied cleanly to a temporary Git index of the recorded
  production base. `git diff --check` passed.

The current ad run is recovered. On 23 November 2026 the user explicitly
authorized committing, integrating, pushing and deploying the permanent repair,
and updating the installed companion to 1.7.49. Release verification receipts
are recorded separately in `output/companion-recovery/`. No local preview used
production credentials or provider writes. External services, an awake desktop
and a signed-in Edge session remain operational dependencies.
