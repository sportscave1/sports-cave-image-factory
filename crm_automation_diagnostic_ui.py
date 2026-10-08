"""Explicit admin-only checks; no page-render Shopify reads or publication."""
import streamlit as st
from crm_automation_capabilities import TOPICS,blocking_reasons,verify


def run_diagnostic(shop,store,user):
    import os_accounts
    if not os_accounts.is_admin(user):raise PermissionError('Only an administrator can run the Shopify diagnostic.')
    return verify(shop,store)


@st.fragment
def control(shop,store,user,kind,key,automation=None):
    import os_accounts
    if not os_accounts.is_admin(user):return
    state=store.state('shopify_automation_capabilities')
    failures=blocking_reasons(state,kind)
    if failures:st.caption('Shopify trigger needs attention · '+'; '.join(failures))
    if automation:operational_status(store,automation)
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
        st.caption('Optional app pixel · '+state.get('pixel','UNVERIFIED')+' · checked '+str(state.get('pixel_checked_at') or 'not recorded'))


def operational_status(store,automation):
    try:
        from crm_email_diagnostics import automation_status,worker_label,utc
        report=automation_status(store,automation)
        st.caption(worker_label(report.get('worker') or {}))
        st.caption('Leased schedule checkpoint · '+utc((report.get('schedule_health') or {}).get('checked_at')))
        st.caption('Latest verified relevant webhook · '+utc(report['latest_event']))
        sync=report.get('reconciliation') or {}
        st.caption(('Checkout reconciliation completed · ' if sync.get('started_at') else 'Last checkout reconciliation checkpoint · ')+utc(sync.get('last_synced_at')))
        st.caption('Published v'+str(automation['config'].get('published_version',0))+' · '+automation['status'].title())
        st.caption('Published · '+'; '.join(str(step.get('name') or 'Email')+' enabled, '+str(step['delay_seconds'])+' seconds delay' for step in report['steps']))
        st.caption('Draft · '+'; '.join(step['name']+' '+('enabled' if step['enabled'] else 'disabled')+', '+str(step['delay_seconds'])+' seconds delay' for step in report['draft_steps']))
        st.caption('Draft edits do not change delivery until published. Existing journeys retain their frozen sequence.')
        st.caption('Next persisted email due · '+utc(report['next_due'])+' · verification retry · '+utc(report['retry_after']))
        counts=report.get('sends') or {}
        st.caption(str(report['enrolled'])+' journeys · '+str(report['accepted'])+' accepted by Resend · '+str(counts.get('FAILED',0))+' failed · '+str(counts.get('BLOCKED',0))+' blocked · '+str(counts.get('UNCERTAIN',0))+' uncertain')
        evaluations=report.get('evaluations') or {}
        if evaluations:
            st.caption('Latest evaluations (up to 100 checkouts) · '+'; '.join(str(n)+' '+reason for reason,n in sorted(evaluations.items())))
        else:st.caption('No checkout evaluation recorded for this flow. Historical checkouts are not automatically enrolled.')
    except Exception:
        st.caption('Operational status unavailable. Check the worker and database connection; no delivery is confirmed here.')
