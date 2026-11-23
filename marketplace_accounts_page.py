"""OS administrator controls for customer accounts; no staff roles or token display."""
from marketplace import BASE_PATH, PUBLIC_ORIGIN, money
from marketplace_chat import invoice_url


def actor(user):
    return str(user.get('id') or user.get('username') or 'administrator')


def render_accounts(st, store, user):
    st.subheader('Marketplace accounts')
    st.caption('Customer accounts are separate from OS staff access. Customers verify their email and choose their own password.')
    with st.expander('Create customer invitation'):
        with st.form('marketplace-customer-invitation'):
            name = st.text_input('Customer display name', max_chars=70)
            address = st.text_input('Customer email', max_chars=254)
            submitted = st.form_submit_button('Save invitation')
        if submitted:
            try:
                store.invite(address, name, actor(user))
                st.success('Invitation saved. Share the signup link with the customer; no email was sent.')
            except ValueError as exc:
                st.error(str(exc))
        st.code(PUBLIC_ORIGIN + BASE_PATH + '/signup', language=None)
        pending = [r for r in store.invitations() if r['status'] == 'awaiting signup']
        if pending:
            st.dataframe([{'Name': r['name'], 'Email': r['email'], 'Status': r['status']} for r in pending], hide_index=True, width='stretch')
    rows = store.accounts()
    search = st.text_input('Find customer', placeholder='Display name or email').strip().casefold()
    filtered = [r for r in rows if not search or search in (r['name'] + ' ' + r['email']).casefold()]
    st.caption(f'{len(rows)} registered marketplace accounts · Most recent 500 shown')
    if filtered:
        key = st.selectbox('Customer', [r['id'] for r in filtered],
                           format_func=lambda uid: next(r['name'] + ' · ' + r['email'] for r in filtered if r['id'] == uid))
        row = next(r for r in filtered if r['id'] == key)
        st.text(row['name'] + ' · ' + row['email'])
        st.caption(f'{row["status"].title()} · Joined {row["created_at"][:10]} · Verified email')
        choice = 'active' if row['status'] == 'blocked' else 'blocked'
        if st.button('Restore marketplace access' if choice == 'active' else 'Block marketplace access'):
            store.set_account_status(key, choice, actor(user))
            st.rerun()
    else:
        st.info('Verified customers appear here after their first sign-in. Invitations do not create staff access.')
    with st.expander('Account connection & PayPal setup'):
        from marketplace_mail import smtp_plan, check_smtp
        plan = smtp_plan()
        st.write('Account email delivery: existing Resend subscription')
        from marketplace_notifications import status as alert_status
        alerts = alert_status()
        st.caption('Chat email alerts: ' + ('Running through Resend' if alerts['running'] else
                   'Paused' if not alerts['enabled'] else 'Waiting for the server connection'))
        st.caption('Unread messages, offers and invoices · Maximum one alert per conversation every 15 minutes')
        if plan['configured']:
            st.caption(f'Sender: {plan["sender_name"]} <{plan["sender_email"]}> · {plan["host"]}:{plan["port"]}')
            if st.button('Check Resend SMTP'):
                try:
                    check_smtp()
                    st.success('Resend SMTP authentication verified. No email was sent.')
                except ValueError as exc:
                    st.error(str(exc))
        else:
            st.info('Configure the existing OS Resend sender and sending key before connecting account email delivery.')
        st.caption('Managed email/password accounts · PayPal API connection pending · Commission collection off')
        st.text('PayPal app contact: hello@sportscave.com.au')
        st.write('Sellers can share genuine PayPal invoice links in private chat. Buyers pay the seller on PayPal. Automatic invoices, payment verification and platform fees need the later seller-authorised PayPal integration.')
        if st.button('Check account connection'):
            try:
                from marketplace_accounts import Provider
                settings = Provider().call('GET', 'settings')
                with store.db() as conn:
                    conn.execute('SELECT id FROM auth.sessions WHERE false').fetchone()
                if settings.get('disable_signup') or not settings.get('external', {}).get('email') or settings.get('mailer_autoconfirm'):
                    st.error('Email signup must be enabled with email confirmation required before accepting customer accounts.')
                else:
                    st.success('Account service connected. Email signup and confirmation are enabled; session checks are available.')
                    st.caption('Customer email delivery and the confirmation/reset redirect URLs must also be configured in the Auth provider.')
            except Exception:
                st.error('Account connection could not be verified. Check the configured Auth project and database permissions.')


def render_conversations(st, store, user):
    st.subheader('Buyer & seller conversations')
    reports_only = st.toggle('Reports needing review')
    threads = store.admin_threads()
    rows = [t for t in threads if not reports_only or t.get('report', {}).get('status') == 'new']
    st.caption('Authorised support access · Most recent 200 conversations · Latest 50 messages per conversation')
    if not rows:
        st.info('Customer conversations and reports will appear here.')
        return
    selected = st.selectbox('Conversation', [t['id'] for t in rows],
        format_func=lambda uid: next(t['item_title'] + ' · ' + t['buyer_name'] for t in rows if t['id'] == uid))
    thread = next(t for t in rows if t['id'] == selected)
    st.write(thread['item_title'])
    st.caption(thread['buyer_name'] + ' ↔ ' + thread['seller_name'])
    if not thread.get('seller_id'):
        st.info('Seller has not joined messaging yet. They must sign up with the email used on the listing.')
        listing = store.listing(thread['listing_id'])
        if listing:
            st.text('Seller email (private): ' + listing['seller_email'])
    if thread.get('blocked_by'):
        st.warning('A participant has paused messaging in this conversation.')
    report = thread.get('report')
    if report:
        st.warning('Customer report · ' + report['status'])
        st.text(report['reason'])
        if report['status'] == 'new' and st.button('Mark report reviewed'):
            store.resolve_report(selected, actor(user))
            st.rerun()
    for row in store.admin_messages(selected, max(0, thread['seq'] - 50)):
        with st.container(border=True):
            st.caption(row['sender'].title() + ' · ' + row['created_at'][:16].replace('T', ' ') + ' UTC')
            if row['kind'] in ('offer', 'invoice', 'offer_response'):
                label = 'PayPal invoice shared' if row['kind'] == 'invoice' else 'Offer ' + row.get('choice', row.get('status', ''))
                st.write(label + ' · ' + money(row['amount_cents']) + ' AUD')
            if row.get('text'):
                st.text(row['text'])
            if row['kind'] == 'invoice':
                st.link_button('View seller-provided PayPal invoice', invoice_url(row['url']))
                st.caption('Payment status is checked in PayPal. No commission was collected by this website.')
