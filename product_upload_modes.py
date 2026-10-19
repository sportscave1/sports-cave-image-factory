"""Mode-specific finalisation for the existing exported Shopify SOP workflow.

No API client or mutations live here. Execution takes place in the connected
Shopify/Dropbox assistant after the operator copies the selected prompt.
"""
import re

START='SPORTS CAVE NEW PRODUCT FINALISATION'
END='END SPORTS CAVE NEW PRODUCT FINALISATION'
CORE='COMMON PRODUCT BUILD — STAGING ONLY'
CORE_END='END COMMON PRODUCT BUILD'

DRAFT_FINAL='''UPLOAD TO DRAFT — FINALISATION
Stop after the complete common build and fresh Draft QA/read-back.
Final Status: DRAFT. Published: false. Verify no product sales-channel publication.
Never set ACTIVE, publish to Online Store, Facebook & Instagram, Google & YouTube,
Shop, Pinterest or Linktree; never change Markets availability or release publicly.
Preserve the existing Draft inventory behaviour; do not set quantity to 20.
Do not mutate collection publications. Normal media, variants, prices, SKUs, SEO,
copy, category, tags, collections and continue-selling setup still apply.
Only after all Draft checks pass report PRODUCT UPLOADED TO DRAFT, product title,
admin link and verified 8-image package, 16 variants, pricing, SEO and variant
images. State Not published. Missing checks mean INCOMPLETE DRAFT, not success.'''

LIVE_FINAL='''UPLOAD & PUBLISH LIVE — FINALISATION
The operator has explicitly selected and confirmed this live-publication mode.
Complete ALL common staging work first. A successful productCreate or media
mutation is not QA. Do not expose the product before a fresh read verifies all
8 required image roles and gallery order, 16 variants, selling/compare-at prices,
SKUs, image assignments, title/description, SEO/alt text, tags and exact category.
If any required product/publication check fails or cannot be verified, leave the
product Draft; do not activate. Edition setup is a separate readiness result:
missing edition metadata, an unassigned edition/number, pending PSD mapping or an
unverified Edition Ops mirror alone must not block staging QA or Live publication.
Create product, publish live, then the operator returns to MAP and edition setup.
A recovery/incomplete-image override is NOT permission to publish incomplete work.

Use the same verified newly created Shopify product ID throughout. Before creation
or retry, reconcile this operation's product ID and exact handle; never create a
duplicate to bypass an error. Refuse an ambiguous identity or an unrelated existing
product. On retries, reread state and perform only missing work. Do not duplicate
media, variants, memberships or publication records. Do not reset any edition data.

1. CLASSIFY AND RESOLVE COLLECTIONS
Resolve the verified Sports Cave sport from supplied research/current product data,
not an invented category. Follow the shared NEW PRODUCT MULTI-COLLECTION POLICY:
evaluate the full catalogue and resolve ALL relevant collections to stable IDs,
including the SPORT COLLECTION and COLLECTOR SERIES. No duplicate collections.
If sport or collection identity is ambiguous, leave Draft and report the problem.
Apply every selected manual ID, preserving other legitimate memberships. For
automated collections, evaluate established rules and verify actual membership;
never rewrite rules or product facts to force inclusion or manually add to smart collections.

2. INVENTORY — LIVE MODE ONLY
Discover the normal Sports Cave fulfilment location; if ambiguous, stop in Draft.
For all 16 exact variants, track inventory where supported and set available
quantity to exactly 20 at that location, with continue-selling enabled and inventory
policy CONTINUE. Use current inventory item/location IDs and compare quantities
before setting; retries must SET 20, never increment by 20. Preserve other locations
and unrelated items. Re-read quantities and policies for every variant.

3. DISCOVER PUBLICATIONS AND MARKETS BEFORE ACTIVATION
Paginate current enabled channel publications and active Markets/catalogs using
the existing configured Shopify connector/API. Never hardcode IDs. Include every
enabled normal wall-art channel, including Online Store, Facebook & Instagram,
Google & YouTube, Shop, Pinterest and Linktree where enabled. List disabled or
absent channels as not applicable with evidence, never as verified publications.
Discover active normal wall-art Market catalogs/publications and availability rules.
If a catalog has no publication, verify its inherited sales-channel availability.
Do not create Markets, change currency, international pricing, catalogs' price
lists or global settings. Check required permissions/capabilities before activation.
An enabled required channel that cannot be verified is a blocker, not a silent skip.

4. ACTIVATE AND PUBLISH
Only after all prior product/publication checks pass: change this product from DRAFT to ACTIVE.
Pending edition setup is not one of these publication prerequisites.
Ensure this product's availability in each discovered applicable active Market.
Publish this PRODUCT to every discovered enabled required channel publication.
Separately verify/publish EACH selected collection to every enabled required channel,
including SPORT COLLECTION and COLLECTOR SERIES; never stop at the first two.
Reuse existing memberships/publications and repair only missing ones. Never remove
legitimate shared collection publications or change unrelated collection contents.
Use supported publishable operations for each resource, inspect every userError,
and never mistake ACTIVE for published. Unsupported enabled required publication
or Market operations are failures; do not invent API support or mark them complete.
Collection publication is checked independently of product publication; it does
not prove downstream Meta Product Set synchronisation. Report any downstream
catalogue/collection eligibility or propagation issue separately, without editing ads.

5. FRESH FINAL READ-BACK — SUCCESS GATE
Do not trust mutation responses. Read this exact product and ALL selected collection IDs
again, paginate variants/media/publications, and verify current Market availability.
Verify ACTIVE, verified sport, all selected collection memberships,
all 16 quantities = 20 at the selected location, tracking where supported, and
CONTINUE. Verify all common build QA again. Independently verify PRODUCT, SPORT
COLLECTION, COLLECTOR SERIES and every other selected collection publication for each required enabled channel.
Use a matrix: Resource | Channel/Market | Required | Observed | Verified/Error.
Retain the existing media verification table. Retry transient processing failures
with bounded polling and fresh reads; never report a pending publication as success.
EDITION OPS READINESS — REPORT SEPARATELY FROM PUBLICATION
Where supported, read this exact Shopify ID's existing ledger/run and canonical
Shopify edition metafield mirror without changing them. If missing, pending or
inaccessible, report EDITION OPS READINESS UNVERIFIED / edition setup pending.
The operator completes PSD mapping and edition assignment afterward through
Product Uploads → MAP and the existing reconciliation service / edition setup.
Do not invent an edition number, create/reset a run, modify counters, allocate
editions or mark anything sold. Do not set an archive flag to represent pending
setup. Never change edition ledger data or bypass storefront purchasing checks.
STOREFRONT CHECKS
During staging and final read-back, “Edition archived — Collector run closed”
and disabled Add to Cart caused solely by pending edition setup are expected.
Leave this archived/unavailable behaviour intact until normal MAP and edition
setup completes. Do not enable Add to Cart. These effects alone must not block
publication, require unpublishing or trigger a return to Draft. Other critical
storefront/product/publication failures retain the recovery rules below.
After EVERY required product/publication check passes, report product title,
admin URL, ACTIVE, ALL selected collections, 16 variants, inventory 20,
continue-selling, applicable active Markets and each verified channel/resource.
Include the stable product ID and verified publication matrix. If edition setup
is pending, use the exact heading PRODUCT PUBLISHED LIVE — EDITION SETUP PENDING
and state: “The product is published. Purchasing remains disabled until edition setup is completed. Return to Product Uploads → MAP, then complete edition assignment.”
Report publication and edition readiness separately. Do not describe the product
as ready to purchase or fully operational until edition readiness is verified.
Only when edition readiness is also verified use PRODUCT PUBLISHED LIVE without
the pending qualifier.

6. FAILURE / PARTIAL-LIVE RECOVERY — CRITICAL PRODUCT/PUBLICATION FAILURES
Pending edition metadata/assignment, PSD mapping, an unverified Edition Ops mirror
and their expected archived message/disabled Add to Cart are excluded from Draft
fallback. This exception applies only to pending edition setup and its effects.
On any critical failure (including classification, media, variants, prices,
inventory, status, memberships, Markets, any selected collection publication, product
publication or final read-back), do not report Live success. Attempt to restore
ONLY this newly created product to DRAFT and verify it by a fresh read. Where
needed, unpublish only this operation's product publications; never roll back
shared collection publications or delete the product. Preserve completed work.
Report the exact failed step/resource/channel, errors, remaining work and whether
safe Draft fallback was verified. If verified, report PRODUCT CREATED — LEFT IN
DRAFT. If fallback fails, report CRITICAL: DRAFT FALLBACK UNVERIFIED with the exact
product ID and observed status; do not claim it is safe or leave the failure silent.
Retries must resume the same product; never restart by creating a replacement.'''


# Scope inherited Draft-only appendix checks to staging in the Live export.
# Reverse these substitutions before rebuilding a saved prompt in either mode.
LIVE_STAGING_WORDING = {
    '- Never set product status to Active.': '- Never set product status to Active during staging; use the selected Live finalisation afterward.',
    '- Never publish to Online Store.': '- Never publish to Online Store during staging; use the selected Live finalisation afterward.',
    '- Keep the product Draft and unpublished.': '- Keep the product Draft and unpublished during staging only.',
    '- Return the Shopify draft/admin link for manual review.': '- Record the Shopify admin link for staging QA, then continue to selected Live finalisation.',
    'These rules do not authorise live publishing or live Shopify price updates.': 'During staging only: These rules do not authorise live publishing or live Shopify price updates. Explicit Upload to Live finalisation authorises publication after product/publication QA.',
    '- Status: Draft for a new product': '- Status: Draft during staging; ACTIVE after verified Live finalisation',
    '- Published: false for a new product': '- Published: false during staging; verify required publications after Live finalisation',
    '- Product remains unpublished until manually approved': '- Product remains unpublished during staging; explicit Upload to Live selection authorises the separate Live finalisation',
}


def common_build(prompt):
    text=str(prompt).replace('\r\n','\n').replace('\r','\n').strip()
    for old, new in LIVE_STAGING_WORDING.items(): text=text.replace(new, old)
    text=re.sub(re.escape(START)+r'.*?'+re.escape(END),'',text,flags=re.S).strip()
    text='\n'.join(line for line in text.splitlines() if line not in (CORE,CORE_END)).strip()
    text=re.sub(r'BRUTAL DRAFT RULE\n.*?(?=REQUIRED ASSETS)',
        'STAGING SAFETY\nCreate as DRAFT and unpublished. Complete all build checks before the separate finalisation stage.\n\n',text,flags=re.S)
    replacements={
        'Direct Draft Product Upload — Current Sports Cave Standard':'Shared staged product build — Current Sports Cave Standard',
        'Do not publish automatically.':'Do not publish during this common build stage.',
        '- Leave the product ready for manual review and publishing.':'- Complete staging QA before the selected finalisation stage.',
        '- Product will remain Draft and unpublished.':'- Product is Draft and unpublished throughout staging.',
        '20. Return the Shopify draft/admin link and a concise manual-review list.':'20. Record the admin link and QA results, then enter the selected finalisation stage.',
        'Create it as Draft and keep it unpublished.':'Create it as Draft and keep it unpublished throughout staging.',
        'Do not make it live, do not set it Active, and do not publish it to the Online Store.':'Do not activate or publish during the common build stage.',
        'Do not publish. Return the Shopify draft/admin link and validation results for manual review.':'Finish staging with a fresh Draft read-back, then execute only the selected finalisation stage.',
        'but never substitute a wrong category or publish the product.':'but never substitute a wrong category or publish an incomplete product.',
    }
    for old,new in replacements.items(): text=text.replace(old,new)
    return text


def finalise_prompt(prompt, mode='DRAFT'):
    if mode not in ('DRAFT','LIVE'): raise ValueError('Unknown New Product publication mode.')
    core=common_build(prompt)
    if mode == 'LIVE':
        for old, new in LIVE_STAGING_WORDING.items(): core=core.replace(old, new)
    return f'{CORE}\n{core}\n{CORE_END}\n\n{START}\n{DRAFT_FINAL if mode=="DRAFT" else LIVE_FINAL}\n{END}'
