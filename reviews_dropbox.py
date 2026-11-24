"""Dropbox is the durable source for originals and WebP review display files."""
import hashlib
import io
import json
import threading
import time

import dropbox_integration as dbx
from marketplace_dropbox import MarketplaceDropboxStorage,receipt

ROOT='/Sportscave Team Folder/03_ASSETS/Reviews'
ROOT_ID='id:u1tYiAa2O-AAAAAAAADIAQ'
_AUTH={}
_LOCK=threading.Lock()

def connection():
    config=dbx.dropbox_config();fingerprint=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    with _LOCK:
        if _AUTH.get('fingerprint')==fingerprint and _AUTH.get('until',0)>time.monotonic():return _AUTH['context']
        token=dbx.resolve_server_auth(config,validate=False)['access_token']
        context=dbx._team_space_context(token)
        folder=dbx.get_file_metadata(token,ROOT_ID)
        root=dbx.normalize_dropbox_path(folder.get('path_display') or folder.get('path_lower'))
        if folder.get('.tag')!='folder' or folder.get('id')!=ROOT_ID or not dbx.path_is_within_root(root,'/Sportscave Team Folder/03_ASSETS'):
            raise ValueError('The Reviews Dropbox folder is unavailable.')
        result={'token':token,'root':root,'namespace':context['root_namespace_id'],'client':context['client']}
        _AUTH.update(fingerprint=fingerprint,until=time.monotonic()+1200,context=result)
        return result

def content_hash(data):
    return hashlib.sha256(b''.join(hashlib.sha256(data[i:i+4194304]).digest() for i in range(0,len(data),4194304))).hexdigest()

class ReviewDropboxStorage:
    def __init__(self,context=None,http=None):self._context=context;self.http=http
    @property
    def context(self):
        if self._context is None:self._context=connection()
        return self._context
    def put(self,name,data):
        # Hash-derived filenames never overwrite an existing revision.
        import re
        if not re.fullmatch(r'[a-f0-9]{64}-(?:original\.(?:jpg|png|webp|mp4|webm)|(?:320|640|1280)\.webp|poster-(?:320|640|1280)\.webp|display-640-v1\.webp)',name):raise ValueError('Invalid review asset name.')
        path=self.context['root']+'/'+name
        metadata=dbx.get_metadata_if_exists(self.context['token'],path,missing_only=True)
        if not metadata:
            metadata=dbx.upload_stream(self.context['token'],path,io.BytesIO(data),size=len(data),conflict='cancel',max_bytes=50*1024*1024)
            if not metadata:metadata=dbx.get_file_metadata(self.context['token'],path)
        if metadata.get('content_hash')!=content_hash(data):raise ValueError('Dropbox review bytes could not be verified.')
        return {**receipt(metadata,data),'path':metadata.get('path_display') or path}
    def open(self,value,start=0,end=None):
        # Reuse the OS's revision-pinned, size-checked Range transport only.
        return MarketplaceDropboxStorage(context=self.context,http=self.http).open(value,start,end,limit=50*1024*1024)

    def verify(self,value):
        from marketplace_dropbox import validate_receipt
        validate_receipt(value,50*1024*1024)
        meta=dbx.get_file_metadata(self.context['token'],value['id'])
        path=dbx.normalize_dropbox_path(meta.get('path_display') or meta.get('path_lower'))
        if not dbx.path_is_within_root(path,self.context['root']) or meta.get('id')!=value['id'] or meta.get('rev')!=value['rev'] or meta.get('size')!=value['size']:
            raise ValueError('The Dropbox review source changed or is outside Reviews.')
        return True

def asset(storage,size='1280',kind='image'):
    if not isinstance(storage,dict) or storage.get('provider')!='dropbox':raise ValueError('Media has not been transferred to Dropbox.')
    if size not in ('320','640','1280','original'):raise ValueError('Invalid review media size.')
    if kind=='video' and size=='original':
        if storage.get('video_format') not in ('mp4','webm'):raise ValueError('Unsupported review video format.')
        return storage['original'],'video/'+storage['video_format']
    group='posters' if kind=='video' else 'variants'
    if size=='original':raise ValueError('Public review images use WebP display copies.')
    value=(storage.get(group) or {}).get(size)
    if not value:raise ValueError('Review display media is unavailable.')
    return value,'image/webp'
