# Campaign Home cleanup

No production cleanup was executed in this checkout: no supported database URL
is configured. Production IDs, before/after counts, and the requested two retained
titles have not been verified. Deploying these files does not execute the cleanup.

On the explicitly selected connected environment, an administrator can inspect
the canonical inventory without writing anything:

```text
python scripts/cleanup_campaign_home.py
```

Create a reviewed JSON plan using the returned UUIDs and versions, never title
matching. `keep` must identify the two verified legitimate campaigns (Peter Brock
20th Anniversary Tribute and Ryan Fox Open Championship — Product Spotlight).
Both require non-test ACCEPTED receipts with provider IDs. `remove` must cover
every remaining visible ID exactly, with its current version:

```json
{"keep": ["VERIFIED_UUID_1", "VERIFIED_UUID_2"],
 "remove": [{"id": "VERIFIED_REMOVE_UUID", "version": 1}]}
```

Preview and then explicitly apply the reviewed plan:

```text
python scripts/cleanup_campaign_home.py --plan reviewed-plan.json
python scripts/cleanup_campaign_home.py --plan reviewed-plan.json --apply --actor ADMINISTRATOR_ID
```

Apply locks and rechecks the complete inventory, recipient receipts, versions,
and eligibility, then verifies precisely the two retained IDs remain. A failed
check rolls the entire operation back. This is a trusted server-side operator
tool, not a public endpoint; the actor is the accountable administrator invoking
it, not an application authentication bypass.

Removal always archives and writes the existing `campaign_deleted` history
marker. Every list/count excludes this marker. No campaign, receipt, tracking,
order, attribution, revision, or provider record is hard deleted. Archived
successful campaigns may be hidden only through this deliberate cleanup tool;
the normal trash action refuses accepted/uncertain receipts, evidence, and active
sending. Additional successful unarchived campaigns block the cleanup.

Home no longer fetches or renders currency amounts. Backend revenue reporting
remains intact. Bounce rate is unique accepted non-test production messages with
a verified `email.bounced` event divided by accepted non-test production messages,
times 100. Submission and event timestamps use the shared rolling UTC
`[now - 30 days, now)` period. A zero denominator is unknown (`—`). Duplicate
webhooks count once. No new hard/soft bounce classifications are introduced.

Deleting locally detaches only list/count requests and removes the row from all
session-resolved tab results. Delivery/order KPI jobs, reporting window, and
last-good values remain intact. A single native parent-fragment refresh closes
the compact confirmation and updates the UI; no full-page rerun is requested.
