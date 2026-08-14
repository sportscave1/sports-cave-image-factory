# Google SEO Phase 4

Phase 4 builds canonical Shopify page mappings, imports privacy-safe Shopify
order facts and GA4 transaction identifiers, reconciles revenue, and exposes a
database-only reporting read model. It extends the existing Phase 1 connection
and Phase 3 imports; it does not replace either system.

## Runtime commands

Run migrations before starting a worker:

```powershell
python run_migrations.py
```

Inspect saved Phase 3 and Phase 4 health without calling Google or Shopify:

```powershell
python google_seo_phase4.py health
```

For local or manual Phase 4 recovery, process one queued item with:

```powershell
python google_seo_phase4.py worker --once
```

The normal analytics refresh does not require another paid Render worker.

The existing Render morning job now refreshes Google imports and saved
analytics in one command:

```powershell
python google_seo_import.py daily
```

Keep the existing paid morning schedule after the normal Google reporting-day
boundary. No additional Render service is required.

## Safe rollout

1. Confirm the existing Phase 3 GSC run is complete and its inventory has a
   latest stored date.
2. Confirm the Phase 3 GA4 job has no duplicate active run. A live lease and an
   advancing active date are safe; an expired lease must be reclaimed by the
   existing Phase 3 worker before Phase 4 is queued.
3. Run the additive migration.
4. Run `python google_seo_import.py daily` once to activate the saved analytics
   refresh.
5. Confirm source-specific GSC, GA4 and Shopify/Supabase dates on SEO / Store
   Analytics. A missing joined date no longer hides valid source metrics.

## Data rules

- GSC site totals come from `seo_gsc_daily_totals`; detailed query/page rows are
  not summed to manufacture site totals.
- GSC, GA4, and Shopify retain separate grains and are aggregated independently
  before canonical page results are joined.
- GA4 revenue remains labelled `GA4 attributed/unconfirmed`.
- Shopify-confirmed revenue requires an exact transaction/order identifier match.
- Test, cancelled, fully refunded, duplicate, conflicting, and currency-mismatch
  records are never counted as confirmed revenue.
- Currencies remain separate. Phase 4 performs no exchange-rate conversion.
- Locale-prefixed URLs remain distinct unless an exact Shopify canonical or an
  explicit saved alias supports the mapping.
- The Phase 4 order fact table stores no customer names, email addresses,
  addresses, credentials, or tokens.
