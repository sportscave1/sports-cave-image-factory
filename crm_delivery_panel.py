"""Admin-only manual diagnostic, independent of CRM workflow storage."""
import uuid
import streamlit as st
import os_accounts
from crm_resend_marketing import get_resend_marketing_config_status, send_resend_test_email, DeliveryError


def render_delivery_panel(user):
    if not os_accounts.is_admin(user):
        return
    status = get_resend_marketing_config_status()
    with st.expander('RESEND DELIVERY', expanded=True):
        st.caption('TEST ONLY · One manually entered recipient. No customers, segments or campaigns.')
        st.text('Domain: ' + (status['domain'] or 'Missing') + '\n'
                'API: ' + ('Configured' if status['api_configured'] else 'Missing') + '\n'
                'Sender: ' + (status['sender'] or 'Missing') + '\n'
                'Reply-To: ' + (status['reply_to'] or 'Missing') + '\n'
                'Marketing Delivery: ' + ('ENABLED' if status['marketing_enabled'] else 'DISABLED'))
        if not status['from_name_configured']:
            st.caption('Sender name configuration is missing or invalid.')
        key = 'crm_resend_admin_test'
        st.session_state.setdefault(key + '_operation', str(uuid.uuid4()))
        with st.form(key, clear_on_submit=True):
            recipient = st.text_input('Test recipient email', value='', key=key + '_recipient')
            confirmed = st.checkbox('I confirm this is one admin TEST ONLY email.', key=key + '_confirm')
            clicked = st.form_submit_button('Send Test Email', disabled=not status['configured'] or status['marketing_enabled'])
        if clicked:
            operation = st.session_state[key + '_operation']
            # Consume this action before I/O; a rerun is not another send.
            st.session_state[key + '_operation'] = str(uuid.uuid4())
            try:
                result = send_resend_test_email(user=user, recipient=recipient, confirmed=confirmed,
                                                operation_id=operation)
                st.success(result['message'])
                st.text('Resend message ID: ' + result['message_id'])
                if not result['audit_saved']:
                    st.warning('Resend accepted the test, but the final audit receipt could not be saved. Do not resend; check Resend using the message ID.')
            except (DeliveryError, PermissionError) as exc:
                st.error(str(exc))
