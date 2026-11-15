from copy import deepcopy
import pytest
from desktop_recorder.contract import Invalid, validate
from test_chat_submission import output_task

def download_task():
    task=output_task();a=task['actions'][0];a.update(kind='chat_download',requires=['chat.download.v3'],timeout_ms=300000)
    a['value'].update(directory='C:\\Users\\test\\Downloads',csv_sha256='a'*64,images=[dict(role=role,index=i,title='Image '+str(i),filename=str(i)+'.png',sha256=str(i)*64) for i,role in enumerate(['Man Cave','Office','Living Room'],1)])
    return task

def test_downloads_bound_to_three_images_and_request():
    t=download_task();assert validate(t)==t

@pytest.mark.parametrize('change',['duplicate_role','duplicate_hash','duplicate_index','unsafe_name','changed_page','missing_csv','relative_directory'])
def test_ambiguous_downloads_rejected(change):
    t=download_task();v=t['actions'][0]['value']
    if change=='duplicate_role':v['images'][1]['role']='Man Cave'
    if change=='duplicate_hash':v['images'][1]['sha256']=v['images'][0]['sha256']
    if change=='duplicate_index':v['images'][1]['index']=1
    if change=='unsafe_name':v['images'][0]['filename']='../outside.png'
    if change=='changed_page':v['conversation']=v['conversation'].replace('chatgpt.com','evil.test')
    if change=='missing_csv':v.pop('csv_sha256')
    if change=='relative_directory':v['directory']='Downloads'
    with pytest.raises(Invalid):validate(t)
