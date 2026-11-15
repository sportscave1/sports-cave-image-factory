"""One focused contract regression for the transient Product Uploads picker."""
from copy import deepcopy
from uuid import uuid4
import pytest
from desktop_recorder.contract import validate,Invalid,FORMAT


def test_psd_picker_result_is_scoped_to_exact_edge_control_and_document():
    target=dict(app=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        window_key='Sports Cave OS',control_type='Button',automation_id='choose',name='Choose PSD',
        scope=[dict(control_type='Document',automation_id='RootWebArea',name='Product Uploads')],
        postcondition='sports-cave.product-psd-picker.v1')
    task=dict(format=FORMAT,version=1,id=str(uuid4()),name='PSD picker regression',
        starting_context=dict(mode='prepared',binding=None),
        actions=[dict(version=2,kind='invoke',requires=['uia.invoke.v2'],target=target,timeout_ms=8000)])
    assert validate(task)['actions'][0]['target']==target
    for changes in ({'automation_id':'other'},{'name':'Other button'},{'app':'other.exe'},
                    {'scope':[dict(control_type='Document',automation_id='RootWebArea',name='Other page')]}):
        wrong=deepcopy(task);wrong['actions'][0]['target'].update(changes)
        with pytest.raises(Invalid,match='application result contract'):
            validate(wrong)
