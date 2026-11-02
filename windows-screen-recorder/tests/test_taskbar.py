import copy
import unittest
from desktop_recorder.contract import validate, Invalid
from desktop_recorder.coordinator import action_log

class TaskbarContractTests(unittest.TestCase):
    def test_explicit_local_caption_identity(self):
        task=self.task()
        caption=dict(surface='XamlExplorerHostIslandWindow',control_type='ListItem',class_name='SC.LocalCaption.v1',automation_id='exact-caption',name='Sports Cave OS')
        task['actions'][0]['value']['thumbnail']=caption
        with self.assertRaises(Invalid):validate(copy.deepcopy(task))
        task['actions'][0]['requires'].append('windows.taskbar.caption.v1')
        self.assertEqual(validate(copy.deepcopy(task)),task)
        for key,value in [('surface','TaskListThumbnailWnd'),('control_type','Button'),('automation_id',''),('x',20)]:
            altered=copy.deepcopy(task);altered['actions'][0]['value']['thumbnail'][key]=value
            with self.subTest(key=key),self.assertRaises(Invalid):validate(altered)

    def task(self):
        return dict(format='sports-cave.desktop',version=1,id='4f6d4385-400f-4ea2-877e-0cb03a28d28d',name='Taskbar',
            starting_context=dict(mode='desktop_session',binding=None), actions=[dict(version=3,kind='taskbar_activate',
            requires=['windows.taskbar.v3'],timeout_ms=8000,target=dict(app=r'C:\Apps\chrome.exe',window_key='Sports Cave OS',
            name='Sports Cave OS',automation_id='window',control_type='Window',scope=[]),value=dict(button=dict(
            surface='Shell_TrayWnd',control_type='Button',class_name='Taskbar.TaskListButtonAutomationPeer',
            automation_id='Appid:SC.test',name='Sports Cave OS - 1 running window')))])
    def test_round_trip_and_visible_route(self):
        task=self.task();self.assertEqual(validate(copy.deepcopy(task)),task)
        self.assertIn('Switch via taskbar',action_log(task)[0])
        task['actions'][0]['value']['thumbnail']=dict(surface='TaskListThumbnailWnd',control_type='ListItem',class_name='',automation_id='',name='Sports Cave OS')
        self.assertEqual(validate(copy.deepcopy(task)),task)
    def test_no_route_loss_or_coordinate_handle_injection(self):
        for key,value in [('version',2),('requires',['windows.focus.v2']),('value',{}),('value',{'x':2,'y':4}),('kind','focus_window')]:
            task=self.task();task['actions'][0][key]=value
            with self.subTest(key=key),self.assertRaises(Invalid):validate(task)
        for key,value in [('surface','Chrome_WidgetWin_1'),('control_type','MenuItem'),('hwnd',123),('name','Bearer abcdef')]:
            task=self.task();task['actions'][0]['value']['button'][key]=value
            with self.subTest(key=key),self.assertRaises(Invalid):validate(task)
    def test_thumbnail_must_be_shell_thumbnail(self):
        task=self.task();task['actions'][0]['value']['thumbnail']=copy.deepcopy(task['actions'][0]['value']['button'])
        with self.assertRaises(Invalid):validate(task)
    def test_existing_focus_retains_semantics(self):
        task=self.task();action=task['actions'][0];action.update(version=2,kind='focus_window',requires=['windows.focus.v2']);del action['value']
        self.assertEqual(validate(task),task)

    def test_never_launch_pinned_or_choose_close_control(self):
        for part, change in [('button', {'name':'Sports Cave OS pinned'}), ('button', {'automation_id':'StartButton'}),
                             ('button', {'class_name':'ToggleButton'}), ('thumbnail', {'name':'Close window'})]:
            task=self.task()
            if part == 'thumbnail':
                task['actions'][0]['value'][part]=dict(surface='TaskListThumbnailWnd', control_type='Button', class_name='', automation_id='', name='Sports Cave OS')
            task['actions'][0]['value'][part].update(change)
            with self.subTest(change=change),self.assertRaises(Invalid):validate(task)
