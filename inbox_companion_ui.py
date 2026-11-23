"""Owner controls only; Inbox Companion intentionally has no top status bar."""
def controls(actor):
    import streamlit as st
    import os_accounts
    import inbox_companion as inbox
    if not os_accounts.is_admin(actor) or not os_accounts.can_access_page(actor,'Email'):
        st.caption('Inbox Companion requires administrator and Email access.');return
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
