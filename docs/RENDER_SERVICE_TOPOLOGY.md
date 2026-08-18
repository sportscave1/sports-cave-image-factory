# Production Render service topology

Verified on 18 August 2026 against the Render dashboard, service events, the
active Blueprint resource list, and live health/log evidence.

## Canonical services

| Role | Render name | Immutable ID | Ownership | Production endpoint / command |
|---|---|---|---|---|
| Primary Sports Cave OS web app | `sports-cave-os` | `srv-d8kl4on7f7vs73dvavv0` | Preserve as an existing service; do not declare or rename it in `render.yaml` | `https://sports-cave-image-factory.onrender.com` |
| Shopify webhook receiver | `sports-cave-os-webhooks` | `srv-d9146onlk1mc739nrm7g` | Blueprint `sports-cave-image-factory-prod` | `https://sports-cave-os-webhooks.onrender.com` |
| SEO reporting worker | `sports-cave-seo-worker` | `srv-d9ujm9navr4c73amurgg` | Manually managed with repository auto-deploy | Background worker |
| SEO daily sync | `sports-cave-seo-daily-sync` | `crn-d9ujqvvqj5pc73fpe0ag` | Manually managed with repository auto-deploy | `python google_seo_import.py daily` at 18:30 UTC |

Repository: `sportscave1/sports-cave-image-factory`. Production branch: `main`.
The visible product name “Sports Cave OS” does not determine the Render service
name and must never be implemented by creating or renaming infrastructure.

Render still displays a legacy “Blueprint managed” badge on the canonical
service page, but the Blueprint's live Resources table no longer contains that
service. It contains only the duplicate primary and the webhook receiver. Until
Render's stale ownership metadata is explicitly reconciled, the repository
must treat the canonical service as an existing external resource and must not
ask a Blueprint sync to recreate or replace it.

## Duplicate incident

The service `sports-cave-image-factory` (`srv-da1tkqflk1mc73aavi00`, URL
`https://sports-cave-image-factory-rnb7.onrender.com`) was created by Blueprint
sync `exe-da1tkqad0e5s73epppj0` for commit `64b9aad` on 18 August 2026. The
Blueprint explicitly reported “Create web service sports-cave-image-factory”.
It is not the canonical primary app: it is a Free service, while the established
`sports-cave-os` service is Standard and owns the established production URL.

The duplicate must remain out of `render.yaml`. Suspend it only after the
canonical primary, webhook receiver, Orders page, and Orders badge have been
verified healthy. Permanent deletion additionally requires confirmation that it
has no unique domain, traffic, environment, disk, callback, or dependency.

## Blueprint ownership and deployment

The Blueprint `sports-cave-image-factory-prod`
(`exs-d8kl46v7f7vs73dva7f0`) owns only `sports-cave-os-webhooks`. The canonical
primary, SEO worker, and SEO cron are existing externally/manually managed
resources and auto-deploy from `main`; declaring them in the Blueprint would
risk recreating or replacing production infrastructure.

Before every Blueprint sync:

1. Run `python scripts/validate_render_topology.py`.
2. Inspect the Blueprint preview.
3. Reject any preview that creates a primary web app or changes the canonical
   primary identity.
4. Confirm the preview preserves exactly one webhook receiver and does not
   propose another `sports-cave-os` or `sports-cave-image-factory` web app.
5. Never add a migration or schema verification command to a Free service’s
   pre-deploy step. Render rejects pre-deploy commands on the Free tier.

Normal application deployment follows the established auto-deploy from `main`.
Do not commit, push, or manually deploy from an incident audit unless separately
authorised. Database migrations remain controlled, additive actions outside the
interactive application startup path.
