"""Durable archive recovery, with an in-memory Dropbox boundary; never sends mail."""
import os
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import wall_preview_archive as worker
import wall_preview_crm_store as store
from scripts.recover_wall_preview_archives import recover
from tests import test_wall_preview_crm_v2 as fixture


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class RecoveryTests(unittest.TestCase):
    setUpClass=classmethod(fixture.DatabaseTests.setUpClass.__func__)
    tearDown=fixture.DatabaseTests.tearDown

    def setUp(self):
        fixture.DatabaseTests.setUp(self)
        self.data['archive_image']=fixture.jpeg()
        base='/Sportscave Team Folder/03_ASSETS/11 Wall Preview Inbox/Anonymous'
        self.upload.return_value={'pending_archive':True,'file_id':'','folder':base,
                                  'path':base+'/'+self.data['client_preview_id']+'.jpg'}
        self.files={}
        self.calls=[]
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        db=worker.archive.dropbox_integration
        self.stack.enter_context(patch.object(worker.archive,'_dropbox_connection',return_value=('server-token','/Sportscave Team Folder')))
        self.stack.enter_context(patch.object(db,'ensure_folder_path'))
        self.stack.enter_context(patch.object(db,'get_metadata_if_exists',side_effect=lambda token,path:self.files.get(path)))
        self.stack.enter_context(patch.object(db,'upload_stream',side_effect=self.put))
        self.stack.enter_context(patch.object(db,'move_path',side_effect=self.move))

    def put(self,token,path,stream,**kwargs):
        self.assertEqual(kwargs['conflict'],'replace')
        self.calls.append(('put',path))
        self.files[path]={'id':self.files.get(path,{}).get('id','id:'+str(len(self.calls))), 'image':stream.read()}
        return self.files[path]

    def move(self,token,source,destination,**kwargs):
        self.assertNotIn(destination,self.files)
        self.calls.append(('move',destination))
        self.files[destination]=self.files.pop(source)
        return self.files[destination]

    def read(self,pid):
        with self.Adapter() as cur:
            cur.execute('SELECT * FROM public.wall_previews WHERE id=%s',(str(pid),))
            return dict(cur.fetchone())

    def confirm(self):return store.confirm(self.data,self.upload)[0]

    def fail(self,pid,reason='archive_unavailable'):
        with self.Adapter() as cur:
            cur.execute("UPDATE public.wall_preview_archive_jobs SET state='failed',attempts=5,reason=%s WHERE preview_id=%s",(reason,str(pid)))

    def test_place_anonymous_then_download_email_moves_one_file_and_permission_separate(self):
        row=self.confirm();pid=row['id'];self.assertEqual(row['archive_status'],'queued')
        self.assertTrue(worker.tick(str(pid)));original=self.read(pid)['dropbox_file_id']
        self.data.update(image_reuse_allowed=False)
        self.data['identity']['customer_email']='collector@example.test'
        enriched=self.confirm();self.assertEqual(enriched['id'],pid);self.assertEqual(enriched['version'],1)
        self.assertFalse(enriched['marketing_permission']);self.assertEqual(enriched['archive_status'],'queued')
        self.assertTrue(worker.tick(str(pid)))
        saved=self.read(pid);self.assertIn('/collector@example.test/',saved['dropbox_path'])
        self.assertEqual(saved['dropbox_file_id'],original);self.assertEqual(len(self.files),1)
        self.assertNotIn(row['dropbox_path'],self.files)
        self.data['image_reuse_allowed']=True
        approved=self.confirm();self.assertTrue(approved['marketing_permission'])
        self.assertEqual(approved['archive_status'],'archived');self.assertFalse(worker.tick(str(pid)))
        with self.Adapter() as cur:
            cur.execute('SELECT count(*) n FROM public.wall_preview_email_jobs');self.assertEqual(cur.fetchone()['n'],0)

    def test_download_without_place_and_twice_is_same_archived_preview(self):
        self.data['identity']['customer_email']='collector@example.test'
        self.data['image_reuse_allowed']=False
        row=self.confirm();worker.tick(str(row['id']))
        again=self.confirm();self.assertEqual(again['id'],row['id']);self.assertEqual(again['archive_status'],'archived')
        self.assertEqual(len(self.files),1);self.assertFalse(worker.tick(str(row['id'])))

    def test_three_placements_only_latest_bytes_one_file(self):
        row=self.confirm();worker.tick(str(row['id']))
        for i,color in enumerate(('green','blue')):
            self.data.update(image_sha256=str(i)*64,archive_image=fixture.jpeg(color))
            self.assertEqual(self.confirm()['id'],row['id'])
        worker.tick(str(row['id']))
        self.assertEqual(len(self.files),1)
        self.assertEqual(next(iter(self.files.values()))['image'],fixture.jpeg('blue'))
        self.assertEqual(self.read(row['id'])['version'],3)

    def test_identical_download_repairs_failed_job_without_new_version(self):
        row=self.confirm();self.fail(row['id'])
        again=self.confirm();self.assertEqual(again['version'],1);self.assertEqual(again['archive_status'],'queued')
        self.assertTrue(worker.tick(str(row['id'])));self.assertEqual(len(self.files),1)

    def test_missing_file_receipt_even_done_job_is_repaired(self):
        row=self.confirm()
        with self.Adapter() as cur:cur.execute("UPDATE public.wall_preview_archive_jobs SET state='done',image=NULL")
        self.assertEqual(self.confirm()['archive_status'],'queued')
        self.assertTrue(worker.tick(str(row['id'])))

    def test_queued_identical_retry_preserves_attempts_and_backoff(self):
        self.confirm()
        with self.Adapter() as cur:cur.execute("UPDATE public.wall_preview_archive_jobs SET attempts=2,due_at=now()+interval '1 hour'")
        self.confirm()
        with self.Adapter() as cur:
            cur.execute('SELECT attempts,due_at>now() future FROM public.wall_preview_archive_jobs')
            self.assertEqual(cur.fetchone(),{'attempts':2,'future':True})

    def test_no_provider_receipt_never_marks_done(self):
        row=self.confirm()
        with patch.object(worker.archive.dropbox_integration,'upload_stream',return_value={}):worker.tick(str(row['id']))
        self.assertFalse(self.read(row['id'])['dropbox_file_id']);self.assertIsNotNone(store.pending_archive_image(row['id']))
        with self.Adapter() as cur:cur.execute('UPDATE public.wall_preview_archive_jobs SET due_at=now()')
        worker.tick(str(row['id']));self.assertTrue(self.read(row['id'])['dropbox_file_id'])

    def test_move_failure_preserves_source_and_retry_completes(self):
        row=self.confirm();worker.tick(str(row['id']))
        self.data.update(image_reuse_allowed=False);self.data['identity']['customer_email']='collector@example.test';self.confirm()
        with patch.object(worker.archive.dropbox_integration,'move_path',side_effect=RuntimeError('temporary')):worker.tick(str(row['id']))
        self.assertIn(row['dropbox_path'],self.files);self.assertEqual(self.read(row['id'])['dropbox_path'],row['dropbox_path'])
        with self.Adapter() as cur:cur.execute('UPDATE public.wall_preview_archive_jobs SET due_at=now()')
        worker.tick(str(row['id']));self.assertEqual(len(self.files),1);self.assertNotIn(row['dropbox_path'],self.files)

    def test_move_succeeded_before_db_commit_retry_does_not_duplicate(self):
        row=self.confirm();worker.tick(str(row['id']))
        self.data.update(image_reuse_allowed=False);self.data['identity']['customer_email']='collector@example.test';self.confirm()
        destination=row['dropbox_path'].replace('/Anonymous/','/collector@example.test/')
        self.move('token',row['dropbox_path'],destination)
        worker.tick(str(row['id']));self.assertEqual(len(self.files),1);self.assertEqual(self.read(row['id'])['dropbox_path'],destination)

    def test_recovery_command_scoped_dry_run_idempotent_no_upload(self):
        row=self.confirm();pid=str(row['id']);self.fail(pid)
        self.assertTrue(recover([pid])[0]['eligible']);self.assertFalse(recover([pid])[0]['requeued'])
        self.assertTrue(recover([pid],True)[0]['requeued']);self.assertFalse(recover([pid],True)[0]['requeued'])
        self.assertFalse(self.files)
        self.fail(pid,'obsolete_version');self.assertFalse(recover([pid],True)[0]['eligible'])

    def test_relocation_collision_preserves_both_files_and_job_image(self):
        row=self.confirm();worker.tick(str(row['id']))
        self.data.update(image_reuse_allowed=False);self.data['identity']['customer_email']='collector@example.test';self.confirm()
        destination=row['dropbox_path'].replace('/Anonymous/','/collector@example.test/')
        self.files[destination]={'id':'id:unrelated','image':b'untouched'}
        worker.tick(str(row['id']))
        self.assertIn(row['dropbox_path'],self.files);self.assertEqual(self.files[destination]['image'],b'untouched')
        self.assertIsNotNone(store.pending_archive_image(row['id']))
        self.assertFalse(recover([str(row['id'])],True)[0]['eligible'])

    def test_targeted_tick_and_requeue_leave_other_preview_untouched(self):
        first=self.confirm();self.fail(first['id'])
        self.data.update(client_preview_id=fixture.payload()['client_preview_id'])
        second=self.confirm();self.fail(second['id'])
        recover([str(first['id'])],True);worker.tick(str(first['id']))
        with self.Adapter() as cur:
            cur.execute('SELECT state,attempts FROM public.wall_preview_archive_jobs WHERE preview_id=%s',(str(second['id']),))
            self.assertEqual(cur.fetchone(),{'state':'failed','attempts':5})


class ConfigurationTests(unittest.TestCase):
    def test_diagnostic_contains_key_names_only(self):
        with patch.object(worker.archive.dropbox_integration,'missing_server_config_keys',return_value=('DROPBOX_REFRESH_TOKEN','DROPBOX_ACCESS_TOKEN')),self.assertLogs(worker.LOG,level='WARNING') as logs:
            worker.configuration_diagnostic()
        self.assertIn('DROPBOX_REFRESH_TOKEN',logs.output[0])


if __name__=='__main__':unittest.main()
