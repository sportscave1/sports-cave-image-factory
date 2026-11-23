"""Shared Orders / Fulfilment view of the same durable preparation record."""
import os
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
        request_failure=queue.request_failure(int(allocation))
    except Exception:
        st.warning('Prodigi preparation status is unavailable. No order was submitted.')
        return
    key = 'prodigi-prepare-' + allocation + ('-orders' if compact else '-fulfilment')
    with st.expander('Fulfilment · Orders companion', expanded=not compact or str(st.session_state.get('orders-prodigi-review'))==allocation):
        st.caption('Attach artwork, check the saved order, then follow the owner’s submission setting. No supplier delay settings are changed.')
        if request_failure:
            st.warning(request_failure['message'])
            st.caption('Failed at request · '+request_failure['last_failure']['at'])
            if st.button('Retry failed preparation',key=key+'-retry-request'):
                try:queue.request(user,int(allocation))
                except ValueError as error:st.warning(str(error))
                else:st.rerun()
            if not saved:return
            saved=dict(saved,status='Needs review',message=request_failure['message'])
        if os.getenv('SPORTS_CAVE_PRODIGI_DRAFT_EDIT_ACCEPTED', '').lower() != 'true':
            st.caption('The companion uploads artwork through the Prodigi browser. The API only reads and verifies the draft. Payment and production stay manual.')
        if saved:
            st.write(saved['status'])
            st.caption(f"Prodigi order {saved['order_id'] or 'matching pending'} · item {saved['item_id'] or 'matching pending'} · allocation {allocation}")
            if saved.get('order_id'):
                from prodigi_client import identifier
                st.link_button('Open this existing Prodigi order', 'https://dashboard.prodigi.com/orders/'
                               + identifier(saved['order_id']) + '/detail')
            if saved['status']=='Ready for manual payment':st.success('All QA passed · submission follows the Orders companion setting.')
            elif saved['status'] in ('Needs QA','Needs review'):st.warning(saved['message'])
            else:st.info(saved['message'])
            if saved.get('last_failure'):
                failure=saved['last_failure']
                st.caption('Last failed check: '+failure['stage']+' · '+failure['at'])
            if saved.get('artwork_expires_at'):
                st.caption('Recheck before manual payment. Artwork link review date: ' + saved['artwork_expires_at'][:10])
            if saved.get('qa'):
                if saved['qa'].get('checked_at'):st.caption('Last full QA check: '+saved['qa']['checked_at'])
                st.caption('Prodigi download: ' + ('confirmed' if saved['qa'].get('supplier_download_confirmed')
                    else 'pending; the exact artwork is attached for manual release'))
                if (saved.get('document_browser') or {}).get('verified'):
                    st.caption('Certificate attachment verified. Supplier document download: '+
                        ('confirmed' if saved['qa'].get('supplier_certificate_download_confirmed') else 'pending until manual release'))
            approval=saved.get('print_approval') or {}
            if not (saved.get('browser') or {}).get('verified') and not str((saved.get('qa') or {}).get('policy','')).startswith('prodigi-dashboard-inserts-') and approval and not approval.get('print_ready') and approval.get('source_ppi'):
                st.warning(f"Native source: {min(approval['source_ppi']):.0f} PPI; supplier recommendation: {approval['required_ppi']} PPI. Enlarging the JPG does not create native detail.")
                st.caption('A higher-resolution original master is required. This limitation is not automatically waived.')
            if saved.get('document') and not (saved.get('browser') or {}).get('verified'):
                st.link_button('Open verified certificate / packing slip PDF',saved['document']['url'])
            if saved.get('order_id') and saved.get('item_id'):
                with st.expander('Companion QA review prompt'):
                    st.code(queue.review_prompt(saved), language=None)
            from prodigi_dashboard_qa import CHECKS as dashboard_checks
            labels=dashboard_checks if str((saved.get('qa') or {}).get('policy','')).startswith('prodigi-dashboard-inserts-') or (saved.get('browser') or {}).get('verified') else queue.CHECKS
            active=saved['status'] in ('Checking QA','Awaiting dashboard QA','Checking dashboard QA')
            for field, label in labels.items():
                st.caption(('✓ ' if saved['checks'].get(field) else ('Checking · ' if active else 'Review required · ')) + label)
            if 'production_approval' in saved['checks']:
                st.caption(('✓ ' if saved['checks']['production_approval'] else 'Review required · ')+'Production print approval')
            if st.button('Check all QA again', key=key+'-recheck',disabled=bool(saved.get('submission'))):
                try:
                    queue.reconcile(user, int(allocation))
                except Exception as error:
                    st.error(str(error) if isinstance(error, ValueError) else 'Could not queue a recheck.')
                else:
                    st.rerun()
            from prodigi_full_qa import live_enabled
            if answers is not None and not live_enabled():
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
    st.caption('Orders companion attaches artwork and checks the exact saved order.')
    import os_accounts
    user=st.session_state.get('sports_cave_current_user')
    if user and os_accounts.is_admin(user):
        from prodigi_submission import controls
        controls(user)
    if not queue.enabled():
        st.info('Orders preparation is disabled pending imported-order acceptance.')
        return
    @st.fragment(run_every='10s' if st.session_state.get('companion-visible-now', True) else None)
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
