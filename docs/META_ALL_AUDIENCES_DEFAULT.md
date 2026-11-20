# Explicit all-audiences default

Task: 20261119-1f73f7ce. Owner: codex-meta-lifecycle-20261119.
Verified 19 November 2026 in Meta Graph API Explorer in Edge using v26.0.

## Graph evidence

- Ads Manager displayed **Get conversions from all audiences** for ad set
  `120251076250220554`.
- A GET of that ad set with `fields=id,name,ad_set_goal,existing_customer_budget_percentage`
  returned `ad_set_goal: {"type": 0}`; the budget-percentage field was absent.
- A GET of `act_528975349337773/adsets?fields=id,name,ad_set_goal&limit=5`
  returned five recent ad sets, all with `ad_set_goal: {"type": 0}`.
- POST to `120251076250220554` with `ad_set_goal={"type":"BROAD"}` and
  `execution_options=["validate_only"]` failed with code 100:
  `Param ad_set_goal['type'] must be a number`.
- The same validate-only request with `ad_set_goal={"type":0}` returned
  `{"success":true}`. Neither POST saved a change. No ads were created or published.

Official references:
- https://developers.facebook.com/docs/graph-api/reference/ad-campaign/
  documents BROAD as numeric type 0, acquisition goals as types 1 and 2.
- https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adaccount.py
  exposes `ad_set_goal` as a map in `create_ad_set`.

The live check validates the field on an existing ad set, not an end-to-end
creation of a new campaign. New ad-set creation/serialization and downstream
guards were tested offline with mocked Meta. Account-specific creation and the
resulting Ads Manager UI still need confirmation during an authorized release.

## Local behavior

Both Instant Experience and Carousel builders send `ad_set_goal: {"type": 0}`.
The transport JSON-encodes the map. New ad sets (including compatible siblings)
must explicitly read back a broad goal before further ad work proceeds. Missing
goals are unknown and stop the run; acquisition goals/exclusions also stop it.
Existing-ad-set attachment continues to inherit its existing settings and does
not update the parent ad set.

## Validation

173 tests passed with the workspace's existing Python environment:

```powershell
python -m unittest tests.test_meta_posting.ExistingTargetClientTests tests.test_meta_posting.PostingPayloadTests tests.test_meta_posting.MetaPostingClientTests tests.test_meta_posting.PostingReferenceRepairTests tests.test_meta_posting.PostingServiceTests tests.test_meta_posting.ReviewAndPersistenceTests tests.test_meta_carousel_posting tests.test_ads_direct_post tests.test_meta_posting_repair -q
```

The broader baseline had one pre-existing failure:
`PostingNavigationTests.test_pages_are_lazy_loaded_and_routed`, which expects an
old import string in `app.py`. It failed before edits and remained the sole
failure in the initial post-change broader run. No navigation code was changed.

Studio Verify passed syntax, Studio tests, changed-file secret-pattern checks,
and `git diff --check`. Changes remain local and uncommitted; no deployment.
