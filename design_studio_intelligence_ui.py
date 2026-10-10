"""Compact UI; preparation is explicit so opening a page performs no analytics I/O."""
import streamlit as st
import design_studio_sales_intelligence as intelligence


def render_summary(snapshot, *, key, sport, can_refresh=False):
    with st.expander('Sales & Design Intelligence', expanded=False):
        if not snapshot:
            st.caption('Analytics not prepared. Preparing Research or a Design Brief includes available sales evidence automatically.')
            return None
        st.caption(f"{snapshot['status']} · {snapshot['period_start']} to {snapshot['period_end_exclusive']} (end exclusive) · {snapshot['products_analysed']} products")
        st.caption(f"Snapshot prepared {snapshot['prepared_at']} · {snapshot['scope']}")
        st.caption('Preparation time is not source freshness. Source timestamps and coverage are included in the evidence.')
        for row in snapshot.get('performers', [])[:3]:
            money = f"{row['currency']} {row['net_revenue']:,.2f} net" if row['net_revenue'] is not None else 'net revenue unavailable'
            st.write(f"{row['title']} — {row['market']}: {row['gross_units']} gross units / {row['orders']} orders; {money}.")
            st.caption(f"Shopify stored {row['sales_source_refreshed_at'] or 'unknown'} · {row['source_freshness']} · {row['confidence']}")
        st.caption('Direction: compare these products for presentation and collection gaps; preserve the selected subject and approved moment. Artwork inspection is pending.')
        for limitation in snapshot.get('limitations', [])[:3]:
            st.caption(limitation)
        st.caption('Full source coverage, financial caveats and artwork-inspection rules are included in the prompt.')
        if can_refresh and st.button('Refresh intelligence', key=key + '::refresh'):
            with st.spinner('Refreshing stored sales evidence…'):
                return intelligence.get_snapshot(sport, snapshot.get('market', 'All'), refresh=True)
    return None


def prepare_research(sport, *, key, can_refresh=False):
    scope_key = key + '::' + str(sport)
    snapshot = st.session_state.get(scope_key)
    if st.button('Prepare Research', key=scope_key + '::prepare', type='primary'):
        with st.spinner('Preparing Research with available sales evidence…'):
            snapshot = intelligence.get_snapshot(sport)
            st.session_state[scope_key] = snapshot
    refreshed = render_summary(snapshot, key=scope_key, sport=sport, can_refresh=can_refresh)
    if refreshed is not None:
        snapshot = refreshed
        st.session_state[scope_key] = snapshot
    return snapshot
