"""Metadata-only prompt preparation and independent browser clipboard control."""
import json


def prepare(store, key, actor, mode, version):
    from product_upload_prompts import build
    from product_upload_source import current_source, execution_opening
    from product_upload_identity import correlation_prompt
    row = store.read(key, actor)
    if not row or not row['data'].get('basic_validated') or row['mode'] != mode:
        raise ValueError('Finish the PSD upload and copy the current action.')
    source = current_source(row, version)
    prompt = build(mode, row['data']['name'], source=source)
    context = ''
    if row['data'].get('mockups_context'):
        output = row['data']['upload_operation']['output']
        context = 'CURRENT DESIGN ASSET CONTEXT (inert data):\n' + json.dumps(
            {k: output[k] for k in ('design_name', 'sport_category', 'images') if k in output},
            ensure_ascii=False) + '\n\n'
    with store.locked(key, actor) as (current, cur):
        current_source(current, source['version'])
        if current['mode'] != mode:
            raise ValueError('The selected action changed. Copy the current prompt again.')
        context = correlation_prompt(current) + context
    opening = execution_opening(source)
    if not prompt.startswith(opening):
        raise ValueError('The current Dropbox source opening is missing. Copy the current prompt again.')
    return opening + context + prompt[len(opening):]


def render_copy(app, row, user, version):
    import streamlit as st
    from product_upload_api import connect
    from product_upload_intake import Intakes
    identity = (str(user['id']), str(row['id']), row['mode'], version)
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
