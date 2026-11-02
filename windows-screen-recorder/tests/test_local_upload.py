import pytest
from desktop_recorder.contract import Invalid, validate
from test_chat_submission import output_task


def task():
    result=output_task();a=result['actions'][0]
    a.update(kind='local_upload',requires=['local.upload.v3'],timeout_ms=300000,
             value={'images':[dict(role=role,path='C:\\Downloads\\'+str(i)+'.png',sha256=str(i)*64)
                              for i,role in enumerate(['Man Cave','Office','Living Room'],1)]})
    a['target'].pop('browser',None)
    return result


def test_local_upload_contract():
    t=task();assert validate(t)==t


@pytest.mark.parametrize('failure',['role','path','hash','relative','extra','version'])
def test_local_upload_contract_refuses_unsafe_mapping(failure):
    t=task();a=t['actions'][0];rows=a['value']['images']
    if failure in ('role','path','hash'):
        key='sha256' if failure=='hash' else failure;rows[1][key]=rows[0][key]
    elif failure=='relative':rows[0]['path']='relative.png'
    elif failure=='extra':a['value']['live']=True
    elif failure=='version':a['version']=2
    with pytest.raises(Invalid):validate(t)
