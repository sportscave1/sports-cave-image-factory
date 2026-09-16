# Product Upload description and collections

## Active path and scope

`render_product_uploads_page` uses `get_product_upload_prompt` →
`build_product_upload_prompt` → `apply_product_upload_prompt_updates` for the
preview/export. Saved prompt text uses the same final transform.
`product_collector_copy.apply_rules` supplies the authoritative description;
`product_upload_collections.apply_rules` adds the new-product collection policy;
`product_upload_modes.finalise_prompt` supplies Draft/Live finalisation.

This app exports a SOP to a connected assistant. It has no Product Upload Shopify
mutation client, collection selector, or researched product metadata loader.
The executor performs discovery, matching, compact review, assignment and read-back.
No new Shopify API client or automatic live action was added. The existing UI mode
confirmation, prices, inventory, media and publication contracts remain in place.

The previous copy policy prohibited a universal ending. Normal confirmed limited-100
worldwide products must now finish with these two HTML paragraphs:

```html
<p>Limited to 100 worldwide.</p>
<p>Real fans remember this. Own the moment.</p>
```

History and any existing specifications precede this ending. Explicit nonlimited,
other-limit and unknown-edition exceptions remain. Media Update Mode still preserves
copy. Ads image wording is outside this policy.

The previous Live finalisation explicitly requested just the sport collection and
Collector Series, then read back “both collection IDs”. It now applies and verifies
every selected ID. Draft receives the same collection coverage without publication.

## Actual catalogue inspection

Read-only Shopify collection search on 2026-09-16 returned all 34 collections;
`hasNextPage` was false. Exact titles, IDs, handles and rule sets are recorded in
`tests/fixtures/product_upload_collections_2026_09_16.json`. This is a test snapshot,
not a production cache or source of IDs for uploads.

Manual collections:

- NBA Wall Art; Horse Racing Wall Art; Motor Racing Wall Art; Tennis Wall Art
- Cricket Wall Art; Football Wall Art; Matilda's Wall Art
- Motivational Quotes Sports Wall Art; Combat Wall Art
- Cristiano Ronaldo Wall Art; Lionel Messi Wall Art
- Best Online Sports Wall Art; Michael Jordan Wall Art; Lebron James Wall Art
- Stephen Curry Wall Art; Kobe Bryant Wall Art; Featured Sports Wall Art
- All-Star Legends Wall Art; Collector Series Wall Art
- Best Selling Wall Art UK; Popular; Rivalries Wall Art
- NFL Wall Art; Ice Hockey Wall Art; Baseball Wall Art; WWE Wrestling Wall Art
- Apparel; Rugby League Wall Art; AFL Wall Art; Olympics Wall Art; Formula One Wall Art

Automated collections:

- All Sports Wall Art: variant price greater than 0.1
- Best Selling Sports Wall Art: variant price greater than 20
- New Sports Wall Art: variant price greater than 20

Automatic membership requires current rule evaluation and fresh Shopify read-back;
none of these IDs is sent to a manual assignment operation. Do not change price or
collection rules to force inclusion. Current API capabilities must also be checked.
Manual curated Best Sellers/Popular/Featured are not inferred from sport/country.
No USA or Australia merchandising collection, sport-specific Collector Series,
driver-specific or Ferrari collection was present. Do not invent them.

## Local preview examples

`preview_collections(verified_facts, catalogue)` is a conservative read-only preview
for known canonical handles and exact subjects. It returns a deduplicated manual-ID
list plus review rows for the whole catalogue. It does not infer facts from titles.
Unknown, curated and automatic collections remain review items. Optional
`verified_collection_facts` and `collection_catalogue` metadata embeds that advisory
preview in the actual public prompt; ordinary UI use has no such data and relies on
the executor's mandatory fresh catalogue research. The executor must evaluate all
additional team/event/era/market mappings, not treat this preview as exhaustive.

| Verified product | Selected manual collections |
| --- | --- |
| F1 collector artwork | Formula One Wall Art; Motor Racing Wall Art; Collector Series Wall Art |
| Michael Jordan NBA collector artwork | NBA Wall Art; Michael Jordan Wall Art; Collector Series Wall Art |
| US NFL collector artwork | NFL Wall Art; Collector Series Wall Art |
| Australian Supercars collector artwork | Motor Racing Wall Art; Collector Series Wall Art |

For each, automatic collections are separately evaluated by their real rules.
Country alone does not add Best Selling Wall Art UK or manufacture an absent market
collection. Generic “legend”, “king” or “champion” words never establish a match.

## Local verification

Run:

```
.venv\Scripts\python.exe -m unittest tests.test_product_upload_collections tests.test_product_upload_modes tests.test_product_collector_copy tests.test_product_upload_prompts -q
```

Tests cover complete Draft/Live public prompts, UI preview/export, saved-prompt
idempotence, multiple IDs, deduplication, cross-sport rejection, smart/unknown type
safety, curated exclusions and the exact ending with edition exceptions. These are
prompt-contract and local preview tests, not evidence of a completed Shopify upload
or of externally generated description text. Use Upload to Draft for the first
operator-approved connected execution and inspect its collection read-back.
