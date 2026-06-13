# Sports Cave Edition Pill

This folder contains the lightweight Shopify theme snippet for Phase 5B.

Install `snippets/sports-cave-edition-pill.liquid` in the Shopify theme, then render it on product pages with:

```liquid
{% render 'sports-cave-edition-pill' %}
```

The snippet reads only the `sports_cave` product metafields synced from Sports Cave OS:

- `sports_cave.edition_limit`
- `sports_cave.next_available_edition`
- `sports_cave.editions_remaining`
- `sports_cave.edition_status`
- `sports_cave.edition_display_text`

Sports Cave OS remains the backend source of truth. Shopify metafields are only the storefront display mirror.

The snippet does not read Shopify inventory, variant inventory, stock, or `product.selected_or_first_available_variant.inventory_quantity`.

## Install checklist

1. Copy `snippets/sports-cave-edition-pill.liquid` into the active Shopify theme snippets folder.
2. Add `{% render 'sports-cave-edition-pill' %}` to the product template where the edition pill should appear.
3. In Sports Cave OS, update the edition limit, next edition, and sold count.
4. Click `Sync Edition Display` on Limited Editions.
5. Do not use the old inventory-based scarcity widget for Sports Cave limited editions.
