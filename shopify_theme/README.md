# Sports Cave Edition Widgets

This repo now keeps the product page widget code in `shopify/snippets`.

Use these snippets:

- `sports-cave-remaining-pill.liquid`
- `sports-cave-numbered-edition-bar.liquid`
- `sports-cave-edition-widget.liquid` if both snippets are installed in a theme

The widgets read only these product metafields:

- `sports_cave.edition_enabled`
- `sports_cave.edition_total`
- `sports_cave.edition_remaining`
- `sports_cave.edition_next_number`

They do not read variant inventory, product stock, or Sports Cave OS.
