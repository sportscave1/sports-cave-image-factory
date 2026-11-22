# Instagram Community Like / Unlike

The earlier comment-feed release checked the IG Comment reference only. Meta
now documents comment likes under the IG User `/likes` endpoint. This supersedes
the Instagram-like limitation in `SOCIAL_COMMENT_SCROLL_20261122.md`.

Official contract:
https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/user-likes

POST or DELETE `/v27.0/{instagram-user-id}/likes` with `comment_id` likes or
unlikes a comment. This requires a Facebook User token with `instagram_basic`,
`instagram_manage_engagement`, `pages_read_user_content`, and `pages_show_list`.
Stories and private-account content are unsupported. Distinct Like and Unlike
buttons are provided because this contract does not document a GET like-state
endpoint.

Only `META_SOCIAL_ACCESS_TOKEN` is used for these operations. The Page and ads
credentials are retained. Existing unrelated Graph calls keep their configured
version. Before each write, the server verifies token validity, USER type, app
identity, grants, linked Page/Instagram identity, and comment membership. UI
capability reads use the existing session cache. Writes are never retried and
require Meta's explicit success acknowledgement. A process-wide limit of 20
Like/Unlike attempts per five seconds stays below Meta's documented burst cap.

Existing Facebook Login for Business configuration Sports Cave Community
(`2009683517103204`) is reused. Its original five scopes are retained and the
two engagement-related scopes were added with the user's action-time approval.
No new app, configuration, primary Render service, or ads/CRM credential is
created or replaced.

Offline validation: 142 tests and six subtests passed (eight legacy database
tests skipped), covering the official
endpoint, token isolation, invalid and mismatched token rejection, comment
membership, write acknowledgements, no retries, shared burst limits, visible
native controls, feed paging, and disposable local PostgreSQL ledger behavior.
Render topology validation and `git diff --check` passed. Production token
activation and live action verification are recorded separately after completion.
