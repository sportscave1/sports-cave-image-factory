import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from desktop_recorder.download_install import activate,restore,install_bridge,restore_bridge,configure_installed

class Registry:
    def __init__(self):self.values={'32':{'value':'old-32','type':1},'64':None};self.fail=False
    def get(self,view):return copy.deepcopy(self.values[view])
    def put(self,view,record):
        if self.fail and view=='64':self.fail=False;raise OSError('simulated write failure')
        self.values[view]=copy.deepcopy(record)

class DownloadInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.folder=self.root/'host';self.folder.mkdir()
        self.exe=self.folder/'DownloadReceiptHost.exe';self.exe.write_bytes(b'isolated fixture never executed')
        self.extension='a'*32
        (self.folder/'host.json').write_text(json.dumps({'name':'com.sportscave.recorder.downloads','type':'stdio','path':str(self.exe),'allowed_origins':['chrome-extension://'+self.extension+'/']}))
        self.registry=Registry();self.before=copy.deepcopy(self.registry.values)

    def test_register_and_restore_both_views_preserving_unrelated_files(self):
        journal=activate(self.folder,self.root/'journals',self.registry)
        self.assertEqual(self.registry.get('32'),self.registry.get('64'))
        restore(journal,self.registry);self.assertEqual(self.registry.values,self.before)
        self.assertTrue(self.exe.exists())

    def test_partial_registration_failure_restores_previous_values(self):
        self.registry.fail=True
        with self.assertRaises(OSError):activate(self.folder,self.root/'journals',self.registry)
        self.assertEqual(self.registry.values,self.before)

    def test_rollback_refuses_new_owner_before_writing_either_view(self):
        journal=activate(self.folder,self.root/'journals',self.registry)
        self.registry.values['64']={'value':'different-owner','type':1}
        before=copy.deepcopy(self.registry.values)
        with self.assertRaisesRegex(RuntimeError,'independently'):restore(journal,self.registry)
        self.assertEqual(self.registry.values,before)

    def test_install_configure_restart_and_rollback_preserve_data(self):
        data=self.root/'data';data.mkdir();(data/'recording.json').write_text('preserved')
        transaction=self.root/'transaction.json'
        with patch('task_recorder.release.windows_x64'):
            folder=install_bridge(self.exe,self.root/'install',data,self.extension,transaction,self.registry)
        first=configure_installed(data);second=configure_installed(data)
        self.assertNotEqual(first['SC_RECORDER_DOWNLOAD_SESSION'],second['SC_RECORDER_DOWNLOAD_SESSION'])
        self.assertTrue(Path(first['SC_RECORDER_DOWNLOAD_EVENTS']).exists())
        self.assertEqual((data/'recording.json').read_text(),'preserved')
        restore_bridge(transaction,data,self.registry)
        self.assertFalse((data/'download-bridge.json').exists())
        self.assertEqual(self.registry.values,self.before)
        self.assertTrue(folder.exists())

    def test_configure_rejects_modified_host(self):
        data=self.root/'data'
        with patch('task_recorder.release.windows_x64'):
            folder=install_bridge(self.exe,self.root/'install',data,self.extension,self.root/'txn.json',self.registry)
        (folder/'DownloadReceiptHost.exe').write_bytes(b'modified')
        with self.assertRaisesRegex(ValueError,'differs'):configure_installed(data)
