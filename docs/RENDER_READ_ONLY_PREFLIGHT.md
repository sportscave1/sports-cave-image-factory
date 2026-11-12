# Read-only preflight in the existing Render service

Completed successfully on 6 November 2026 at 12:56 AEDT using the existing OS environment in the canonical primary's authenticated Web Shell. No deployment or environment change was needed. There is no need to repeat it unless access changes.

## Exact repeat procedure

1. Open [sports-cave-os → Shell](https://dashboard.render.com/web/srv-d8kl4on7f7vs73dvavv0/shell) in Nathan's existing workspace. Use the current running instance's **Web Shell**. Do not create an ephemeral shell, service or deployment. The free webhook service does not offer this shell.
2. In **local PowerShell**, from this verified task worktree, copy the reviewed standalone probe command to the clipboard:

```powershell
$probePath = Join-Path (Get-Location) 'scripts/render_source_preflight.py'
$probeSource = [System.IO.File]::ReadAllText($probePath).Replace("`r`n", "`n")
$probeCommand = "cd /opt/render/project/src`npython -B - <<'SPORTSCAVE_READ_ONLY_PREFLIGHT'`n" + $probeSource + "`nSPORTSCAVE_READ_ONLY_PREFLIGHT`n"
Set-Clipboard -Value $probeCommand
```

3. Paste once into the **Render Web Shell terminal**, then press Enter if it has not executed. The actual server command is `python -B -` with the reviewed script supplied on stdin. This works before the new file is deployed; do not run `python scripts/render_source_preflight.py` on an older deployed revision where that file does not exist.
4. Retain only the single sanitised JSON result. Do not run `env`, `printenv`, shell tracing, token-printing commands or normal sync/application entry points. Never copy secret values to local development, chat or reports. A failure is one bounded attempt: retain status/code/subcode/request ID and investigate before retrying.

The copied text contains program code, not credentials. It reads existing environment values only inside Render. It uses the existing `requests` dependency; no install, application import, database connection, schema setup, sync, AI call or file write occurs. Shopify may exchange the already configured client credentials for a token held only in process memory; its GraphQL operation is read-only. Meta uses GETs only. Ambient proxies and redirects are disabled; each request has a 5-second connect/20-second read timeout and no automatic retry.

Credential names and precedence match this OS: `SHOPIFY_STORE_DOMAIN`, `SHOPIFY_API_VERSION`, `SHOPIFY_CLIENT_ID`+`SHOPIFY_CLIENT_SECRET` preferred over `SHOPIFY_ADMIN_ACCESS_TOKEN`; `META_AD_ACCOUNT_ID`, `META_ACCESS_TOKEN`, `META_API_VERSION` (or the literal default read from deployed `meta_ads_client.py`). Do not change these just to perform this check. The probe never emits any credential value.

## Observed Shopify result

- Actual **OS Render credentials**, client-credentials authentication.
- HTTP 200; requested and served Admin GraphQL version **2026-04**.
- `read_orders=true`, `read_all_orders=true`: installed-app historical-order scope is present. Existing `write_orders=true` was observed but unused; no permission expansion.
- Request ID: `b8eea439-6fd3-4eb3-8a9b-44362e8a65b5-1793930201`.
- A separate six-ID, financial-fields-only read through the same OS auth path succeeded. This establishes access to those IDs, not complete historical inventory/refund coverage.

## Observed Meta result

- Configured account **528975349337773**, requested and served **v26.0**.
- Account GET HTTP 200: **AUD**, **Australia/Sydney**. Request ID `AppJJb1VAdrhFVhBgE3kyRA`.
- Completed-day Insights GET for **5 November 2026** HTTP 200; one returned ad/day row with `has_more=true`. Request ID `A3VsErWdQjmBsqPQlQo1q_Y`.
- Access works now. This sample is deliberately incomplete, does not persist anything and does not repair stale OS reporting rows. It does not establish full purchases/value coverage, per-adset attribution windows or a matched Ads Manager total.

AI automation flags/settings were not changed. This standalone probe cannot start an AI worker or call OpenAI. No paid ephemeral shell or hosting resource was created.

Render's connector lacks remote command execution; the existing authenticated Web Shell was used as the fallback. [Render shell documentation](https://render.com/docs/ssh) and [CLI documentation](https://render.com/docs/cli) describe the available execution paths. This task does not need CLI installation or authentication.

Sanitised evidence is outside the development preview:
`C:\Dev\SportsCaveWorktrees\.studio\runtime\20261101-d2835a7c\source-repair-20261106\canary-preparation\render-preflight.json`.
