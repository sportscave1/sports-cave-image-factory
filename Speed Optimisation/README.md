# Speed Optimisation

Daily execution is assigned to Codex's native local scheduler, at 01:00
Australia/Sydney, GPT-6.1 Sol with medium reasoning (the third setting in the
provided screenshot). No clipboard bot, second Render primary or additional
always-running companion is required. The computer and Codex must be available
for local scheduled execution; this is not an always-on cloud service.

Installed automation: `speed-optimisation-daily-1am-sydney`, active, daily at 1am.
Its Codex project entry is the existing Sports Cave OS project; its instructions
explicitly select this isolated coordination folder and prohibit editing the
unrelated task behind the project entry. A separate sidebar project has not been
registered. Successful-run notifications are muted; failures remain visible.

Read `DAILY_TASK.md` at the start of every run. This directory is the permanent
coordination folder, not a shared coding checkout. Allocate one Studio task per
improvement; retain unfinished tasks and use their recorded owner for follow-up.
Runtime history and queued publication payloads belong in ignored
`.local-data/speed/`, not source control. Never store credentials or customer data.

The local implementation adds Developer → Speed Optimisation and an owner-session
publication form at `/ops/speed/publish`, plus `/api/speed/reports` for history.
Reports use individual immutable keys in existing `app_settings`; no new table,
schema migration or Render service is needed. Publishing a report cannot execute
code, change configuration or trigger deployment.

Before enabling automatic releases, the exact source base must be reconciled
with current production and safe synthetic workflow/browser checks must exist.
The initial task's approved Studio base is `7f9f617e2bce2f150d51561c2f0873412312b036`;
GitHub main observed on 21 November 2026 was
`106c611462c3832c7734762c87e677bde7d1f031`. They must not be treated as identical.
Preview is disabled under the current Studio policy. A report must expose these
blockers, and cannot label a proposed change live or verified.
