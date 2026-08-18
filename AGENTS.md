# Repository operating rules

## Production Render topology — do not duplicate

The only canonical primary web service is `sports-cave-os`
(`srv-d8kl4on7f7vs73dvavv0`). Exactly one primary Sports Cave OS web service is
allowed. Never delete, replace, rename, or recreate it to change application
branding.

The services `sports-cave-os-webhooks`, `sports-cave-seo-worker`, and
`sports-cave-seo-daily-sync` are intentional supporting services. Never create
another primary service. Never change the primary identity in `render.yaml`
without first checking [docs/RENDER_SERVICE_TOPOLOGY.md](docs/RENDER_SERVICE_TOPOLOGY.md).
Always run `python scripts/validate_render_topology.py` and inspect a Blueprint
preview before syncing. A preview that creates another primary application must
not be applied.
