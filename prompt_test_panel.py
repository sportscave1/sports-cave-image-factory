"""Lazy, session-local text test panel for unsaved prompt edits."""
import logging
import secrets
from prompt_test_runner import WORKFLOWS, build_prompt
from prompt_test_inputs import load_choices


def render(st, prompt, text, user, valid=True):
    key = 'prompt-test-' + prompt.key
    with st.expander('Prepare prompt to copy'):
        st.caption('Apply a product to the current draft, then copy the full prompt to test it yourself. No AI connection or generation.')
        if not st.toggle('Select a product', key=key + '-enabled'):
            return
        workflow = st.selectbox('Test workflow', WORKFLOWS[prompt.category], key=key + '-workflow')
        source_key = key + '-' + workflow
        custom = st.checkbox('Enter a custom test product', key=source_key + '-custom')
        choice = None
        if custom:
            title = st.text_input('Test product name or Sports Cave URL', key=source_key + '-title')
            details = st.text_area('Test product details', key=source_key + '-details', height=120)
            if title.strip():
                choice = dict(id='custom', title=title.strip(), context={'details': details}, source='Custom test product')
        else:
            if st.button('Load / refresh test inputs', key=source_key + '-load'):
                try:
                    with st.spinner('Loading test inputs...'):
                        rows = load_choices(workflow)
                    st.session_state[source_key + '-rows'] = rows
                    st.session_state.pop(source_key + '-pick', None)
                except Exception:
                    logging.getLogger(__name__).exception('Prompt test inputs unavailable')
                    st.error('Test inputs could not be loaded. Retry, or enter a custom test product.')
            rows = st.session_state.get(source_key + '-rows')
            if rows is not None:
                if not rows:
                    st.info('No matching test inputs are currently available. Refresh the relevant Home brief or Design Studio list, or enter a custom test product.')
                else:
                    options = [r['id'] for r in rows]
                    if source_key + '-pick' not in st.session_state:
                        st.session_state[source_key + '-pick'] = secrets.choice(options)
                    if st.button('Choose another at random', key=source_key + '-random'):
                        st.session_state[source_key + '-pick'] = secrets.choice(options)
                    label = 'Design Studio design' if workflow in ('Upload', 'Edit design') else 'Test product / suggestion'
                    chosen = st.selectbox(label, options, format_func=lambda value: next(r['title'] for r in rows if r['id'] == value), key=source_key + '-pick')
                    choice = next(r for r in rows if r['id'] == chosen)
        if choice:
            st.caption('Test input: ' + choice['title'] + ' - ' + choice['source'])
        if choice and valid:
            compiled = build_prompt(text, workflow, choice)
            st.subheader('Full prompt with product applied')
            st.caption('Use the copy button at the top-right of the prompt below to copy everything. Changes to the draft or product update this prompt automatically.')
            st.code(compiled, language=None, wrap_lines=True)
        elif not valid:
            st.info('Fix the editor validation errors to prepare this prompt.')
