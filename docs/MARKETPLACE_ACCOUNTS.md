# Marketplace accounts, conversations and email

Task: `20261122-ad3af25d`. Customer accounts never create OS staff users or roles.
The restored homepage, existing approval queue and Dropbox media pipeline are
preserved. `/marketplace/demo` is an original illustrated demo, clearly marked
not for sale, excluded from inventory, sales totals and the sitemap.

## Customer flow

- Product pages offer **Message seller** and **Make offer**. Visitors create an
  account or sign in before either action. Confirmation returns to the intended
  item on the same browser. Customers choose their own password and verify email.
- Accounts use managed Supabase Auth; the browser receives only a random opaque
  HttpOnly/Secure/SameSite cookie, scoped to `/marketplace`. Provider access and
  refresh tokens remain in private server storage. Every protected request checks
  the provider session and marketplace account status. Password recovery uses PKCE
  and cannot establish a normal account session from a link or URL fragment.
- Conversation membership is checked for every read/write. Only a listing's buyer
  and seller can participate. An existing seller identity cannot be reassigned by
  posting an email or re-registering its email. Guest seller submissions connect
  to messaging after the seller verifies the original submission email.
- Offers include an AUD total with postage. Sellers can accept or decline them.
  Acceptance never collects money or records a sale. A seller can share an amount
  and a genuine PayPal-hosted invoice link. The buyer checks recipient and amount
  on PayPal. The site does not verify payment status or collect commissions.
- Customers can block/report conversations. Authorised OS admins can manage
  customer access and review conversations/reports. Support access is disclosed
  in privacy terms; messaging does not claim end-to-end encryption.

## Minimal storage and runtime

All account and chat records use the existing private `crm_runtime_state` table.
No new database, service, media bucket, framework or dependency is required.
The table has RLS enabled and no anon/authenticated SELECT grant. Customer views
never receive private email indexes, provider tokens or Dropbox receipts.

Photos and videos remain solely in the existing Dropbox item folders. Chat has
bounded text, structured offers and invoice links; no media attachments or extra
message-body email copies. Messages use indexed key ranges, bounded pages and
incremental polling every six seconds while the tab is visible. Expired app
sessions and recovery records are pruned in batches of 25 on subsequent logins
or recovery requests. No chat history is removed by this cleanup.

## Reuse the existing Resend subscription

Supabase remains the identity provider; **Resend delivers account email via SMTP**.
No additional email account or subscription is created. Use the existing paired
`RESEND_MARKETING_API_KEY` / `RESEND_FROM_EMAIL`, or the existing reporting
`RESEND_API_KEY` / `ACTIVITY_DIGEST_FROM` fallback. Keep its actual verified sender
domain. `marketplace_mail.smtp_plan()` exposes configuration presence and sender
only; it never returns the key. The OS **Check Resend SMTP** control performs TLS
authentication only and sends no message.

After explicit release authorisation, connect the same account in the existing
Supabase project `ceyzbfpuwuuxaiqwiltz`, Authentication → Emails → SMTP Settings:

| Setting | Value |
| --- | --- |
| Sender email | Existing verified OS Resend sender |
| Sender name | Sports Cave Marketplace |
| Host | `smtp.resend.com` |
| Port | `465` with TLS |
| Username | `resend` |
| SMTP password | Existing matching Resend sending key, kept secret |

Do not copy the key into Git, chat, logs, browser assets or a public form. Do not
change the OS marketing sender, enable campaigns, add customers to marketing
audiences or send real email during development checks.

Append these exact URLs to Authentication → URL Configuration → Redirect URLs:

```
https://sports-cave-image-factory.onrender.com/marketplace/account/confirmed
https://sports-cave-image-factory.onrender.com/marketplace/auth/recovery
```

Preserve the existing Site URL and redirect entries, because this project also
has an older app configuration. Confirmation/reset templates must use the
provider's `ConfirmationURL`, including the requested redirect. Keep email
confirmation enabled. Avoid link tracking that rewrites verification links.

The versioned `marketplace_auth_public.json` contains only the verified project's
public URL and publishable key, never a service secret. Paired server environment
overrides are `MARKETPLACE_SUPABASE_URL` and
`MARKETPLACE_SUPABASE_PUBLISHABLE_KEY`. They must refer to the same project as the
existing database, since session checks deliberately fail closed otherwise.

Reference: [Resend's official Supabase SMTP integration](https://resend.com/docs/send-with-supabase-smtp).

## PayPal API later

The existing PayPal app contact is `hello@sportscave.com.au`. Its API and commission
collection remain deferred at the owner's request. Future API invoices must use
the actual seller's authorisation and payee; the Sports Cave app must not collect
every seller's payment into its own account. Add provider invoice identifiers,
verified and deduplicated webhook receipts, payment reconciliation and explicit
seller onboarding before enabling payment status or fees. Existing manual invoice
messages remain marked `shared`; never convert them to `paid` from a browser claim.

## Validation and release

Run `python -B scripts/test_marketplace.py`, `node tests/marketplace_accounts.cjs`,
`node tests/marketplace_gallery.cjs`, JS syntax checks and
`python scripts/validate_render_topology.py`. Tests use synthetic accounts,
transactions and provider doubles; no production credential, email or PayPal
request is used. Phase 1 application previews remain disabled.

Publication requires fresh authorisation for committing, GitHub main, the
existing primary Render service, and the production SMTP/redirect configuration.
No Blueprint sync or additional Render service is needed. After publication,
verify the live demo, both sign-up gates, private caching headers and OS controls.
SMTP authentication proves the credentials work; actual delivery and a first real
signup still require the customer's normal email confirmation journey.
