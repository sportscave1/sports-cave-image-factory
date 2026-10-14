import os
import re
import subprocess
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class PreservationTests(unittest.TestCase):
    def test_unchanged_file_operations_and_v11_dependencies_are_preserved(self):
        source=(ROOT/'components/files_window/index.html').read_text(encoding='utf-8')
        baseline=subprocess.check_output(['git','show','823a1966:components/files_window/index.html'],cwd=ROOT).decode('utf-8')
        def fn(text,name):
            start=re.search(r'^      (?:async )?function '+name+r'\(',text,re.M).start()
            rest=text[start:];end=re.search(r'^      (?:async )?function ',rest[1:],re.M)
            return rest[:end.start()+1] if end else rest
        for name in ['pasteFiles','showDeleteDialog','uploadChunk','runUpload','setSingleSelection','selectByIndex']:
            self.assertEqual(fn(source,name),fn(baseline,name),name)
        for name in ['auto_editions_api.py','dropbox_integration.py','supabase_backend.py','desktop_helper_macos/SportsCaveFilesHelper.py','desktop_helper/Install.ps1']:
            self.assertEqual((ROOT/name).read_bytes(),subprocess.check_output(['git','show','823a1966:'+name],cwd=ROOT),name)

    def test_existing_native_transfer_and_cache_implementations_are_unchanged(self):
        source=(ROOT/'desktop_helper/SportsCaveFilesDesktop.cs').read_text(encoding='utf-8')
        baseline=subprocess.check_output(['git','show','823a1966:desktop_helper/SportsCaveFilesDesktop.cs'],cwd=ROOT).decode('utf-8')
        for name in ['TransferGrant','NativeCache','NativePayload']:
            pattern=r'internal (?:sealed |static )?class '+name+r'\b'
            def section(text):
                start=re.search(pattern,text).start();end=re.search(r'^internal ',text[start+1:],re.M)
                return text[start:start+end.start()+1] if end else text[start:]
            self.assertEqual(section(source),section(baseline),name)
        self.assertIn('Flags=4',source);self.assertNotIn('Flags=3',source)
        self.assertIn('config.Allows(args.Source)',source)

if __name__=='__main__':unittest.main()
