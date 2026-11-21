"""Shared Orders / Fulfilment view of the same durable preparation record."""
import prodigi_preparation as queue


def render(row, user, *, answers=None, compact=False):
    import streamlit as st
    import os_accounts
    if not queue.enabled() or not os_accounts.is_admin(user):
        return
    allocation = str(row.get('edition_order_id') or '')
    if not allocation.isdigit():
        return
    try:
        queue.require_user(user)
        saved = queue.read(int(allocation))
    except Exception:
        st.warning('Prodigi preparation status is unavailable. No order was submitted.')
        return
    key = 'prodigi-prepare-' + allocation + ('-orders' if compact else '-fulfilment')
    with st.expander('Prepare for Prodigi · manual payment', expanded=not compact):
        st.caption('Attach the numbered production JPG to an existing draft. Payment and release stay manual.')
        if saved:
            st.write(saved['status'])
            st.caption(f"Prodigi order {saved['order_id'] or 'matching pending'} · item {saved['item_id'] or 'matching pending'} · allocation {allocation}")
            if saved.get('order_id'):
                from prodigi_client import identifier
                st.link_button('Open this existing Prodigi order', 'https://dashboard.prodigi.com/orders/'
                               + identifier(saved['order_id']) + '/detail')
            st.info(saved['message'])
            if saved.get('order_id') and saved.get('item_id'):
                with st.expander('Companion QA review prompt'):
                    st.code(queue.review_prompt(saved), language=None)
            for field, label in queue.CHECKS.items():
                st.caption(('✓ ' if saved['checks'].get(field) else 'Review required · ') + label)
            if st.button('Recheck same Prodigi item', key=key+'-recheck'):
                try:
                    queue.reconcile(user, int(allocation))
                except Exception as error:
                    st.error(str(error) if isinstance(error, ValueError) else 'Could not queue a recheck.')
                else:
                    st.rerun()
            if answers is not None:
                slip = st.checkbox('I verified the certificate and paid packing slip are attached to this exact Prodigi order.', key=key+'-slip')
                if st.button('Save QA · ready for manual payment', key=key+'-ready', disabled=saved['status'] != 'Needs QA'):
                    try:
                        queue.complete_qa(user, int(allocation), answers, slip)
                    except Exception as error:
                        st.error(str(error) if isinstance(error, ValueError) else 'QA could not be saved.')
                    else:
                        st.rerun()
        else:
            st.caption('Finds the existing order and item by their exact saved Shopify references. Uncertain matches stop for review.')
            with st.expander('Existing order IDs · optional'):
                order_id = st.text_input('Existing Prodigi order ID', key=key+'-order')
                item_id = st.text_input('Exact Prodigi item ID', key=key+'-item')
            if st.button('Prepare for Prodigi', key=key+'-start'):
                try:
                    queue.request(user, int(allocation), order_id, item_id)
                except Exception as error:
                    st.error(str(error) if isinstance(error, ValueError) else 'Preparation could not be queued.')
                else:
                    st.rerun()
        if compact:
            if st.button('Open Fulfilment QA', key=key+'-qa'):
                import orders_page
                orders_page._open_prodigi_for_row(row)
                st.rerun()


def dashboard():
    import streamlit as st
    st.caption('Orders companion attaches artwork and checks API evidence. Pay and release orders manually in Prodigi.')
    if not queue.enabled():
        st.info('Orders preparation is disabled pending imported-order acceptance.')
        return
    @st.fragment(run_every='10s')
    def status():
        try:
            rows = queue.list_jobs()
        except Exception:
            st.warning('The Orders companion queue is unavailable.')
            return
        for row in rows:
            st.write(f"{row['snapshot']['order_reference']} · #{row['snapshot']['number']:03}/{row['snapshot']['total']} · {row['status']}")
            st.caption(f"Prodigi {row['order_id']} / {row['item_id']} · {row['message']}")
        if not rows:
            st.info('No orders queued. Use Prepare for Prodigi in Orders or Fulfilment.')
    status()
