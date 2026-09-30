"""Offline extraction and UI-payload tests. No mailbox writes or AI calls."""
import copy
import unittest
from unittest.mock import patch
from support_email_reply_prompts import build_reply_prompts, extract_review, FIVE_STAR_TEMPLATE

SUBJECT="Mark James left a 5 star review for 'Six Laps Ahead Peter Brock Wall Art'"
MESSAGE={'subject':SUBJECT,'sender':{'name':'Judge.me','email':'support@judge.me'}}
BODY={'html':"<p><b><i>Mark James</i></b> left a 5 star review for 'Six Laps Ahead Peter Brock Wall Art'</p><p><b>Happy</b><br><i>I am more than happy with my purchase</i></p><p>Mark James is a verified buyer. Learn how reviews are verified.</p><p>Kind regards</p><p>Judge.me Team<br>support@judge.me</p><a href='https://admin.shopify.com/'>Manage review</a>"}

class ReplyPromptTests(unittest.TestCase):
    def test_acceptance_case(self):
        context=extract_review(MESSAGE,BODY)
        self.assertEqual(context,{'customer_first_name':'Mark','product_name':'Six Laps Ahead Peter Brock Wall Art','review_text':'Happy\nI am more than happy with my purchase'})
        result=build_reply_prompts(MESSAGE,BODY)[0]
        self.assertEqual(result['label'],'5-star review response')
        self.assertEqual(result['error'],'')
        self.assertIn('First name: Mark',result['text'])
        self.assertIn('PRODUCT\nSix Laps Ahead Peter Brock Wall Art',result['text'])
        self.assertIn('REVIEW RATING\n5/5',result['text'])
        self.assertIn('CUSTOMER REVIEW\nHappy\nI am more than happy with my purchase',result['text'])
        self.assertNotIn('<b>',result['text'])
        for value in ('support@','admin.shopify','verified buyer','Judge.me Team'):
            self.assertNotIn(value,result['text'])

    def test_quotes_names_and_star_spellings(self):
        for rating in ('5 star','5-star','5 stars'):
            for quote in ("'",'"','“'):
                message={**MESSAGE,'subject':f'Ana Maria left a {rating} review for {quote}A Different Product{quote}'}
                context=extract_review(message,{'text':'Wonderful\nExactly what I hoped for.\nKind regards,\nJudge.me Team'})
                self.assertEqual(context['customer_first_name'],'Ana')
                self.assertEqual(context['product_name'],'A Different Product')

    def test_structured_fields_precede_subject_and_body(self):
        message={**MESSAGE,'review':{'reviewer_name':'Sam Jones','product_name':'Limited Print','rating':5,'review_title':'Love it','review_text':'<b>Looks amazing</b>'}}
        self.assertEqual(extract_review(message,BODY),{'customer_first_name':'Sam','product_name':'Limited Print','review_text':'Love it\nLooks amazing'})

    def test_body_notification_and_normal_sender_fallback(self):
        self.assertEqual(extract_review({**MESSAGE,'subject':'New review'},BODY)['customer_first_name'],'Mark')
        for label in ('rating 5','Rating: 5/5','5 stars','5-star'):
            context=extract_review({'subject':'My purchase','sender':{'name':'Jo Smith'}},{'text':label+'\nReview: Looks fantastic'})
            self.assertEqual(context['customer_first_name'],'Jo')
            self.assertEqual(context['product_name'],'')
            self.assertEqual(context['review_text'],'Looks fantastic')

    def test_platform_sender_is_never_the_customer(self):
        context=extract_review({**MESSAGE,'subject':'New review'},{'text':'Rating 5\nReview: Very happy'})
        self.assertEqual(context['customer_first_name'],'Customer')

    def test_escaped_literal_html_uses_existing_safe_converter(self):
        context=extract_review(MESSAGE,{'html':'&lt;b&gt;Happy&lt;/b&gt;\n&lt;i&gt;I am more than happy with my purchase&lt;/i&gt;\n<script>secret()</script>'})
        self.assertEqual(context['review_text'],'Happy\nI am more than happy with my purchase')

    def test_non_five_unknown_conflicting_and_other_scale_fail_closed(self):
        for stars in ('1','2','3','4'):
            result=build_reply_prompts({**MESSAGE,'subject':SUBJECT.replace('5 star',stars+' star')},{'text':'Happy'})[0]
            self.assertEqual(result['text'],'')
            self.assertIn('could not be confirmed',result['error'])
        for message,body in [({'subject':'Love it','sender':{'name':'Jo'}},{'text':'So happy with this!'}),
            (MESSAGE,{'text':'Rating 4\nReview: Nice'}),
            ({**MESSAGE,'review':{'rating':5,'rating_scale':10}},BODY)]:
            self.assertTrue(build_reply_prompts(message,body)[0]['error'])

    def test_unknown_notification_wrapper_is_not_dumped(self):
        result=build_reply_prompts({**MESSAGE,'subject':'New review'},{'text':'Rating 5\nA new notification.\nVisit our dashboard.'})[0]
        self.assertEqual(result['text'],'')
        self.assertIn('review text could not be identified',result['error'])

    def test_explicit_subject_rating_with_normal_sender(self):
        for subject in ('5 star', '5-star', '5 stars', 'Rating 5'):
            result=build_reply_prompts({'subject':subject,'sender':{'name':'Alex Smith'}},{'text':'Love my artwork.'})[0]
            self.assertFalse(result['error'])
            self.assertIn('First name: Alex',result['text'])

    def test_instructions_discount_permission_no_invention_and_signoff(self):
        for requirement in ('thank-you specifically for sending the photo or video','15% off their next Sports Cave order',
          'Do not imply that the 15% discount was given in exchange for the positive review',
          'with their permission','Do not invent any facts','Do not mention Judge.me','Do not include a subject line',
          'Do not use bullet points or markdown','70–120 words','Thanks again,\nNathan\nSports Cave',
          'Return ONLY the finished customer email reply'):
            self.assertIn(requirement,FIVE_STAR_TEMPLATE)

    def test_input_dictionaries_are_unchanged(self):
        message,body=copy.deepcopy(MESSAGE),copy.deepcopy(BODY)
        build_reply_prompts(message,body)
        self.assertEqual(message,MESSAGE);self.assertEqual(body,BODY)

    def test_workspace_payload_preserves_draft_and_does_not_fetch_or_send(self):
        from tests.test_support_email_v2 import WorkspaceTests
        fixture=WorkspaceTests();fixture.setUp()
        try:
            fixture.compose('reply')
            original=copy.deepcopy(fixture.state['draft'])
            calls=copy.deepcopy(fixture.imap.calls)
            smtp_calls=copy.deepcopy(fixture.smtp.mock_calls)
            fixture.w.model()
            self.assertEqual(fixture.state['draft'],original)
            self.assertEqual(fixture.imap.calls,calls)
            self.assertEqual(fixture.smtp.mock_calls,smtp_calls)
            with patch('support_email_reply_prompts.build_reply_prompts',return_value=[{'id':'fixture'}]) as build:
                self.assertEqual(fixture.w.model()['reply_prompts'],[{'id':'fixture'}])
                build.assert_called_once()
            fixture.state['view']='mail'
            with patch('support_email_reply_prompts.build_reply_prompts') as build:
                self.assertEqual(fixture.w.model()['reply_prompts'],[]);build.assert_not_called()
        finally:fixture.doCleanups()

if __name__=='__main__':unittest.main()
