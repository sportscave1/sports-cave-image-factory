"""Loading feedback and rapid-refresh invalidation; fake mailbox only."""
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import Mock, patch
import unittest
from tests import test_support_email_v2 as existing


class RefreshIdentityTests(unittest.TestCase):
    setUp=existing.WorkspaceTests.setUp
    event=existing.WorkspaceTests.event

    def test_same_clock_tick_still_refreshes_membership_and_invalidates_history(self):
        import support_email_logic
        fixed=datetime(2026,9,28,tzinfo=timezone.utc)
        with patch.object(support_email_logic,'datetime') as clock:
            clock.now.return_value=fixed
            self.event('refresh')
            version=self.state['mailbox_version']
            removed=self.state['threads'][0]['messages'][0]['uid']
            self.imap.messages=[m for m in self.imap.messages if m['uid']!=removed]
            self.event('refresh')
            self.assertGreater(self.state['mailbox_version'],version)
            self.assertFalse(any(m['uid']==removed for t in self.state['threads'] for m in t['messages']))
            self.assertEqual(self.w.model()['selected'],self.w.model()['threads'][0]['key'])


class LoadingFeedbackTests(unittest.TestCase):
    def test_initial_and_return_load_have_feedback_while_provider_is_pending(self):
        import support_email_page as page
        for loaded,label in ((False,'Loading inbox…'),(True,'Refreshing inbox…')):
            state={'support_email_scope':('fixture','fixture'),'support_email_workspace':{'loaded':loaded}}
            active=[];seen=[]
            @contextmanager
            def spinner(text):
                active.append(text)
                try:yield
                finally:active.pop()
            workspace=Mock()
            workspace.load.side_effect=lambda **kw:seen.append(list(active))
            with patch.object(page.st,'session_state',state),patch.object(page.st,'query_params',{}), \
                 patch.object(page.st,'spinner',side_effect=spinner),patch.object(page,'Workspace',return_value=workspace), \
                 patch.object(page,'load_configuration',return_value=Mock(scope='fixture')), \
                 patch.object(page,'load_smtp_configuration'),patch.object(page,'get_component',return_value=Mock(return_value=None)):
                page._render_workspace.__wrapped__({'id':'fixture'})
            if loaded:self.assertEqual(seen,[[label]])
            else:
                self.assertEqual(seen,[])
                self.assertTrue(state['support_email_workspace']['initial_load_pending'])
            self.assertFalse(active)


if __name__=='__main__':unittest.main()
