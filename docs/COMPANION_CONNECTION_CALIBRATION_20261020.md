# Bounded real-connection calibration — 20 October 2026

Task `20261020-06c0d1d1`, owner `codex/companion-phase4-20261020`, retained
Phase 4 worktree/branch. Starting released Git/main, all three active Render
services and installed immutable Windows companion: `5d06bf8482a74d3262c8cb53d21fa2f8b9e41482`.
Source tree was clean and the Studio registry matched before editing.
User explicitly authorised this isolated WAN measurement and final release.

## Method and limits

`scripts/calibrate_companion_connection.py` is an explicitly invoked diagnostic,
not an automatic saturation loop. It refuses any running companion process,
processor lock, active/checkpointed job, or a starting selection other than
Maximum speed. The idle companion was stopped through its normal authenticated
supervisor after its native busy guard cleared; nothing was killed. An outer
`finally` restored its unchanged scheduled supervisor after the test.

Maximum remained selected throughout measurement. A separate **non-persistent**
instance of the released streaming controller ran one upload at a time. Three
uncapped observations preceded two candidate-cap trials, never concurrently.
One reproducible random 8 MiB disposable file was sent to Cloudflare's documented
`https://speed.cloudflare.com/__up` receiver; no customer/provider destination,
credentials, artwork, orders or jobs were involved. Its synthetic file was
removed afterward. Maximum budget: five requests / 40 MiB application payload,
240 seconds; no upload retries. Actual total: **41,943,040 bytes**, all five HTTP
200 responses, zero retries. Request duration includes connection/receiver
response time and is deliberately conservative; it is **application goodput**,
not measured raw wire capacity or a signed Sports Cave durable receipt.

Independent small HTTPS probes used Cloudflare's zero-byte download and the
actual OS `/_stcore/health` route. Five idle samples per target preceded the
uploads; loaded probes ran only while application body handoff was active.
Counts were bounded. Headers containing public IP/location and response bodies
were not retained. Warm connections and time-varying network conditions are
confounders; this is a sequential operational calibration, not a randomised
household study. No human browsing, other-device responsiveness, router counters
or Dropbox desktop traffic were measured. The cap only governs companion traffic.

Cloudflare's endpoint is documented in its primary-source
[speed-test configuration](https://github.com/cloudflare/speedtest/blob/main/README.md).

## Observations

| Selection in test controller | Payload per trial | Seconds | Application Mbps |
| --- | ---: | ---: | ---: |
| Uncapped 1 | 8,388,608 | 17.653 | 3.802 |
| Uncapped 2 | 8,388,608 | 14.075 | 4.768 |
| Uncapped 3 | 8,388,608 | 17.649 | 3.802 |
| Candidate cap 1 | 8,388,608 | 26.422 | 2.540 |
| Candidate cap 2 | 8,388,608 | 26.595 | 2.523 |

Three uncapped samples lasted 14–18 seconds each; their max/min ratio was 1.254
(below this diagnostic's 1.35 rejection threshold). Use the slowest successful
observation, rounded down: **3.8 Mbps**, rather than the peak. With existing
25% headroom, Balanced's aggregate allowance is **2.85 Mbps = 356,250 bytes/s**.
The released bucket's burst bound at that rate is 16,384 bytes. Both real capped
requests respected `sent <= allowance × elapsed + burst`; achieved goodput was
below the upper bound. This check covers request-average application traffic;
it does not observe sub-window packets/bursts at the remote NIC. Existing local
receiver tests cover controller pacing and bounded bursts.

| Small HTTPS target | Idle n / median / p95 ms | Uncapped loaded n / median / p95 ms | Capped loaded n / median / p95 ms |
| --- | --- | --- | --- |
| Cloudflare edge | 5 / 63.392 / 363.546 | 40 / 138.696 / 235.110 | 32 / 73.661 / 119.368 |
| Sports Cave OS health | 5 / 237.590 / 488.923 | 40 / 277.918 / 387.486 | 32 / 192.610 / 264.534 |

No probe failed. Capped versus uncapped loaded medians were 46.9% lower at the
edge and 30.7% lower at OS health. These observations support the conservative
initial cap; they do not prove a causal browsing improvement. Idle samples include
cold setup and are small, so their p95 should not be treated as stable tail latency.
Observed payload speed is intentionally lower under Balanced. This is a headroom
trade-off, not a new upload-speed claim. Historical 288.020 seconds remains unknown.

## Live application and preservation

Only after both capped trials were reviewed, the existing authenticated Worker
Health controls requested Balanced with measured basis 3.8 and headroom 25.
The installed helper persisted **`request_5674`**, Balanced, unpaused; background
25%, manual/download caps blank. The source label remains honestly **Operator
supplied**: this is a reviewed external measurement, not a qualifying production
transfer observation. No receipt counters/server receive timings were invented
to train the automatic policy. Recheck this operator-supplied basis after an ISP,
connection or substantial network change; it has no automatic age expiry.

All **392 prior customer job journals** remained byte-identical. No active
Photoshop job was interrupted, no failed backlog enabled, no design retried.
Normal resumable admissions remain enabled under the existing accepted generation
and report hash; the temporary real-provider acceptance harness stays disabled.
No generation, package, recovery, publication, colour approval or quality code
changed. The production controller and its existing independent control traffic,
single upload slot, burst bounds and chunk-boundary pause remain intact.

## Deliverables and verification

New files: this report and `scripts/calibrate_companion_connection.py` only.
Seven offline acceptance/rejection/summary checks passed before network use.
Focused transfer/Phase 4/Phase 5 regressions: **35 passed, 5 skipped, 3 deselected**
in 28.77 seconds. Skips require the optional database fixture; this documentation/
diagnostic-only change does not alter durable sessions. Deselection excludes
unaffected publication/session paths. Existing provider acceptance remains valid.
Studio Verify, topology and whitespace checks passed. Live Worker Health showed
**Effective: Balanced / Limited / 2.85 Mbps / Running**, with Operator supplied
3.80 Mbps; the acknowledged screenshot and AX state are retained.
The bounded WAN result itself is retained at
`output/companion-balanced-calibration/wan-trial/measurements.json`, with individual
sanitised traces/probes and preservation assertions. Release/acknowledgement,
focused regression results and final runtime revisions are retained alongside it.

Final release contains the diagnostic and report, with all previous speed changes
preserved. Do not interpret this document alone as runtime release evidence; use
the retained final rollout/heartbeat/UI records. Unfinished unrelated Studio
worktrees are excluded, and the intentionally suspended daily cron stays suspended.
Next tuning work should use passive normal-transfer and loaded/idle observations;
no new saturation loop or settings dashboard is warranted by this result.
