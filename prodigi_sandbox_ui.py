"""Clearly separated sandbox rows on Orders; no Shopify/Edition Ops writes."""
import os


def render(selected, user):
    import streamlit as st
    import os_accounts
    import prodigi_preparation as prep
    if not prep.enabled() or not os_accounts.is_admin(user):
        return
    with st.expander('Prodigi sandbox test · no payment or production'):
        import prodigi_sandbox as sandbox
        st.caption('Copies one selected unit’s customer details and exact retained numbered JPG into a separate sandbox draft. '
                   'Live orders, Shopify and edition allocations stay unchanged.')
        ready = bool(os.getenv('PRODIGI_SANDBOX_API_KEY'))
        if not ready:
            st.info('The separate Prodigi sandbox API key is required on the server.')
        eligible = len(selected) == 1 and str(selected[0].get('edition_order_id') or '').isdigit()
        if st.button('Create sandbox test from selected unit', disabled=not ready or not eligible, key='orders-sandbox-create'):
            try:
                sandbox.request(user, int(selected[0]['edition_order_id']))
            except Exception as error:
                st.error(str(error) if isinstance(error, ValueError) else 'The sandbox test could not be created.')
            else:
                st.rerun()
        if not eligible:
            st.caption('Select exactly one numbered order in the table first.')
        try:
            rows = [r for r in sandbox.list_tests() if not r.get('hidden')]
        except Exception:
            st.warning('Sandbox test rows could not be loaded.')
            return
        if not rows:
            st.caption('No sandbox orders in the app.')
        for row in rows:
            snap = row['snapshot']
            st.dataframe([{'Order': 'SANDBOX · '+row['id'][:8], 'Source': row['source_snapshot']['order_reference'],
                'Customer': snap['recipient']['name'], 'Product': snap['product'],
                'Edition': f"{snap['number']:03}/{snap['total']}", 'Status': row['status']}], hide_index=True)
            st.info(row['message'])
            if not (row['source_snapshot'].get('production_evidence') or {}).get('print_ready'):
                st.warning('This export has no production approval. It can be tested in sandbox; live preparation still requires approval.')
            with st.expander('Sandbox customer and QA · '+row['id'][:8]):
                st.json(snap['recipient'])
                st.caption('QA passes only with evidence; missing certificate/packing slip checks remain for review.')
                for field, label in prep.CHECKS.items():
                    st.caption(('✓ ' if row['checks'].get(field) else 'Review required · ') + label)
            if row.get('order_id'):
                from prodigi_client import identifier
                st.link_button('Open sandbox draft', 'https://sandbox-beta-dashboard.pwinty.com/orders/'
                    + identifier(row['order_id'])+'/detail')
            if row.get('sandbox_unpaid_verified') and row.get('artwork_readback_verified'):
                st.success('Exact artwork read back from the sandbox. Draft remains unpaid and unsubmitted.')
            if st.button('Remove sandbox row from app', key='sandbox-remove-'+row['id'],
                         disabled=row['status'] in ('Queued','Uploading','Creating sandbox draft')):
                try:
                    sandbox.remove(user, row['id'])
                except Exception as error:
                    st.error(str(error) if isinstance(error, ValueError) else 'The sandbox row could not be removed.')
                else:
                    st.rerun()
        if rows and st.button('Refresh sandbox status', key='sandbox-refresh'):
            st.rerun()
