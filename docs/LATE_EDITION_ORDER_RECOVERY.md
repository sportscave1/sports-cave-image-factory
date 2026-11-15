# Late Edition Ops product recovery

An order line without an exact product/variant ID or SKU match is persisted as
`Needs product mapping`. Adding a product later does not replay those lines.
Historical direct allocation is deliberately disabled in the normal importer.
Title similarity is not sufficient evidence to choose an artwork.

Edition Ops now exposes **Allocate Existing Unallocated Order**. Enter an exact
order number and use **Find unallocated order lines**. Copy the desired line ID,
choose the existing Edition Ops product and **Preview allocation**. Verify the
artwork, confirm the mapping and press **Allocate Existing Unallocated Order**.
The next number shown is a preview: a changed counter requires a new preview.
No page load, preview, product creation or search allocates historical orders.

The action locks the product, order and line, uses the existing atomic allocator,
links the line and writes an `edition_adjustments` audit in the same transaction.
It never sets the edition cursor itself. Existing allocations are returned without
counter changes. Conflicting stable IDs/handles cannot be overridden by confirmation.
Lines with neither require an explicit exact order/line/product confirmation.
The normal product metafield mirror runs after commit; pending mirror state remains
retryable. Certificates use the normal missing-certificate workflow.

Equivalent preview command in the configured production application environment:

```powershell
python -m scripts.recover_unallocated_edition --order '#SC3232' --line 'gid://shopify/LineItem/50761092759859' --product 723
```

Only after independently confirming the replacement artwork, execute with `--apply`,
`--expected-next` from that preview and `--confirm-mapping` equal to the exact
confirmation string in the preview. No secret, hard-coded edition number, schema
migration or broad historical replay is needed.

## SC3232 investigation (2026-10-06)

- Authoritative project: `ceyzbfpuwuuxaiqwiltz`.
- Shopify order `18924580208947`, paid, processed 2026-10-04 03:20:49 UTC.
- Line `50761092759859`, one unit, Tom Brady Motivational Quote Art, SKU TBRADYA3.
- Stored product/variant IDs and handle are empty; Shopify still shows the old title/SKU.
- Candidate record 723: Shopify product `15399569064243`,
  `tom-brady-further-to-go`, Tom Brady — Further To Go, created 2026-10-05.
- Observed counters: next 1, sold 0, remaining 100, edition limit 100.
- Different titles/SKU families mean this replacement mapping requires confirmation.
  Investigation made no production writes. These observed counters are not allocation inputs.
