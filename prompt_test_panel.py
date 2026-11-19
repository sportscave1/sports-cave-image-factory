"""Lazy, session-local text test panel for unsaved prompt edits."""
import logging
import secrets
from prompt_test_runner import WORKFLOWS, build_prompt
from prompt_test_inputs import load_choices
from prompt_clipboard import render_copy


def render(st, prompt, text, user, valid=True):
    key = 'prompt-test-' + prompt.key
    with st.expander('Prepare prompt to copy'):
        st.caption('Apply a product to the current draft, then copy the full prompt to test it yourself. No AI connection or generation.')
        if not st.toggle('Select a product', key=key + '-enabled'):
            return
        workflow = st.selectbox('Test workflow', WORKFLOWS[prompt.category], key=key + '-workflow')
        source_key = key + '-' + workflow
        custom = st.checkbox('Enter a product URL instead', key=source_key + '-url-mode')
        choice = None
        if custom:
            title = st.text_input('Product URL', key=source_key + '-url')
            if title.strip():
                choice = dict(id='custom', title=title.strip(), context={'product_url': title.strip()}, source='Custom test product')
        else:
            refresh = st.button('Refresh products' if workflow == 'Ads' else 'Load / refresh test inputs', key=source_key + '-load')
            if refresh or (workflow == 'Ads' and source_key + '-rows' not in st.session_state):
                try:
                    with st.spinner('Loading test inputs...'):
                        rows = load_choices(workflow)
                    st.session_state[source_key + '-rows'] = rows
                    st.session_state.pop(source_key + '-pick', None)
                except Exception:
                    st.session_state[source_key + '-rows'] = []
                    logging.getLogger(__name__).exception('Prompt test inputs unavailable')
                    st.error('Test inputs could not be loaded. Refresh to retry, or enter a product URL.')
            rows = st.session_state.get(source_key + '-rows')
            if rows is not None:
                if not rows:
                    st.info('No matching products or suggestions are available. Refresh the list, or enter a product URL.')
                else:
                    by_id = {r['id']: r for r in rows}
                    options = list(by_id)
                    if source_key + '-pick' not in st.session_state:
                        st.session_state[source_key + '-pick'] = secrets.choice(options)
                    if st.button('Choose another at random', key=source_key + '-random'):
                        st.session_state[source_key + '-pick'] = secrets.choice(options)
                    label = 'Design Studio design' if workflow in ('Upload', 'Edit design') else ('Edition Ops product' if workflow == 'Ads' else 'Test product / suggestion')
                    chosen = st.selectbox(label, options, format_func=lambda value: by_id[value]['title'], key=source_key + '-pick')
                    choice = by_id[chosen]
        if choice and choice['source'] == 'Edition Ops':
            st.text_input('Product URL', value=choice['context']['product_url'], disabled=True, key=source_key + '-selected-url-' + choice['id'])
        if choice:
            st.caption('Test input: ' + choice['title'] + ' - ' + choice['source'])
        if choice and valid:
            compiled = build_prompt(text, workflow, choice)
            st.subheader('Full prompt with product applied')
            st.caption('Copies the complete current draft with your selected product applied.')
            render_copy(st, compiled, preview_label='Show product-applied prompt')
        elif not valid:
            st.info('Fix the editor validation errors to prepare this prompt.')
