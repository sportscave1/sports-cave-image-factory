import copy
import json
import unittest
from uuid import uuid4
from desktop_recorder.contract import validate,Invalid,FORMAT


class TransferContracts(unittest.TestCase):
    def action(self,kind,slot=0):
        capabilities={'transfer_copy':'transfer.editor-copy.v3','transfer_paste':'transfer.paste.v3'}
        return dict(version=3,kind=kind,requires=[capabilities[kind]],
            target=dict(app='test.exe',window_key='Disposable',control_type='Edit',automation_id=kind,name='Test field',scope=[]),
            timeout_ms=8000,value=dict(slot=slot,mode='whole_text' if kind=='transfer_copy' else 'replace_all'))

    def task(self,actions):
        return dict(format=FORMAT,version=1,id=str(uuid4()),name='Transfer test',starting_context=dict(mode='prepared',binding=None),actions=actions)

    def test_no_transferred_text_serialized(self):
        task=self.task([self.action('transfer_copy'),self.action('transfer_paste')])
        self.assertEqual(validate(task),task)
        self.assertNotIn('source_sha256',json.dumps(task))

    def test_missing_stale_duplicate_and_wrong_version_rejected(self):
        cases=[[self.action('transfer_paste')],
            [self.action('transfer_copy'),self.action('transfer_copy',1),self.action('transfer_paste',0)],
            [self.action('transfer_copy'),self.action('transfer_copy')]]
        bad=self.action('transfer_copy');bad['version']=2;cases.append([bad])
        bad=self.action('transfer_copy');bad['value']['text']='must not persist';cases.append([bad])
        for actions in cases:
            with self.assertRaises(Invalid):validate(self.task(actions))

    def test_old_fixed_copy_unchanged(self):
        a=self.action('transfer_copy');a.update(version=2,kind='copy_text',requires=['clipboard.copy-text.v2'],
            value=dict(text='original fixed text',source_sha256='a'*64))
        self.assertEqual(validate(self.task([a]))['actions'][0],a)

    def test_secure_target_rejected(self):
        a=self.action('transfer_copy');a['target']['name']='Password'
        with self.assertRaises(Invalid):validate(self.task([a]))
