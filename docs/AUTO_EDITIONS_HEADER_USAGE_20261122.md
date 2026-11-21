Auto Editions header usage controls — 22 November 2026

The bottom of the Auto Editions status popup now offers the existing Balanced,
Background, Maximum and Manual transfer modes, upload/download Mbps settings,
and safe Pause/Resume for the preparation queue. The current saved mode is read
on open; displaying the panel never sends a settings change. Photoshop processing
speed is not changed by network bandwidth settings.

Controls use the existing authenticated, same-origin, audited Worker Health write
endpoint. A bounded admin-only GET reads only queue pause state and the latest
Companion heartbeat/request; it does not rebuild Worker Health or scan jobs.
There is no additional background polling, provider request or companion restart.
Requests have a 15-second timeout, immediate busy feedback and duplicate-click
protection. Refresh/reopening reads acknowledgement; dirty edits survive refresh.
Uncalibrated Balanced/Background requires a measured upload rate, preventing a
silent transfer stall. Queue pausing allows current work to finish safely.

Validation: 58 focused Python/browser tests passed (Worker Health, shared header,
usage controls and top bar); Studio static/unit/secret checks and Render topology
validation passed. Browser tests cover preserved defaults, manual caps, no writes
on opening, dirty form refresh, pending acknowledgement, duplicate clicks, failed
requests/retry and safe pause/resume. Synthetic fixtures only.
