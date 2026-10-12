"""Offline-safe, shared product/PSD directory. No network on table rendering."""
import json
import re
import os
from functools import lru_cache
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, quote

ROOT = '/Sportscave Team Folder/02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED'
STORE = Path(__file__).resolve().parent / 'output' / 'psd_directory.json'


def product_id(row):
    value = str(row.get('shopify_product_gid') or row.get('shopify_product_id') or '').strip()
    if value.isdigit():
        value = 'gid://shopify/Product/' + value
    return value if re.fullmatch(r'gid://shopify/Product/[1-9][0-9]*', value) else ''


def filename_key(value):
    # Same replacements as Dropbox integration's filename sanitisation.
    clean = ''.join('_' if ord(c) < 32 or c in '<>:"/\\|?*' else c for c in str(value or '').strip())
    return ' '.join(clean.split()).strip(' .')[:255].casefold()


def title_filename_keys(value):
    # Approved export uses spaced hyphens for filesystem-forbidden punctuation.
    # Retain the existing integration's underscore convention as a second exact form.
    spaced = ''.join(' - ' if c in '<>:"/\\|?*' else '_' if ord(c) < 32 else c for c in str(value or ''))
    return {filename_key(value), filename_key(spaced)}


def protected_url(value):
    value = str(value or '').strip()
    try:
        url = urlsplit(value)
        if (url.scheme == 'https' and url.netloc == 'www.dropbox.com'
                and url.path.startswith(('/home/', '/preview/'))
                and not any(c.isspace() for c in value)):
            return value
    except ValueError:
        pass
    return ''


def approved_file(row):
    path = str(row.get('path_display') or row.get('path_lower') or '')
    return (row.get('.tag') == 'file' and PurePosixPath(path).parent.as_posix().casefold() == ROOT.casefold()
            and path.casefold().endswith('.psd') and str(row.get('id') or '').startswith('id:')
            and PurePosixPath(path).name.casefold() == str(row.get('name') or '').casefold())


def reconcile(products, entries, previous=None):
    """Complete approved-folder inventory + verified catalogue; never fuzzy match."""
    previous = previous or {}
    files = {}
    names = {}
    for entry in entries:
        if approved_file(entry):
            files.setdefault(entry['id'], []).append(entry)
            key = filename_key(PurePosixPath(entry['name']).stem)
            names.setdefault(key, set()).add(entry['id'])
    identities, titles, handles = {}, {}, {}
    for row in products:
        pid = product_id(row)
        handle = str(row.get('handle') or row.get('shopify_handle') or '').strip()
        if not pid or not handle:
            continue
        identities.setdefault(pid, []).append(row)
        for key in title_filename_keys(row.get('product_title') or row.get('title')):
            titles.setdefault(key, set()).add(pid)
        handles.setdefault(handle, set()).add(pid)
    reserved = {record.get('dropbox_file_id'): pid for pid, record in previous.items() if record.get('verified')}
    result = dict(previous)
    for pid, rows in identities.items():
        row = rows[0]
        keys = title_filename_keys(row.get('product_title') or row.get('title'))
        handle = str(row.get('handle') or row.get('shopify_handle') or '').strip()
        old = previous.get(pid) or {}
        state = 'Not linked'
        fid = old.get('dropbox_file_id') if old.get('verified') else None
        if not fid:
            candidates = set().union(*(names.get(key, set()) for key in keys))
            competing_products = set().union(*(titles.get(key, set()) for key in keys))
            if len(rows) != 1 or len(competing_products) != 1 or len(handles[handle]) != 1 or len(candidates) > 1:
                state = 'Review: ambiguous match'
            elif len(candidates) == 1:
                candidate = next(iter(candidates))
                if candidate in reserved and reserved[candidate] != pid:
                    state = 'Review: file already verified for another product'
                else:
                    fid = candidate
        entry_rows = files.get(fid, [])
        if len(entry_rows) == 1:
            entry = entry_rows[0]
            url = protected_url(entry.get('preview_url'))
            result[pid] = {'verified': True, 'handle': old.get('handle') or handle,
                           'dropbox_file_id': fid, 'path': entry.get('path_display') or entry.get('path_lower'),
                           'url': url, 'state': 'Linked', 'namespace_path': entry.get('namespace_path') or ''}
        elif old.get('verified'):
            result[pid] = {**old, 'url': '', 'state': 'Review: approved file missing'}
        else:
            result[pid] = {'verified': False, 'url': '', 'state': state}
    return result


@lru_cache(maxsize=4)
def _read(path, stamp):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def directory(path=None):
    if path is None:
        from psd_mapping_store import STORE as persistent_store
        return persistent_store.read()
    # Explicit paths are offline fixture/export storage only, never the runtime source.
    try:
        stat = Path(path).stat()
        return _read(str(path), (stat.st_mtime_ns, stat.st_size))
    except OSError:
        return {}


def save(mapping, path=None):
    if path is None:
        raise ValueError('Runtime writes require the audited mapping repository; use reviewed backfill or manual attachment.')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(mapping, indent=2), encoding='utf-8')
    os.replace(temp, path)
    _read.cache_clear()


def link(row, mapping):
    record = mapping.get(product_id(row)) or {}
    if not record.get('verified') or record.get('state') != 'Linked':
        return ''
    fid = str(record.get('dropbox_file_id') or '')
    if not re.fullmatch(r'id:[A-Za-z0-9_-]+', fid):
        return ''
    return '/api/files-psd-open?product_gid=' + quote(product_id(row), safe='')


def display_link(row, mapping, missing='Not linked'):
    if getattr(mapping, 'unavailable', False):
        return 'Unavailable'
    url = link(row, mapping)
    # Fragment is client-only; the authenticated endpoint resolves the stable ID.
    return url.split('#', 1)[0] + '#Open PSD' if url else (picker_link(row) + '#Add' if missing == 'Add' and product_id(row) else missing)


def status(row):
    """Display-only edition-run state. Never inspect storefront publication."""
    def number(value, default=0):
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    run = str(row.get('current_run_status') or row.get('run_status') or '').casefold()
    total = number(row.get('current_run_total', row.get('edition_total')), 0)
    next_number = number(row.get('current_run_next_number', row.get('edition_next_number', row.get('next_edition_number'))), 1)
    sold = number(row.get('current_run_sold_count', row.get('edition_sold_count', row.get('sold_count'))), 0)
    if run in {'expired', 'sold_out'} or (total > 0 and (next_number > total or sold >= total)):
        return 'Expired'
    sync = str(row.get('sync_status') or row.get('metafields_sync_status') or '').casefold()
    enabled = row.get('edition_enabled', row.get('active', False))
    if (not enabled or total <= 0 or row.get('sync_error') or row.get('allocation_blocked')
            or run in {'inactive', 'archived', 'closed', 'pending_sync'}):
        return 'Offline'
    return 'Live' if sync in {'synced', 'synced to shopify', 'shopify mirror updated'} else 'Offline'


class UnavailableDirectory(dict):
    unavailable = True


def page_directory(ui=None):
    from psd_mapping_store import MappingUnavailable
    try:
        return directory()
    except MappingUnavailable:
        if ui and hasattr(ui, 'warning'):
            ui.warning('PSD directory unavailable. Retry or check database activation.')
        return UnavailableDirectory()


def picker_link(row):
    return '/files-psd-picker?product_gid=' + quote(product_id(row), safe='')


def refresh_from_dropbox(access_token, products, path=None):
    """Explicit read-only refresh with existing integration; never called per row."""
    from dropbox_integration import list_folder_page
    entries, cursor = [], ''
    seen = set()
    while True:
        page = list_folder_page(access_token, ROOT, cursor=cursor, limit=2000)
        entries.extend(page.get('entries') or [])
        if not page.get('has_more'):
            break
        cursor = page.get('cursor') or ''
        if not cursor or cursor in seen:
            raise ValueError('Incomplete Dropbox inventory; directory unchanged.')
        seen.add(cursor)
    mapping = reconcile(products, entries, directory(path))
    if path is None:
        from psd_mapping_store import STORE as persistent_store
        return persistent_store.backfill(mapping)  # Preview only; never automatic writes.
    save(mapping, path)
    return mapping


def render_import(products, ui=None):
    import streamlit
    import os_accounts
    st = ui or streamlit
    if not hasattr(st, 'link_button') or not os_accounts.is_admin(st.session_state.get('sports_cave_current_user') or {}):
        return
    with st.expander('PSD links', expanded=False):
        by_id = {product_id(r): r for r in products if product_id(r)}
        if by_id:
            pid = st.selectbox('Product', list(by_id), format_func=lambda key: by_id[key]['product_title'], key='psd-replace-product')
            st.link_button('Add or replace PSD', picker_link(by_id[pid]))


def render_missing_link_guard(ui):
    if getattr(ui, '__name__', '') == 'streamlit':
        import streamlit.components.v1 as components
        component = components.declare_component('psd_picker_events', path=str(Path(__file__).resolve().parent / 'components' / 'psd_picker'))
        component(key='psd-picker-events', default=None)


def snapshot_mapping(products, approved, excluded, previous=None):
    """Validate offline CSVs without trusting their claimed match classifications."""
    catalogue, by_id, entries = [], {}, []
    excluded_ids = {str(r.get('dropbox_file_id') or '') for r in excluded} - {''}
    excluded_paths = {str(r.get('Current Dropbox path') or '').casefold() for r in excluded}
    for row in products:
        item = {'product_title': row.get('edition_ops_title'), 'handle': row.get('shopify_handle'),
                'shopify_product_gid': row.get('shopify_product_gid'), 'status': row.get('shopify_status_snapshot')}
        pid = product_id(item)
        if not pid or not item['handle'] or pid in by_id:
            raise ValueError('Snapshot catalogue has invalid or duplicate identities.')
        by_id[pid] = row
        catalogue.append(item)
    for row in approved:
        raw = str(row.get('dropbox_namespace_path') or '')
        match = re.fullmatch(r'ns:([0-9]+)//(02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/[^/]+\.psd)', raw, re.IGNORECASE)
        if not match:
            raise ValueError('Approved file is outside the main namespace folder.')
        path = '/Sportscave Team Folder/' + match.group(2)
        fid = str(row.get('dropbox_file_id') or '')
        if not re.fullmatch(r'id:[A-Za-z0-9_-]+', fid) or fid in excluded_ids or path.casefold() in excluded_paths:
            raise ValueError('Approved file has invalid identity or overlaps exclusions.')
        pid = product_id(row)
        product = by_id.get(pid)
        if (not product or row.get('edition_ops_title') != product.get('edition_ops_title')
                or row.get('shopify_handle') != product.get('shopify_handle')
                or row.get('dropbox_filename') != PurePosixPath(path).name
                or product.get('approved_dropbox_file_id') != fid
                or product.get('approved_psd_filename') != row.get('dropbox_filename')
                or product.get('approved_dropbox_namespace_path') != raw):
            raise ValueError('Approved file identity disagrees with catalogue.')
        entries.append({'.tag': 'file', 'name': row['dropbox_filename'], 'id': fid,
                        'path_display': path, 'namespace_path': raw})
    return catalogue, reconcile(catalogue, entries, previous)
