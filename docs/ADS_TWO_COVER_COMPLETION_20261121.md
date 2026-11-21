# Two-cover completion and provider-review status

Task 20261121-ba540270. User authorized the clearer review status, continuation
with two available covers and a Git/Render release.

## Behavior

The ad queue displays `Needs provider review · 2/3 covers saved` for a moderation
block with two saved originals. Counts come from the job's receipts, including
historical failed records. Collection remains a running stage. A technical
incomplete-delivery record uses `Needs delivery review` instead.

After a finished partial handoff, collect the successful original covers and
the CSV. If exactly two distinct non-rejected routes have complete verified
Dropbox receipts, freeze those original route IDs and continue with two separate
paused Meta ads. Each cover uses its own original CSV route's copy. The third
route remains unavailable and its exact blocker is retained. There is no new
image generation, substitute slot or archive lookup.

The new partial Posting request is explicit. Ordinary manual Posting still
requires three creatives. One-cover, duplicate-cover, rejected-route and missing
receipt packages cannot enter this path. The normal metadata, revision/hash,
image, targeting and Posting checks still run before Meta submission.

The service creates two durable per-ad ledger entries with an explicit
expected-count marker in the existing JSON ledger. Legacy ledgers without that
marker retain their three-ad default, including older truncated two-row data.
Completion requires two independently confirmed PAUSED ads. Retries retain the
same campaign, ad set, submission ID and completed ad IDs. Request fingerprints
continue to prevent changing a submitted run's creative set.

The queue can finish the two-ad workflow while retaining provider-review status
for the missing third cover. Detail text explicitly states that two ads were
created paused. Posting success receipts display the actual created ad count.

## Scope

No folder search or old-image substitution is added. No rejected generation is
retried or worked around. Existing successful outputs are independent approved
results and are the only assets eligible for this smaller package. No ad is
activated by this change. The approved generator prompt and two-line footer
profile remain unchanged.

Meta's API creates individual ads against an ad set; the former three-ad batch
requirement was application validation. Primary reference:
https://developers.facebook.com/docs/graph-api/reference/adgroup/

## Verification

Offline tests exercise the real Posting service using fake Meta clients,
verified file receipt flows in disposable PGlite, route-to-copy mapping for
nonconsecutive successful slots, explicit two-ad validation, legacy count
compatibility, partial completion and retry without duplicate objects.

An initial broader run exposed the existing
`test_companion_shows_selected_ads_queue` assertion expecting four tabs after
the concurrent SEO release added a fifth tab. Neither that test nor the
companion tab implementation was changed by this task; it is excluded from the
focused ad verification until its owning change updates the expectation.
