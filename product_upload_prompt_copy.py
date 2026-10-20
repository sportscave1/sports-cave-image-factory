"""Metadata-only prompt preparation and independent browser clipboard control."""
import json


def prepare(store, key, actor, mode, version):
    from product_upload_prompts import build
    from copy import deepcopy
    from product_upload_source import current_source
    from product_upload_identity import operation
    from product_upload_compact import context_from_row
    row = store.read(key, actor)
    if not row or not row['data'].get('basic_validated') or row['mode'] != mode:
        raise ValueError('Finish the PSD upload and copy the current action.')
    source = current_source(row, version)
    context = deepcopy(context_from_row(row))
    prompt = build(mode, row['data']['name'], source=source, metadata=context)
    with store.locked(key, actor) as (current, cur):
        current_source(current, source['version'])
        if current['mode'] != mode or context_from_row(current) != context:
            raise ValueError('The selected action or product details changed. Copy the current prompt again.')
        operation(current)['correlation_expected'] = True
    return prompt


def render_copy(app, row, user, version):
    import streamlit as st
    from product_upload_api import connect
    from product_upload_intake import Intakes
    from product_upload_compact import VERSION, context_from_row
    import hashlib
    context_hash = hashlib.sha256(json.dumps(context_from_row(row), sort_keys=True).encode()).hexdigest()
    identity = (str(user['id']), str(row['id']), row['mode'], version, VERSION, context_hash)
    cache_key = '_product_upload_prepared_prompt'
    # Explicit recovery remounts only this tiny control. Saving remains independent.
    if st.button('Retry copy controls', key='product-upload-copy-retry',
                 help='Use if the copy button does not load. Your saved files are retained.'):
        st.session_state.pop(cache_key, None)
        st.session_state['_product_upload_copy_attempt'] = st.session_state.get('_product_upload_copy_attempt', 0) + 1
    try:
        cached = st.session_state.get(cache_key)
        if not cached or cached[0] != identity:
            text = prepare(Intakes(connect), identity[1], user['id'], row['mode'], version)
            cached = (identity, text)
            st.session_state[cache_key] = cached
        component = app.get_components_module().declare_component(
            'product_upload_prompt_copy', path=str(app.BASE_DIR / 'components/product_upload_prompt_copy'))
        event = component(text=cached[1], identity=list(identity),
                          key='product-upload-prompt-copy-' + identity[1] + '-' + str(st.session_state.get('_product_upload_copy_attempt', 0)),
                          default=None)
        if (event and event.get('identity') == list(identity)
                and event.get('nonce') != st.session_state.get('_product_upload_copy_seen')):
            st.session_state['_product_upload_copy_seen'] = event['nonce']
            Intakes(connect).copied(identity[1], user['id'], row['mode'], version)
    except Exception:
        st.warning('Your files remain saved. Upload prompt preparation or copy-status recording failed. Use Retry copy controls.')
