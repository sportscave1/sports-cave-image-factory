# Native premium Campaign Catalogue

The old renderer used columns=1 as its single-product mode and assigned sc-stack to every card. The existing mobile wrapper forced those cells to 100% width. New presentation is selected by the number of valid products; no Shopify calls are required to render saved snapshots.

One product: optional headline/subtext, a natural-ratio full-width linked image on a cream well, charcoal title/edition/price panel and strong gold CTA. No title truncation or rewriting. Image width is approximately 545px in the 600px browser fixture; narrower screens scale naturally.

Two or more products: hybrid inline-block presentation tables with a baseline width of 50%. Trusted wrapper CSS enhances at >=540px. Counts 2/3/4/5–6/7–12 choose 2/3/4/3/4 desktop columns; four-up is reduced to two (count 4) or three (count 7–12) when the longest exact title exceeds 65 characters. Mobile remains two-up. Incomplete rows are left-aligned on the same charcoal background. All explicitly selected valid products remain present.

Outlook Word receives two-up conditional ghost-table rows, with a system-owned conditional width override. Browser/no-media fallback was checked; actual Outlook/Gmail/Apple Mail inbox screenshots were not obtained, so identical client rendering is not claimed.

Only trusted generated catalogue output may retain the exact table classes sc-cat-item sc-cat-2/3/4 and four exact conditional comment strings. Pasted HTML cannot retain these classes or conditional markup. Existing sc-stack handling is unchanged. Inline table-layout/word-wrap properties are conservatively sanitized; arbitrary CSS/classes are not enabled.

Optional settings headline (80 characters) and subtext (180) default to blank on a deep-copied runtime section. Validation accepts legacy shapes and rejects unknown keys/overlength values. Text is escaped; no migration or production record writes on rendering. Compact inputs replace the misleading legacy layout selector inside existing expanded Catalogue settings. The stored columns value remains valid for old JSON but does not control the automatic new presentation. Pending copy edits are flushed before Send test acknowledges editor synchronization.

Existing Shopify query already requests featured-media altText; the resolver now retains optional image_alt in snapshots. Legacy snapshots use their exact title. Generic/missing ALT falls back to title, and imported markup is stripped from verified ALT. Image/title/CTA use the same canonical_product_url and existing campaign_link destination. Edition Ops remains authoritative; next renders only with remaining >0 and 1<=next<=limit, sold-out replaces remaining, missing edition facts are omitted, and all display toggles remain authoritative.

Fixture raw UTF-8 catalogue bytes (old → new): 1: 2025 → 1887; 2: 3912 → 4247; 4: 7695 → 8262; 6: 11478 → 12277; 12: 22833 → 24328 (+6.5%). Remote asset bytes are excluded. The 80/95 KB final production guard is unchanged.

Browser evidence: 600px four-up; 430/390/375/320px two-up, no horizontal overflow, all images loaded from localhost. Single-product natural ratio retained at all five widths. Desktop enhancement removed: two-up without overflow. Fixtures use the supplied concept image as a local stand-in, not a live Shopify product fetch. No remote asset downloads, customer/order reads, production writes or email sends occurred.

Files changed for this task:
- crm_catalogue.py
- crm_middle_sections.py
- crm_campaign_html.py
- crm_campaign_content.py
- components/crm_sections/composer.js
- tests/test_crm_catalogue_presentation.py
- tests/test_crm_modular_catalogue.py
- tests/test_crm_premium_catalogue.py
- tests/test_crm_sections_component.cjs
- tests/fixtures/crm_catalogue_old_renderer.py
- tests/fixtures/crm_premium_catalogue_preview.py
- docs/PREMIUM_CATALOGUE.md

Header/footer, Ads, tracking architecture, Shopify/Edition Ops, schema, Render and environment configuration remain unchanged. No commit/push/deploy was performed by the assistant.

Validation: 127 Python tests, 90 passed and 37 SQL-dependent skips. Three relevant JavaScript scripts passed, including optional-copy debounce/pre-send flush, section acknowledgement and image controls. py_compile and git diff --check passed.
