# Resumable upload acceptance release

Owner explicitly authorised isolated real-provider acceptance and activation on
20 October 2026. This extends task 20261020-06c0d1d1, preserving the released
Phase 1–5 processing, colour approval, transfer settings and customer queue.

The prior release's missing isolated grant facility is addressed by a temporary
host-authenticated acceptance harness. It uses the existing Sessions protocol,
PostgreSQL schema, Dropbox upload-session adapter, independent package proofs,
immutable publisher and existing serial background worker. No new service or
customer job, allocation, product, certificate or PSD is created or changed.

## Isolation and controls

- New private `companion_acceptance_v1` schema; RLS enabled, no public/client
  schema/table access. Its connection sets only this schema in search_path; it
  cannot fall back to customer upload rows if the migration is missing.
- Endpoints are disabled by default and require an exact operator-configured
  32-hex `COMPANION_ACCEPTANCE_RUN`, a registered preparation host and the same
  current administrator/session checks as the existing host protocol. Run,
  owner and host binding is durable. Production create/grant/current gates are
  unchanged. No token, grant, signed URL or body is recorded as telemetry.
- Synthetic 1024×768 RGB fixture, embedded ICC, one master and 100 patches,
  independent first/last references and outside-number original proof. Under
  12 MiB, two practical 8 MiB protocol chunks, never a customer design. Server
  checks every synthetic pixel as well as the unchanged production unpacker.
- Dropbox paths are under the existing resumable staging root's
  `Acceptance/<run>` subtree. The ordinary provider adapter/publisher performs
  immutable publication. Every one of the 101 assets is independently downloaded
  and matched to its exact hash, ID, revision and byte count before isolated
  Cloud Ready. That status belongs to this test only, not a customer product.
- Inject one lost durable chunk acknowledgement and one lost finalisation
  acknowledgement. After the first, normal supervisor restart resumes the same
  on-disk journal inside the installed singleton. One shared controller and
  upload slot are used; no Photoshop process or competing companion is started.
- Publish and verify only the master, inject a retryable failure, then reuse its
  immutable receipt on retry. A second tiny test packet exercises expiry and
  recoverable provider cleanup while preserving the main accepted packet.
- The local diagnostic refuses active work, blocks customer claiming while it
  runs and blocks normal Close while transfer/checkpoint activity is active.
  Existing heartbeat thread and transfer controls remain independent. Maximum
  mode is preserved; a short safe-boundary pause is restored without switching
  modes. The interrupted diagnostic alone may restore after a normal restart.

## Local validation

43 focused acceptance/Phase 3/Phase 5 tests passed (59.38s), including disabled
and unregistered access, full package/ICC proofs, private SQL isolation,
lost acknowledgements, partial publication, immutable receipts, safe expiry,
busy-companion refusal and rejection of arbitrary protocol endpoint paths.
The new private-schema flow also passed separately against native PostgreSQL17
(4.49s), extending the retained seven native multi-process/crash tests. Test-only
fake metadata races and synthetic ID formatting were corrected before release;
no production integrity or source validation was relaxed.

Real-provider results are deliberately not asserted by these local tests.
The first real attempt exposed the generic download helper normalising a
permanent receipt ID into `/id:...`. It is corrected to preserve validated SDK
IDs, with focused positive/negative coverage; ordinary path downloads retain
their existing normalisation. The same retained isolated session is retried
after that fix, without sending the household packet again. This is why actual
provider acceptance is required before enabling normal admissions.
Runtime release/acceptance evidence is retained in the task's ignored
`output/companion-real-provider-acceptance/` directory. This includes exact
Git/Render/helper revisions and module hashes, real-provider receipts, durable
progress across restarts, transfer-only counters, pause/controls, isolated SQL
results, and a reviewed report. Do not infer acceptance from this document alone.

## Activation and rollback

Apply the private-schema migration after local checks. Release compatible code
(`20261020051839_companion_isolated_acceptance.sql` matches the applied
Supabase migration version; the CLI-created draft was renamed to that version).
backend first, then update the idle installed helper through the existing
supervisor/action-only startup update. Keep new normal resumable sessions
disabled during the isolated run. Preserve journals/settings/old immutable
helper and all customer state; leave failed-backlog recovery disabled.

Only after the actual provider checks pass, set acceptance marker
`provider-postgres-retention-v1`, exact generation, and SHA-256 of the reviewed
evidence report, then enable `COMPANION_RESUMABLE_UPLOADS_ENABLED=true`.
Verify normal negotiated capability with the installed host; repeat recognition
of the completed isolated session without uploading it again. Disable the
temporary `COMPANION_ACCEPTANCE_RUN` admission afterward. Retain the isolated
receipts/packet and private SQL evidence; no automatic deletion of required
accepted evidence. This harness is not an autonomous speed-test loop.

Rollback new admissions first, retaining schema, receipts, packets and compatible
recovery backend. Do not drop either schema, reinterpret old generation packets,
or downgrade partial sessions to legacy transfers. An unrelated newer main
change must be preserved during any rollback. No new Photoshop speed claim,
household connection calibration or attribution of the historical 288.020-second
interval follows from the existence of this harness.
