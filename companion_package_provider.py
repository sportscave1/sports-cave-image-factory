"""Adapter to the existing Dropbox durable upload-session implementation."""
from pathlib import Path
import re
import auto_editions as ae
from product_upload_services import Dropbox


class PackageProvider(Dropbox):
    ROOT='/Sportscave Team Folder/03_ASSETS/Auto Editions/Prepared/Cache/Resumable'

    def destination(self,key):
        if not re.fullmatch('[a-f0-9]{64}',key):raise ValueError('Invalid package storage identity.')
        self.api.ensure_folder_path(self.token,self.ROOT,root_path=self.context['root_path'])
        return self.ROOT+'/'+key+'.zip'

    def download(self,receipt,destination):
        meta,response=self.api.get_file_response(self.token,receipt['id'])
        try:
            if any(meta.get(k)!=receipt[k] for k in ('id','rev','size','content_hash')):raise ValueError('Durable package revision changed.')
            length=0
            with Path(destination).open('xb') as output:
                for block in response.iter_content(chunk_size=1024*1024):
                    length+=len(block)
                    if length>receipt['size']:raise ValueError('Durable package exceeds its receipt.')
                    output.write(block)
            if length!=receipt['size'] or ae.file_hash(destination,dropbox=True)!=receipt['content_hash']:
                raise ValueError('Durable package receipt verification failed.')
        finally:response.close()

    def discard(self,path,receipt):
        if not re.fullmatch(re.escape(self.ROOT)+r'/[a-f0-9]{64}\.zip',path):raise ValueError('Cleanup outside resumable staging refused.')
        current=self.metadata_if_present(path)
        if current is None:return
        if any(current.get(k)!=receipt[k] for k in ('id','rev','size','content_hash')):raise ValueError('Cleanup receipt changed; staged file retained.')
        self.api.delete_path_recoverable(self.token,path,root_path=self.ROOT)
