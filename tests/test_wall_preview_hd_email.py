"""HD-request consent isolation. Provider boundaries are mocked; SQL is loopback only."""
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from pathlib import Path

import wall_preview_customer as customer
import wall_preview_crm_api as api
import wall_preview_crm_store as store
from tests import test_wall_preview_crm_v2 as v2


class CustomerTests(unittest.TestCase):
    def setUp(self):
        self.row = {'customer_email':'COLLECTOR@example.com','customer_name':'Nathan Baker',
                    'submitted_marketing_opt_in':False,'marketing_consent_at':datetime.now(timezone.utc)}
        self.existing = {'id':'gid://shopify/Customer/42','firstName':'Existing','lastName':'Name',
                         'defaultEmailAddress':{'emailAddress':'collector@example.com','marketingState':'SUBSCRIBED'}}
        self.records = [self.existing]
        self.calls = []
        def transport(document, variables, **kwargs):
            self.calls.append((document,variables))
            if document==customer.LOOKUP:
                return {'customers':{'nodes':self.records,'pageInfo':{'hasNextPage':False}}},'2026-04'
            field = {customer.CREATE:'customerCreate',customer.UPDATE:'customerUpdate',
                     customer.TAG:'tagsAdd',customer.CONSENT:'customerEmailMarketingConsentUpdate'}[document]
            if document==customer.CREATE:self.records=[self.existing]
            return {field:{'customer':self.existing,'userErrors':[]}},'2026-04'
        self.transport = transport

    def test_existing_customer_reused_names_and_tags_preserved_no_consent_write(self):
        self.assertEqual(customer.synchronize(self.row,self.transport),('gid://shopify/Customer/42','SUBSCRIBED'))
        self.assertEqual([d for d,_ in self.calls],[customer.LOOKUP,customer.TAG])
        self.assertEqual(self.calls[-1][1]['tags'],['Wall Preview'])

    def test_customer_create_retry_searches_before_create_and_creates_once(self):
        self.records=[]
        for _ in range(2):customer.synchronize(self.row,self.transport)
        creates=[v for d,v in self.calls if d==customer.CREATE]
        self.assertEqual(creates,[{'input':{'email':'collector@example.com','firstName':'Nathan','lastName':'Baker'}}])
        self.assertNotIn('emailMarketingConsent',creates[0]['input'])

    def test_only_explicit_true_subscribes_single_optin_with_audit_timestamp(self):
        self.row['submitted_marketing_opt_in']=True
        customer.synchronize(self.row,self.transport)
        consent=next(v['input']['emailMarketingConsent'] for d,v in self.calls if d==customer.CONSENT)
        self.assertEqual(consent,{'marketingState':'SUBSCRIBED','marketingOptInLevel':'SINGLE_OPT_IN',
                                  'consentUpdatedAt':self.row['marketing_consent_at'].isoformat()})

    def test_absent_consent_does_not_write_even_if_image_reuse_allowed(self):
        self.row.pop('submitted_marketing_opt_in');self.row['marketing_permission']=True
        customer.synchronize(self.row,self.transport)
        self.assertNotIn(customer.CONSENT,[d for d,_ in self.calls])

    def test_fill_missing_name_only(self):
        self.existing['lastName']=''
        customer.synchronize(self.row,self.transport)
        update=next(v['input'] for d,v in self.calls if d==customer.UPDATE)
        self.assertEqual(update,{'id':self.existing['id'],'lastName':'Baker'})

    def test_market_tag_preserves_tags_and_never_updates_customer_address(self):
        self.row.update(market_country_code='AU',market_country_name='Australia')
        customer.synchronize(self.row,self.transport)
        self.assertEqual(self.calls[-1],(customer.TAG,{'id':self.existing['id'],
                         'tags':['Wall Preview','Wall Preview Market: AU']}))
        for _,variables in self.calls:
            self.assertNotIn('address',str(variables).lower())

    def test_new_customer_market_signal_does_not_create_postal_address(self):
        self.records=[];self.row.update(market_country_code='NZ',market_country_name='New Zealand')
        customer.synchronize(self.row,self.transport)
        create=next(v['input'] for d,v in self.calls if d==customer.CREATE)
        self.assertEqual(set(create),{'email','firstName','lastName'})
        self.assertIn('Wall Preview Market: NZ',self.calls[-1][1]['tags'])

    def test_ambiguous_or_incomplete_lookup_never_creates(self):
        self.records.append(dict(self.existing,id='gid://shopify/Customer/43'))
        with self.assertRaises(ValueError):customer.synchronize(self.row,self.transport)
        self.assertEqual(len(self.calls),1)

    def test_provider_error_not_logged_as_payload(self):
        transport=Mock(return_value=({'tagsAdd':{'userErrors':[{'message':'private@example.com'}]}},None))
        with self.assertRaisesRegex(ValueError,'^shopify_customer_operation_rejected$'):
            customer.operation(customer.TAG,{},'tagsAdd',transport)

    def test_newer_unsubscribe_is_not_overwritten_by_retry(self):
        from datetime import timedelta
        self.row['submitted_marketing_opt_in']=True
        self.existing['defaultEmailAddress'].update(marketingState='UNSUBSCRIBED',
            marketingUpdatedAt=(self.row['marketing_consent_at']+timedelta(minutes=1)).isoformat())
        self.assertEqual(customer.synchronize(self.row,self.transport)[1],'UNSUBSCRIBED')
        self.assertNotIn(customer.CONSENT,[d for d,_ in self.calls])


class ContractTests(unittest.TestCase):
    def test_backward_compatible_unknown_permissions(self):
        options=api.email_options({'email':'collector@example.com'})
        self.assertIsNone(options['image_reuse_allowed']);self.assertIsNone(options['marketing_opt_in'])

    def test_flags_independent_name_normalized(self):
        options=api.email_options({'name':'  Nathan  Baker  ','image_reuse_allowed':True,'marketing_opt_in':False})
        self.assertEqual(options['name'],'Nathan Baker');self.assertTrue(options['image_reuse_allowed']);self.assertFalse(options['marketing_opt_in'])

    def test_country_normalization_and_old_payload_unknown_market(self):
        options=api.email_options({'market_country_code':' au ','market_country_name':' Australia '})
        self.assertEqual(options['market_country_code'],'AU');self.assertEqual(options['market_country_name'],'Australia')
        self.assertIsNone(api.email_options({})['market_country_code'])
        self.assertIsNone(api.email_options({})['market_country_name'])

    def test_invalid_country_fields_rejected(self):
        for fields in ({'market_country_code':'AUS'},{'market_country_code':1},{'market_country_code':'A1'},
                       {'market_country_name':['Australia']},{'market_country_name':'x'*101},
                       {'market_country_name':'Australia\nHeader'},{'market_country_name':''}):
            with self.subTest(fields=fields),self.assertRaises(ValueError):api.email_options(fields)

    def test_invalid_types_sources_name_and_product_rejected(self):
        for payload in ({'image_reuse_allowed':'true'},{'marketing_opt_in':1},{'name':'x\nheader'},
                        {'name':'x'*201},{'reuse_consent_source':'other'},{'product_url':'https://evil.example/products/a'}):
            with self.subTest(payload=payload),self.assertRaises(ValueError):api.email_options(payload)

    def test_email_asset_remains_capability_private_no_dropbox_share(self):
        import wall_preview_email
        row={'product_url':'https://sportscaveshop.com/products/a','share_token':'a'*43}
        message=wall_preview_email.message(row)
        self.assertIn('/wall-preview/'+'a'*43+'/image',message['html'])
        self.assertNotIn('dropbox',message['html']);self.assertNotIn('Unsubscribe',message['html'])

    def test_inbox_permission_and_subscription_badges_are_separate(self):
        from streamlit.testing.v1 import AppTest
        from tests.test_wall_preview_feature import INBOX_PAGE
        import wall_preview_inbox as inbox
        originals=(inbox.wall_preview_store.summary,inbox.wall_preview_store.list_previews,inbox._temporary_link)
        try:
            for reuse in (True,False,None):
                app=AppTest.from_string(INBOX_PAGE.replace('inbox.render(user)', "inbox._details(user,st.session_state['fixture-rows'][0])"))
                app.session_state['fixture-rows']=[{'id':'fixture','marketing_permission':reuse,
                    'market_country_code':'AU','market_country_name':'Australia',
                    'customer_name':'Collector','customer_email':'collector@example.com',
                    'email_marketing_state':'SUBSCRIBED' if reuse is False else 'UNKNOWN',
                    'email_requested_at':'2026-10-05T00:00:00Z','email_job_state':'queued'}]
                app.run();self.assertEqual(len(app.exception),0)
                markup='\n'.join(m.value for m in app.caption)
                self.assertIn('MARKETING USE: ALLOWED' if reuse else 'N/A',markup)
                self.assertEqual('EMAIL: SUBSCRIBED' in markup,reuse is False)
                self.assertIn('HD email · queued',markup)
                self.assertIn('MARKET: AUSTRALIA (AU)',markup)
        finally:
            inbox.wall_preview_store.summary,inbox.wall_preview_store.list_previews,inbox._temporary_link=originals


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable database required')
class HdDatabaseTests(unittest.TestCase):
    setUpClass=classmethod(v2.DatabaseTests.setUpClass.__func__)
    setUp=v2.DatabaseTests.setUp
    tearDown=v2.DatabaseTests.tearDown
    create=v2.DatabaseTests.create

    def read(self,pid):
        with self.Adapter() as cur:
            cur.execute('SELECT * FROM public.wall_previews WHERE id=%s',(pid,))
            return cur.fetchone()

    def test_request_updates_same_preview_independent_consents_idempotent_image_unchanged(self):
        row=self.create();pid=str(row['id'])
        options=api.email_options({'name':'Nathan Baker','image_reuse_allowed':True,'marketing_opt_in':False})
        for _ in range(2):self.assertEqual(store.request_email(pid,str(row['session_id']),'collector@example.com',options),'queued')
        saved=self.read(pid)
        for key in ('id','dropbox_path','archive_sha256','version'):self.assertEqual(saved[key],row[key])
        self.assertTrue(saved['marketing_permission']);self.assertFalse(saved['submitted_marketing_opt_in'])
        self.assertEqual(saved['customer_name'],'Nathan Baker');self.assertIsNotNone(saved['image_reuse_consent_at'])
        with self.Adapter() as cur:
            cur.execute('SELECT count(*) AS n FROM public.wall_preview_customer_jobs');self.assertEqual(cur.fetchone()['n'],1)
            cur.execute('SELECT count(*) AS n FROM public.wall_preview_email_jobs');self.assertEqual(cur.fetchone()['n'],3)
        captured=store.timeline(pid)[-1]['metadata']
        self.assertEqual(captured['email'],'collector@example.com');self.assertTrue(captured['image_reuse_allowed'])

    def test_duplicate_cannot_change_first_request_consent(self):
        row=self.create();pid=str(row['id']);sid=str(row['session_id'])
        store.request_email(pid,sid,'collector@example.com',api.email_options({'marketing_opt_in':False}))
        store.request_email(pid,sid,'collector@example.com',api.email_options({'marketing_opt_in':True,'image_reuse_allowed':True}))
        saved=self.read(pid);self.assertFalse(saved['submitted_marketing_opt_in']);self.assertFalse(saved['marketing_permission'])

    def test_market_persisted_once_event_audit_and_reconfirm_preserves_original_signal(self):
        row=self.create();pid=str(row['id']);sid=str(row['session_id'])
        options=api.email_options({'market_country_code':'AU','market_country_name':'Australia','marketing_opt_in':True})
        store.request_email(pid,sid,'collector@example.com',options)
        store.request_email(pid,sid,'collector@example.com',api.email_options({'market_country_code':'US','market_country_name':'United States'}))
        saved=self.read(pid)
        self.assertEqual((saved['market_country_code'],saved['market_country_name']),('AU','Australia'))
        self.assertEqual(store.timeline(pid)[-1]['metadata']['market_country_code'],'AU')
        self.data['image_sha256']='b'*64
        updated,_=store.confirm(self.data,self.upload)
        self.assertEqual(updated['market_country_code'],'AU')

    def test_old_request_unknown_reuse_and_marketing(self):
        row=self.create();pid=str(row['id'])
        store.request_email(pid,str(row['session_id']),'collector@example.com')
        saved=self.read(pid);self.assertFalse(saved['marketing_permission']);self.assertIsNone(saved['submitted_marketing_opt_in'])
        self.assertIsNone(saved['image_reuse_consent_at'])

    def test_reconfirm_never_reuses_old_image_permission(self):
        row=self.create();pid=str(row['id'])
        store.request_email(pid,str(row['session_id']),'collector@example.com',api.email_options({'image_reuse_allowed':True}))
        self.data['image_sha256']='b'*64
        changed,_=store.confirm(self.data,self.upload)
        self.assertFalse(changed['marketing_permission']);self.assertIsNone(changed['image_reuse_consent_at'])
        self.assertEqual(changed['id'],row['id'])

    def test_reuse_filter_email_state_and_identity_cannot_bypass_authorization(self):
        row=self.create();pid=str(row['id'])
        with self.assertRaises(PermissionError):store.request_email(pid,'untrusted','collector@example.com')
        store.request_email(pid,str(row['session_id']),'collector@example.com',api.email_options({'image_reuse_allowed':True}))
        result=store.legacy.list_previews(status='all',intent='reuse_allowed',include_private=True)
        self.assertEqual(len(result),1);self.assertEqual(result[0]['email_job_state'],'queued')

    def test_customer_worker_retries_independently_email_stays_queued(self):
        row=self.create();pid=str(row['id']);store.request_email(pid,str(row['session_id']),'collector@example.com')
        with patch.object(customer,'synchronize',side_effect=RuntimeError('never log payload')):self.assertTrue(customer.tick())
        with self.Adapter() as cur:
            cur.execute('SELECT state,attempts FROM public.wall_preview_customer_jobs');self.assertEqual(cur.fetchone(),{'state':'queued','attempts':1})
            cur.execute("UPDATE public.wall_preview_customer_jobs SET due_at=now()")
        with patch.object(customer,'synchronize',return_value=('gid://shopify/Customer/42','SUBSCRIBED')):customer.tick()
        self.assertEqual(self.read(pid)['email_marketing_state'],'SUBSCRIBED')
        with self.Adapter() as cur:
            cur.execute("SELECT state FROM public.wall_preview_email_jobs WHERE kind='requested'");self.assertEqual(cur.fetchone()['state'],'queued')
        self.assertEqual(store.timeline(pid)[-1]['metadata']['shopify_customer_id'],'gid://shopify/Customer/42')

    def test_migration_replay_rls_counts_and_private_customer_queue(self):
        with self.Adapter() as cur:
            sql=Path('migrations/20261005183000_wall_preview_hd_consent.sql').read_text()
            for _ in range(2):
                for statement in sql.split(';'):
                    if statement.strip():cur.execute(statement)
            cur.execute("SELECT count(*) AS n FROM information_schema.columns WHERE table_name='wall_previews'")
            self.assertEqual(cur.fetchone()['n'],55)
            cur.execute("SELECT has_table_privilege('anon','public.wall_preview_customer_jobs','SELECT') AS allowed")
            self.assertFalse(cur.fetchone()['allowed'])

    def test_market_migration_replay_preserves_previews_indexes_and_rls(self):
        row=self.create()
        with self.Adapter() as cur:
            cur.execute("SELECT indexname FROM pg_indexes WHERE tablename='wall_previews'")
            before=cur.fetchall()
            sql=Path('migrations/20261005194500_wall_preview_market_country.sql').read_text()
            for _ in range(2):
                for statement in sql.split(';'):
                    if statement.strip():cur.execute(statement)
            cur.execute("SELECT indexname FROM pg_indexes WHERE tablename='wall_previews'")
            self.assertEqual(cur.fetchall(),before)
            cur.execute("SELECT relrowsecurity FROM pg_class WHERE relname='wall_previews'")
            self.assertTrue(cur.fetchone()['relrowsecurity'])
        self.assertEqual(self.read(str(row['id']))['archive_sha256'],row['archive_sha256'])


class ApiTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=v2.HttpTests.asyncSetUp
    asyncTearDown=v2.HttpTests.asyncTearDown

    async def test_new_payload_queues_only_no_inline_shopify_and_no_subscription_claim(self):
        import wall_preview_email
        headers={**self.headers,'X-Wall-Preview-Token':self.sid}
        with patch.object(wall_preview_email,'configured',return_value=True),patch.object(store,'request_email',return_value='queued') as enqueue,patch.object(customer,'synchronize') as sync:
            result=await self.client.post(f'/api/wall-previews/{self.pid}/email',headers=headers,
                json={'email':' COLLECTOR@example.com ','name':'Nathan Baker','image_reuse_allowed':True,
                      'marketing_opt_in':True,'reuse_consent_source':'wall_preview_hd_email',
                      'market_country_code':'AU','market_country_name':'Australia'})
            self.assertEqual(result.status_code,200);self.assertFalse(result.json()['marketing_subscribed'])
            self.assertEqual(enqueue.call_args.args[2],'collector@example.com');sync.assert_not_called()
            self.assertEqual(enqueue.call_args.args[3]['market_country_code'],'AU')

    async def test_invalid_consent_is_rejected_before_enqueue(self):
        with patch.object(store,'request_email') as enqueue:
            result=await self.client.post(f'/api/wall-previews/{self.pid}/email',headers=self.headers,
                json={'email':'collector@example.com','marketing_opt_in':'false'})
            self.assertEqual(result.status_code,400);enqueue.assert_not_called()



if __name__=='__main__':unittest.main()
