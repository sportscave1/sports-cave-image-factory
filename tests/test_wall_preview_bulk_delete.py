"""Destructive boundaries are mocked; SQL uses the disposable loopback fixture."""
import asyncio
import os
import unittest
import uuid
from unittest.mock import Mock, patch

import httpx
from starlette.applications import Starlette
from starlette.routing import Route

import wall_preview_deletion as deletion
import wall_preview_inbox_api as api
import wall_preview_archive as worker
import wall_preview_crm_store as crm
import wall_preview_store as ledger
from tests.test_wall_preview_crm_v2 import DatabaseTests as Fixture, payload

ADMIN={'id':str(uuid.uuid4()),'role':'admin','is_active':True}


class AssetsTests(unittest.TestCase):
    def setUp(self):
        self.pid=str(uuid.uuid4())
        self.path=deletion.ROOT+'/Anonymous/'+self.pid+'.jpg'
        self.row={'id':self.pid,'dropbox_path':self.path,'dropbox_file_id':'id:one'}
        self.asset={'id':'id:one','path':self.path,'rev':'1'}
        self.provider=deletion.Assets()
        self.provider._client=Mock()
        self.metadata={'.tag':'file','id':'id:one','path_display':self.path,'rev':'1'}
        self.provider._client.files_get_metadata.return_value=self.metadata

    def test_exact_file_id_deleted_never_folder(self):
        self.assertEqual(self.provider.resolve(self.row,[self.path]),[self.asset])
        self.provider.remove(self.asset)
        self.provider._client.files_delete_v2.assert_called_once_with('id:one')

    def test_wrong_id_folder_outside_root_and_changed_revision_are_rejected(self):
        for change in ({'id':'id:other'},{'.tag':'folder'},{'path_display':'/Shopify/artwork.jpg'}):
            self.provider._client.files_get_metadata.return_value={**self.metadata,**change}
            with self.assertRaises(deletion.WallPreviewStoreError):self.provider.resolve(self.row,[self.path])
        self.provider._client.files_get_metadata.return_value={**self.metadata,'rev':'2'}
        with self.assertRaises(deletion.WallPreviewStoreError):self.provider.remove(self.asset)
        self.provider._client.files_delete_v2.assert_not_called()

    def test_pending_upload_requires_owned_filename(self):
        row={**self.row,'dropbox_file_id':''}
        self.assertEqual(self.provider.resolve(row,[self.path]),[self.asset])
        self.provider._client.files_get_metadata.return_value={**self.metadata,'path_display':deletion.ROOT+'/unrelated.jpg'}
        with self.assertRaises(deletion.WallPreviewStoreError):self.provider.resolve(row,[self.path])

    def test_missing_is_idempotent_but_auth_errors_are_not(self):
        import dropbox
        missing=dropbox.exceptions.ApiError('test',dropbox.files.GetMetadataError.path(dropbox.files.LookupError.not_found),None,None)
        self.provider._client.files_get_metadata.side_effect=missing
        self.provider.remove(self.asset)
        self.provider._client.files_delete_v2.assert_not_called()
        self.provider._client.files_get_metadata.side_effect=RuntimeError('secret token')
        with self.assertRaisesRegex(deletion.WallPreviewStoreError,'Dropbox lookup failed'):self.provider.remove(self.asset)

    def test_batch_validates_every_id_before_any_deletion_and_deduplicates(self):
        with patch.object(deletion,'delete_one') as delete:
            for ids in ([self.pid,'bad'],[self.pid]*25,[],[''],None):
                with self.assertRaises((ValueError,TypeError)):deletion.bulk_delete(ids,user=ADMIN)
            delete.assert_not_called()
            delete.return_value={'id':self.pid,'status':'deleted'}
            self.assertEqual(len(deletion.bulk_delete([self.pid,self.pid],user=ADMIN)),1)
            delete.assert_called_once()
            with self.assertRaises(PermissionError):deletion.bulk_delete([self.pid],user={'role':'worker'})

    def test_rate_limit_honours_backoff_without_repeating_requests(self):
        import dropbox
        self.provider._client.files_get_metadata.side_effect=dropbox.exceptions.RateLimitError('test',backoff=60)
        for _ in range(2):
            with self.assertRaises(deletion.WallPreviewStoreError):self.provider.metadata(self.path)
        self.provider._client.files_get_metadata.assert_called_once()


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable loopback PostgreSQL required')
class DeletionDatabaseTests(unittest.TestCase):
    setUpClass=classmethod(Fixture.setUpClass.__func__)
    setUp=Fixture.setUp
    tearDown=Fixture.tearDown
    create=Fixture.create

    def provider(self):
        provider=Mock()
        provider.resolve.side_effect=lambda row,paths:[{'id':row['dropbox_file_id'],'path':row['dropbox_path'],'rev':'1'}] if row['dropbox_file_id'] else []
        return provider

    def test_twenty_deleted_unrelated_record_preserved_and_progress(self):
        ids=[]
        for i in range(21):
            row=crm.confirm(payload(),Mock(return_value={'path':deletion.ROOT+f'/test-{i}.jpg','folder':deletion.ROOT,'file_id':f'id:{i}'}))[0]
            ids.append(str(row['id']))
        provider=self.provider();progress=Mock()
        with patch('activity_log.record_activity_log'):
            results=deletion.bulk_delete(ids[:20],user=ADMIN,assets=provider,progress=progress)
        self.assertTrue(all(r['status']=='deleted' for r in results))
        self.assertEqual(provider.remove.call_count,20);self.assertEqual(progress.call_count,20)
        self.assertEqual([str(r['id']) for r in ledger.list_previews(status='all',include_private=True)],[ids[20]])
        with self.Adapter() as cur:
            cur.execute('SELECT customer_email,dropbox_path,session_id,product_title,attribution FROM wall_previews WHERE id=%s',(ids[0],))
            row=cur.fetchone();self.assertIsNone(row['session_id']);self.assertEqual(row['dropbox_path'],'');self.assertEqual(row['product_title'],'')
            self.assertEqual(set(row['attribution']),{'inbox_deleted_at','inbox_deleted_by'})

    def test_partial_failure_retry_and_crash_after_provider_success(self):
        first=self.create();other=crm.confirm(payload(),Mock(return_value={'path':deletion.ROOT+'/other.jpg','folder':deletion.ROOT,'file_id':'id:other'}))[0]
        provider=self.provider()
        provider.remove.side_effect=lambda asset: (_ for _ in ()).throw(deletion.WallPreviewStoreError('Dropbox unavailable')) if asset['id']=='id:fixture' else None
        with patch('activity_log.record_activity_log'):
            results=deletion.bulk_delete([str(first['id']),str(other['id'])],user=ADMIN,assets=provider)
        self.assertEqual([r['status'] for r in results],['failed','deleted'])
        row=ledger.get_preview(str(first['id']),include_private=True)
        self.assertTrue(row['attribution']['inbox_deletion']['assets'])
        with self.assertRaises(ValueError):crm.confirm(self.data,self.upload)
        provider.remove.side_effect=None
        with patch.object(deletion,'_finish',side_effect=RuntimeError('db failed')):
            self.assertEqual(deletion.bulk_delete([str(first['id'])],user=ADMIN,assets=provider)[0]['status'],'failed')
        self.assertTrue(ledger.get_preview(str(first['id']),include_private=True)['attribution']['inbox_deletion'])
        with patch('activity_log.record_activity_log'):
            self.assertEqual(deletion.bulk_delete([str(first['id'])],user=ADMIN,assets=provider)[0]['status'],'deleted')
            self.assertEqual(deletion.bulk_delete([str(first['id'])],user=ADMIN,assets=provider)[0]['status'],'already_deleted')
        self.assertEqual(provider.resolve.call_count,2)  # no rediscovery after provider/DB failures

    def test_shared_file_preserved_until_last_reference_deleted(self):
        first=self.create();other=crm.confirm(payload(),self.upload)[0];provider=self.provider()
        with patch('activity_log.record_activity_log'):
            result=deletion.delete_one(str(first['id']),user=ADMIN,assets=provider)
            self.assertEqual(result['shared_files_preserved'],1);provider.remove.assert_not_called()
            deletion.delete_one(str(other['id']),user=ADMIN,assets=provider)
        provider.remove.assert_called_once()

    def test_processing_preview_is_fenced_and_pending_bytes_are_removed(self):
        self.data['archive_image']=b'fixture';self.upload.return_value.update(file_id='',pending_archive=True)
        row=self.create();provider=self.provider()
        with patch('activity_log.record_activity_log'):
            deletion.delete_one(str(row['id']),user=ADMIN,assets=provider)
        with patch.object(worker.archive,'_dropbox_connection') as connection:
            self.assertFalse(worker.tick());connection.assert_not_called()
        with self.assertRaises(ValueError):crm.confirm(self.data,self.upload)
        with self.assertRaises(PermissionError):crm.add_event(str(row['id']),self.data['session_id'],'WallPreviewDownloaded',str(uuid.uuid4()))
        self.assertIsNone(crm.pending_archive_image(str(row['id'])))


class EndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_admin_confirmation_origin_and_partial_result(self):
        app=Starlette(routes=[Route(p,e,methods=m) for p,e,m in api.ROUTES])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://os.example') as client:
            data={'preview_ids':[str(uuid.uuid4())],'confirmed':True}
            headers={'Origin':'https://os.example','X-Wall-Preview-Action':'delete'}
            with patch.object(api,'authorize',return_value=ADMIN),patch.object(deletion,'bulk_delete',return_value=[{'id':data['preview_ids'][0],'status':'failed','error':'Dropbox unavailable'}]) as delete:
                for extra in ({}, {'Origin':'https://evil.example','X-Wall-Preview-Action':'delete'}):
                    self.assertEqual((await client.post(api.ROUTES[0][0],json=data,headers=extra)).status_code,403)
                delete.assert_not_called()
                self.assertEqual((await client.post(api.ROUTES[0][0],json={**data,'confirmed':False},headers=headers)).status_code,400)
                response=await client.post(api.ROUTES[0][0],json=data,headers=headers)
                self.assertEqual(response.status_code,207);self.assertEqual(response.json()['results'][0]['status'],'failed')
            with patch.object(api,'authorize',return_value={'role':'worker'}),patch.object(deletion,'bulk_delete') as delete:
                self.assertEqual((await client.post(api.ROUTES[0][0],json=data,headers=headers)).status_code,403)
                delete.assert_not_called()


if __name__=='__main__':unittest.main()
