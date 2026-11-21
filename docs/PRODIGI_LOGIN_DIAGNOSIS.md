# Prodigi login diagnosis — 21 November 2026

Observed in the user's live Edge login at
`https://dashboard.prodigi.com/login?redirect=%2Fdashboard` around 02:10 UTC.

The user clicked Continue; the page waited and displayed **An error occurred**,
**Code: 0**. Edge's Console showed:

- `https://live-services.pwinty.com/auth/api/auth/refresh`:
  `net::ERR_CONNECTION_RESET`.
- `https://live-services.pwinty.com/auth/api/auth/validate`:
  `net::ERR_TIMED_OUT`.

A separate unauthenticated HTTPS connection from this computer to the observed
authentication host timed out at the connection stage. The dashboard HTML itself
returned HTTP 200. Local DNS and an independent Google public DNS answer both
resolved the authentication host through Azure to `23.102.34.174`. The user
confirmed their worker experiences the same failure from a different network.

This is evidence of authentication-service connectivity failure, not evidence
of an invalid print API key. The direct request had no key, cookies or account
data. Two affected networks make an upstream service/routing problem more
likely, but do not prove a global outage. No official login-outage incident
confirmation was available. The supplier must restore its service/network path;
changing the Sports Cave OS print API code cannot repair that remote endpoint.
At this stage login success had not been verified.

A recheck at approximately 02:15 UTC reached the same authentication endpoint
in 0.9 seconds and received HTTP 404 for an unauthenticated GET. This is a
connectivity recovery signal (the login validation method is not GET), not a
successful login. The user was asked to retry Continue in the existing Edge
tab. No OS deployment, cookie clearance, credential change or API-key change
occurred between the failed connections and that recovery signal.

The user subsequently confirmed login was working again. A fresh, read-only
dashboard visit also showed the authenticated Prodigi dashboard and existing
orders. No deployment, account change or credential change was made to achieve
that recovery. The diagnosis therefore records recovery, not an OS fix to the
supplier's authentication service.

## Separate confirmed OS navigation defect

The live Fulfilment dashboard button contained a hard-coded old Shopify
connection callback, including one-use OAuth state/code/timestamp. That is an
installation/connection flow, not a reusable dashboard bookmark. The task
replaces it with `https://dashboard.prodigi.com/`. Do not replay the old callback
to test it. The direct login error is a separate issue; the stale button alone
does not explain failure at the normal login URL.

The correction is local only until a separately authorised release. The new
Orders companion is also local only and disabled; it was never run against
Prodigi and cannot have caused this observed production login failure.

## Isolation safeguards

- The print adapter is server-only and addresses `api.prodigi.com/v5` only.
- The adapter allowlists order GET and draft item-artwork PATCH paths. It has no
  authentication, password, submit, resume, order-create or payment operation.
- Provider redirects are refused; provider cookies are neither stored nor sent.
- The Orders extension calls the OS queue endpoint with its paired device
  credential, `credentials: omit`. It does not call Prodigi or its login host.
- The Companion manifest grants no Prodigi/Pwinty content-script access,
  cookie permissions, request interception or request-blocking permissions.
- Credentials, security settings, browser cookies, account/session settings and
  Prodigi sales-channel connections were not changed during diagnosis.

Regression tests cover the clean dashboard URL, allowed API paths, cookie
policy, redirect refusal, extension isolation and safe queued retries.
