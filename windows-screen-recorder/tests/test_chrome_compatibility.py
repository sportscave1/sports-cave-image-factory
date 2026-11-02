"""Chrome page contracts; no desktop input or external writes."""
import copy
import json
import unittest
from desktop_recorder.contract import identity, validate, Invalid
import test_browser_navigation
import test_download_contract
import test_product_prompt

class ChromeCompatibilityTests(unittest.TestCase):
    def test_saved_navigation_roundtrip_preserves_chrome_identity(self):
        task = test_browser_navigation.NavigationContractTests().task()
        task['actions'][0]['target']['app'] = r'C:\Apps\chrome.exe'
        self.assertEqual(validate(json.loads(json.dumps(task))), task)
        for field, value in [('profile', '11111111-1111-4111-8111-111111111111'),
                             ('page', 'https://example.com/'), ('frame', 'child')]:
            bad = copy.deepcopy(task)
            bad['actions'][0]['value'][field] = value
            with self.subTest(field=field), self.assertRaises(Invalid): validate(bad)

    def test_chrome_prompt_and_product_acknowledgements(self):
        prompt = test_product_prompt.ProductPromptContractTests().target()
        prompt['app'] = r'C:\Apps\chrome.exe'
        self.assertEqual(identity(prompt), prompt)
        for name, aid, contract in [('Generate mockups', '', 'sports-cave.product-generation.v1'),
                                    ('Choose PSD', 'choose', 'sports-cave.product-psd-picker.v1')]:
            target = dict(app=r'C:\Apps\CHROME.EXE', window_key='Sports Cave OS',
                          control_type='Button', automation_id=aid, name=name,
                          postcondition=contract, scope=[dict(control_type='Document',
                          automation_id='RootWebArea', name='Product Uploads')])
            self.assertEqual(identity(target), target)
            for bad_app in ['notepad.exe', 'chrome_proxy.exe', 'chrome.exe.old', 'fakechrome.exe']:
                bad = dict(target, app=bad_app)
                with self.subTest(app=bad_app), self.assertRaises(Invalid): identity(bad)
            bad = dict(target, name='Other button')
            with self.assertRaises(Invalid): identity(bad)

    def test_chrome_does_not_inherit_edge_only_transport(self):
        task = test_download_contract.DownloadContractTests().task()
        task['actions'][0]['target']['app'] = r'C:\Apps\chrome.exe'
        with self.assertRaisesRegex(Invalid, 'Edge bridge'): validate(task)
        task = test_browser_navigation.NavigationContractTests().task()
        step = task['actions'][0]
        step.update(version=2, kind='browser_tab', requires=['edge.tab.v2'])
        step.pop('value')
        step['target'].update(app=r'C:\Apps\chrome.exe',control_type='TabItem')
        with self.assertRaisesRegex(Invalid, 'Edge tab'): validate(task)
