"""Non-secret recorder context for the existing account-scoped upload recovery."""
import html
import json
import streamlit as st


def restore(row):
    """Consume explicit recorder restoration only after authorized row lookup."""
    if st.query_params.get('recorder_source') is None:
        return
    key = str(row['id'])
    source = row['data'].get('source') or {}
    if st.query_params.get('recorder_source') != source.get('content_hash'):
        raise ValueError('The recorded PSD has changed. Recording context cannot be restored.')
    name = st.query_params.get('recorder_name', '')
    category = st.query_params.get('recorder_category', '')
    if not name.strip() or len(name) > 100 or not category or len(category) > 180:
        raise ValueError('Recorded product details are incomplete.')
    from product_upload_sport import state_key
    st.session_state['product-upload-name-'+key] = name
    st.session_state[state_key(key)+'-id'] = category
    for field in ('recorder_source','recorder_name','recorder_category'):
        st.query_params.pop(field, None)


def publish(row, name, choice):
    source = row['data'].get('source') or {}
    context = dict(kind='product_uploads', workflow=str(row['id']), name=name.strip(),
                   category=(choice or {}).get('id',''), source=source.get('content_hash',''),
                   source_id=source.get('id',''), revision=source.get('rev',''))
    ready = bool(context['name'] and context['category'] and context['source']
                 and row['data'].get('server_artwork',{}).get('state') == 'Ready')
    st.html('<span id="sc-recorder-context" hidden data-ready="'+str(ready).lower()+
            '" data-context="'+html.escape(json.dumps(context), quote=True)+'"></span>')
