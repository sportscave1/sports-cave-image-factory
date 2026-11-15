"""Received mail privacy: no live mailbox, customer data, or transport."""
import unittest
import uuid
from copy import deepcopy
from unittest.mock import patch
from support_email_render import sanitize_received_html, reader_document


class Privacy(unittest.TestCase):
    def test_remote_image_is_inert_by_default(self):
        html = sanitize_received_html('<img src="https://tracker.test/open.gif" width="1" height="1">')
        self.assertNotIn(' src=', html)
        self.assertIn('data-sc-remote-src="https://tracker.test/open.gif"', html)
        self.assertIn("img-src data:;", reader_document(html))
        self.assertIn('img[data-sc-remote-src]{display:none!important}',reader_document(html))

    def test_approval_only_restores_sanitized_image_sources(self):
        html = sanitize_received_html('<img src="https://image.test/a" onerror="evil()"><script>evil()</script>')
        allowed = reader_document(html, allow_remote=True)
        self.assertIn('src="https://image.test/a"', allowed)
        self.assertIn("script-src 'none'", allowed)
        self.assertNotIn('evil()', allowed)

    def test_css_svg_srcset_and_active_resources(self):
        html = sanitize_received_html('''<link rel="stylesheet" href="https://bad.test/css">
        <style>@import 'https://bad.test/import';</style><svg><image href="https://bad.test/svg"/></svg>
        <div style="background-image:url(https://bad.test/bg);color:red">Text</div>
        <img src="https://safe.test/img" srcset="https://bad.test/2x 2x">
        <video poster="https://bad.test/poster"></video><iframe src="https://bad.test/frame"></iframe>''')
        for forbidden in ['bad.test','srcset=','url(','<svg','<iframe','<link','<style','<video']:
            self.assertNotIn(forbidden, html)
        self.assertIn('color:red', html)

    def test_srcset_only_uses_one_inert_https_fallback(self):
        html = sanitize_received_html('<img srcset="https://images.test/one 1x, https://images.test/two 2x">')
        self.assertIn('data-sc-remote-src="https://images.test/one"', html)
        self.assertNotIn('srcset=', html)

    def test_cid_only_from_safe_attachment_map(self):
        html = sanitize_received_html('<img src="cid:logo"><img src="data:image/svg+xml,bad">', {'logo':'data:image/png;base64,aGVsbG8='})
        self.assertIn('src="data:image/png;base64,aGVsbG8="', html)
        self.assertNotIn('svg+xml', html)

    def test_untrusted_marker_and_non_https_urls_cannot_be_promoted(self):
        for url in ['http://image.test/a','//image.test/a','javascript:alert(1)','file:///a','https://user:pw@image.test/a']:
            with self.subTest(url=url):
                html=sanitize_received_html(f'<img src="{url}" data-sc-remote-src="https://forged.test/a">')
                self.assertNotIn('data-sc-remote-src=', html)

class Consent(unittest.TestCase):
    def setUp(self):
        from tests.test_support_email_v2 import WorkspaceTests
        self.fixture=WorkspaceTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.w=self.fixture.w
        self.message=self.w._select_thread(self.fixture.state['threads'][0])
        self.body={'text':'Private message','html':'<img src="https://images.test/one">','attachments':[],'warnings':[]}
        with patch.object(self.fixture.imap,'read_message',return_value=self.body):self.w._body(self.message)

    def approve(self, identity=None):
        from support_email_workspace import reference_key
        self.w.handle({'id':str(uuid.uuid4()),'action':'show_images','message_key':reference_key(self.message),
                       'reader_identity':identity or self.w._reader_identity(self.message)})

    def test_explicit_exact_message_only_and_cache_remains_blocked(self):
        self.approve();row=next(m for m in self.w.model()['messages'] if m['expanded'])
        self.assertTrue(row['images_allowed'])
        self.assertIn('img-src data:;',row['reader_document'])
        self.assertIn('src="https://images.test/one"',row['approved_reader_document'])
        for field,value in [('uid','999'),('uidvalidity','new'),('message_id','<reused@test>'),('folder','Archive')]:
            altered=dict(self.message,**{field:value})
            self.assertNotIn(self.w._reader_identity(altered),self.w.state['image_grants'])

    def test_spoofed_identity_fails_closed(self):
        self.approve('wrong')
        self.assertFalse(self.w.state.get('image_grants'))

    def test_selection_resets_approval(self):
        self.approve()
        self.w.handle({'id':str(uuid.uuid4()),'action':'open_thread','thread_key':self.w.state['selected']})
        self.assertFalse(self.w.state['image_grants'])

    def test_actor_and_mailbox_and_session_isolation(self):
        from support_email_workspace import Workspace
        from dataclasses import replace
        old=self.w._reader_identity(self.message);self.approve()
        for user,cfg in [(dict(self.w.user,id='other'),self.w.config),
                         (self.w.user,replace(self.w.config,address='other@example.test'))]:
            other=Workspace(deepcopy(self.w.state),user,cfg,self.w.smtp_config,imap=self.fixture.imap)
            self.assertNotEqual(other._reader_identity(self.message),old)
            self.assertFalse(other.state['image_grants'])

    def test_revocation_clears_approval_and_rejects_action(self):
        self.approve()
        with patch('os_accounts.can_access_page',return_value=False):
            with self.assertRaises(PermissionError):self.approve()
        self.assertFalse(self.w.state['image_grants'])

    def test_logout_new_session_has_no_permission(self):
        from support_email_workspace import Workspace
        self.approve()
        fresh=Workspace({},self.w.user,self.w.config,self.w.smtp_config,imap=self.fixture.imap)
        self.assertFalse(fresh.state['image_grants'])
        self.assertNotEqual(fresh._reader_identity(self.message),self.w._reader_identity(self.message))

    def test_revoked_page_removes_stored_grants(self):
        import support_email_page as page
        self.approve()
        with patch.object(page.st,'session_state',{'support_email_workspace':self.w.state}), \
             patch.object(page.st,'info'),patch('os_accounts.can_access_page',return_value=False):
            page.render_page(self.w.user)
        self.assertFalse(self.w.state['image_grants'])

    def test_revoked_model_cannot_reenable_old_permission_on_regrant(self):
        self.approve()
        with patch('os_accounts.can_access_page',return_value=False):self.w.model()
        row=next(m for m in self.w.model()['messages'] if m['expanded'])
        self.assertFalse(row['images_allowed'])
        self.assertEqual(row['approved_reader_document'],'')

    def test_legacy_cached_document_resanitized_once(self):
        from support_email_render import RENDER_POLICY
        cached=self.w._content(self.message)
        cached.update(reader_document='<img src="https://old.test/track">',render_policy=0)
        self.assertIn('img-src data:;',self.w._content(self.message)['reader_document'])
        with patch('support_email_render.sanitize_received_html',side_effect=AssertionError('Repeated sanitization')):
            self.w.model();self.w.model()
        self.assertEqual(cached['render_policy'],RENDER_POLICY)

if __name__ == '__main__':unittest.main()
