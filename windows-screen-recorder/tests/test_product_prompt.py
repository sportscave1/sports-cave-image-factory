import copy
import unittest
from desktop_recorder.contract import identity, browser_identity, Invalid


class ProductPromptContractTests(unittest.TestCase):
    def target(self):
        return dict(app=r'C:\Apps\msedge.exe',window_key='Sports Cave OS',control_type='Button',
                    automation_id='copyPrompt',name='Copy Black Frame Prompt',scope=[],
                    prompt_proof=dict(sha256='a'*64,utf16_length=45000,utf8_length=47000))

    def test_full_prompt_proof_not_editor_limit(self):
        self.assertEqual(identity(self.target())['prompt_proof']['utf16_length'],45000)

    def test_invalid_proofs_rejected(self):
        for field,value in [('utf16_length',True),('utf8_length',1048577),('sha256','bad'),('utf16_length',0)]:
            target=self.target();target['prompt_proof'][field]=value
            with self.assertRaises(Invalid):identity(target)
        target=self.target();target['name']='Some other copy'
        with self.assertRaises(Invalid):identity(target)

    def test_product_binding_is_bounded_digest(self):
        value=dict(profile='00000000-0000-4000-8000-000000000000',page='http://127.0.0.1:18963/?page=product_uploads',
                   frame='top',control='document',product='b'*64)
        self.assertEqual(browser_identity(value)['product'],'b'*64)
        value['product']='Tim Cahill'
        with self.assertRaises(Invalid):browser_identity(value)
