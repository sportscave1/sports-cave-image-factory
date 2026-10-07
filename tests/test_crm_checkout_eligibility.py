from copy import deepcopy
from datetime import timedelta
import os
import unittest
from crm_logic import now, eligibility
from crm_checkout_eligibility import recovery_eligibility, POLICY_KEY


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.at=now()
        self.customer={'id':'gid://shopify/Customer/1','email':'fixture@example.test',
                       'emailMarketingConsent':{'marketingState':'NOT_SUBSCRIBED'}}
        self.checkout={'id':'gid://shopify/AbandonedCheckout/1','createdAt':self.at.isoformat(),
                       'customer':deepcopy(self.customer),'shippingAddress':{'countryCodeV2':'AU'},
                       'abandonedCheckoutUrl':'https://fixture.myshopify.com/checkouts/test/recover',
                       'lineItems':{'nodes':[{'variant':{'id':'v','availableForSale':True,
                           'product':{'status':'ACTIVE','onlineStoreUrl':'https://example.test/p'}}}]}}
        self.rules={'regions':{'*':{'mode':'explicit_or_valid_inferred',
                    'inferred_basis':'checkout_contact','effective_at':(self.at-timedelta(seconds=1)).isoformat()}}}

    def decision(self, **kwargs):
        return recovery_eligibility(self.checkout,self.customer,self.rules,**kwargs)

    def test_unsubscribed_newsletter_is_not_required(self):
        self.assertEqual(self.decision(),(True,''))
        self.assertFalse(eligibility(self.customer)[0])

    def test_all_configured_countries(self):
        for country in ('AU','US','GB','NZ','CA','DE','JP','BR'):
            self.checkout['shippingAddress']['countryCodeV2']=country
            self.assertTrue(self.decision()[0])

    def test_explicit_region_override(self):
        self.rules['regions']['AU']={'mode':'explicit_only'}
        self.assertEqual(self.decision(),(False,'region_requires_consent'))

    def test_unconfigured_defaults_explicit(self):
        self.assertEqual(recovery_eligibility(self.checkout,self.customer), (False,'region_requires_consent'))

    def test_explicit_opt_out_vetoes_conflicting_subscription(self):
        self.customer['emailMarketingConsent']['marketingState']='UNSUBSCRIBED'
        self.customer['defaultEmailAddress']={'marketingState':'SUBSCRIBED'}
        self.assertEqual(self.decision(),(False,'recovery_opted_out'))

    def test_suppressions_veto(self):
        for option in ('suppressed','provider_suppressed'):
            self.assertFalse(self.decision(**{option:True})[0])

    def test_historical_never_newly_enrolled(self):
        self.checkout['createdAt']=(self.at-timedelta(days=2)).isoformat()
        self.assertEqual(self.decision(),(False,'historical_not_enrolled'))

    def test_recovered_never_eligible(self):
        self.checkout['completedAt']=self.at.isoformat()
        self.assertEqual(self.decision(),(False,'recovered'))

    def test_contact_is_not_arbitrary_profile(self):
        self.checkout['customer']['email']='someoneelse@example.test'
        self.assertEqual(self.decision(),(False,'recovery_evidence_required'))

    def test_missing_email(self):
        self.customer['email']=''
        self.assertEqual(self.decision(),(False,'missing_email'))

    def test_missing_basis_or_cutoff_is_held(self):
        for key in ('effective_at','inferred_basis'):
            rules=deepcopy(self.rules);del rules['regions']['*'][key]
            self.assertFalse(recovery_eligibility(self.checkout,self.customer,rules)[0])

    def test_unavailable_product_or_deleted_variant(self):
        self.checkout['lineItems']['nodes'][0]['variant']['availableForSale']=False
        self.assertEqual(self.decision(),(False,'products_unavailable'))
        self.checkout['lineItems']['nodes'][0]['variant']=None
        self.assertFalse(self.decision()[0])

    def test_unrecoverable_or_partial_checkout(self):
        self.checkout['lineItems']['pageInfo']={'hasNextPage':True}
        self.assertFalse(self.decision()[0])
        self.checkout['lineItems']['pageInfo']={}
        self.checkout['abandonedCheckoutUrl']=''
        self.assertFalse(self.decision()[0])

    def test_platform_mode_needs_real_authority(self):
        self.rules['regions']['*']['mode']='platform_eligible'
        self.assertEqual(self.decision(),(False,'platform_eligibility_unavailable'))

    def test_native_unsubscribe_not_gated_by_newsletter_for_recovery(self):
        from crm_native_unsubscribe import native_unsubscribe_url
        self.customer['defaultEmailAddress']={'emailAddress':self.customer['email'],'validFormat':True,
             'marketingState':'NOT_SUBSCRIBED','marketingUnsubscribeUrl':'https://example.test/unsubscribe'}
        self.assertEqual(native_unsubscribe_url(self.customer),'')
        self.assertTrue(native_unsubscribe_url(self.customer,recovery=True))

    def test_policy_configuration_is_authorized_and_cannot_backdate(self):
        from unittest.mock import Mock
        from crm_checkout_eligibility import configure_regions
        from tests.test_crm import ADMIN
        store=Mock();store.state.return_value={}
        with self.assertRaises(ValueError):
            configure_regions(store,ADMIN,{'*':{'mode':'explicit_or_valid_inferred','effective_at':'2020-01-01'}})
        store.set_state.assert_not_called()
        result=configure_regions(store,ADMIN,{'*':{'mode':'explicit_or_valid_inferred','inferred_basis':'checkout_contact'}})
        from crm_logic import date
        self.assertGreaterEqual(date(result['regions']['*']['effective_at']),self.at)


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable SQL required')
class WorkerTests(unittest.TestCase):
    from tests.test_crm_automation_analytics import AnalyticsTests
    setUp=AnalyticsTests.setUp
    prepared=AnalyticsTests.prepared
    published=AnalyticsTests.published
    event=AnalyticsTests.event

    def prepare(self):
        from crm_checkout_analytics import details
        a,c=self.prepared()
        self.customer['emailMarketingConsent']['marketingState']='NOT_SUBSCRIBED'
        c['customer']=deepcopy(self.customer)
        self.store.set_state(POLICY_KEY,{'regions':{'*':{'mode':'explicit_or_valid_inferred',
            'inferred_basis':'checkout_contact','effective_at':a['activated_at']}}})
        self.addCleanup(lambda:self.store.q('DELETE FROM crm_runtime_state WHERE key=%s',(POLICY_KEY,)))
        self.store.set_state('checkout-auto-start-v2',{'started_at':a['activated_at']})
        details(self.store,c)
        return a,c

    def test_new_checkout_background_enrollment_delay_send_and_no_duplicate(self):
        from crm_automation_runtime import reconcile,advance
        from crm_logic import date
        a,c=self.prepare();reconcile(self.engine,a)
        j=self.store.q('SELECT * FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],),True)
        self.assertIsNotNone(j)
        self.assertEqual(date(j['next_due_at']),date(c['updatedAt']))
        # Advance disposable clocks to due; the production queue owns scheduling.
        self.store.q("UPDATE crm_automation_enrollments SET next_due_at=now()-interval '1 second' WHERE id=%s",(j['id'],))
        advance(self.engine,j)
        self.store.q("UPDATE crm_marketing_sends SET due_at=now()-interval '1 second' WHERE enrollment_id=%s",(j['id'],))
        self.engine.send_one();self.engine.send_one()
        self.provider.send.assert_called_once()
        self.assertEqual(self.store.q('SELECT status FROM crm_marketing_sends WHERE enrollment_id=%s',(j['id'],),True)['status'],'ACCEPTED')

    def test_history_not_enrolled(self):
        from crm_automation_runtime import reconcile
        a,c=self.prepare()
        self.store.set_state(POLICY_KEY,{'regions':{'*':{'mode':'explicit_or_valid_inferred',
            'inferred_basis':'checkout_contact','effective_at':self.clock.isoformat()}}})
        reconcile(self.engine,a)
        self.assertFalse(self.store.q('SELECT id FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],)))
        self.provider.send.assert_not_called()

    def test_recovered_and_opt_out_rechecked_before_send(self):
        from crm_automation_runtime import reconcile
        a,c=self.prepare();reconcile(self.engine,a)
        j=self.store.q('SELECT * FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],),True)
        self.assertIsNotNone(j)
        self.customer['emailMarketingConsent']['marketingState']='UNSUBSCRIBED'
        self.assertEqual(self.engine.validate(self.customer['id'],j)[2],'recovery_opted_out')
        c['completedAt']=self.clock.isoformat()
        self.assertEqual(self.engine.validate(self.customer['id'],j)[2],'recovered')
        self.provider.send.assert_not_called()

    def test_delay_wait_and_enrollment_identity_survive_reconciliation(self):
        from crm_automation_runtime import reconcile,advance
        a,c=self.prepare();reconcile(self.engine,a)
        j=self.store.q('SELECT * FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],),True)
        j['next_due_at']=(self.clock+timedelta(hours=1)).isoformat()
        advance(self.engine,j)
        self.assertFalse(self.store.q('SELECT id FROM crm_marketing_sends WHERE enrollment_id=%s',(j['id'],)))
        reconcile(self.engine,a)
        self.assertEqual(self.store.q('SELECT count(*) n FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],),True)['n'],1)
        self.provider.send.assert_not_called()
