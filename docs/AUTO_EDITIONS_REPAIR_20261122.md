# Orders repair and automatic editions — 22 November 2026

Owner requested diagnosis, repair of all eligible failed editions, automatic numbering, and Git/Render release. Owner explicitly selected sRGB for the three failing order PSDs and all future missing-profile editions.

## Diagnosis

The three screenshot products had no embedded ICC and no approved source membership. Repairs reached `Codex queued`, but the background companion inherited a PATH without Codex and silently returned without claiming. Orders read the repair audit; the header read only the underlying failed preparation.

Unfinished Business already has sRGB. Its pinned source hash is `81dee004554928c1163dd62398303fdee07646b67e18a9598d40e23460a36f35`. Both native Open and scripting reject it. Its linked-data table retains three unused historical embedded assets, including old generative PSBs. Removing only those unreferenced entries makes Photoshop open it while retaining the referenced plaque and editable number. A Photoshop PNG export of the byte-repaired candidate is pixel-exact against the original saved composite (2835 × 2004). Original Dropbox source and local original remain unchanged.

## Behavior

- Bounded repair admission reuses the durable audit, excludes active leases and unresolved mapping/reset work, and respects Pause.
- Companion discovers the registered Codex desktop package when inherited PATH is stale and reports unavailable handoffs.
- The header reflects the repair audit instead of presenting its previous preparation error as current progress.
- Cloud Ready repair queues every valid outstanding assigned allocation, retaining per-unit blockers and requiring actual Ready results before completion.
- Owner-approved sRGB is the fallback for missing-profile RGB8 sources, with exact prior approvals taking precedence. Tagged sources retain their ICC. Unsupported modes/depths and conflicting/malformed profiles still require correction.
- Staged PSD cleanup removes only unreferenced embedded history. Raw layer records/channel data, masks, text, referenced object bytes, ICC/resources and saved composite are copied unchanged. No source PSD, mapping, allocation or issued edition number is edited.

## Validation

102 focused tests passed before final release verification, including disposable PostgreSQL admission/status/JPG cases, local executable discovery, byte-preserving profile assignment, synthetic PSD cleanup, native preflight and preparation-host tests. Native Unfinished Business opening and pixel-exact PNG comparison passed. Render topology validation passed. Additional backlog, recovery and catalogue checks recorded with the Studio task.
