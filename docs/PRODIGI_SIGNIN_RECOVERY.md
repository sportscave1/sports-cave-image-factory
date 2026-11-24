# Prodigi sign-in recovery

Sports Cave Companion 1.7.55 keeps sign-in recovery separate from supplier action
permissions. The account is `hello@sportscave.com.au`.

When the owned order tab reaches its exact Prodigi login redirect, or the image
library reports expired authentication, the companion records a durable sign-in
wait before navigating. The Orders row and Companion header show **Sign in to
Prodigi**. The extension shows a badge, opens the login tab once per incident and
adds a visible reminder that waiting orders resume automatically.

The companion can enter the existing saved Prodigi username and password through
the shared Credentials permission checks. `PRODIGI_PASSWORD` remains the source;
the explicitly configured account is checked against the account above. An empty
`PRODIGI_USERNAME` can use that owner-provided login. A different configured
username requires manual review. There is one automatic credential release per
incident, including across extension restarts and multiple orders. A lost reply,
rejected password, unavailable credential, changed form, verification code or
CAPTCHA leaves a manual sign-in path. The companion never solves a challenge or
changes a password.

After sign-in, a ready order page wakes recovery immediately; the independent
30-second alarm also retries. An extension reload, missing receiver or closed
tab can recover through a fresh owned tab, preserving the previous tab. Unused
Save, Select and shipping permits are blocked while waiting. The server checks
the current source, edition, exact supplier item and saved business state before
retiring the old token and issuing a new handoff. A long manual sign-in never
extends an expired permit.

An already permitted Save or Select receives independent readback. A permitted
QA step can receive a fresh full QA pass only after the saved shipping target,
artwork and business state have been checked. An ambiguous action or changed
order remains visibly **Needs review**, with the original evidence retained.
Recovery never declares QA passed just because login succeeded and never blindly
repeats an uncertain supplier action. Existing review/Reset controls remain the
manual recovery route for changed orders.

Preparation, status sync and independent server readback continue during a
login wait. Additional browser claims on that desktop wait for authentication.
No email, SMS or push subscription is required for the alert.

Credential values travel only in a no-store response to the paired, freshly
authorised desktop and a top-frame message to the exact Prodigi login page.
They are never included in tick plans, order records, Chrome storage, clipboard,
progress, error messages or audit metadata. The login form receives them in
memory. Credential access is audited by service, action and field only.

Offline checks are in `tests/test_prodigi_signin.py` and
`tests/test_prodigi_signin_recovery.cjs`, and run in the Orders release gate.
Use synthetic credentials and disposable PGlite for tests. Do not sign out a
production session or modify a real customer order to simulate an outage.
