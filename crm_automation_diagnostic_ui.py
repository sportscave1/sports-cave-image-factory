"""Explicit admin-only checks; no page-render Shopify reads or publication."""
import streamlit as st
from crm_automation_capabilities import TOPICS,blocking_reasons,verify


def run_diagnostic(shop,store,user):
    import os_accounts
    if not os_accounts.is_admin(user):raise PermissionError('Only an administrator can run the Shopify diagnostic.')
    return verify(shop,store)


@st.fragment
def control(shop,store,user,kind,key):
    import os_accounts
    if not os_accounts.is_admin(user):return
    state=store.state('shopify_automation_capabilities')
    failures=blocking_reasons(state,kind)
    if failures:st.caption('Shopify trigger needs attention · '+'; '.join(failures))
    with st.expander('Shopify trigger diagnostic',expanded=bool(failures)):
        if st.button('Run diagnostic',key=key+'shopify_diagnostic'):
            try:
                state=run_diagnostic(shop,store,user)
                failures=blocking_reasons(state,kind)
            except Exception as exc:
                # Never expose provider error bodies, tokens or connection strings.
                st.caption('Diagnostic could not be saved · '+type(exc).__name__+'. Retry or check server configuration.')
        st.caption(('Abandoned checkout' if kind=='abandoned' else kind.replace('_',' ').title())+' trigger · '+('NOT READY' if failures else 'READY'))
        checks=state.get('checks',{})
        for name in ('App identity','Shopify API','read_customers',*(() if kind=='welcome' else ('read_orders',)),'Webhook HMAC','Callback configuration',*TOPICS.get(kind,())):
            st.caption(name+' · '+checks.get(name,'UNVERIFIED'))
            if name in TOPICS.get(kind,()) and checks.get(name)!='VERIFIED':
                for row in state.get('webhook_details',{}).get(name,{}).get('subscriptions',[]):
                    st.caption('↳ '+row['api_version']+' · '+row['callback'])
        st.caption('Required webhook API version · 2026-04')
        st.caption('Last checked · '+str(state.get('checked_at') or 'Never'))
