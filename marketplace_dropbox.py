"""Private source files for marketplace submissions, using the OS Dropbox account.

One item folder contains listing.json, 2–4 photos and an optional recorded video.
The database is a moderation/search index, never the new submission's media store.
"""
import base64
from copy import deepcopy
import hashlib
import json
import re
import threading
import time

import dropbox_integration as dbx
from marketplace import identifier

ROOT = '/Sportscave Team Folder/Marketplace'
ROOT_ID = 'id:u1tYiAa2O-AAAAAAAAC4Qg'
_AUTH = {}
_AUTH_LOCK = threading.Lock()
MAX_PHOTO = 450_000
MAX_VIDEO = 12_000_000
MAX_RECORD = 30_000


def configured():
    return not dbx.missing_server_config_keys()


def connection():
    config = dbx.dropbox_config()
    fingerprint = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    with _AUTH_LOCK:
        if _AUTH.get('fingerprint') == fingerprint and _AUTH.get('until', 0) > time.monotonic():
            return _AUTH['context']
        token = dbx.resolve_server_auth(config, validate=False)['access_token']
        context = dbx._team_space_context(token)
        folder = dbx.get_file_metadata(token, ROOT_ID)
        if folder.get('.tag') != 'folder' or folder.get('id') != ROOT_ID:
            raise RuntimeError('The marketplace source folder is unavailable.')
        root = dbx.normalize_dropbox_path(folder.get('path_display') or folder.get('path_lower'))
        if not dbx.path_is_within_root(root, '/Sportscave Team Folder'):
            raise RuntimeError('The marketplace source folder is outside the team folder.')
        result = {'token': token, 'root': root, 'namespace': context['root_namespace_id'], 'client': context['client']}
        _AUTH.update(fingerprint=fingerprint, until=time.monotonic() + 1200, context=result)
        return result


def receipt(metadata, data):
    if not re.fullmatch(r'id:[A-Za-z0-9_-]+', str(metadata.get('id', ''))) or not re.fullmatch(r'[a-fA-F0-9]+', str(metadata.get('rev', ''))):
        raise RuntimeError('The uploaded file did not return a durable receipt.')
    if metadata.get('size') != len(data):
        raise RuntimeError('The uploaded file size was not confirmed.')
    return {'provider': 'dropbox', 'id': metadata['id'], 'rev': metadata['rev'],
            'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def validate_receipt(value, limit):
    if not isinstance(value, dict) or value.get('provider') != 'dropbox' or not re.fullmatch(r'id:[A-Za-z0-9_-]+', str(value.get('id', ''))) or not re.fullmatch(r'[a-fA-F0-9]+', str(value.get('rev', ''))):
        raise ValueError('Invalid item media reference.')
    if not isinstance(value.get('size'), int) or not 0 < value['size'] <= limit or not re.fullmatch(r'[a-f0-9]{64}', str(value.get('sha256', ''))):
        raise ValueError('Invalid item media size or digest.')
    return value


class Download:
    def __init__(self, response, size):
        self.response, self.size = response, size

    def iter_chunks(self, chunk_size=65536):
        received = 0
        try:
            for chunk in self.response.iter_content(chunk_size=chunk_size):
                received += len(chunk)
                if received > self.size:
                    raise RuntimeError('Item media exceeded its recorded size.')
                if chunk:
                    yield chunk
            if received != self.size:
                raise RuntimeError('Item media download was incomplete.')
        finally:
            self.close()

    def read(self, limit):
        if self.size > limit:
            raise ValueError('Item media exceeds the preview limit.')
        return b''.join(self.iter_chunks())

    def close(self):
        self.response.close()


class MarketplaceDropboxStorage:
    def __init__(self, context=None, http=None):
        self._context, self.http = context, http

    @property
    def context(self):
        if self._context is None:
            self._context = connection()
        return self._context

    def save(self, record, photos, video=None):
        listing_id = identifier(record['id'])
        slug = re.sub(r'[^a-z0-9]+', '-', record['title'].lower()).strip('-')[:60].strip('-') or 'item'
        folder = self.context['root'] + '/' + slug + '--' + listing_id
        client = self.context['client']
        client.files_create_folder_v2(folder, autorename=False)
        def upload(name, data):
            sdk = dbx._dropbox_sdk()
            metadata = client.files_upload(data, folder + '/' + name, mode=sdk.files.WriteMode.add,
                                           autorename=False, strict_conflict=True, mute=True)
            return receipt(dbx._metadata_to_dict(metadata), data)
        photo_refs = [upload(f'photo-{index + 1}.webp', base64.b64decode(value, validate=True)) for index, value in enumerate(photos)]
        video_ref = None
        if video:
            video_ref = {**upload('video.mp4', video['bytes']), 'seconds': video['seconds']}
        manifest = {'version': 1, 'listing': deepcopy(record), 'photos': photo_refs, 'video': video_ref}
        encoded = json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8')
        if len(encoded) > MAX_RECORD:
            raise ValueError('Item submission details exceed the storage limit.')
        # The manifest is written last; it represents a complete received submission.
        manifest_ref = upload('listing.json', encoded)
        return {'provider': 'dropbox', 'folder': folder, 'manifest': manifest_ref,
                'photos': photo_refs, 'video': video_ref}

    def open(self, value, start=0, end=None, *, limit=MAX_VIDEO):
        value = validate_receipt(value, limit)
        end = value['size'] - 1 if end is None else end
        if not 0 <= start <= end < value['size']:
            raise ValueError('Invalid media byte range.')
        context = self.context
        # Credentials, IDs and source locations remain server-side. Revisions pin
        # the exact reviewed bytes even if someone later edits the Dropbox file.
        headers = {'Authorization': 'Bearer ' + context['token'],
            'Dropbox-API-Path-Root': json.dumps({'.tag': 'root', 'root': context['namespace']}),
            'Dropbox-API-Arg': json.dumps({'path': value['id'], 'rev': value['rev']}),
            'Range': f'bytes={start}-{end}', 'Accept-Encoding': 'identity'}
        response = (self.http or dbx._requests()).get(dbx.DROPBOX_CONTENT_URL + '/files/download',
            headers=headers, stream=True, allow_redirects=False, timeout=(5, 30))
        try:
            metadata = json.loads(response.headers.get('Dropbox-API-Result', '{}'))
            if response.status_code not in (200, 206) or metadata.get('id') != value['id'] or metadata.get('rev') != value['rev']:
                raise RuntimeError('Item source media is temporarily unavailable.')
            if metadata.get('size') != value['size']:
                raise RuntimeError('Item source media size changed.')
            if response.status_code == 206:
                if response.headers.get('Content-Range') != f'bytes {start}-{end}/{value["size"]}':
                    raise RuntimeError('Item source did not return the requested byte range.')
            elif start or end != value['size'] - 1:
                raise RuntimeError('Item source did not honour the requested byte range.')
            return Download(response, end - start + 1)
        except Exception:
            response.close()
            raise

    def read(self, value, limit):
        stream = self.open(value, limit=limit)
        try:
            data = stream.read(limit)
        finally:
            stream.close()
        if hashlib.sha256(data).hexdigest() != value['sha256']:
            raise RuntimeError('Item source does not match the received submission.')
        return data

    def manifest(self, source):
        return json.loads(self.read(source['manifest'], MAX_RECORD))
