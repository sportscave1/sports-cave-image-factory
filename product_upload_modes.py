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
If any check fails or cannot be verified, leave the product Draft; do not activate.
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
Only after all prior checks pass: change this product from DRAFT to ACTIVE.
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
with bounded polling and fresh reads; never report a pending state as success.
EDITION OPS OPERATIONAL READINESS
After activation, the existing products/update webhook must register this eligible
product through the canonical Edition Ops service. Where the execution environment
supports Edition Ops access, verify this exact Shopify ID has its committed ledger,
correct active run and verified canonical Shopify edition metafield mirror. Use
the existing reconciliation service to recover missing registration; never create
edition defaults, runs or counters independently or reset existing editions.
If access is unavailable, report EDITION OPS READINESS UNVERIFIED and request the
operator's Edition Ops Pull New Products reconciliation/read-back. Shopify ACTIVE
alone is not proof. A pending mirror remains retryable; do not roll back the ledger.
Do not claim the full workflow is operational until this verification passes.
Only if EVERY required check passes report PRODUCT PUBLISHED LIVE, product title,
admin URL, ACTIVE, ALL selected collections, 16 variants, inventory 20,
continue-selling, applicable active Markets and each verified channel/resource.

6. FAILURE / PARTIAL-LIVE RECOVERY — APPLIES TO EVERY STEP
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


def common_build(prompt):
    text=str(prompt).replace('\r\n','\n').replace('\r','\n').strip()
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
    return f'{CORE}\n{core}\n{CORE_END}\n\n{START}\n{DRAFT_FINAL if mode=="DRAFT" else LIVE_FINAL}\n{END}'
