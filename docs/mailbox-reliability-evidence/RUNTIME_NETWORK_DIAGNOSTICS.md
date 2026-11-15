# Read-only actual Render runtime diagnostics — 26 October 2026

## Result

The actual live primary instance currently reaches both IMAP 993 and SMTP 465 over IPv4, with valid TLS and the expected Axigen greetings. IPv6 DNS succeeds, but TCP immediately returns Linux errno 101 (`ENETUNREACH`) for both ports. A control probe from the existing paid worker has the same result. This is current runtime evidence, unlike the earlier Windows-only greeting probe.

This supersedes any assumption that an IPv4 TCP block is still continuously present. It does not identify the cause of the previous timeouts, prove mailbox authentication/ingestion has recovered, or resolve the October 7 unknown send. No authentication or SMTP submission was attempted.

## Identity and method

- Existing primary `sports-cave-os`: `srv-d8kl4on7f7vs73dvavv0`, instance `srv-d8kl4on7f7vs73dvavv0-75d57c5f9d-9ch8w`, Standard, Oregon, one instance.
- Existing supporting `sports-cave-seo-worker`: `srv-d9ujm9navr4c73amurgg`, instance `srv-d9ujm9navr4c73amurgg-79b85fbdd6-r8dzc`, Starter, Oregon, one instance.
- Both runtime environments identify live commit `5980a803e5c0073f2e430b7d8e495e10c9b7d78d`.
- Primary sample window 00:01:32–00:01:38 UTC (11:01 Sydney); worker 00:05:01–00:05:04 UTC (11:05 Sydney).
- Used the signed-in Render Dashboard Web Shell on these existing instances. MCP has metadata/log access but no remote-execution capability; no local SSH key/agent or Render CLI was configured. No keys were created or installed. No ephemeral instances, one-off jobs or new services were created.
- Primary: two serial samples per protocol/family, eight attempted connections maximum. Worker control: one sample per protocol/family, four attempted connections. Only one diagnostic connection at a time, 0.5 seconds between samples; five-second SIGALRM/socket deadline per stage. All probes completed and closed their sockets.
- DNS: separate AF_INET/AF_INET6 `getaddrinfo` calls. TCP: connect to the returned address directly, excluding DNS time. TLS: default verified SSL context, SNI and hostname validation, handshake measured separately. Greeting: bounded recv up to first newline/4096 bytes. No provider protocol commands were sent; no login, SELECT, AUTH, EHLO, envelope or DATA.
- DNS measurements include normal resolver caching; no cold-DNS claim. TLS context creation is outside handshake time. These are stage timings, not end-to-end application latency.

## Measurements

Milliseconds. Primary values are medians of n=2, not meaningful p95 estimates. IPv6 TCP values time the immediate failed attempt; TLS/greeting are unattempted, not zero.

| Primary protocol/family | DNS | TCP | TLS | Greeting | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| IMAP IPv4 | 2.601 | 157.664 | 320.747 | 13.036 | 2/2 success |
| SMTP IPv4 | 3.145 | 156.855 | 320.198 | 5.318 | 2/2 success |
| IMAP IPv6 | 2.974 | 0.053 | — | — | 2/2 ENETUNREACH |
| SMTP IPv6 | 3.763 | 0.047 | — | — | 2/2 ENETUNREACH |

| Worker control, n=1 | DNS | TCP | TLS | Greeting | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| IMAP IPv4 | 7.810 | 156.441 | 318.869 | 2.995 | success |
| SMTP IPv4 | 60.390 | 156.148 | 320.242 | 0.561 | success |
| IMAP IPv6 | 4.008 | 0.090 | — | — | ENETUNREACH |
| SMTP IPv6 | 1.750 | 0.065 | — | — | ENETUNREACH |

Resolved IPv4 `110.232.143.200`, IPv6 `2400:b800:8::200`; one address per family was returned in these samples. Successful connections negotiated TLSv1.2. IMAP greeting `* OK AXIGEN IMAP4rev1 service is ready`; SMTP primary `220 fe.s3.ax.email Axigen ESMTP ready`, worker `220 fe.s1.ax.email Axigen ESMTP ready`. Distinct frontend labels behind the same address are not proof of configuration drift.

Raw transcribed samples, timestamps, endpoint settings and method are in `runtime-network-samples.json`. The existing primary network namespace showed two established IMAP sockets and no SMTP sockets after probes completed. This one aggregate snapshot is not a provider-wide/account-wide connection count. The kernel's `disable_ipv6` value is 0; errno 101 indicates unusable routing, not a DNS failure or evidence that this sysctl disables IPv6.

## Restrictions, limits and configuration

The current service is paid Standard; the control worker is paid Starter. [Render's free-service documentation](https://render.com/docs/free) blocks SMTP 465/587 for free web services and port 25 for all services. The free SMTP restriction does not apply to either tested service, and the IPv4 465 successes directly demonstrate current reachability. The free webhooks service is a separate supporting service; it was not used for mailbox diagnostics. No port 25 or 587 probes were performed.

The primary service's Dashboard Connect → Outbound view lists **74.220.48.0/24 and 74.220.56.0/24**, shared regional egress ranges. [Render documents regional shared outbound IP ranges](https://render.com/docs/outbound-ip-addresses); exact public NAT IP per connection was not independently measured. Service metadata's `0.0.0.0/0` IP allowlist describes inbound access, not a proof of unrestricted outbound routing. No allowlists, firewall rules, plan, region or IP allocation were changed.

[Render documents outbound routing changes that can reset long-lived connections](https://render.com/docs/outbound-connection-resets). This is a possible operational mechanism, not evidence that it caused the observed history. Older logs show repeated TCP timeouts around 8.1–8.4 seconds on old instance `ptdzp`, including 25 October 22:22:34 UTC while the release rolled over. Current instance `9ch8w` has periodic IDLE `idle_done` BYE reconnect warnings at 22:42:10, 23:02:32, 23:22:53 and 23:43:15 UTC, about 20 minutes apart. These later protocol-stage disconnects differ from the previous pre-auth TCP failure. No disconnect cause should be inferred without provider session logs.

Read only the six non-secret endpoint variables from the live primary process environments (PID 1 launcher and PID 60 application): both explicitly use `ventraip.email`, IMAP 993/SSL true and SMTP 465/SSL true. The worker supervisor (PID 1 launcher, PID 39) and CRM child (PID 42) leave all six unset. Released code defaults are the same endpoints and SSL modes. Password/token values were not output, compared or saved; credential equivalence is unverified and was not necessary for the pre-auth network measurements.

Architecture review confirms the primary's `IdleLifecycle` starts the mailbox IDLE watcher, inbox index and outbox threads. The separate Render worker starts the CRM supervisor; it is not the mailbox polling/outbox host. Thus its unset mailbox endpoint variables do not demonstrate a misconfigured mailbox worker. The app's IMAP connection runtime serialises short operations within a process, permits at most six background starts per minute, and releases that short-operation admission slot after IDLE establishment. SMTP is separate. This budget is not a global limit across processes/services or other devices sharing the mailbox.

[VentraIP's official configuration guide](https://ventraip.com.au/support-centre/troubleshooting-email-client-problems/) matches the observed endpoints and secure ports. No numeric concurrent-connection limit for this particular VentraIP Axigen service was established from official public material. cPanel defaults are not applicable evidence for the observed Axigen service. No provider admin/firewall/session logs are available in this session. Successful unauthenticated greetings rule out a blanket current IPv4 block for the sampled routes, but do not rule out intermittent bans, per-account post-auth limits, per-IP quotas shared with other customers, or different historical NAT routes. Exact limit/ban history and the regular IDLE BYE cause require provider-side evidence keyed to the UTC timestamps and Render egress ranges. No provider support message was sent.

## Local/live status

Only evidence documents were added locally in task `20261025-35ed7e58`; existing implementation remains preserved. No runtime application imports, mailbox reads/writes, sends, service changes, restarts, commits, pushes or deployments. No production credentials copied into a local preview. Previous local code fixes remain unpatched live until an authorised release.
