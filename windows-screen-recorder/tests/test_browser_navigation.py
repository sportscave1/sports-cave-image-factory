import copy
import unittest
from desktop_recorder.contract import Invalid, validate


class NavigationContractTests(unittest.TestCase):
    def task(self):
        source = dict(profile='56578ebe-3793-47ba-b81f-fbc2c2755cf9',
                      page='http://127.0.0.1:18963/?page=product_uploads',
                      frame='top', control='id:home')
        destination = dict(source, page='http://127.0.0.1:18963/?page=dashboard', control='document')
        return dict(format='sports-cave.desktop', version=1,
                    id='4f6d4385-400f-4ea2-877e-0cb03a28d28d', name='Navigation',
                    starting_context=dict(mode='desktop_session', binding=None),
                    actions=[dict(version=3, kind='browser_navigation', requires=['edge.navigation.v3'],
                                  timeout_ms=8000, value=destination,
                                  target=dict(app=r'C:\Apps\msedge.exe', window_key='Sports Cave OS',
                                              control_type='Button', automation_id='', name='Home', scope=[], browser=source))])

    def test_navigation_roundtrip(self):
        task = self.task()
        self.assertEqual(validate(task), task)

    def test_reject_unrelated_profile_page_and_unversioned_navigation(self):
        for change in [dict(profile='11111111-1111-4111-8111-111111111111'),
                       dict(page='https://example.com/'),
                       dict(page='http://127.0.0.1:18963/?page=product_uploads'),
                       dict(frame='child'), dict(control='id:unrelated')]:
            task = self.task()
            task['actions'][0]['value'].update(change)
            with self.subTest(change=change), self.assertRaises(Invalid):
                validate(task)
        task = self.task()
        task['actions'][0]['version'] = 2
        with self.assertRaises(Invalid):
            validate(task)

    def test_old_invoke_cannot_carry_navigation_destination(self):
        task = self.task()
        task['actions'][0].update(version=2, kind='invoke', requires=['uia.invoke.v2'])
        with self.assertRaises(Invalid):
            validate(task)
