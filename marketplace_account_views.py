"""Small server-rendered account and messaging screens, using the existing brand."""
from marketplace import BASE_PATH as B, listing_url, money
from marketplace_accounts import safe_next
from marketplace_views import h, shell, icon
from urllib.parse import urlencode

DEMO = {'id': 'demo', 'title': 'Sports Cave Club jersey', 'category': 'jerseys', 'sport': 'Other',
    'team': 'Sports Cave Club', 'condition': 'Excellent', 'location': 'Sydney, NSW',
    'description': 'An example collector jersey in black and gold. Size L. Original illustration for this demo; no physical item is offered for sale.',
    'provenance': 'Demonstration only. This is not a signed or match-worn item.', 'seller_name': 'Demo collector',
    'seller_type': 'Private collector', 'price_cents': 18000, 'shipping_cents': 1500,
    'photo_count': 2, 'has_video': False, 'status': 'published'}


def document(content, title, path, nonce):
    return shell(content, title=title + ' | Sports Cave Marketplace', description=title,
                 path=B + path, nonce=nonce, noindex=True, account_page=True)


def form(fields, action, label, *, hidden='', note=''):
    return f'''<form class="account-form" data-account-action="{action}">{hidden}{fields}
<label class="trap" aria-hidden="true">Website<input name="website" tabindex="-1" autocomplete="off"></label>
<button type="submit" class="button dark">{label}</button><p class="form-status" role="status" aria-live="polite"></p>{note}</form>'''


def email_field():
    return '<label>Email<input type="email" name="email" autocomplete="email" maxlength="254" required></label>'


def password_field(new=False):
    return f'<label>{"Choose a password" if new else "Password"}<input type="password" name="password" autocomplete="{"new-password" if new else "current-password"}" {"minlength=12" if new else ""} maxlength="128" required>{"<span class=hint>At least 12 characters.</span>" if new else ""}</label>'


def auth(mode='signup', next_path='', nonce='', notice=''):
    next_path = safe_next(next_path)
    is_signup, recover, reset = mode == 'signup', mode == 'recover', mode == 'reset'
    title = 'Create your account.' if is_signup else 'Reset your password.' if recover or reset else 'Welcome back.'
    fields = '' if reset else email_field()
    if is_signup:
        fields = '<label>Display name<input name="name" autocomplete="nickname" maxlength="70" required></label>' + fields
    if not recover:
        fields += password_field(is_signup or reset)
    if is_signup:
        fields += f'<label class="consent"><input type="checkbox" name="consent" required><span>I agree to the <a href="{B}/terms">marketplace terms and privacy notice</a>.</span></label>'
    label = {'signup': 'Create account', 'signin': 'Sign in', 'recover': 'Send reset link', 'reset': 'Save new password'}[mode]
    next_query = h(urlencode({'next': next_path}))
    toggle = f'<p class="account-switch">Already collecting with us? <a href="{B}/signin?{next_query}">Sign in</a></p>' if is_signup else f'<p class="account-switch">New here? <a href="{B}/signup?{next_query}">Create account</a></p>'
    intro = 'Message collectors. Make an offer. Find your next piece.' if is_signup else 'Your collection, your conversations.'
    if recover:
        intro = 'Open the email in this browser to choose a new password.'
    if reset:
        intro = 'Choose a new password, then sign in again.'
    content = f'''<main id="main" class="account-layout section-width"><section class="account-intro"><p class="eyebrow">SPORTS CAVE MARKETPLACE</p><h1>{title}</h1><p>{intro}</p><span class="account-emblem" aria-hidden="true">SC<span>FOR THE LOVE<br>OF THE GAME.</span></span></section><section class="account-card" aria-label="{label}">{f'<p class="account-notice" role="status">{h(notice)}</p>' if notice else ''}
{form(fields, mode, label, hidden=f'<input type="hidden" name="next" value="{h(next_path)}">')}
{toggle}{f'<a class="subtle-link" href="{B}/recover">Forgot your password?</a>' if mode == 'signin' else ''}<p class="hint">Your email stays private. Sports Cave support can review reported conversations.</p></section></main>'''
    return document(content, label, '/' + mode, nonce)


def confirmed(nonce='', next_path=''):
    query = h(urlencode({'next': safe_next(next_path)}))
    return document(f'''<main id="main" class="narrow account-confirmed"><p class="eyebrow">YOUR MARKETPLACE ACCOUNT</p><h1>Ready to collect.</h1><p>If your email was confirmed successfully, sign in to continue. If the link expired, create your account again to request another confirmation.</p><a class="button dark" href="{B}/signin?{query}">Sign in</a></main>''', 'Confirm your account', '/account/confirmed', nonce)


def account(profile, nonce=''):
    alerts = f'<label class="consent"><input type="checkbox" name="email_notifications" {"checked" if profile.get("email_notifications", True) else ""}><span>Email me about new messages, offers and invoices.</span></label>'
    return document(f'''<main id="main" class="narrow"><p class="eyebrow">YOUR ACCOUNT</p><h1>Hello, {h(profile['name'])}.</h1><p>{h(profile['email'])} · Verified email</p><div class="account-shortcuts"><a class="button dark" href="{B}/inbox">Your messages</a><a class="button outline" href="{B}/sell">List an item</a></div><p class="hint">Selling? Use this verified email on your listing so enquiries arrive in your inbox.</p><section class="email-preference"><h2>Email alerts</h2>{form(alerts, 'notifications', 'Save email preference')}<p class="hint">Private chat details stay in your inbox. Repeated activity is grouped into fewer emails.</p></section>{form('', 'signout', 'Sign out')}<p class="hint">For an account correction or deletion request, <a href="mailto:hello@sportscaveshop.com">contact Sports Cave</a>.</p></main>''', 'Your account', '/account', nonce)


def contact(row, intent, nonce=''):
    offer = intent == 'offer'
    fields = '<label>Total offer (AUD, including postage)<input type="number" name="amount" min="1" max="51000" step=".01" inputmode="decimal" required></label>' if offer else ''
    fields += f'<label>{"Note (optional)" if offer else "Your message"}<textarea name="text" rows="4" maxlength="{500 if offer else 2000}" {"" if offer else "required"} placeholder="Ask about condition, provenance or postage."></textarea></label>'
    content = f'''<main id="main" class="narrow contact-page"><a class="back" href="{h(listing_url(row))}">Back to the item</a><p class="eyebrow">A CONVERSATION STARTS HERE</p><h1>{'Make an offer.' if offer else 'Message the seller.'}</h1><div class="contact-item"><strong>{h(row['title'])}</strong><span>{money(row['price_cents'])} + {money(row['shipping_cents'])} postage · {h(row['seller_name'])}</span></div>
{form(fields, 'start', 'Send offer' if offer else 'Send message', hidden=f'<input type="hidden" name="listing_id" value="{h(row["id"])}"><input type="hidden" name="kind" value="{"offer" if offer else "text"}">')}
<p class="hint">An offer does not reserve the item or take payment. Keep personal and payment details out of messages.</p></main>'''
    return document(content, 'Make offer' if offer else 'Message seller', '/contact/' + row['id'], nonce)


def inbox(threads, selected=None, messages=None, nonce=''):
    links = ''.join(f'<a class="thread-link" href="{B}/inbox/{h(t["id"])}" {"aria-current=page" if selected and selected["id"] == t["id"] else ""}><strong>{h(t["item_title"])}</strong><span>{h(t["seller_name"] if t["role"] == "buyer" else t["buyer_name"])}</span><small>{"Buying" if t["role"] == "buyer" else "Selling"} · {h(t["updated_at"][:10])}</small></a>' for t in threads)
    sidebar = f'<aside class="inbox-sidebar"><h2>Your conversations</h2>{links or "<p>No conversations yet. Message a seller from an item page.</p>"}<a class="text-link" href="{B}">Explore the collection ↗</a></aside>'
    if selected:
        t = selected
        seller = t['role'] == 'seller'
        options = '<option value="text">Message</option>' + ('<option value="invoice">PayPal invoice</option>' if seller else '<option value="offer">Make offer</option>')
        fields = f'<label class="sr-only" for="message-kind">Message type</label><select id="message-kind" name="kind">{options}</select><div data-payment-fields hidden><label>Total (AUD, including postage)<input type="number" name="amount" min="1" max="51000" step=".01" inputmode="decimal"></label></div>'
        if seller:
            fields += '<div data-invoice-fields hidden><p class="hint">Create the invoice in your own PayPal Business account. Paste its share link here; the buyer pays you directly on PayPal.</p><label>PayPal invoice share link<input name="url" type="url" maxlength="300" placeholder="https://www.paypal.com/invoice/p/#INV2-…"></label></div>'
        fields += '<label class="sr-only" for="message-text">Message or note</label><textarea id="message-text" name="text" rows="2" maxlength="2000" placeholder="Write a message…" required></textarea>'
        safety = f'<details class="conversation-safety"><summary>Conversation options</summary><button type="button" data-safety="{"unblock" if t["blocked_by_me"] else "block"}">{"Unblock" if t["blocked_by_me"] else "Block"} conversation</button><form data-report><label>Report a concern<textarea name="reason" rows="2" maxlength="500" required></textarea></label><button type="submit">Send to Sports Cave</button></form><p data-safety-status role="status"></p></details>'
        body = f'''<section class="conversation" data-conversation="{h(t['id'])}" data-role="{t['role']}"><header class="conversation-heading"><div><p class="eyebrow">{'SELLING' if seller else 'BUYING'}</p><h1>{h(t['item_title'])}</h1><p>With {h(t['buyer_name'] if seller else t['seller_name'])}</p></div><a class="text-link" href="{B}/item/{h(t['listing_id'])}">View item ↗</a></header>
<p class="conversation-notice">{'Messaging is paused in this conversation.' if t['blocked'] else 'Seller has not joined messaging yet. Your message is saved here for them.' if not t['seller_joined'] else 'Your email stays private. Pay only through a genuine PayPal invoice.'}</p>
<div class="message-log" role="log" aria-label="Conversation messages" aria-live="polite">{''.join(message(m, t['role']) for m in messages or [])}</div><p class="chat-status" role="status" aria-live="polite"></p><div class="message-composer" {'hidden' if t['blocked'] else ''}>{form(fields, 'send', 'Send', hidden=f'<input type="hidden" name="thread_id" value="{h(t["id"])}">')}</div><p class="hint">Offers are agreements to discuss a purchase. Invoice amounts and payment status are checked on PayPal; fees are not collected here.</p>{safety}</section>'''
    else:
        body = f'<section class="inbox-empty">{icon("chat")}<h1>Your next conversation.</h1><p>Select a conversation or find a piece you love.</p><a class="button dark" href="{B}">The collection</a></section>'
    return document(f'<main id="main" class="inbox-layout section-width">{sidebar}{body}</main>', 'Your messages', '/inbox' + ('/' + selected['id'] if selected else ''), nonce)


def message(row, role):
    kind = row['kind']
    heading = 'You' if row['sender'] == role else 'Seller' if row['sender'] == 'seller' else 'Buyer'
    body = f'<p>{h(row["text"])}</p>' if row.get('text') else ''
    if kind in ('offer', 'invoice', 'offer_response'):
        label = 'Offer ' + row['status'] if kind == 'offer' else 'Seller-provided PayPal invoice' if kind == 'invoice' else 'Offer ' + row['choice']
        body = f'<strong class="message-label">{h(label)}</strong><span class="message-amount">{money(row["amount_cents"])} AUD</span>' + body
        if kind == 'invoice':
            body += f'<a class="button dark" href="{h(row["url"])}" target="_blank" rel="noopener noreferrer">View &amp; pay on PayPal ↗</a><small>Check the recipient and total on PayPal. Payment status is not tracked here.</small>'
        if kind == 'offer' and role == 'seller' and row['status'] == 'pending':
            body += f'<div class="offer-actions"><button type="button" data-offer="{row["seq"]}" data-choice="accepted">Accept offer</button><button type="button" data-offer="{row["seq"]}" data-choice="declined">Decline</button></div>'
    return f'<article class="message {"mine" if row["sender"] == role else "theirs"}" data-seq="{row["seq"]}" data-kind="{h(kind)}"><header><strong>{heading}</strong><time datetime="{h(row["created_at"])}">{h(row["created_at"][:16].replace("T", " "))} UTC</time></header>{body}</article>'


def demo_conversation(nonce=''):
    content = f'''<main id="main" class="narrow"><p class="eyebrow">DEMO · NO MESSAGES OR PAYMENTS</p><h1>A conversation, made simple.</h1><div class="message theirs"><strong>Demo collector</strong><p>Happy to share more photos of the jersey. What would you like to know?</p></div><div class="message mine"><strong>Example offer</strong><span class="message-amount">A$170.00 AUD</span><p>Total including tracked postage.</p></div><div class="message theirs"><strong>Example PayPal invoice</strong><span class="message-amount">A$170.00 AUD</span><p>A real seller can share their PayPal invoice here for the buyer to view and pay on PayPal.</p></div><p class="hint">This is a preview. No real account, conversation or invoice was created for the demo seller.</p><a class="button dark" href="{B}/demo">Back to demo product</a></main>'''
    return document(content, 'Demo conversation', '/contact/demo', nonce)
