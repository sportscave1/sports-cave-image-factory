"""Additive, authenticated browser handoff to the existing Windows desktop host."""
import re
import secrets
import threading
import time
from pathlib import Path, PurePosixPath
from urllib.parse import quote
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, HTMLResponse

BLOCKED = set('appref-ms application bat chm cmd com cpl dll exe gadget hta inf ins isp jar js jse lnk msc msi msp mst pif ps1 py pyw reg scr sct shb shs url vbs vbe website ws wsc wsf'.split())
PAGE = Path(__file__).parent / 'components' / 'files_window' / 'native_launch.html'


def create_open_transfer(context, user, selection):
    import files_upload_api as files
    if not isinstance(selection, dict) or set(selection) != {'id', 'revision'}:
        raise files.FilesUploadError('Select one file by its Dropbox identity.', code='invalid_arguments')
    fid, revision = str(selection['id']), str(selection['revision'])
    if not re.fullmatch(r'id:[A-Za-z0-9_-]+', fid) or not revision:
        raise files.FilesUploadError('Refresh Files before opening this item.', code='item_changed', status_code=409)
    meta = files.dropbox_integration.psd_open_metadata(context['access_token'], fid, include_preview=False)
    root = files.dropbox_integration.normalize_dropbox_path(context['root_path'])
    path = str(meta.get('path_display') or meta.get('path_lower') or '')
    name = str(meta.get('name') or '')
    if (meta.get('id') != fid or meta.get('rev') != revision or meta.get('.tag') != 'file'
        or not files.dropbox_integration.path_is_within_root(path, root)
        or PurePosixPath(path).name != name or not re.fullmatch(r'[a-fA-F0-9]{64}', str(meta.get('content_hash') or ''))):
        raise files.FilesUploadError('The selected file changed or cannot be verified. Refresh Files and retry.', code='item_changed', status_code=409)
    if PurePosixPath(name.rstrip(' .')).suffix.lower().lstrip('.') in BLOCKED:
        raise files.FilesUploadError('This file type cannot be opened by the desktop helper.', code='file_type_denied', status_code=403)
    relative = path[len(root):].lstrip('/')
    if any(part.endswith((' ', '.')) or ':' in part or chr(92) in part or any(ord(c)<32 for c in part) for part in relative.split('/')):
        raise files.FilesUploadError('This filename cannot be safely opened on Windows. Use the browser download action.', code='unsafe_path', status_code=403)
    if files._validated_relative_path(relative, root) != path:
        raise files.FilesUploadError('The file location cannot be opened.', code='scope_denied', status_code=403)
    item = files.NATIVE_TRANSFER_MANAGER._manifest_item(meta, path, name, is_directory=False)
    item['content_hash'] = meta['content_hash']
    record = files.NativeTransferRecord(ticket=secrets.token_urlsafe(24), secret=secrets.token_urlsafe(32),
        access_token=context['access_token'], user_id=str(user['id']),
        roots=[{'source_relative_path':relative,'name':name,'is_directory':False,'revision':revision}],
        items=[item], purpose='native_open')
    with files.NATIVE_TRANSFER_MANAGER._lock:
        files.NATIVE_TRANSFER_MANAGER._cleanup()
        files.NATIVE_TRANSFER_MANAGER._records[record.ticket] = record
    return record


class LaunchManager:
    def __init__(self):
        self.records = {}
        self.lock = threading.RLock()

    def create(self, user, transfer, action):
        import files_upload_api as files
        with self.lock:
            self._cleanup()
            if len(self.records) >= 128:
                raise files.FilesUploadError('Too many pending desktop requests. Wait and retry.', status_code=429)
            code = secrets.token_urlsafe(32)
            self.records[code] = {'user':str(user['id']), 'version':str(user.get('session_version') or ''),
                'transfer':transfer, 'action':action, 'expires':time.monotonic()+120, 'claimed':False}
            return code

    def _cleanup(self):
        import files_upload_api as files
        for code, record in list(self.records.items()):
            if record['expires'] <= time.monotonic():
                self.records.pop(code, None)
                with files.NATIVE_TRANSFER_MANAGER._lock:
                    files.NATIVE_TRANSFER_MANAGER._records.pop(record['transfer'].ticket, None)

    def use(self, code, user, cancel=False):
        import files_upload_api as files
        with self.lock:
            self._cleanup()
            record = self.records.get(str(code))
            if (not record or record['user'] != str(user.get('id') or '') or
                record['version'] != str(user.get('session_version') or '')):
                raise files.FilesUploadError('Sign in to Sports Cave Desktop with the same account, then retry from Files. This request may have expired.', status_code=403, code='launch_unavailable')
            if cancel:
                self.records.pop(str(code), None)
                with files.NATIVE_TRANSFER_MANAGER._lock:
                    files.NATIVE_TRANSFER_MANAGER._records.pop(record['transfer'].ticket, None)
                return None
            if record['claimed']:
                raise files.FilesUploadError('This desktop request was already used. Retry from Files.', status_code=409, code='launch_used')
            record['claimed'] = True
            # Claim is single-use. Transfer lifetime remains the existing 15 minutes for large files.
            record['expires'] = record['transfer'].expires_at
            return record


LAUNCHES = LaunchManager()


async def prepare(request):
    import files_upload_api as files
    try:
        if not request.headers.get('origin') or not files._same_origin(request):
            raise files.FilesUploadError('Desktop opening is not allowed from this origin.', status_code=403)
        user = await run_in_threadpool(files._request_user, request)
        data = await files._json_body(request)
        if set(data) != {'item','action'} or data['action'] not in ('openFile','openWith'):
            raise files.FilesUploadError('Invalid desktop opening request.', code='invalid_arguments')
        context = await run_in_threadpool(files._dropbox_context)
        transfer = await run_in_threadpool(create_open_transfer, context, user, data['item'])
        if request.url.path == '/api/files-native-open':
            return JSONResponse({'ok':True,'ticket':transfer.ticket,'secret':transfer.secret}, headers={'Cache-Control':'no-store'})
        code = LAUNCHES.create(user, transfer, data['action'])
        origin = str(request.base_url).rstrip('/')
        return JSONResponse({'ok':True,'code':code,'launch_url':'sports-cave-files://launch?origin='+quote(origin,safe='')+'#'+code,'expires_in':120,'minimum_helper':11},
            headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
    except Exception as error:
        files._psd_failure(error, 'native_launch_prepare', secrets.token_hex(8))
        return files._response_error(error)


async def claim(request):
    import files_upload_api as files
    try:
        if not request.headers.get('origin') or not files._same_origin(request):
            raise files.FilesUploadError('Desktop opening is not allowed from this origin.', status_code=403)
        user = await run_in_threadpool(files._request_user, request)
        data = await files._json_body(request)
        if set(data) != {'code'} or not re.fullmatch(r'[A-Za-z0-9_-]{43}', str(data['code'])):
            raise files.FilesUploadError('Invalid desktop launch.', code='invalid_arguments')
        record = LAUNCHES.use(data['code'], user, cancel=request.method=='DELETE')
        if record is None:
            return JSONResponse({'ok':True}, headers={'Cache-Control':'no-store'})
        transfer = record['transfer']
        return JSONResponse({'ok':True,'action':record['action'],'transfer':{'base_url':str(request.base_url).rstrip('/'),'ticket':transfer.ticket,'secret':transfer.secret}}, headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
    except Exception as error:
        return files._response_error(error)


async def page(request):
    return HTMLResponse(PAGE.read_text(encoding='utf-8'), headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY',
        'Content-Security-Policy':"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'"})
