# Edition Companion repair procedure

Orders and Edition Ops use **Repair** for failed/review states. Clicking it
creates one durable request in `auto_edition_onboarding_audit`, scoped to the
existing product, mapped PSD and (from Orders) saved allocation. **Repairing**
remains visible during diagnosis, preparation, upload, technical verification,
and JPG generation. Opening a status page without clicking Repair is read-only.

The existing Render cloud worker diagnoses one request at a time. It resumes a
deferred checkpoint, queues a verified changed revision through the existing
replacement pipeline, or uses the existing guarded retry/export repair. It
retains the mapping, old packages, original error history and all allocations.
Every native preparation still runs through the installed Photoshop singleton
and its processor lock. No additional Render service or schema is required.

Structural, font, colour or unresolved validation failures enter the Edition
Companion's durable Codex outbox. The installed Companion submits the pinned
diagnosis prompt to the configured existing Codex chat using `codex exec resume`.
The prompt includes only edition/source identities and technical details, with
no customer information, credentials or transfer grants. It requires an isolated
Studio task, the Edge extension for live diagnosis where useful, preserved PSD
backups, unchanged-artwork proofs, and authoritative queue verification. It does
not authorise code commits/deploys, colour assumptions or invented approvals.

Configure this computer once in
`Documents/SportsCaveAutoEditions/edition-repair-target.json`:

```json
{
  "thread_id": "01a1fb74-41fa-7893-a9fe-6147c82ecf39",
  "cwd": "C:/Dev/SportsCaveWorktrees/sports-cave-editions"
}
```

Codex must already be installed and signed in. Its existing permission and
sandbox configuration is retained. The Companion encrypts handoff capabilities
with Windows user-scoped DPAPI, saves local execution receipts, and acknowledges
results to the authenticated preparation-host endpoint. An uncertain launch is
never launched twice. A single Codex attempt is permitted per repair request;
unresolved/expired work becomes **Repair** with the retained prompt available
in the status page. This is an escalation mechanism, not a guarantee that every
unknown PSD can be repaired without owner input. An unconfigured/offline
Companion retains the pending request for later processing.

Codex returning successfully does not mark a design fixed. The cloud worker
requires real `Cloud Ready` evidence and, for the selected Orders allocation,
an actual `Ready` JPG job. Only then does the request complete and Orders return
to the normal **Open** link. A mapping change stops the original request.

## 21 November 2026 scoped recovery

- The Captains, product `15396974854451`, order `SC3520`, allocation `950`:
  old preparation was deferred (`priority=0`), then technical verification
  confirmed missing source ICC evidence. The owner explicitly approved sRGB
  interpretation for this exact PSD. The repaired copy embeds that ICC while
  preserving the original layer bytes; the original is backed up. Verified
  replacement content hash:
  `1da063f995329d310045c0393b7e01c4a2fd496bf335b85f41c7438307d413b8`.
- Pray for the Bear, product `8882143756595`, order `SC3517`, allocation `945`:
  historical digit-width rejection and absent recognised number backing.
  The current formatter handles the existing two-digit field growing to 100.
  A backing copied from the exact number-hidden composite was added beneath
  the editable number. Full RGBA before/after composites are pixel identical;
  the source profile, text, font and artwork remain intact. Verified replacement
  content hash:
  `76742ce248810c430474b721637c8eb4e4b797c92c6e81f4613de16207373277`.

Local source backups and verification evidence are retained under
`output/edition-repair` in Studio task `20261121-da49129f`. Both existing Dropbox
file IDs and product mappings are preserved. Certificates and fulfilment are
separate and are not modified by these repairs.
