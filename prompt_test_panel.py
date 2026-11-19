"""Lazy, session-local text test panel for unsaved prompt edits."""
import json
import logging
import secrets
from prompt_test_runner import WORKFLOWS, configuration, fingerprint, run
from prompt_test_inputs import load_choices, prepare


def render(st, prompt, text, user, valid=True):
    key = 'prompt-test-' + prompt.key
    with st.expander('Test prompt before activating'):
        st.caption('Generate a text result using this editor draft. Tests do not activate prompts, generate artwork, create queue jobs or publish products or ads.')
        if not st.toggle('Set up a test', key=key + '-enabled'):
            return
        workflow = st.selectbox('Test workflow', WORKFLOWS[prompt.category], key=key + '-workflow')
        source_key = key + '-' + workflow
        custom = st.checkbox('Enter a custom test product', key=source_key + '-custom')
        choice = None
        if custom:
            title = st.text_input('Test product name', key=source_key + '-title')
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
        configured = bool(configuration()[0])
        if not configured:
            st.info('The server OpenAI connection is required to run a text test.')
        if st.button('Test prompt', key=key + '-run', disabled=not valid or not choice or not configured):
            try:
                with st.spinner('Testing the current draft...'):
                    item, image = prepare(choice)
                    result = run(text, workflow, item, image)
                result['selection_fingerprint'] = fingerprint(text, workflow, choice)
                st.session_state[key + '-result'] = result
            except ValueError as exc:
                st.error(str(exc))
            except Exception:
                logging.getLogger(__name__).exception('Prompt test failed')
                st.error('The test could not finish. Your draft is retained; retry explicitly.')
        result = st.session_state.get(key + '-result')
        if result:
            if not choice or result['selection_fingerprint'] != fingerprint(text, workflow, choice):
                st.warning('Previous test result: the draft, workflow or selected input has changed. Run Test prompt again to test the current version.')
            if result['incomplete']:
                st.warning('The model reached its response limit. This is a partial result.')
            st.subheader('Test result')
            st.caption(result['item']['title'] + ' - ' + result['model'] + ' - ' + result['created_at'][:19] + ' UTC')
            st.markdown(result['text'])
            st.download_button('Download test result', result['text'], file_name='prompt-test-result.txt', key=key + '-download')
            with st.expander('Draft and input used for this test'):
                st.json(result['item'])
                st.code(result['draft'], language=None, wrap_lines=True)
