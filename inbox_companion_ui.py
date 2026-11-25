"""Owner controls only; Inbox Companion intentionally has no top status bar."""

def certificate_outcome(status, reason=''):
    """Explain the authoritative outbox result, never an older queue reason."""
    messages = {
        'accepted': ('✓ Companion sent', 'Reply sent automatically.'),
        'queued': ('Queued', 'Waiting to send automatically.'),
        'in_progress': ('Sending', 'Sending the automatic reply.'),
        'unknown': ('Checking reply', 'Checking whether the original reply was sent. Do not resend.'),
        'rejected': ('Needs attention', 'The reply was not accepted. Review this request.'),
        'answered': ('Already answered', 'A reply already exists in Sent.'),
    }
    if status in messages:
        return messages[status]
    if status == 'review':
        return 'Needs attention', reason or 'Review this request before replying.'
    if status == 'ignored':
        return 'No automatic reply', reason or 'This message does not match the certificate reply rules.'
    return 'Checking request', 'The reply status has not been confirmed.'


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
            st.caption('Review the customer email and supplier order before clearing this flag. Verified, unsubmitted drafts return to fresh QA before configured submission. Existing supplier pauses remain unchanged.')
            if st.button('Reviewed — clear order flag',key='inbox-review-'+job['key']):
                inbox.review(actor,job['key']);st.rerun()


def _certificate_toggle(actor):
    import streamlit as st
    import inbox_certificate_replies as replies
    try:
        replies.configure(actor, bool(st.session_state['certificate-replies-enabled']))
    except Exception:
        st.session_state['certificate-replies-action-error'] = 'The reply setting could not be changed. Try again shortly.'


def _certificate_current(actor, header):
    import streamlit as st
    import inbox_certificate_replies as replies
    try:
        replies.configure(actor, True, existing=header)
        st.session_state.pop('certificate-replies-current', None)
    except Exception:
        st.session_state['certificate-replies-action-error'] = 'This request could not be queued. Check it again; no new reply was authorised.'


def certificate_controls(actor):
    import streamlit as st
    import inbox_certificate_replies as replies
    import inbox_companion as state
    with st.expander('Missing certificate replies', expanded=True):
        config = state.read(replies.SETTING)
        # Synchronise before instantiating the widget. Only actual user callbacks
        # change server settings; stale page state must never disable another action.
        st.session_state['certificate-replies-enabled'] = bool(config.get('enabled'))
        st.toggle('Automatically reply to missing certificate or packing slip emails',
                  key='certificate-replies-enabled', on_change=_certificate_toggle, args=(actor,))
        error = st.session_state.pop('certificate-replies-action-error', None)
        if error:
            st.error(error)
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
                st.button('Enable and reply to this request', key='certificate-replies-current-send',
                          on_click=_certificate_current, args=(actor, preview['header']))
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
                label, message = certificate_outcome(row['status'], row['reason'])
                st.caption((row['sender'] or 'Customer request') + ' · ' + label + ' · ' + message)
