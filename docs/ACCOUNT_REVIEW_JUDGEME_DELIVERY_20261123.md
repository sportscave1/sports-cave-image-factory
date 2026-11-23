# My Collection review delivery audit and fixes

Task 20261123-b598c0c3, owner codex-judgeme-review-20261123.
The owner clarified that the existing compact native account form should stay;
it need not be Judge.me's storefront widget. No frontend/theme file is changed.
The live account form was inspected: rating, optional title, body, optional photo,
Cancel and Submit review; no YouTube URL field and no navigation away required.

Existing delivery uses Judge.me POST /api/v1/reviews, with the stable external
Shopify product ID and the owner-bound order customer's name/email. Private
credentials remain server-side. Existing signed references enforce ownership.
The live form has an eligible prompt; bootstrap only produces that prompt after
Judge.me configuration and product mapping have passed. No real review or email
was created for this audit.

Two local changes are ready:

- Reencode accepted WebP uploads as JPEG (transparent areas on white). Judge.me's
  picture_urls accepts JPEG/PNG, not WebP. Keep PNG/JPEG input support. Validate
  the final byte size too, capped at the configured limit and provider's 10MB.
- Reject non-2xx statuses and explicit error/errors/success:false provider bodies,
  including HTTP 200 application errors. Preserve documented asynchronous HTTP
  200 acceptance with no immediate review ID; do not invent a receipt or force
  verified-buyer status.

Judge.me's API-created reviews cannot be marked verified through this API. They
remain subject to the store's Judge.me moderation settings. The genuine widget
has its own identity/verification process, so exact verification parity is not
claimed. Video uploads are not supported in this native API flow.

Sources inspected 23 November 2026:

- https://judge.me/help/en/articles/8409180-using-judge-me-api
- https://judge.me/api/docs.yaml (reviews#create: background creation, HTTP 200)
- https://judge.me/help/en/articles/11960176-collecting-web-reviews

Validation: 56 focused Python checks and 12 subtests passed. New checks cover all
three input formats, transparent WebP, provider payload identity/photo/rating,
HTTP-200 error bodies, asynchronous empty acceptance and non-success statuses.
Topology and diff checks pass. Task is local-only; no commit, merge, push, deploy,
Shopify publication or production customer write was performed for these fixes.
The task starts at Studio's older approved base; only the two unchanged provider
functions are edited. Production integration must preserve current collection,
order and multi-item changes and rerun focused checks before release.
