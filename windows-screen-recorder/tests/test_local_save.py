import pytest
from desktop_recorder.contract import identity, Invalid


def target():
    return dict(app=r'C:\Apps\chrome.exe', window_key='Sports Cave recorder save test - Google Chrome',
                control_type='Button', automation_id='', name='Save all', scope=[],
                postcondition='sports-cave.local-save.v1')


def test_local_save_contract():
    assert identity(target()) == target()


@pytest.mark.parametrize('key,value', [('name', 'Save in a numbered folder'), ('control_type', 'Edit'),
    ('window_key', 'Sports Cave OS'), ('app', r'C:\Apps\notepad.exe'), ('postcondition', 'sports-cave.local-save.v2')])
def test_refuse_other_save_scopes(key, value):
    t = target(); t[key] = value
    with pytest.raises(Invalid):
        identity(t)
