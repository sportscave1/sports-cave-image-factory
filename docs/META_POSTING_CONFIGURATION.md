# Meta Posting configuration

Sports Cave OS uses one central Graph API version and one existing Meta connection.
The production environment variables are:

- `META_ACCESS_TOKEN`: System User access token generated for the Sports Cave OS Meta app.
- `META_APP_ID` and `META_APP_SECRET`: the same Meta app used to generate that token. These allow the read-only token metadata diagnostic; neither value is displayed.
- `META_AD_ACCOUNT_ID`: the Sports Cave ad account (with or without the `act_` prefix).
- `META_FACEBOOK_PAGE_ID`: the fixed Facebook Page identity used by Posting creatives.
- `META_INSTAGRAM_ACTOR_ID`: the Instagram professional-account user ID sent as `instagram_user_id` in the current creative payload. The legacy environment-variable name is retained for deployment compatibility.
- `META_API_VERSION=v26.0`: the central version used by every Meta read and write in this repository.

## Required Business Portfolio setup

In **Business Settings → Users → System Users → sportscaveapi**:

1. The Sports Cave ad account must be assigned with permission to manage campaigns. This is required to read existing campaigns/ad sets and to create an image, creative and paused ad inside an existing ad set.
2. The Sports Cave Facebook Page must be assigned with its advertising/create-ads task so the Page can be used as the creative identity.
3. The `sportscaveshop` Instagram professional account must be assigned for advertising so its Instagram user ID can be used as the creative identity.
4. Generate the System User token for the **Sports Cave OS** app, not another app, with `ads_read` and `ads_management`. The current Posting payload does not create or update campaigns, ad sets, audiences, budgets, schedules or tracking.

In the **Sports Cave OS App Dashboard**:

1. Confirm the app is owned by or shared with the same Business Portfolio as the System User and ad account.
2. Confirm Marketing API access is available and there is no app, business or developer-account restriction blocking API calls.
3. Standard Access is sufficient when this app manages only the business's own ad account. Advanced Access is relevant when an app manages other businesses' ad accounts; do not request it merely to mask a token/app/asset assignment problem.

## Read-only connection gate

Posting reports connected only when local configuration and identities are present and both the configured ad account and its campaign list can be read. `/me` and `/me/permissions` remain diagnostic because System User behavior can differ, but a shared `API access blocked` response from the ad-account reads keeps Posting disconnected.

When `META_APP_ID` and `META_APP_SECRET` are present, the app also calls read-only `/debug_token` and retains only safe metadata: validity, token type, app ID, app match and scope names. Tokens, app secrets, authorization headers and complete authenticated URLs are never returned to the UI or logs.

## Posting endpoints

Connection/selection uses GET requests for `/me`, `/debug_token`, `/me/permissions`, the configured `act_<account>`, its `/campaigns`, and selected campaign `/adsets`.

Only an explicit **Create Paused Ad** submission may write to `/adimages`, `/adcreatives` and `/ads`. The ad-create payload is hard-coded to `PAUSED`.
