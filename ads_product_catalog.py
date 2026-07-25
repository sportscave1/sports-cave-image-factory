import streamlit as st


ADS_PRODUCT_CATALOG_CACHE_SECONDS = 300


@st.cache_data(ttl=ADS_PRODUCT_CATALOG_CACHE_SECONDS, show_spinner=False)
def load_live_edition_product_rows():
    """Return the lightweight Edition Ops catalogue without importing its page."""
    try:
        import supabase_backend

        if not supabase_backend.is_configured():
            return []
        return list(supabase_backend.list_product_edition_summary() or [])
    except Exception:
        return []
