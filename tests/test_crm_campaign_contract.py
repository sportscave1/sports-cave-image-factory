from copy import deepcopy
import unittest
from crm_campaign_contract import capture,validate
from tests.test_crm_send_flow import CFG,LIVE


class ContractTests(unittest.TestCase):
    def test_failed_recovery_does_not_mistake_original_receipt_for_acceptance(self):
        from crm_campaign_reprepare import recovery_receipt
        editor={'recovery_operation':'old'}
        self.assertIsNone(recovery_receipt(editor,{'operation_id':'old','status':'FAILED'}))
        accepted={'operation_id':'new','status':'PREPARING'}
        self.assertIs(recovery_receipt(editor,accepted),accepted)
        self.assertIsNone(recovery_receipt(editor,None))
        self.assertIs(recovery_receipt({},accepted),accepted)
    def test_only_preview_url_may_differ(self):
        frozen=capture(CFG,LIVE)
        changed={**frozen,'test_unsubscribe_url':''}
        self.assertEqual(validate(frozen,changed),frozen)
        for key in ('business','contact','postal','font','logo','email_defaults'):
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'settings changed'):
                validate(frozen,{**frozen,key:'changed'})
    def test_sender_reply_to_renderer_and_json_normalization(self):
        frozen=capture(CFG,LIVE)
        for key in ('sender','reply_to','renderer'):
            changed=deepcopy(frozen);changed['_delivery'][key]='changed'
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'_delivery'):validate(frozen,changed)
        self.assertEqual(validate({**frozen,'social_links':[]},{**frozen,'social_links':()}),{**frozen,'social_links':[]})

    def test_completed_review_reused_after_old_30_second_cutoff(self):
        from crm_campaign_review import start_review
        from tests.test_crm_simple_editor import document
        from unittest.mock import patch,Mock
        import time
        editor={'id':'fixture','version':1,'name':'Fixture','document':document()}
        with patch('crm_campaign_review.review',return_value={'snapshot_id':'one'}) as reviewed:
            first=start_review(None,Mock(),Mock(),{},editor,deepcopy(editor),CFG)
            first.future.result(3);first.started=time.monotonic()-90;first.completed=time.monotonic()-60
            self.assertIs(start_review(first,None,None,{},editor,editor,CFG),first)
            reviewed.assert_called_once()
            first.completed=time.monotonic()-241
            second=start_review(first,None,None,{},editor,editor,CFG)
            second.future.result(3);self.assertIsNot(first,second)

    def test_preparation_loop_does_not_wait_for_lifecycle_maintenance(self):
        from crm_worker import preparation_run
        from unittest.mock import patch,Mock
        stop=Mock();stop.is_set.side_effect=[False,False,True]
        with patch('crm_worker._prepare_campaign',side_effect=[False,True]) as prepare, \
             patch('crm_lifecycle_sync.tick',side_effect=AssertionError('Maintenance must be independent')):
            preparation_run(Mock(),Mock(),stop)
        self.assertEqual(prepare.call_count,2)
        self.assertEqual([c.args[0] for c in stop.wait.call_args_list],[2,.2])
