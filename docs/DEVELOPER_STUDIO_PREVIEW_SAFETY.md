# Phase 2 preview safety prerequisites

Phase 1 preview startup fails closed. Port/runtime metadata is a plan, not an
application safeguard. No app server, database or worker is started.

Inspection:
- sports_cave_server.py imports application/runtime components and invokes
  run_deployment_migrations when RENDER or a database URL is configured.
  Start command: python sports_cave_server.py; default PORT 8501.
- run_migrations.py discovers database settings; localhost does not isolate data.
- shopify_sync.py contains edition/price GraphQL mutations and outbound POSTs.
- meta_ads_client.py / meta_posting_service.py contain advertising write paths.
- Email/CRM transport and dispatch modules perform provider writes.
- edition_ledger.py / edition_ops.py perform inventory/allocation operations.
Existing local fixtures do not prove application-wide denial of live writes.
No production credentials were copied to the worktrees.

Phase 2 must:
1. Launch on demand on loopback and check the port is free. Registry suggests
   unique ports from 8600; Phase 1 does not bind/reserve OS sockets.
2. Create runtime/cache/temp and private synthetic databases under
   .studio/runtime/<task-id>; configure actual app cache paths and TEMP/TMP.
   A metadata directory alone does not isolate existing caches.
3. Use an allowlisted child environment and synthetic secrets. Prevent .env,
   Streamlit secrets and inherited provider settings from falling back to
   production. Never copy original secrets or customer data.
4. Enforce mock/offline transports for Shopify writes, Meta publishing, email,
   customer automations, Edition Ops and external write APIs, including jobs.
5. Deny migrations against non-test databases; disable schedulers, workers,
   webhook processing and shared runtime paths. Provision test schema only.
6. Prove safe startup/import, cross-module and responsive browser behavior.
   Bind preview to draft ID, commit and selected synthetic dataset.
7. Keep credentials/runtime state outside shared source control.

Do not use production launch/deploy scripts for preview. Phase 1 does not invent
a safe-mode environment flag that the application does not actually implement.
