"""Real batch recovery, conflict and code-permission tests in disposable assigned fixtures."""
import json
import unittest
from unittest.mock import patch
import test_editor, source_editor as source, editor, studio

class BatchTests(unittest.TestCase):
    def setUp(self):
        test_editor.EditorTests.setUp(self)
        (self.root/'orders_page.css').write_text('body { color: #111111; }')
        (self.root/'components/session_recovery.js').write_text('const fixture = 1;')
    def rows(self):
        rows=[]
        for path in (editor.CODE_FILES[0],'orders_page.css','components/session_recovery.js'):
            opened=source.open_file(self.home,self.draft['id'],'owner-a',path)
            extra='<p>Batch</p>' if path.endswith('.html') else '\n/* Batch */'
            rows.append({'path':path,'expected_hash':opened['hash'],'source':opened['source']+extra})
        return rows
    def save(self,rows,revision=0):return source.write_all(self.home,self.draft['id'],'owner-a',revision,rows)
    def test_batch_is_one_revision_and_file_history(self):
        result=self.save(self.rows());self.assertEqual(result['revision'],1)
        registry=studio.read(self.home/'.studio/registry.json');draft=registry['drafts'][0]
        self.assertEqual(len(draft['editor_history']),3)
        self.assertEqual(len({h['batch_id'] for h in draft['editor_history']}),1)
        self.assertEqual(len(draft['revisions'][-1]['files']),3)
        self.assertNotIn('editor_batch_pending',draft)
    def test_later_conflict_writes_nothing(self):
        rows=self.rows();before=(self.root/rows[0]['path']).read_bytes();rows[-1]['expected_hash']='0'*64
        with self.assertRaises(RuntimeError):self.save(rows)
        self.assertEqual((self.root/rows[0]['path']).read_bytes(),before)
        self.assertEqual(source.open_file(self.home,self.draft['id'],'owner-a','orders_page.css')['revision'],0)
    def test_owner_revision_path_and_secret_rejections(self):
        rows=self.rows()
        with self.assertRaises(RuntimeError):source.write_all(self.home,self.draft['id'],'wrong',0,rows)
        with self.assertRaises(RuntimeError):self.save(rows,9)
        for path in ('app.py','../app.py','.env','sc_auth.py','C:/file.css'):
            with self.assertRaises(ValueError):self.save([{'path':path,'expected_hash':'0'*64,'source':'unsafe'}])
        rows[0]['source']='ghp_'+'A'*30
        with self.assertRaises(ValueError):self.save(rows)
    def test_invalid_js_css_and_presentation_python(self):
        for path,value in [('orders_page.css','a {'),('components/session_recovery.js','const = ;'),('signin_presentation.py','import os\nos.remove("file")')]:
            with self.assertRaises((ValueError,SyntaxError)):source.validate_source(path,value)
        source.validate_source('signin_presentation.py','TITLE="Safe"\nDESCRIPTION="Text"\nBRAND="Sports Cave"\nCOLUMNS=(1,1.2,1)\n')
    def test_write_failure_rolls_back_all_and_keeps_revision(self):
        rows=self.rows();before={r['path']:(self.root/r['path']).read_bytes() for r in rows};real=source.replace;calls=0
        def fault(target,data):
            nonlocal calls
            calls+=1
            if calls==2:raise OSError('simulated replacement failure')
            real(target,data)
        with patch.object(source,'replace',fault):
            with self.assertRaises(OSError):self.save(rows)
        for path,data in before.items():self.assertEqual((self.root/path).read_bytes(),data)
        self.assertEqual(source.open_file(self.home,self.draft['id'],'owner-a',rows[0]['path'])['revision'],0)
    def test_process_interruption_rolls_back_on_next_read(self):
        rows=self.rows();before={r['path']:(self.root/r['path']).read_bytes() for r in rows};real=source.replace;calls=0
        def crash(target,data):
            nonlocal calls
            calls+=1
            if calls==2:raise KeyboardInterrupt('simulated process exit')
            real(target,data)
        with patch.object(source,'replace',crash):
            with self.assertRaises(KeyboardInterrupt):self.save(rows)
        self.assertIn('editor_batch_pending',studio.read(self.home/'.studio/registry.json')['drafts'][0])
        source.open_file(self.home,self.draft['id'],'owner-a',rows[0]['path'])
        for path,data in before.items():self.assertEqual((self.root/path).read_bytes(),data)
    def test_committed_interruption_finalises_once(self):
        rows=self.rows();real=studio.atomic
        def crash(file,registry):
            real(file,registry)
            if registry['drafts'][0].get('editor_batch_pending',{}).get('phase')=='committed':raise KeyboardInterrupt()
        with patch.object(studio,'atomic',crash):
            with self.assertRaises(KeyboardInterrupt):self.save(rows)
        self.assertEqual(source.open_file(self.home,self.draft['id'],'owner-a',rows[0]['path'])['revision'],1)
        self.assertEqual(source.open_file(self.home,self.draft['id'],'owner-a',rows[0]['path'])['revision'],1)
    def test_foreign_edit_during_recovery_is_not_overwritten(self):
        rows=self.rows();real=source.replace;calls=0
        def crash(target,data):
            nonlocal calls
            calls+=1
            if calls==2:raise KeyboardInterrupt()
            real(target,data)
        with patch.object(source,'replace',crash):
            with self.assertRaises(KeyboardInterrupt):self.save(rows)
        target=self.root/rows[0]['path'];target.write_text('Foreign edit')
        with self.assertRaises(RuntimeError):source.open_file(self.home,self.draft['id'],'owner-a',rows[0]['path'])
        self.assertEqual(target.read_text(),'Foreign edit')
        self.assertIn('editor_batch_pending',studio.read(self.home/'.studio/registry.json')['drafts'][0])
    def test_complete_read_and_history_undo(self):
        path=editor.CODE_FILES[0];original=source.open_file(self.home,self.draft['id'],'owner-a',path)
        self.assertTrue(original['complete']);result=self.save(self.rows())
        after=source.open_file(self.home,self.draft['id'],'owner-a',path);entry=after['history'][-1]
        old=source.history_source(self.home,self.draft['id'],'owner-a',path,entry['id'],'before')
        self.assertEqual(old['source'],original['source'])
        result=source.write_all(self.home,self.draft['id'],'owner-a',1,[{'path':path,'expected_hash':after['hash'],'restore':{'id':entry['id'],'side':'before'}}])
        self.assertEqual(result['revision'],2);self.assertEqual((self.root/path).read_text(),original['source'])

    def test_withheld_import_does_not_break_full_catalogue(self):
        (self.root/'app.py').write_text('import secret_store\nimport sc_auth\n')
        (self.root/'sc_auth.py').write_text('DEFAULT_PASSWORD="private-default"')
        listing=source.files(self.home,self.draft['id'],'owner-a')['files']
        self.assertFalse(next(f for f in listing if f['path']=='sc_auth.py')['available'])
        self.assertTrue(next(f for f in listing if f['path']=='orders_page.css')['available'])
        with self.assertRaises(ValueError):source.open_file(self.home,self.draft['id'],'owner-a','sc_auth.py')
        with self.assertRaises(ValueError):source.open_file(self.home,self.draft['id'],'owner-a',[])

    def test_full_file_is_not_truncated(self):
        path=editor.CODE_FILES[0];value='<p>Full source</p>\n'*10000;(self.root/path).write_text(value)
        opened=source.open_file(self.home,self.draft['id'],'owner-a',path)
        self.assertEqual(opened['source'],(self.root/path).read_bytes().decode('utf-8'))

if __name__=='__main__':unittest.main()
