"""In-memory Dropbox boundary. No network, credentials, or cloud writes."""
from copy import deepcopy
from pathlib import Path
import uuid
import dropbox_integration as api
import auto_editions as ae


class Outputs:
    delay=0
    normalize_dropbox_path=staticmethod(api.normalize_dropbox_path)
    path_is_within_root=staticmethod(api.path_is_within_root)
    join_upload_path=staticmethod(api.join_upload_path)
    sanitize_path_component=staticmethod(api.sanitize_path_component)
    sort_folder_entries=staticmethod(api.sort_folder_entries)
    root='/Sportscave Team Folder'
    base=root+'/04_OUTPUT/product-images'

    def __init__(self):
        self.files={};self.calls=[];self.fail_once=None;self.lose_once=None
        for path in (self.root,self.root+'/04_OUTPUT',self.base,self.base+'/Baseball',self.base+'/Cricket'):
            self.files[path]=dict(id='id:'+uuid.uuid4().hex,name=path.rsplit('/',1)[-1],path_display=path,**{'.tag':'folder'})

    def get_metadata_if_exists(self,token,path):return deepcopy(self.files.get(path))

    def numbered_path(self,token,path):
        index=2
        while path+f' ({index})' in self.files:index+=1
        return path+f' ({index})'

    def create_folder(self,token,parent,name,conflict='cancel'):
        path=api.join_upload_path(parent,name)
        if path in self.files:return None
        value=dict(id='id:'+uuid.uuid4().hex,name=name,path_display=path,**{'.tag':'folder'})
        self.files[path]=value;self.calls.append(('folder',path));return deepcopy(value)

    def entries(self,token,parent,**kwargs):
        return [deepcopy(m) for path,m in self.files.items() if path.rsplit('/',1)[0]==parent]

    def upload_batch(self,token,target,items,**kwargs):
        successes=[];failures=[]
        for item in items:
            name=item['relative_path'];path=api.join_upload_path(target,name)
            self.calls.append(('upload',path))
            assert kwargs['conflict']=='cancel' and path not in self.files
            if self.fail_once in (name,'*'):
                self.fail_once=None;failures.append(dict(relative_path=name,error='Isolated failure'));continue
            local=Path(item['local_path']);value=dict(id='id:'+uuid.uuid4().hex,content_hash=ae.file_hash(local,dropbox=True),size=local.stat().st_size,**{'.tag':'file'})
            self.files[path]=value
            kwargs['progress_callback'](1,1,name,value['size']//2,value['size'])
            if self.delay:__import__('time').sleep(self.delay)
            kwargs['progress_callback'](1,1,name,value['size'],value['size'])
            if self.lose_once==name:
                self.lose_once=None;failures.append(dict(relative_path=name,error='Lost acknowledgement'));continue
            successes.append(dict(relative_path=name,metadata=deepcopy(value)))
        return dict(successes=successes,failures=failures)
