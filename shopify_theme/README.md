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
