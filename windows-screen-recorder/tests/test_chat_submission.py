from copy import deepcopy
from uuid import uuid4
import pytest
from desktop_recorder.contract import FORMAT, Invalid, validate


def task():
    return dict(format=FORMAT, version=1, id=str(uuid4()), name='Submit prepared',
        starting_context=dict(mode='desktop_session', binding=None), actions=[dict(
            version=3, kind='chat_submit', requires=['chat.submit.v3'], timeout_ms=30000,
            target=dict(app='C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe', window_key='ChatGPT',
                control_type='Button', automation_id='', name='Send', scope=[], browser=dict(
                    profile=str(uuid4()), page='https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b/project',
                    frame='top', control='label:button:Send')),
            value=dict(request_id=str(uuid4()), sha256='a'*64, characters=124023))])


def test_request_contains_only_immutable_identity():
    original=task()
    assert validate(original)==original


@pytest.mark.parametrize('field,value', [('request_id','../escape'), ('sha256','prefix'), ('characters',False), ('characters',0), ('characters',1048577), ('text','private prompt')])
def test_invalid_or_content_bearing_request_rejected(field,value):
    modified=task(); modified['actions'][0]['value'][field]=value
    with pytest.raises(Invalid): validate(modified)


@pytest.mark.parametrize('field,value', [('page','https://chatgpt.com/c/12345678-1234-1234-1234-123456789abc'), ('frame','other'), ('control','label:button:Retry')])
def test_other_destination_rejected(field,value):
    modified=task(); modified['actions'][0]['target']['browser'][field]=value
    with pytest.raises(Invalid): validate(modified)


def test_saved_replay_with_lost_ack_is_refused_before_native_arm(tmp_path, monkeypatch):
    from desktop_recorder.coordinator import Coordinator
    from test_phase2 import command
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    coordinator = Coordinator(tmp_path / 'recorder')
    submit = task()['actions'][0]
    coordinator.apply(command('record', {'mode': 'desktop_session'}))
    coordinator.apply(command('event', dict(action=submit, privacy='safe', generation=coordinator.recording.generation)))
    coordinator.apply(command('stop'))
    coordinator.apply(command('save', {'name': 'One request'}))
    receipt = tmp_path / 'SportsCaveRecorder' / 'submission-receipts-v1' / (submit['value']['request_id'] + '.json')
    receipt.parent.mkdir(parents=True)
    receipt.write_text('{"state":"attempted"}')  # No acknowledgement: never infer safe retry.
    with pytest.raises(Invalid, match='before any desktop action'):
        coordinator.apply(command('play', dict(id=coordinator.last_saved['id'], revision=coordinator.last_saved['revision'])))
    assert coordinator.pending_play is None
    assert coordinator.playback.run is None


def output_task():
    result=task(); action=result['actions'][0]
    page='https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b-sc-mockups-uploads/c/6ae2d62d-1338-83ec-8619-6ea3635a7fa0'
    action.update(kind='chat_wait', requires=['chat.wait.v3'], timeout_ms=900000,
        value=dict(request_id=str(uuid4()), conversation=page))
    action['target'].update(control_type='Window', automation_id='window', name='ChatGPT')
    action['target']['browser'].update(page=page, control='window')
    return result


def test_output_wait_has_bounded_long_timeout():
    value=output_task(); assert validate(value)==value


@pytest.mark.parametrize('mutation', ['request','page','window','timeout'])
def test_output_wait_rejects_unbound_observation(mutation):
    value=output_task(); action=value['actions'][0]
    if mutation=='request': action['value']['request_id']='../escape'
    if mutation=='page': action['value']['conversation']=action['value']['conversation'].replace('chatgpt.com','evil.test')
    if mutation=='window': action['target']['control_type']='Button'
    if mutation=='timeout': action['timeout_ms']=900001
    with pytest.raises(Invalid): validate(value)
