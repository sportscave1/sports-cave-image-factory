# Auto Editions V14 delivery investigation

Base: 9a3a5d28 (includes V13 813ac3fc, Files V6 and shared eligibility repair).
Scope: authenticated order-time delivery only. No image parameters, worker encoding,
prepared masters, mappings, allocations, Files component or V11 queue changes.

Reported V13 observations (not a controlled fresh A/B): request-to-Ready 16.49s,
click-to-download initiation 21.50s, completed download 28.31s, warm cached 6.54s.
These milestones do not share a starting point: request creation excludes start
endpoint authentication, artwork identity and part of enqueue latency.

Live baseline SC3291 #008, 9a3a5d28, 2026-10-14:
- Click client trace 11:10:24.886 UTC; inline feedback 0.3ms.
- Start response 4.2752s; server auth 1057.492ms, identity 1847.460ms,
  enqueue 1162.726ms; request total 4067.750ms.
- Job created 11:10:28.233670; Ready 11:10:44.432569.
- Job-created to Ready 16.198899s; click to Ready approximately 19.5466s
  (client/server UTC clock comparison, not a single monotonic clock).
- Initiation 21.392s from click; Ready to initiation approximately 1.8454s.
- Browser automatic file completed, but completion timestamp was read only in a
  later tool call: 33.287s upper bound, not an exact transfer duration.
- Independent warm cached download through authenticated fallback: 6.545s.
- Job 44ee703d61d4166147d6dd538c95c8b047e134ac30945afe6568bb491ae4f4fd,
  one attempt, 11340x8016, SHA256
  756f89f78e1db96163ad0146f1b0b1ac4b871e330e95d696d8a721f155db18c6.
- Worker: prepared retrieval 959ms; decode 3057.711ms; number 7.088ms;
  encode 1147.792ms; integrity 992.026ms; archive folder 2023.659ms;
  archive lookup 175.755ms; upload 2451.589ms; verify 301.730ms.

Changes:
- Suppress polling until start returns its bound job ID. Previously a timer could
  start a full artwork resolution during enqueue (observed first poll 4.7664s).
- Shorten polling cadence from 2500ms to 750ms; retain one in-flight poll per unit.
- Overlap independent current-account and bound job/allocation reads; require both
  to succeed before returning any private status/output. No permission caching.
- Preserve final account/allocation check after bytes and archive validation.
- Use 1MiB rather than 64KiB FileResponse chunks (bounded, same verified bytes).
- Fallback uses the same bound status endpoint, avoiding repeated source lookups.
- Add Ready observation and status timing evidence; no public artwork URLs.

Validation before deployment: 40 API/runtime/cloud/speed tests; 33 durable queue,
eligibility/onboarding/priority tests passed. Topology and focused diff checks passed.
Includes revoked-account denial during concurrent reads and final permission fence
with cached bytes. Real post-deployment results will be appended separately.
