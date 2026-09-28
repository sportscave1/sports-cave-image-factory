"""Campaign V1 unit and isolated PostgreSQL tests; never real Shopify or Resend."""
from copy import deepcopy
import json
import os
import unittest
import uuid
from unittest.mock import Mock, patch
from crm_campaign_content import *
from crm_campaign_store import CampaignStore
from crm_eligibility import eligible
from crm_audience import count_page
from crm_logic import now
from tests.test_crm import ADMIN, WORKER
from tests.test_crm_resend_marketing import ENV, RECEIPT
from tests.crm_db_fixture import connect
from crm_shopify import Shopify
from tests.crm_fixtures import ShopifyFixture


def ready_document():
    doc=new_document()
    doc['content'].update(subject='A moment worth collecting',preheader='Discover the new collector piece',
                          headline='For the moments that stay with you',body='Explore the latest Sports Cave release.',
                          cta_label='Explore the collection',cta_url='https://www.sportscaveshop.com')
    doc['copy_reviewed']=True
    doc['counts']={'members':1,'eligible':1,'excluded':{},'complete':True,'checked_at':now().isoformat()}
    return doc


class PolicyTests(unittest.TestCase):
    def test_all_consent_states_and_purchase_not_consent(self):
        c={'email':' FAN@Example.test ', 'numberOfOrders':'25'}
        for state in ('SUBSCRIBED','NOT_SUBSCRIBED','PENDING','INVALID','UNSUBSCRIBED','REDACTED',None):
            c['emailMarketingConsent']={'marketingState':state}
            self.assertEqual(eligible(c)[0],state=='SUBSCRIBED')
        c['emailMarketingConsent']['marketingState']='SUBSCRIBED'
        self.assertFalse(eligible(c,True)[0]);self.assertFalse(eligible(c,False,True)[0])
        for email in ('bad','a..b@example.test','a@example.test,b@example.test'):
            c['email']=email;self.assertFalse(eligible(c)[0])

    def test_exclusion_totals_dedupe_and_consent_evidence(self):
        shop=Mock();store=Mock();store.suppressed.side_effect=lambda cid,h:cid=='5'
        nodes=[]
        for i,state in enumerate(('SUBSCRIBED','NOT_SUBSCRIBED','PENDING','UNSUBSCRIBED','INVALID','SUBSCRIBED','SUBSCRIBED')):
            nodes.append({'id':str(i),'email':('same' if i in (0,6) else str(i))+'@example.test','emailMarketingConsent':{'marketingState':state}})
        shop.members.return_value={'nodes':nodes,'pageInfo':{'hasNextPage':False}}
        result=count_page(shop,store,('Shopify',{'id':'segment'}))
        self.assertEqual(result['eligible'],1);self.assertEqual(result['members'],7)
        self.assertEqual(sum(result['excluded'].values()),6)
        self.assertEqual(result['excluded']['duplicate'],1);self.assertEqual(result['excluded']['local_suppression'],1)

    def test_footer_is_locked_escaped_and_no_fake_unsubscribe_url(self):
        doc=ready_document();doc['content']['body']='<script>removeFooter()</script>'
        mail=render_campaign(doc,settings(ENV))
        self.assertNotIn('<script>',mail['html']);self.assertIn('&lt;script&gt;',mail['html'])
        self.assertIn('because you subscribed',mail['html']);self.assertIn('Unsubscribe',mail['text'])
        self.assertNotIn('href="#',mail['html']);self.assertIn('production link not activated',mail['html'])
        self.assertIn('max-width:600px',mail['html']);self.assertIn('role="presentation"',mail['html'])
        self.assertNotIn('<form',mail['html'])
        doc['content']['footer']='Remove it'
        with self.assertRaises(ValueError):render_campaign(doc)

    def test_preflight_never_live_ready_even_with_all_config_and_master_true(self):
        env=dict(ENV,BUSINESS_POSTAL_ADDRESS='Public business address supplied for test only',CRM_BUSINESS_ADDRESS_VERIFIED='true',CRM_SENDING_DOMAIN_VERIFIED='true',CRM_MARKETING_ENABLED='true')
        p=preflight(ready_document(),env)
        self.assertTrue(p['test_ready']);self.assertFalse(p['live_ready'])
        self.assertTrue(p['live']['Business postal address configured and verified'])
        self.assertFalse(preflight(ready_document(),ENV)['live']['Business postal address configured and verified'])
        with self.assertRaisesRegex(RuntimeError,'DISABLED'):BroadcastDelivery().send()
        with self.assertRaises(RuntimeError):BroadcastDelivery().prepare()

    def test_alt_text_https_subject_and_review_preflight(self):
        for field,value in (('hero_url','https://example.test/art.jpg'),('cta_url','javascript:alert(1)'),('subject','RE: Fake reply')):
            doc=ready_document();doc['content'][field]=value
            self.assertFalse(preflight(doc,ENV)['test_ready'])
        doc=ready_document();doc['counts']['complete']=False;self.assertFalse(preflight(doc,ENV)['test_ready'])
        doc=ready_document();doc['counts']['checked_at']='2000-01-01T00:00:00Z';self.assertFalse(preflight(doc,ENV)['test_ready'])

    def test_prompt_uses_only_supplied_facts_and_copy_cannot_replace_footer(self):
        doc=ready_document();doc['product']={'title':'Known title','id':'gid://shopify/Product/1'}
        prompt=prompt_for(doc)
        self.assertIn('Known title',prompt);self.assertIn('Unknown facts must be omitted',prompt)
        self.assertNotIn('A$',prompt);self.assertNotIn('Only 10 left',prompt)
        self.assertIn('do not output HTML',prompt)
        for data in ({'footer':'fake'},{'cta_url':'https://evil.test'},{'subject':['not text']}):
            with self.assertRaises(ValueError):parse_copy(json.dumps(data))
        self.assertEqual(parse_copy('{"subject":"Known"}'),{'subject':'Known'})

    def test_membership_cannot_be_persisted(self):
        doc=ready_document();doc['counts']['emails']=['person@example.test']
        with self.assertRaises(ValueError):validate_document(doc)

    def test_complaint_thresholds(self):
        self.assertIn('Below',reputation(0,1000));self.assertIn('Above',reputation(1,1000));self.assertIn('Critical',reputation(3,1000))


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Requires isolated local PostgreSQL fixture.')
class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.store=CampaignStore(connect)
        self.row=self.store.save(ADMIN,'V1 '+str(uuid.uuid4())[:8],ready_document(),env=ENV)

    def test_draft_round_trip_conflict_version_history_and_no_queue(self):
        self.assertEqual(self.store.draft(self.row['id'])['document'],self.row['document'])
        doc=deepcopy(self.row['document']);doc['content']['body']='Changed'
        updated=self.store.save(ADMIN,self.row['name'],doc,self.row['id'],1,env=ENV)
        self.assertEqual(updated['version'],2)
        with self.assertRaisesRegex(ValueError,'changed elsewhere'):self.store.save(ADMIN,'Old',doc,self.row['id'],1,env=ENV)
        self.assertIn('content_changed',[h['action'] for h in self.store.history(self.row['id'])])
        self.assertFalse(self.store.q('SELECT 1 FROM crm_marketing_sends WHERE campaign_id=%s',(self.row['id'],)))

    def test_permission_and_forbidden_live_states(self):
        with self.assertRaises(PermissionError):self.store.save(WORKER,'x',ready_document(),env=ENV)
        for status in ('READY FOR FUTURE LIVE SEND','SCHEDULED','SENT','ACTIVE'):
            with self.assertRaises(ValueError):self.store.save(ADMIN,'x',ready_document(),requested_status=status,env=ENV)

    def test_duplicate_archive_and_review_reset(self):
        copy=self.store.duplicate(ADMIN,self.row['id'])
        self.assertEqual(copy['status'],'DRAFT');self.assertEqual(copy['document']['counts'],{})
        self.assertFalse(copy['document']['copy_reviewed'])
        self.store.archive(ADMIN,copy['id'],1)
        self.assertEqual(self.store.draft(copy['id'])['status'],'ARCHIVED')
        self.assertIn('campaign_archived',[h['action'] for h in self.store.history(copy['id'])])

    def test_test_send_single_manual_recipient_only_and_safe_receipt(self):
        receipt=str(uuid.uuid4())
        setting=self.store.setting('sending')
        self.store.save_setting(ADMIN,'sending',{'internal_recipients':['manual@example.test'],'smart_hours':16},setting['version'])
        wire=Mock();wire.post.return_value=Mock(status_code=200,json=lambda:{'id':receipt})
        with patch('crm_resend_marketing._audit',return_value=True),patch('requests.sessions.Session.request',side_effect=AssertionError('Network forbidden')):
            for address in (['a@example.test'],{'segment':'1'},'a@example.test,b@example.test'):
                with self.assertRaises(RuntimeError):
                    self.store.test_campaign(ADMIN,self.row['id'],1,recipient=address,confirmed=True,operation_id=str(uuid.uuid4()),env=ENV,session=wire)
            wire.post.assert_not_called()
            result=self.store.test_campaign(ADMIN,self.row['id'],1,recipient='manual@example.test',confirmed=True,operation_id=str(uuid.uuid4()),env=ENV,session=wire)
        wire.post.assert_called_once();mail=wire.post.call_args.kwargs['json']
        self.assertEqual(mail['to'],['manual@example.test']);self.assertTrue(mail['subject'].startswith('[CAMPAIGN TEST]'))
        self.assertEqual(mail['tags'][0]['value'],'campaign_test')
        self.assertEqual(result['message_id'],receipt)
        row=self.store.draft(self.row['id']);self.assertEqual(row['status'],'TESTED');self.assertEqual(row['tested_version'],1)
        self.assertIn('campaign_test_sent',[h['action'] for h in self.store.history(row['id'])])
        self.store.save(ADMIN,row['name'],row['document'],row['id'],1,env=ENV)
        self.assertIsNone(self.store.draft(row['id'])['tested_version'])

    def test_all_suppression_reasons_are_persistent_and_not_cleared(self):
        for reason in ('manual_unsubscribe','provider_unsubscribe','hard_bounce','spam_complaint','invalid_address','admin_suppression'):
            hashed=str(uuid.uuid4());self.store.suppress(hashed,None,reason,'fixture')
            self.assertTrue(self.store.suppressed(None,hashed))
            self.store.save(ADMIN,'No clearing',new_document(),env=ENV)
            self.assertTrue(self.store.suppressed(None,hashed))


if __name__=='__main__':unittest.main()
