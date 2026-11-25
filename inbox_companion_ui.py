"""Owner controls only; Inbox Companion intentionally has no top status bar."""
def controls(actor):
    import streamlit as st
    import os_accounts
    import inbox_companion as inbox
    if not os_accounts.is_admin(actor) or not os_accounts.can_access_page(actor,'Email'):
        st.caption('Inbox Companion requires administrator and Email access.');return
    certificate_controls(actor)
    st.caption('Address updates and confirmation replies. Other order changes are paused for your review. Never cancels orders or changes products.')
    if not inbox.available():
        st.info('Prepared locally. Inbox Companion is not enabled on this server.');return
    if not inbox.os.getenv('SPORTS_CAVE_INBOX_AUTH_SERVERS','').strip():
        st.info('Inbox Companion needs verified mailbox sender authentication before activation.');return
    config=inbox.read(inbox.SETTING)
    enabled=st.toggle('Run Inbox Companion in the background',value=bool(config.get('enabled')),key='inbox-companion-enabled')
    if enabled!=bool(config.get('enabled')):
        inbox.configure(actor,enabled);st.rerun()
    st.caption('Uses the paired Edge Companion. Only new emails after activation are checked. Existing orders keep their current countdown after a confirmed address update.')
    with inbox.prep.connect() as c,c.cursor() as q:
        q.execute("SELECT value FROM app_settings WHERE key LIKE 'inbox_companion_request:%%' ORDER BY updated_at DESC LIMIT 25")
        jobs=[r['value'] for r in q.fetchall()]
    if not jobs:st.caption('No customer order changes detected since activation.')
    for job in jobs:
        st.write(job['order_name']+' · '+job['state'])
        st.caption(job.get('message') or 'Checking customer request')
        flag=inbox.read(inbox.FLAG+job['shopify_order_id'])
        if flag.get('blocking') and flag.get('request')==job['key']:
            st.caption('Review the customer email and supplier order before clearing this flag. Clearing it does not resume Prodigi.')
            if st.button('Reviewed — clear order flag',key='inbox-review-'+job['key']):
                inbox.review(actor,job['key']);st.rerun()


def certificate_controls(actor):
    import streamlit as st
    import inbox_certificate_replies as replies
    import inbox_companion as state
    with st.expander('Missing certificate replies', expanded=True):
        config = state.read(replies.SETTING)
        enabled = st.toggle('Automatically reply to missing certificate or packing slip emails',
                            value=bool(config.get('enabled')), key='certificate-replies-enabled')
        if enabled != bool(config.get('enabled')):
            try:
                replies.configure(actor, enabled)
                st.rerun()
            except (ValueError, PermissionError) as error:
                st.error(str(error))
        st.caption('Links customers to My Collection, mentions framing and asks for a review. Uses Nathan’s saved signature. Runs on the server; checks new mail only and leaves existing replies and drafts alone.')
        if st.button('Check newest Inbox request', key='certificate-replies-preview'):
            try:
                st.session_state['certificate-replies-current'] = replies.preview_latest(actor)
            except Exception:
                st.error('The Inbox could not be checked. Try again shortly.')
        preview = st.session_state.get('certificate-replies-current')
        if preview:
            if preview['status'] == 'eligible':
                st.write('Reply to ' + preview['header']['sender']['email'])
                st.markdown(preview['html'], unsafe_allow_html=True)
                st.caption('Nathan’s existing signature is appended once when sent.')
                if st.button('Enable and reply to this request', key='certificate-replies-current-send'):
                    try:
                        replies.configure(actor, True, existing=preview['header'])
                        st.session_state.pop('certificate-replies-current', None)
                        st.rerun()
                    except Exception:
                        st.error('This request could not be queued. Check it again; no new reply was authorised.')
            else:
                st.info(preview['reason'])
        with state.prep.connect() as c, c.cursor() as q:
            q.execute("""SELECT value->>'sender_email' AS sender, value->>'reason' AS reason,
              COALESCE(o.status, a.value->>'status') AS status
              FROM app_settings a LEFT JOIN support_email_outbox o
                ON o.operation_id::text=a.value->>'operation_id' AND o.mailbox=%s
              WHERE a.key LIKE 'inbox_certificate_reply:%%' ORDER BY a.updated_at DESC LIMIT 5""",
                      (config.get('mailbox', 'hello@sportscaveshop.com'),))
            for row in q.fetchall():
                st.caption(row['sender'] + ' · ' + row['status'] + ' · ' + row['reason'])
