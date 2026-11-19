"""Owner prompt library: source templates, immutable drafts and deployment receipts."""
import difflib
import html
import json
import os

from prompt_library import ROOT, catalog, digest
from prompt_releases import GitStore, ReleaseError


def render_page(user):
    import os_accounts
    import streamlit as st

    if not os_accounts.is_admin(user) or not os_accounts.account_is_active(user):
        st.error('Prompts is available to administrators only.')
        return
    identity = str(user.get('id') or user.get('email'))
    if st.session_state.get('prompts-connection-owner') != identity:
        for name in ('prompts-github-token', 'prompts-render-token'):
            st.session_state.pop(name, None)
        st.session_state['prompts-connection-owner'] = identity
    st.html('''<style>
    .st-key-prompts-workspace {--prompt-gold:#a17b32;}
    .st-key-prompts-workspace h1 {font-size:2.4rem;letter-spacing:-.055em;font-weight:750;}
    .st-key-prompts-workspace h3 {font-size:1.2rem;letter-spacing:-.025em;}
    .st-key-prompts-workspace [data-baseweb="tab-list"] {gap:28px;border-bottom:1px solid #dedbd3;}
    .st-key-prompts-workspace [data-baseweb="tab"] {padding:12px 4px;font-size:15px;}
    .st-key-prompts-workspace [data-baseweb="tab-highlight"] {background:#a17b32;}
    .st-key-prompts-workspace [data-testid="stVerticalBlockBorderWrapper"] {border-radius:14px;}
    .st-key-prompts-workspace textarea {font-family:ui-monospace,Consolas,monospace;font-size:13px;line-height:1.7;}
    .prompt-eyebrow {font-size:11px;font-weight:650;letter-spacing:.18em;color:#9a7b40;text-transform:uppercase;}
    .prompt-summary {color:#7b7b78;font-size:14px;margin:-10px 0 22px;}
    .prompt-badge {display:inline-block;background:#f5eddb;color:#85631f;border:1px solid #e8dcc1;
      padding:5px 10px;border-radius:20px;font-size:12px;font-weight:600;}
    .prompt-history {border-bottom:1px solid #e9e6df;padding:12px 0;}
    </style>''')
    with st.container(key='prompts-workspace'):
        st.html('<div class="prompt-eyebrow">Sports Cave / Intelligence library</div>')
        st.title('Prompts')
        st.html('<p class="prompt-summary">Refine the instructions. Keep every version. Release with confidence.</p>')
        github_token = st.session_state.get('prompts-github-token') or os.getenv('PROMPTS_GITHUB_TOKEN', '')
        render_token = st.session_state.get('prompts-render-token') or os.getenv('RENDER_API_KEY', '')
        with st.expander('Release connection', expanded=not github_token):
            st.caption('Drafts are saved on a separate Git branch. Activate version publishes only the selected template to the existing Sports Cave OS service. Tokens stay in this signed-in session unless configured on the server.')
            st.text_input('GitHub token · repository Contents read/write', type='password', key='prompts-github-token')
            st.text_input('Render API key · deployment status', type='password', key='prompts-render-token')
            st.caption('Server configuration: PROMPTS_GITHUB_TOKEN and RENDER_API_KEY. Never paste tokens into prompt text.')
        store = GitStore(github_token, render_token)
        prompts = catalog()
        st.caption(f'{len(prompts)} source templates & instruction blocks · Design / Upload / Ads')
        st.info('These are the deployed source templates. Prompts assembled for a specific product also include its context and any previously saved module overrides. Drafts do not change running prompts.')
        for category, tab in zip(('Design', 'Upload', 'Ads'), st.tabs(['Design', 'Upload', 'Ads'])):
            with tab:
                _category(st, store, prompts, category, user)


def _category(st, store, prompts, category, user):
    search = st.text_input('Find a prompt', placeholder=f'Search {category.lower()} prompts…', key='prompt-search-' + category)
    rows = [p for p in prompts if p.category == category and search.casefold() in (p.title + ' ' + p.text).casefold()]
    if not rows:
        st.caption('No matching prompts. Try another search.')
        return
    key = st.selectbox('Prompt library', [p.key for p in rows],
                       format_func=lambda k: next(p.title for p in rows if p.key == k), key='prompt-select-' + category)
    prompt = next(p for p in rows if p.key == key)
    history, history_sha = {'versions': []}, None
    if store.token:
        try:
            history, history_sha = store.history(prompt)
        except ReleaseError as exc:
            st.error(str(exc))
            return
    versions = history['versions']
    left, right = st.columns([2.4, 1], gap='large')
    with right:
        with st.container(border=True):
            st.subheader('Version history')
            choice = st.radio('Open a version', ['deployed'] + [v['id'] for v in reversed(versions)],
                format_func=lambda value: 'Deployed source' if value == 'deployed' else
                    'v' + next(v['version'] for v in versions if v['id'] == value), key='prompt-version-' + key)
            st.caption('Opening an older version lets you save it as a new draft. Saved versions are never overwritten.')
            st.button('Refresh history', key='prompt-refresh-' + key, on_click=lambda: None)
    selected = next((v for v in versions if v['id'] == choice), None)
    initial = selected['text'] if selected else prompt.text
    manifest_path = ROOT / 'prompts' / 'releases.json'
    deployed = json.loads(manifest_path.read_text(encoding='utf-8')).get(key, {}) if manifest_path.exists() else {}
    with left:
        with st.container(border=True):
            st.subheader(prompt.title)
            badge = ('Saved v' + selected['version']) if selected else ('Deployed v' + deployed.get('version', '1.0'))
            st.html('<span class="prompt-badge">' + html.escape(badge) + '</span>')
            edit, preview, compare = st.tabs(['Edit prompt', 'Full prompt preview', 'Compare versions'])
            with edit:
                buffer_key = f'{key}-{choice}'
                buffers = st.session_state.setdefault('prompt-editor-buffers', {})
                widget_key = 'prompt-text-' + buffer_key
                def retain_buffer():
                    st.session_state['prompt-editor-buffers'][buffer_key] = st.session_state[widget_key]
                text = st.text_area('Prompt instructions', buffers.get(buffer_key, initial), height=460,
                                    key=widget_key, on_change=retain_buffer)
                st.caption('Keep {placeholders} and ⟪slot:n⟫ tokens intact. Slots are supplied by the app when the prompt is built.')
            with preview:
                st.code(text, language=None, wrap_lines=True)
                st.download_button('Download prompt', text, file_name=prompt.title + '.txt', key='prompt-download-' + key)
            with compare:
                compare_id = st.selectbox('Compare against', ['deployed'] + [v['id'] for v in versions],
                    format_func=lambda value: 'Deployed source' if value == 'deployed' else 'v' + next(v['version'] for v in versions if v['id'] == value),
                    key='prompt-compare-' + key)
                before = prompt.text if compare_id == 'deployed' else next(v['text'] for v in versions if v['id'] == compare_id)
                delta = '\n'.join(difflib.unified_diff(before.splitlines(), text.splitlines(), fromfile='Comparison', tofile='Editor', lineterm=''))
                st.code(delta or 'No changes.', language='diff', wrap_lines=True)
            note = st.text_input('Version note', placeholder='What changed, and why?', key='prompt-note-' + key)
            save_col, activate_col = st.columns(2)
            if save_col.button('Save draft', key='prompt-save-' + key, use_container_width=True, disabled=not store.token):
                try:
                    store.save(prompt, text, note, str(user.get('email') or user.get('id')), history, history_sha)
                    st.success('Version saved. Open it in Version history to activate.')
                    st.rerun()
                except (ReleaseError, ValueError) as exc:
                    st.error(str(exc))
            can_activate = bool(selected and store.token and store.render_token and text == initial
                                and not selected.get('commit') and not selected.get('baseline'))
            if activate_col.button('Activate version', type='primary', key='prompt-activate-' + key,
                                   use_container_width=True, disabled=not can_activate):
                st.session_state['prompt-confirm-' + key] = selected['id']
            if selected and st.session_state.get('prompt-confirm-' + key) == selected['id']:
                st.warning(f'Publish saved v{selected["version"]} to Git main and deploy Sports Cave OS? Review Compare versions first.')
                if st.button('Publish this saved version', key='prompt-publish-' + key, disabled=not can_activate):
                    st.session_state.pop('prompt-confirm-' + key, None)
                    try:
                        store.activate(prompt, selected['id'], history, history_sha)
                        st.rerun()
                    except (ReleaseError, ValueError) as exc:
                        st.error(str(exc))
            if not store.token:
                st.caption('Connect GitHub above to save durable drafts. You can download edits now.')
            elif not store.render_token:
                st.caption('Connect Render above to enable activation and deployment tracking.')
            if selected:
                st.caption(f'Saved {selected["created_at"][:19].replace("T", " ")} UTC · {selected.get("author", "")}')
                if selected.get('note'):
                    st.caption(selected['note'])
                if selected.get('commit'):
                    _deployment(st, store, prompt, selected)
            with st.expander('Source & template details'):
                st.code(prompt.path + (':' + prompt.symbol if prompt.symbol else ''), language=None)
                st.caption('Editing template text cannot change Python interpolation expressions. Activation rejects stale prompt content and concurrent Git changes.')


def _deployment(st, store, prompt, selected):
    @st.fragment(run_every='15s')
    def status_panel():
        try:
            status = store.status(prompt, selected)
            st.metric('Release status', f'{status} · v{selected["version"]}')
        except ReleaseError as exc:
            st.warning('Status unavailable. ' + str(exc))
        st.caption('Git revision ' + selected['commit'][:12])
        st.link_button('View deployment', 'https://dashboard.render.com/web/srv-d8kl4on7f7vs73dvavv0')
    status_panel()
