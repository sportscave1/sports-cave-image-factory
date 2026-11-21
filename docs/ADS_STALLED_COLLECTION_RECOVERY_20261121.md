# Ads collection recovery — 21 November 2026

Task: 20261121-7e6260d4. Owner: codex-ads-recovery-20261121.
User explicitly requested diagnosis, repair and pushing changes live.

## Incident evidence

Read-only production inspection identified the Lone Star Nine / Mike Modano
job in generating with verified receipts for ad_copy.csv, collector-hallway.jpg
and architectural-wall.jpg. Only man-cave.jpg was missing. The original chat
had finished and visibly displayed “Failed to download man-cave.jpg”.
The header continued to use the generic waiting-for-copy-and-three-covers label.

The observer matched only “Failed to download file”, missing the actual
filename-specific toast. The Library fallback recorded its receipt-search start
after the click acknowledgement; a download starting before that reply was
excluded. The latter is a reproduced protocol race, not a claim that browser
download history proves it happened on this particular click.

Live inspection additionally confirmed that the Library viewer for man-cave.jpg
renders its original 1024x1024 JPEG without any Download button. Its exact image
source is the selected Library file's same-origin content URL. The companion
now retrieves that displayed original when no Download action exists, requiring
the exact file ID, matching filename, full-resolution dimensions, same-origin
response, JPEG signature and existing server verification before accepting it.

Repeated status writes also refreshed updated_at, making some dependency and
posting timeouts ineffective. A native download remaining in_progress had no
deadline. These are independently regression-tested failure paths.

## Changes

- Recognize named download failures immediately and retain exact job, chat,
  response, file-name and content receipt checks.
- Start Library receipt searches before clicking. Bound native downloads and
  Library readiness waits; exhaust the existing three-attempt retry budget.
- After five idle minutes on a completed/partially collected response, request
  the existing one-shot original-file repair protocol in the saved chat. Restore
  missing files only. Preserve already received bytes, copy and targeting.
- Persist stage clocks independently of polling. Generation has a six-hour
  ceiling; an unleased posting checkpoint needs review after thirty minutes;
  consecutive dependency failure ends after two hours even when polls write.
- Explicit Play/resume grants a fresh observation window while preserving the
  original chat and deterministic posting identity.
- Display collected-cover progress and attachment recovery in the header.

The existing repair protocol permits at most two original-attachment repairs,
with a five-minute send-confirmation limit and thirty-minute response deadline.
No provider rejection is bypassed, no replacement artwork is invented, and
no ads are activated. Successful posting still requires three confirmed ads
and leaves them paused for review. External outages, unavailable originals or
provider rejections can require attention; unconditional success is impossible.
Queue advancement requires the paired desktop to be running and connected.

## Validation and release

Focused offline Python/real disposable PostgreSQL/browser contracts and Node
download tests cover partial delivery, missing Library controls, stuck native
downloads, fast Library receipt timing, restart persistence, duplicate-send
protection, targeting, same-ID posting, deadlines and releasing the next job.
Production providers are blocked by tests/ads_offline_guard.py.

Run python scripts/validate_render_topology.py before release. Deploy using the
existing main auto-deploy; do not sync or change the Blueprint or create services.
The installed companion must also be updated to 1.7.10 and reloaded in Edge.
