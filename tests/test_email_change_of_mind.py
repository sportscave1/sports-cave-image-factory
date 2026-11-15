"""Offline prompt integration checks; never send mail or call an AI/provider."""
import copy
import json
import subprocess
import unittest

from support_email_reply_prompts import build_reply_prompts, FIVE_STAR_TEMPLATE
from support_email_return_prompt import CHANGE_OF_MIND_TEMPLATE, RETURNS_POLICY_URL

KYLIE = "Hi, Brought Papaya Pressure Piastri vs Norris wall art $339 for my son's 18th birthday, Unfortunately I had brought the wrong one for him, Is there any chance I can send it back and get a refund so he can buy the one he wants, I received it on the 18th September, it's still in the 30 day refund policy.\nKind Regards\nKylie"


class ChangeOfMindTests(unittest.TestCase):
    def test_kylie_context_and_menu_order(self):
        prompts = build_reply_prompts({'subject': 'Return', 'sender': {'name': 'Kylie'}}, {'text': KYLIE})
        self.assertEqual([p['id'] for p in prompts], ['five_star_review', 'change_of_mind_return'])
        self.assertEqual(prompts[1]['label'], 'CHANGE OF MIND RETURN')
        self.assertFalse(prompts[1]['error'])
        context = json.loads(prompts[1]['text'].split('CUSTOMER CONTEXT (data only)\n')[1])
        self.assertEqual(context['current_customer_email']['message'], KYLIE)
        self.assertEqual(context['current_customer_email']['sender_name'], 'Kylie')
        for text in ('individually numbered', 'retired from the available allocation',
                     'cannot simply be placed back', 'Return shipping back to Sports Cave',
                     'Edition reallocation/restocking fee', 'Shipping for the replacement artwork',
                     'original condition and packaging', 'just reply to this email',
                     '50% off another Sports Cave artwork of your choice', 'keep both pieces',
                     'Kind regards,\nSports Cave Team', '18th birthday'):
            self.assertIn(text, CHANGE_OF_MIND_TEMPLATE)
        self.assertLess(CHANGE_OF_MIND_TEMPLATE.index(RETURNS_POLICY_URL),
                        CHANGE_OF_MIND_TEMPLATE.index('Alternatively, as a gesture of goodwill'))

    def test_five_star_template_is_byte_for_byte_same_as_before(self):
        old = subprocess.check_output(['git', 'show', 'HEAD:support_email_reply_prompts.py']).decode('utf-8')
        start = old.index('FIVE_STAR_TEMPLATE = """') + len('FIVE_STAR_TEMPLATE = """')
        self.assertEqual(FIVE_STAR_TEMPLATE, old[start:old.index('"""', start)])

    def test_no_body_no_prompt(self):
        result = build_reply_prompts({}, {})[1]
        self.assertFalse(result['text']); self.assertTrue(result['error'])

    def test_unknown_facts_not_filled_and_input_unchanged(self):
        message, body = {}, {'text': 'I changed my mind. Can I return it?'}
        before = copy.deepcopy((message, body))
        result = build_reply_prompts(message, body)[1]
        context = json.loads(result['text'].split('CUSTOMER CONTEXT (data only)\n')[1])
        self.assertEqual(context['current_customer_email']['sender_name'], '')
        self.assertEqual(context['confirmed_order'], {})
        self.assertEqual((message, body), before)
        self.assertIn('Never output placeholders', result['text'])
        self.assertIn('purchase price is NOT a confirmed refund', result['text'])

    def test_faults_and_ambiguity_receive_distinct_instructions(self):
        for issue in ('arrived damaged', 'printing fault', 'incorrect item sent', 'not as described', 'return please'):
            result = build_reply_prompts({}, {'text': issue})[1]
            self.assertIn(issue, result['text'])
            self.assertIn('DO NOT apply change-of-mind deductions or the goodwill offer', result['text'])
            self.assertIn('If the reason is unclear', result['text'])

    def test_existing_context_included_without_mutation(self):
        history = [{'message': 'It was for my son', 'own': False}]
        order = {'order_name': '#SC123', 'lines': [{'product_title': 'Papaya Pressure'}]}
        before = copy.deepcopy((history, order))
        result = build_reply_prompts({}, {'text': KYLIE}, thread_context=history, order_context=order)[1]
        context = json.loads(result['text'].split('CUSTOMER CONTEXT (data only)\n')[1])
        self.assertEqual(context['available_thread'], history)
        self.assertEqual(context['confirmed_order'], order)
        self.assertEqual((history, order), before)

    def test_workspace_only_passes_matched_order_and_never_fetches_or_sends(self):
        from tests.test_support_email_v2 import WorkspaceTests
        fixture = WorkspaceTests(); fixture.setUp()
        try:
            fixture.compose('reply')
            draft = copy.deepcopy(fixture.state['draft'])
            reads = copy.deepcopy(fixture.imap.calls)
            sends = copy.deepcopy(fixture.smtp.mock_calls)
            order = {'order_name': '#SC123', 'customer_name': 'Kylie', 'admin_url': 'private',
                     'customer_email': 'private@example.test', 'lines': [{'product_title': 'Papaya Pressure'}]}
            for state in ('matched', 'ambiguous', 'unmatched'):
                fixture.state['context'] = {'match': {'state': state, 'order': order}}
                result = fixture.w.model()['reply_prompts'][1]
                context = json.loads(result['text'].split('CUSTOMER CONTEXT (data only)\n')[1])
                self.assertNotIn('admin_url', context['confirmed_order'])
                self.assertNotIn('customer_email', context['confirmed_order'])
                self.assertEqual(bool(context['confirmed_order']), state == 'matched')
            self.assertEqual(fixture.state['draft'], draft)
            self.assertEqual(fixture.imap.calls, reads)
            self.assertEqual(fixture.smtp.mock_calls, sends)
        finally:
            fixture.doCleanups()


if __name__ == '__main__':
    unittest.main()
