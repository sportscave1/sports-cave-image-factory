from task_recorder.desktop_capabilities import supports
from task_recorder.state_updates import merge_tasks, task_changes
from uuid import uuid4


def test_protocol_number_alone_never_advertises_desktop():
    assert not supports({"protocol": 99})
    assert not supports({"desktop_capabilities": {"format":"sports-cave.desktop", "version":1,
                                                  "action_versions":[1], "capture":True}})
    state = {"protocol":4, "desktop_capabilities":{"format":"sports-cave.desktop","version":1,
             "action_versions":[2],"capture":True,"playback":False}}
    assert supports(state)
    assert not supports(state, playback=True)


def test_scoped_desktop_summary_survives_existing_delta_transport():
    row = {"id":str(uuid4()),"name":"Desktop","format":"sports-cave.desktop","format_version":1,
           "capabilities":["uia.value.v2"],"playback_available":True,"revision":"a"*64,
           "inputs":[],"steps":1}
    assert merge_tasks([], {"upsert":[row], "remove":[]}) == [row]
