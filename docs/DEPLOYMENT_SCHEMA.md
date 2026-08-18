# Deployment schema gate

Sports Cave OS treats application code and its required PostgreSQL schema as one
deployment unit. Render runs the read-only compatibility gate after the build and
before either web service starts:

```bash
python run_migrations.py --verify-required-schema
```

The gate checks required migration records, columns, types, nullability, defaults,
and indexes. It never changes data or schema. A failure keeps the previous healthy
Render deployment serving traffic. The service start commands repeat the same
read-only check as a defence for services or environments where a separate
pre-deploy phase is unavailable; they never apply migrations.

## Shopify marketplace reconciliation

Apply the additive migration once from a controlled Render Shell or one-off job:

```bash
python run_migrations.py --only 20260818_shopify_marketplace_order_reconciliation.sql --check
python run_migrations.py --only 20260818_shopify_marketplace_order_reconciliation.sql
python run_migrations.py --verify-required-schema
```

Do not add this migration command to Streamlit rendering, application startup, or
each web worker. The migration runner records the filename transactionally and its
SQL uses `IF NOT EXISTS`, so a deliberate repeat is safe and does not rewrite order,
line-item, allocation, certificate, or edition data.
