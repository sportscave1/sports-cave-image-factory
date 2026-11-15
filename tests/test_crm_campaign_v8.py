"""Fixed market time contracts and untouched-queue amendments; mocked I/O only."""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import os
import unittest
import uuid
from unittest.mock import patch
from crm_campaign_schedule import validate,due,plan,recipient_zone,change_pending,summary
from tests.test_crm_campaign_v2 import profile,authority

def timing(zone='Australia/Sydney',day='2026-10-10',hour='17:00'):
    return {'mode':'schedule','policy_version':2,'time_basis':'campaign_timezone','timezone':zone,'date':day,'time':hour}

def state(rows):
    from crm_logic import recipient_hash
    return {'recipients':[{'id':r['id'],'hash':recipient_hash(r['email'])} for r in rows],'profiles':{r['id']:r for r in rows}}

class ContractTests(unittest.TestCase):
    def test_incident_1085_fixed_instant_and_legacy_unchanged(self):
        rows=[profile(i,address={'countryCodeV2':'AU','provinceCode':'NSW','timeZone':'Australia/Darwin'}) for i in range(1041)]
        rows += [profile(i+1041,address={'countryCodeV2':'AU'}) for i in range(43)]
        rows += [profile(1084,address={'countryCodeV2':'AU','timeZone':'Europe/London'})]
        audience=state(rows);at=datetime(2026,10,10,5,tzinfo=timezone.utc)
        doc={'market':'AU','send_timing':timing()}
        result=plan(doc,audience,at)
        self.assertEqual(len(result),1085);self.assertEqual({j['due_at'] for j in result.values()},{'2026-10-10T06:00:00+00:00'})
        doc['send_timing']={'mode':'schedule','date':'2026-10-10','time':'17:00'}
        legacy=plan(doc,audience,at)
        # Unknown AU legacy fallback is Sydney; the supplied 43 UTC recipients
        # require missing/unrecognized country in the original frozen evidence.
        self.assertEqual(legacy[audience['recipients'][0]['hash']]['due_at'],'2026-10-10T07:30:00+00:00')
        doc['send_timing']={k:v for k,v in timing().items() if k!='timezone'};doc['send_timing']['time_basis']='recipient_local'
        with self.assertRaisesRegex(ValueError,'conflicting_recipient_timezone.*1042'):plan(doc,audience,at)
    def test_zone_offsets_and_cross_date(self):
        expected={'Australia/Sydney':'06:00','Australia/Melbourne':'06:00','Australia/Brisbane':'07:00','Australia/Darwin':'07:30','Australia/Perth':'09:00','Australia/Adelaide':'06:30','Pacific/Auckland':'04:00','Europe/London':'16:00','America/New_York':'21:00'}
        for zone,result in expected.items():
            with self.subTest(zone=zone):self.assertEqual(due(timing(zone),zone).strftime('%H:%M'),result)
        self.assertEqual(due(timing('Pacific/Auckland',hour='07:00'),'Pacific/Auckland').date().isoformat(),'2026-10-09')
        for zone,summer,winter in [('Europe/London',16,17),('America/New_York',21,22)]:
            self.assertEqual(due(timing(zone,'2026-07-01'),zone).hour,summer)
            self.assertEqual(due(timing(zone,'2026-12-01'),zone).hour,winter)
    def test_dst_rejects_gap_and_requires_explicit_fold(self):
        with self.assertRaisesRegex(ValueError,'does not exist'):due(timing('America/New_York','2026-03-08','02:30'),'America/New_York')
        t=timing('America/New_York','2026-11-01','01:30')
        with self.assertRaisesRegex(ValueError,'ambiguous'):due(t,'America/New_York')
        first=due({**t,'ambiguity':'earlier'},t['timezone']);second=due({**t,'ambiguity':'later'},t['timezone'])
        self.assertEqual(second-first,timedelta(hours=1))
    def test_geography_unknown_conflict_and_provenance(self):
        for address,code in [({},'unknown'),({'countryCodeV2':'AU','timeZone':'UTC'},'conflicting'),({'countryCodeV2':'AU','provinceCode':'NSW','timeZone':'Australia/Darwin'},'conflicting'),({'countryCodeV2':'AU','timeZone':'Australia/Darwin'},'unverified')]:
            with self.subTest(address=address),self.assertRaisesRegex(ValueError,code):recipient_zone({'defaultAddress':address})
        self.assertEqual(recipient_zone(profile(1,'AU','NT'))[0],'Australia/Darwin')
        with self.assertRaisesRegex(ValueError,'market_country_mismatch'):plan({'market':'AU','send_timing':timing()},state([profile(1,'GB','')]),datetime(2026,1,1,tzinfo=timezone.utc))
    def test_contract_rejects_invalid_zone_keys_and_past(self):
        for value in [timing('nonsense'),{**timing(),'policy_version':True},{**timing(),'date':'2026-1-1'},{**timing(),'time':'7:00'},{**timing(),'unexpected':1}]:
            with self.assertRaises(ValueError):validate(value)
        with self.assertRaisesRegex(ValueError,'reschedule'):plan({'market':'AU','send_timing':timing()},state([profile(1)]),datetime(2026,10,10,6,tzinfo=timezone.utc))
        self.assertIn('Sydney time (AEDT)',summary(timing()))
        validate({'mode':'now'})
    def test_market_choices_and_additional_dst_boundaries(self):
        from crm_campaign_schedule import ZONES
        from zoneinfo import ZoneInfo
        for market,zones in ZONES.items():
            for zone in zones:
                with self.subTest(market=market,zone=zone):
                    instant=due(timing(zone),zone)
                    self.assertEqual(instant.astimezone(ZoneInfo(zone)).strftime('%Y-%m-%d %H:%M'),'2026-10-10 17:00')
        for zone,day,hour in [('Australia/Sydney','2026-10-04','02:30'),('Australia/Adelaide','2026-10-04','02:30'),('Pacific/Auckland','2026-09-27','02:30'),('Europe/London','2026-03-29','01:30')]:
            with self.subTest(zone=zone),self.assertRaisesRegex(ValueError,'does not exist'):due(timing(zone,day,hour),zone)
        for zone,day,hour in [('Europe/London','2026-10-25','01:30'),('Australia/Sydney','2026-04-05','02:30'),('America/Toronto','2026-11-01','01:30')]:
            with self.subTest(zone=zone),self.assertRaisesRegex(ValueError,'ambiguous'):due(timing(zone,day,hour),zone)

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class DurableTests(unittest.TestCase):
    def setUp(self):
        from crm_campaign_store import CampaignStore
        from tests.crm_db_fixture import connect
        self.store=CampaignStore(connect)
        # Expose disposable fixture SQL diagnostics instead of sanitized live errors.
        self.store.db=connect
        self.ids=[]
        self.guard=patch('requests.sessions.Session.request',side_effect=AssertionError('No external delivery'));self.guard.start();self.addCleanup(self.guard.stop)
    def tearDown(self):
        for identity in self.ids:self.store.q("UPDATE crm_campaigns SET status='PAUSED' WHERE id=%s AND status='SENDING'",(identity,))
    def change(self,user,identity,t,op,**kwargs):
        prior=self.store.state('campaign-timing:'+str(identity)) or {}
        return change_pending(self.store,user,identity,t,op,expected_operation_id=prior.get('operation_id'),**kwargs)
    def queue(self,count=3):
        from tests.test_crm import ADMIN
        from tests.test_crm_simple_editor import document
        from tests.test_crm_send_flow import CFG,LIVE
        from crm_campaign_send import review,queue_campaign
        seed=uuid.uuid4().int%1000000000
        from crm_campaign_markets import audience
        doc=document();doc.update(market='AU',market_audience=True,audience=audience('AU'),send_timing=timing(day='2099-10-10'))
        rows=[profile(seed+i) for i in range(count)];shop=authority(rows)
        with patch.object(self.store,'render_settings',return_value=CFG):
            saved=self.store.save(ADMIN,'V8 fixture '+uuid.uuid4().hex,doc,env=LIVE)
            reviewed=review(shop,self.store,saved,LIVE)
            self.assertFalse(reviewed['blockers'])
            queue_campaign(shop,self.store,ADMIN,saved,str(uuid.uuid4()),env=LIVE,snapshot_id=reviewed['snapshot_id'])
        self.ids.append(saved['id'])
        return saved
    def test_fixed_queue_snapshot_progress_amendment_and_no_duplicate(self):
        from tests.test_crm import ADMIN
        from crm_campaign_progress import read_progress
        saved=self.queue(1085);identity=saved['id']
        rows=self.store.q('SELECT * FROM crm_marketing_sends WHERE campaign_id=%s',(identity,))
        self.assertEqual(len(rows),1085);self.assertEqual(len({r['due_at'] for r in rows}),1)
        before=self.store.template(rows[0]['template_id'],rows[0]['template_version'])
        op=str(uuid.uuid4());new=timing(day='2099-10-11')
        original_operation=self.store.state('campaign-timing:'+str(identity))['operation_id']
        receipt=self.change(ADMIN,identity,new,op,confirmed=True)
        self.assertEqual(change_pending(self.store,ADMIN,identity,new,op,confirmed=True),receipt)
        with self.assertRaisesRegex(ValueError,'changed elsewhere'):change_pending(self.store,ADMIN,identity,timing(day='2099-10-12'),str(uuid.uuid4()),confirmed=True,expected_operation_id=original_operation)
        after=self.store.q('SELECT * FROM crm_marketing_sends WHERE campaign_id=%s',(identity,))
        self.assertEqual({r['id'] for r in after},{r['id'] for r in rows})
        self.assertEqual(self.store.template(rows[0]['template_id'],rows[0]['template_version']),before)
        self.assertEqual(read_progress(self.store,[identity])[str(identity)]['timing'],new)
        self.assertEqual(self.store.draft(identity)['document'],saved['document'])
    def test_permission_confirmation_attempted_and_due_rejection(self):
        from tests.test_crm import ADMIN
        saved=self.queue();identity=saved['id'];op=str(uuid.uuid4())
        with self.assertRaises(PermissionError):change_pending(self.store,{'role':'worker','active':True},identity,timing(day='2099-10-11'),op,confirmed=True)
        with self.assertRaisesRegex(ValueError,'Explicit'):change_pending(self.store,ADMIN,identity,timing(day='2099-10-11'),op)
        self.store.q("UPDATE crm_marketing_sends SET status='CLAIMED' WHERE campaign_id=%s",(identity,))
        with self.assertRaisesRegex(ValueError,'locked'):self.change(ADMIN,identity,timing(day='2099-10-11'),op,confirmed=True)
        self.store.q("UPDATE crm_marketing_sends SET status='PENDING',due_at=now()-interval '1 minute' WHERE campaign_id=%s",(identity,))
        with self.assertRaisesRegex(ValueError,'already due'):self.change(ADMIN,identity,timing(day='2099-10-11'),op,confirmed=True)
    def test_send_now_preserves_ids_and_immutable_content(self):
        from tests.test_crm import ADMIN
        from tests.test_crm_send_flow import LIVE
        from crm_campaign_progress import read_progress
        saved=self.queue();identity=saved['id']
        rows=self.store.q('SELECT id FROM crm_marketing_sends WHERE campaign_id=%s',(identity,))
        with patch.dict(os.environ,LIVE):self.change(ADMIN,identity,{'mode':'now'},str(uuid.uuid4()),confirmed=True)
        progress=read_progress(self.store,[identity])[str(identity)]
        self.assertEqual(progress['status'],'SENDING');self.assertEqual(progress['timing'],{'mode':'now'})
        self.assertEqual(self.store.q('SELECT id FROM crm_marketing_sends WHERE campaign_id=%s',(identity,)),rows)
    def test_pending_jobs_never_dispatch_before_persisted_due(self):
        from crm_campaign_dispatch import dispatch
        from crm_engine import Engine
        from crm_resend import Config
        from tests.test_crm_send_flow import LIVE
        from unittest.mock import Mock
        saved=self.queue(1085)
        provider=Mock();engine=Engine(self.store,Mock(),provider,Config(LIVE))
        # Fresh worker and database connection, no browser state.
        self.assertFalse(dispatch(engine));provider.assert_not_called()
        provider.send.assert_not_called()
        self.assertEqual(self.store.q("SELECT count(*) n FROM crm_marketing_sends WHERE campaign_id=%s AND status='PENDING'",(saved['id'],),True)['n'],1085)
    def test_fixed_or_unverified_legacy_timezone_cannot_authorize_local_amendment(self):
        from tests.test_crm import ADMIN
        proposed={'mode':'schedule','policy_version':2,'time_basis':'recipient_local','date':'2099-10-11','time':'17:00'}
        saved=self.queue()
        with self.assertRaisesRegex(ValueError,'not validated'):self.change(ADMIN,saved['id'],proposed,str(uuid.uuid4()),confirmed=True)
        from tests.test_crm_campaign_v2 import profile as base_profile
        legacy={'mode':'schedule','date':'2099-10-10','time':'17:00'}
        with patch('tests.test_crm_campaign_v8.timing',return_value=legacy),patch('tests.test_crm_campaign_v8.profile',side_effect=lambda i:base_profile(i,address={'countryCodeV2':'AU','provinceCode':'NSW','timeZone':'Australia/Darwin'})):
            saved=self.queue()
        with self.assertRaisesRegex(ValueError,'not validated'):self.change(ADMIN,saved['id'],proposed,str(uuid.uuid4()),confirmed=True)
