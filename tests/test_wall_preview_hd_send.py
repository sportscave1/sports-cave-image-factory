"""Disclosed Send contract and deferred archive. No real provider writes/delivery."""
import os
import unittest
from pathlib import Path
from unittest.mock import patch
import wall_preview_crm_api as api
import wall_preview_crm_store as store
import wall_preview_archive as archive_worker
from tests import test_wall_preview_crm_v2 as v2
from tests.test_wall_preview_hd_email import HdDatabaseTests


def consent():
    return {'marketing_opt_in':True,'marketing_consent_source':'wall_preview_hd_email_send',
            'marketing_consent_text':api.CONSENT_TEXT,'name':' Nathan Baker ',
            'image_reuse_allowed':False,'market_country_code':'AU','market_country_name':'Australia'}


class ContractTests(unittest.TestCase):
    def test_send_contract_requires_disclosure_without_requiring_checkbox(self):
        options=api.email_options(consent())
        self.assertTrue(options['marketing_opt_in']);self.assertFalse(options['image_reuse_allowed'])
        self.assertEqual(options['marketing_consent_version'],api.CONSENT_VERSION)
        self.assertEqual(options['marketing_consent_text'],api.CONSENT_TEXT)
        for change in ({'marketing_consent_text':None},{'marketing_consent_text':'different'},
                       {'marketing_consent_version':'other'},{'name':123}):
            with self.subTest(change=change),self.assertRaises(ValueError):api.email_options({**consent(),**change})

    def test_legacy_unknown_or_false_is_not_optin(self):
        self.assertIsNone(api.email_options({})['marketing_opt_in'])
        self.assertFalse(api.email_options({'marketing_opt_in':False})['marketing_opt_in'])
        self.assertIsNone(api.email_options({'image_reuse_allowed':True})['marketing_opt_in'])


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class DatabaseTests(HdDatabaseTests):
    def test_send_evidence_saved_once_on_same_preview_and_audit_event(self):
        row=self.create();pid=str(row['id']);sid=str(row['session_id'])
        options=api.email_options(consent())
        for _ in range(2):store.request_email(pid,sid,'collector@example.com',options)
        saved=self.read(pid)
        for key in ('archive_sha256','dropbox_path','version'):self.assertEqual(saved[key],row[key])
        self.assertEqual(saved['marketing_consent_text'],api.CONSENT_TEXT)
        self.assertEqual(saved['marketing_consent_version'],api.CONSENT_VERSION)
        self.assertIsNotNone(saved['marketing_consent_at'])
        self.assertEqual(store.timeline(pid)[-1]['metadata']['marketing_consent_text'],api.CONSENT_TEXT)
        with self.Adapter() as cur:
            cur.execute("SELECT count(*) n FROM public.wall_preview_email_jobs WHERE kind='requested'")
            self.assertEqual(cur.fetchone()['n'],1)

    def test_confirmation_market_is_preserved_on_old_email_only_request_and_retry(self):
        self.data.update(market_country_code='NZ',market_country_name='New Zealand')
        row=self.create();pid=str(row['id'])
        store.request_email(pid,str(row['session_id']),'collector@example.com')
        self.assertEqual(self.read(pid)['market_country_code'],'NZ')
        self.data['market_country_code']='AU'
        retried,duplicate=store.confirm(self.data,self.upload)
        self.assertTrue(duplicate);self.assertEqual(retried['market_country_code'],'NZ')
        self.upload.assert_called_once()

    def defer(self):
        self.data['archive_image']=v2.jpeg()
        self.upload.return_value.update(pending_archive=True,file_id='')
        return self.create()

    def test_archive_retry_same_image_private_fallback_and_cleanup_on_success(self):
        row=self.defer();pid=str(row['id'])
        self.assertEqual(store.pending_archive_image(pid),v2.jpeg())
        retried,duplicate=store.confirm(self.data,self.upload)
        self.assertTrue(duplicate);self.assertEqual(retried['id'],row['id']);self.upload.assert_called_once()
        with patch.object(api.archive,'_dropbox_connection',return_value=('token','/Sportscave Team Folder')),patch.object(api.archive.dropbox_integration,'ensure_folder_path'),patch.object(api.archive.dropbox_integration,'upload_stream',return_value={'id':'id:archived'}) as upload:
            self.assertTrue(archive_worker.tick());self.assertFalse(archive_worker.tick())
            self.assertEqual(upload.call_args.args[1],row['dropbox_path'])
            self.assertEqual(upload.call_args.kwargs['conflict'],'replace')
        self.assertIsNone(store.pending_archive_image(pid));self.assertEqual(self.read(pid)['dropbox_file_id'],'id:archived')

    def test_archive_outage_retries_bounded_and_retains_canonical_hd_image(self):
        row=self.defer();pid=str(row['id'])
        with patch.object(api.archive,'_dropbox_connection',side_effect=RuntimeError('unavailable')):
            for _ in range(5):
                with self.Adapter() as cur:cur.execute('UPDATE public.wall_preview_archive_jobs SET due_at=now()')
                self.assertTrue(archive_worker.tick())
            self.assertFalse(archive_worker.tick())
        self.assertEqual(store.pending_archive_image(pid),v2.jpeg())
        with self.Adapter() as cur:
            cur.execute('SELECT state,attempts FROM public.wall_preview_archive_jobs')
            self.assertEqual(cur.fetchone(),{'state':'failed','attempts':5})

    def test_reconfirm_replaces_pending_version_and_never_replays_old_image(self):
        row=self.defer();pid=str(row['id'])
        self.data.update(image_sha256='b'*64,archive_image=v2.jpeg('blue'))
        newer,_=store.confirm(self.data,self.upload)
        self.assertEqual(newer['id'],row['id']);self.assertEqual(newer['version'],2)
        self.assertEqual(store.pending_archive_image(pid),v2.jpeg('blue'))

    def test_evidence_migration_replay_rls_and_no_public_archive_reads(self):
        row=self.create()
        with self.Adapter() as cur:
            for _ in range(2):
                for sql in Path('migrations/20261005051833_wall_preview_hd_send_evidence.sql').read_text().split(';'):
                    if sql.strip():cur.execute(sql)
            for role in ('anon','authenticated'):
                cur.execute("SELECT has_table_privilege(%s,'public.wall_preview_archive_jobs','SELECT') AS allowed",(role,))
                self.assertFalse(cur.fetchone()['allowed'])
            cur.execute("SELECT relrowsecurity FROM pg_class WHERE relname='wall_preview_archive_jobs'")
            self.assertTrue(cur.fetchone()['relrowsecurity'])
        self.assertEqual(self.read(str(row['id']))['archive_sha256'],row['archive_sha256'])


class HttpTests(v2.HttpTests):
    async def test_disclosed_send_payload_accepted_and_queued(self):
        import wall_preview_email
        with patch.object(wall_preview_email,'configured',return_value=True),patch.object(store,'request_email',return_value='queued') as queue:
            response=await self.client.post(f'/api/wall-previews/{self.pid}/email',
                headers={**self.headers,'X-Wall-Preview-Token':self.sid},json={'email':'collector@example.com',**consent()})
            self.assertEqual(response.status_code,200)
            self.assertEqual(queue.call_args.args[3]['marketing_consent_version'],api.CONSENT_VERSION)

    async def test_confirm_accepts_market_and_defers_dropbox_failure_without_retry_ui(self):
        params={k:v for k,v in v2.payload().items() if k in ('client_preview_id','session_id','product_id','variant_id','product_handle','product_title','product_url')}
        params.update(market_country_code='AU',market_country_name='Australia')
        def confirm(payload,upload):
            storage=upload({},self.pid)
            self.assertTrue(storage['pending_archive']);self.assertEqual(payload['market_country_code'],'AU')
            self.assertEqual(payload['market_country_name'],'Australia');self.assertIsInstance(payload['archive_image'],bytes)
            return {'id':self.pid,'version':1},False
        with patch.object(store,'confirm',side_effect=confirm),patch.object(api.archive,'_dropbox_connection',side_effect=RuntimeError('outage')):
            response=await self.client.post('/api/wall-previews',params=params,headers=self.headers,content=v2.jpeg())
            self.assertEqual(response.status_code,200);self.assertTrue(response.json()['ok'])
            self.assertNotIn('retry',response.text.lower())
