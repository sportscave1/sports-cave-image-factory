# New Product: Draft and Live prompt modes

## Architecture and scope

Product Uploads exports execution prompts for a connected Shopify/Dropbox assistant.
It has no in-app product-creation executor. This change keeps that architecture;
selecting a mode or confirming it in Sports Cave OS does not mutate Shopify.

The original Draft instructions live in app.py's NEW_SHOPIFY_PRODUCT_PROMPT
(SOP 07B), including its purpose, BRUTAL DRAFT RULE, validation and execution tail.
product_upload_modes.common_build extracts the staged build once, replacing
terminal Draft-only instructions with staging-scoped instructions. Both exported
modes have an identical common build and exactly one separate finalisation block.
The collector-copy, media, variant, SEO, SKU and price transforms remain shared.

Both modes deliberately share the same saved Prompt Store ID so editable product
standards cannot drift into two independently maintained SOPs. Render keys and
labels differ. The transform removes a previously saved finalisation block before
applying the selected mode. Tests cover Draft-to-Live and Live-to-Draft transitions.
The internal legacy New product value is retained for compatibility; the dropdown
and prompt heading display UPLOAD TO DRAFT. Existing Product updates are unchanged.

UPLOAD & PUBLISH LIVE requires a product-specific confirmation checkbox and product
name before exposing a copyable Live prompt. This is approval to generate that
execution prompt; actual Shopify work happens only when it is run with the tools.

## Finalisation contracts

Draft: stop after complete QA with DRAFT/Published false. No ACTIVE change,
product/collection publication, Market availability mutation or inventory-20 step.
Successful final read-back permits PRODUCT UPLOADED TO DRAFT; otherwise report
incomplete work rather than a green success.

Live: first finish and verify the same Draft build. Then resolve existing sport
and Collector Series, verify memberships, set all 16 variants to quantity 20 at
the established fulfilment location and policy CONTINUE, discover active applicable
Markets/catalogs and enabled publications, activate and publish. Verify product,
sport collection and Collector Series independently against every required channel.
Fresh read-back of all build and publication checks gates PRODUCT PUBLISHED LIVE.

Ambiguous identity/sport/location, build or publication errors, unsupported required
operations and failed read-back prevent success. The prompt requires restoring only
the new product to Draft, preserving work, with explicit fallback read-back. Failed
fallback must be reported as CRITICAL: DRAFT FALLBACK UNVERIFIED. Shopify operations
are not one atomic transaction; no prompt can guarantee rollback during an outage.
Retries must reconcile the same product and perform only missing work; quantities
are set, not incremented. Shared collection publications are never rolled back.

## Shopify verification

Shopify supports product and collection publishable publication independently:
https://shopify.dev/docs/api/admin-graphql/latest/mutations/publishablePublish
Market catalogs may use a publication or inherit channel availability:
https://shopify.dev/docs/api/admin-graphql/latest/objects/MarketCatalog

The prompt requires discovery, pagination and observed IDs instead of hardcoded
channel/Market IDs. Disabled channels are evidenced as not applicable; unsupported
enabled required channels block completion. Shopify collection publication does
not prove a downstream Meta Product Set has finished syncing. That must be reported
separately; no Meta advertising or Product Set mutations were added.

No Draft Activation service/helper was found in this checkout. Nothing was deleted
or replaced. The exported Live finalisation contract is reusable, but this is not
a new server-side activation service or a claimed integration with an absent one.

## Validation and limits

54 tests pass: shared creation/copy/SEO/media/pricing standards, separate modes,
confirmation gate, saved-mode isolation/idempotence, failure/retry instructions,
and existing prompt/UI regressions. Python compilation and git diff --check pass.
Shopify's schema validator accepted the independent product/collection
publishedOnPublication verification query. No query or mutation was executed
against the production store. The documentation search script failed to fetch;
official Shopify documentation was retrieved through the web fallback instead.

Because this is a prompt-export feature, failure tests check the exported execution
contract, not actual Shopify rollback or runtime mutation sequencing. A supervised
execution with the connected tools remains necessary to verify the real workflow.
No live products, Markets, publications, orders or edition data were changed.
No commit, push, deployment or migration was performed.
