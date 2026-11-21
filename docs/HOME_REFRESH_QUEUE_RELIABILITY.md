# Home refresh queue reliability — 19 November 2026

Task/owner: `codex/home-refresh-queue-reliability`, current Codex chat.
User explicitly authorized Git push and Render deployment.

Production logs showed four successful `action=add` requests at 04:26–04:27
UTC. That action saved the shortlist only; it did not insert queue jobs.
No `home_refresh_queue_failed` entry was returned for the inspected period.
The companion continued returning successful design ticks.

The catalogue picker now submits `enqueue` directly. A committed save emits the
existing companion wake event and refreshes the header. Display caches are
invalidated after commit. Optional status failures cannot turn a committed save
into an unsuccessful acknowledgement. Explicit pause is retained, with a Play
button and offline feedback in the dialog.

Status polling reads at most 40 job identities per request, cycles through loaded
pages, runs faster for active work, and stops when the dialog closes or the tab
is hidden. It does not scan Dropbox or the catalogue. Query time is bounded by
the existing read-connection watchdog. Product selection uses an exact indexed
lookup, and prompt generation happens outside the shared desktop claim lock.
Existing idempotency, deletion checks and retry output identities are retained.

Validation used synthetic PGlite data and mocked browser routes:

- `python -m pytest tests/test_home_refresh_queue.py tests/test_morning_design_queue.py tests/test_companion_queue_controls.py -q --disable-warnings`: 78 passed.
- After the final picker change, `python -m pytest tests/test_home_refresh_queue.py -q --disable-warnings`: 19 passed.
- `node tests/test_companion_status_polling.cjs`: passed.
- `node --test tests/test_morning_design_companion.cjs`: 7 passed.
- Python AST syntax check, `git diff --check`, and `python scripts/validate_render_topology.py`: passed.

No schema, service topology, extension package, or artwork prompt changes.
