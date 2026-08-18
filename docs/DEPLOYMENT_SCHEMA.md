# Deployment schema compatibility

Core Shopify ingestion uses the established order schema and does not depend on
marketplace diagnostic columns. A read-only core check remains available for
operational audits, but it is not a Render startup gate:

```bash
python run_migrations.py --verify-required-schema
```

The check never changes data or schema.

## Shopify marketplace reconciliation

Apply the additive migration once from a controlled Render Shell or one-off job:

```bash
python run_migrations.py --only 20260818_shopify_marketplace_order_reconciliation.sql --check
python run_migrations.py --only 20260818_shopify_marketplace_order_reconciliation.sql
python run_migrations.py --verify-marketplace-schema
```

Do not add this migration command to Streamlit rendering, application startup, or
either web-service start command. If the optional schema is absent, channel
attribution remains available from the saved Shopify payload while only the
marketplace-specific health fields are unavailable. The migration runner records
the filename transactionally and its SQL uses `IF NOT EXISTS`, so a deliberate
repeat is safe and does not rewrite order, line-item, allocation, certificate, or
edition data.
