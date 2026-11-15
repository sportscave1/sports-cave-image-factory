# Combined SEO and CRM worker

Future start command for the existing manually managed `sports-cave-seo-worker`:

```sh
python sports_cave_worker.py
```

Do not create a service or add this worker to `render.yaml`. The supervisor uses
the running Python interpreter to launch the unchanged entry points:

- `python -u google_seo_import.py worker --poll-seconds 15`
- `python -u crm_worker.py`

Each child has its own process and business logic. The supervisor checks every
0.5 seconds and restarts an exited child (including a zero exit) or a failed
launch after five seconds, indefinitely. Its sibling continues running. The
`-u` option makes logs immediately visible; stdout/stderr stay attached to the
service logs. Supervisor failure logs contain only worker names, exit codes,
and exception types, never environment values or exception messages. Existing
child logging is unchanged.

SIGTERM and SIGINT stop restarts and send SIGTERM to both children before
waiting. CRM retains its existing stop-event handler; SEO retains its existing
OS signal behavior. After a shared 20-second grace period, any remaining child
is killed and reaped. The supervisor exits with status zero on normal shutdown.
This does not add a new in-flight SEO drain guarantee.

## Environment and deployment prerequisites

Both children inherit the complete Render service environment (`Popen` has no
`env` override). No new environment variable is introduced. SEO configuration
and its 15-second polling argument stay unchanged. CRM uses the same existing
Postgres connection configuration as SEO through `supabase_backend.connect`.

Before deployment, verify that this worker service has:

- The existing database URL and access to the already-applied CRM schema. This
  entry point runs no migrations or seed operations.
- `SHOPIFY_STORE_DOMAIN` and the existing Shopify authentication configuration:
  `SHOPIFY_ADMIN_ACCESS_TOKEN`, or the supported `SHOPIFY_CLIENT_ID` and
  `SHOPIFY_CLIENT_SECRET` flow; preserve the existing API version and scopes
  needed to read orders and customer journey attribution.
- `CRM_MARKETING_ENABLED=false` for the requested attribution operation. Leave
  send/test gates disabled. The supervisor does not override existing gates;
  if marketing is enabled in the environment, existing CRM send behavior applies.
- `CRM_EMAIL_ATTRIBUTION_MIRROR_ENABLED` unset or false. No code enables it.

No marketing API key or email sending configuration is required for attribution.
If existing Shopify credentials are absent on the SEO service, add them through
normal Render environment configuration, never source code. The offline coding
checks cannot confirm the live service's environment or schema.

CRM attribution keeps its existing bounded reconciliation, retry and lease
logic even with marketing off. The unchanged CRM engine also handles webhook
events, local campaign completion state, pending opt-out reconciliation, and
provider suppression sync when a provider key is configured. In particular,
pending opt-outs can write Shopify consent even with marketing off. Thus this
reuse is attribution-enabled with marketing gated, not a strictly read-only CRM
mode. No campaigns are activated by this supervisor.

Validation uses mocks and fixtures only; neither real worker is started against
production. Production credentials, Render environment, and Render services are
not changed during implementation.
