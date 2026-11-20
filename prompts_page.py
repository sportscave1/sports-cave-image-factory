"""Owner prompt library: source templates, immutable drafts and deployment receipts."""
import difflib
import html
import json
import os

from prompt_library import ROOT, Prompt, catalog
from prompt_bundle import bundle_prompt, combine, is_bundle, split
from prompt_releases import GitStore, ReleaseError
from prompt_clipboard import render_copy


def render_page(user):
    import os_accounts
    import streamlit as st

    if not os_accounts.is_admin(user) or not os_accounts.account_is_active(user):
        st.error('Prompts is available to administrators only.')
        return
    st.html('''<style>
    section.main:has(.st-key-prompts-workspace) .block-container,
    [data-testid="stMainBlockContainer"]:has(.st-key-prompts-workspace) {
      padding-top:calc(var(--sc-topbar-height, 80px) + 24px) !important;}
    .st-key-prompts-workspace {--prompt-gold:#866018;}
    .st-key-prompts-workspace h1 {font-size:2.5rem!important;letter-spacing:-.045em;font-weight:750;padding:0 0 18px!important;}
    .st-key-prompts-workspace h3 {font-size:1.4rem!important;letter-spacing:-.025em;}
    .st-key-prompts-workspace [data-baseweb="tab-list"] {gap:0!important;border-bottom:1px solid #dedbd3;}
    .st-key-prompts-workspace button[role="tab"] {padding:14px 24px!important;background:transparent!important;border-radius:9px 9px 0 0!important;}
    .st-key-prompts-workspace button[role="tab"][aria-selected="true"] {background:#f5edde!important;color:#805b16!important;}
    .st-key-prompts-workspace button[role="tab"][aria-selected="true"] p {color:#805b16!important;font-weight:650!important;}
    .st-key-prompts-workspace [data-baseweb="tab-highlight"] {background:#866018!important;}
    .st-key-prompts-workspace [data-testid="stVerticalBlockBorderWrapper"] {border-radius:12px;}
    .st-key-prompts-workspace textarea {font-family:inherit;font-size:16px;line-height:1.7;}
    .st-key-prompts-workspace button[kind="primary"] {background:#866018!important;border-color:#866018!important;color:white!important;}
    .st-key-prompts-workspace button[kind="primary"] p {color:white!important;}
    .st-key-prompts-workspace [data-testid="stRadio"] label {padding:14px 12px;border-bottom:1px solid #e6e0d5;min-width:100%;}
    .st-key-prompts-workspace [data-testid="stRadio"] label:has(input:checked) {background:#f7efdf;border-radius:8px;}
    .prompt-badge {display:inline-block;background:#f5eddb;color:#85631f;
      padding:6px 12px;border-radius:20px;font-size:13px;font-weight:600;white-space:nowrap;}
    .prompt-preview {white-space:pre-wrap;overflow-wrap:anywhere;font-size:16px;line-height:1.75;padding:18px 4px;}
    </style>''')
    with st.container(key='prompts-workspace'):
        title, save, activate = st.columns([4, 1.3, 1.7], vertical_alignment='center')
        title.title('Prompts')
        save_action, activate_action = save.empty(), activate.empty()
        store = GitStore(os.getenv('PROMPTS_GITHUB_TOKEN', ''), os.getenv('RENDER_API_KEY', ''))
        prompts = catalog()
        tabs = st.tabs(['Design', 'Upload', 'Ads'], key='prompt-category', on_change='rerun')
        for category, tab in zip(('Design', 'Upload', 'Ads'), tabs):
            if tab.open:
                with tab:
                    _category(st, store, prompts, category, user, save_action, activate_action)


def _category(st, store, prompts, category, user, save_action, activate_action):
    search_col, select_col = st.columns([1, 2.4])
    search = search_col.text_input('Find a prompt', placeholder=f'Search {category.lower()} prompts…', key='prompt-search-' + category, label_visibility='collapsed')
    category_rows = [p for p in prompts if p.category == category]
    rows = [p for p in category_rows if search.casefold() in (p.title + ' ' + p.text).casefold()]
    key = select_col.selectbox('Prompt library', ['entire'] + [p.key for p in rows],
                       format_func=lambda k: 'Entire prompt · all sections' if k == 'entire' else next(p.title for p in rows if p.key == k), key='prompt-select-' + category, label_visibility='collapsed')
    entire = bundle_prompt(category_rows, category)
    prompt = entire if key == 'entire' else next(p for p in rows if p.key == key)
    key = prompt.key
    history, history_sha = {'versions': []}, None
    if store.token:
        try:
            history, history_sha = store.history(prompt)
        except ReleaseError as exc:
            st.error(str(exc))
            return
    if not history['versions']:
        snapshot = ROOT / 'prompts' / 'release_history' / (prompt.key + '.json')
        if snapshot.is_file():
            history = json.loads(snapshot.read_text(encoding='utf-8'))
    versions = history['versions']
    labels_path = ROOT / 'prompts' / 'version_labels.json'
    labels = json.loads(labels_path.read_text(encoding='utf-8')) if labels_path.exists() else {}
    manifest_path = ROOT / 'prompts' / 'releases.json'
    deployed = json.loads(manifest_path.read_text(encoding='utf-8')).get(key, {}) if manifest_path.exists() else {}
    left, right = st.columns([2.4, 1], gap='large')
    with right:
        with st.container(border=True):
            st.subheader('Version history')
            choice = st.radio('Open a version', ['deployed'] + [v['id'] for v in reversed(versions)],
                format_func=lambda value: 'v' + deployed.get('version', '1.0') + ' · ' + (deployed['label'] + ' · Live' if deployed.get('label') else 'Deployed') if value == 'deployed' else
                    next('v' + v['version'] + (' · ' + labels[v['id']] if v['id'] in labels else '') + (' · Release' if v.get('commit') else ' · Baseline' if v.get('baseline') else ' · Draft') for v in versions if v['id'] == value), key='prompt-version-' + key, label_visibility='collapsed')
            if st.button('Compare versions', key='prompt-compare-toggle-' + key, use_container_width=True):
                st.session_state['prompt-show-compare-' + key] = not st.session_state.get('prompt-show-compare-' + key, False)
            st.button('Refresh history', key='prompt-refresh-' + key, on_click=lambda: None)
    selected = next((v for v in versions if v['id'] == choice), None)
    initial = selected['text'] if selected else prompt.text
    bundle_rows = ([Prompt(row['path'], row.get('symbol', ''), category, row['text'])
                    for row in selected['sections']]
                   if is_bundle(prompt) and selected and selected.get('sections') else category_rows)
    with left:
        with st.container(border=True):
            heading, status = st.columns([4, 1.2], vertical_alignment='center')
            heading.subheader(category + ' - Entire prompt' if is_bundle(prompt) else prompt.title)
            badge = (('Release v' if selected.get('commit') else 'Baseline v' if selected.get('baseline') else 'Draft v') + selected['version']) if selected else ('Deployed v' + deployed.get('version', '1.0'))
            label = labels.get(selected['id'], '') if selected else deployed.get('label', '')
            if label:
                badge += ' · ' + label
            status.html('<span class="prompt-badge">' + html.escape(badge) + '</span>')
            test_panel = st.container()
            preview, edit = st.tabs(['Copy full prompt', 'Edit prompt'])
            with edit:
                buffer_key = f'{key}-{choice}'
                buffers = st.session_state.setdefault('prompt-editor-buffers', {})
                widget_key = 'prompt-text-' + buffer_key
                def retain_buffer():
                    value = st.session_state[widget_key]
                    buffers[buffer_key] = value
                    try:
                        if is_bundle(prompt):
                            values = split(category_rows, value)
                            for section_key, section_text in values.items():
                                target = section_key + '-deployed'
                                buffers[target] = section_text
                                st.session_state['prompt-text-' + target] = section_text
                        else:
                            values = {p.key: buffers.get(p.key + '-deployed', p.text) for p in category_rows}
                            values[prompt.key] = value
                            target = entire.key + '-deployed'
                            buffers[target] = combine(category_rows, values)
                            st.session_state['prompt-text-' + target] = buffers[target]
                    except ValueError:
                        pass  # Keep incomplete edits; validation below explains how to repair them.
                if is_bundle(prompt):
                    st.caption('Edit inside each SECTION / END pair; keep those headings and placeholders intact. Changes sync to individual section editors. Save a draft, then activate it to publish all changed sections together.')
                text = st.text_area('Prompt instructions', buffers.get(buffer_key, initial), height=700 if is_bundle(prompt) else 460,
                                    key=widget_key, on_change=retain_buffer, label_visibility='collapsed')
                if '\u27easlot:' in text or '{' in text:
                    st.caption('Keep placeholders intact; the app fills them when building each prompt.')
            valid = True
            if is_bundle(prompt):
                try:
                    split(bundle_rows, text)
                except ValueError as exc:
                    valid = False
                    st.error(str(exc))
            with preview:
                render_copy(st, text)
                st.download_button('Download prompt', text, file_name=prompt.title + '.txt', key='prompt-download-' + key)
            if st.session_state.get('prompt-show-compare-' + key, False):
                compare_id = st.selectbox('Compare against', ['deployed'] + [v['id'] for v in versions],
                    format_func=lambda value: 'Deployed source' if value == 'deployed' else 'v' + next(v['version'] for v in versions if v['id'] == value),
                    key='prompt-compare-' + key)
                before = prompt.text if compare_id == 'deployed' else next(v['text'] for v in versions if v['id'] == compare_id)
                delta = '\n'.join(difflib.unified_diff(before.splitlines(), text.splitlines(), fromfile='Comparison', tofile='Editor', lineterm=''))
                st.code(delta or 'No changes.', language='diff', wrap_lines=True)
            from prompt_test_panel import render as render_test
            with test_panel:
                render_test(st, prompt, text, user, valid)
            note = st.text_input('Version note', placeholder='What changed, and why?', key='prompt-note-' + key)
            if save_action.button('Save draft', key='prompt-save-' + key, use_container_width=True, disabled=not store.token or not valid):
                try:
                    store.save(prompt, text, note, str(user.get('email') or user.get('id')), history, history_sha)
                    st.success('Version saved. Open it in Version history to activate.')
                    st.rerun()
                except (ReleaseError, ValueError) as exc:
                    st.error(str(exc))
            can_activate = bool(valid and selected and store.token and text == initial
                                and not selected.get('commit') and not selected.get('baseline'))
            if activate_action.button('Activate version', type='primary', key='prompt-activate-' + key,
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
                st.caption('Draft saving is unavailable. Your administrator can check the server connection; downloads still work.')
            elif not store.render_token:
                st.caption('GitHub publishing is available. Detailed deployment monitoring is not configured; reload after rollout to verify the live version.')
            if selected:
                st.caption(f'Saved {selected["created_at"][:19].replace("T", " ")} UTC · {selected.get("author", "")}')
                if selected.get('note'):
                    st.caption(selected['note'])
                if selected.get('commit'):
                    if store.token and store.render_token:
                        _deployment(st, store, prompt, selected)
                    else:
                        st.caption('Saved Git revision ' + selected['commit'][:12])
            if is_bundle(prompt) and valid:
                st.subheader('Individual sections')
                values = split(bundle_rows, text)
                for section in bundle_rows:
                    with st.expander(section.title):
                        st.html('<div class="prompt-preview">' + html.escape(values[section.key]) + '</div>')
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
