import copy
import unittest
from desktop_recorder.contract import validate, Invalid


class DownloadContractTests(unittest.TestCase):
    def task(self):
        return {'format':'sports-cave.desktop','version':1,
            'id':'fbc8d2ca-cc47-4571-8ff7-56273f699911','name':'Disposable download',
            'starting_context':{'mode':'desktop_session','binding':None},
            'actions':[{'version':3,'kind':'browser_download','requires':['edge.download.v3'],
                'timeout_ms':30000,'value':{'directory':r'C:\Users\hello\Downloads'},
                'target':{'app':r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
                    'window_key':'Recorder acceptance A','scope':[],'control_type':'Button',
                    'automation_id':'download','name':'Download disposable file',
                    'browser':{'profile':'56578ebe-3793-47ba-b81f-fbc2c2755cf9',
                        'page':'http://127.0.0.1:18963/recorder-acceptance/tab-a',
                        'frame':'top','control':'id:download'},
                    'download':{'url':'http://127.0.0.1:18963/recorder-acceptance/sample.txt?sc_download=8f0169ed-36a1-4538-a0a7-80333136a096',
                        'filename':'recorder-disposable.txt','save_as':False}}}]}

    def test_versioned_download_is_accepted(self):
        task=self.task()
        self.assertEqual(validate(task),task)

    def test_structured_metadata_still_rejects_unapproved_source_and_extra_fields(self):
        for mutation in ({'url':'https://example.com/file'}, {'extra':'not allowed'}, {'filename':'../old.txt'}, {'save_as':'true'}):
            task=copy.deepcopy(self.task())
            task['actions'][0]['target']['download'].update(mutation)
            with self.assertRaises(Invalid):validate(task)
