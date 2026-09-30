import base64
import copy
import unittest
import uuid
from unittest.mock import patch
from support_email_render import sanitize_received_html, reader_document, referenced_cids
from support_email_provider import ImapProvider
from tests.test_support_email import FakeImap, CONFIG, header, PLAIN, HTML, ALTERNATIVE

class RendererTests(unittest.TestCase):
    def test_formatting_links_tables_images_and_security(self):
        value='<h2>Hello</h2><b><i>Mark James</i></b><p>Happy<br>Purchase</p><ul><li>One</li></ul><table width="600"><tr><td style="color:#123;font-size:16px;position:fixed;background:url(https://bad)">Cell</td></tr></table><a href="https://example.test/product">Product</a><img src="https://example.test/art.jpg" onerror="evil()"><script>evil()</script><iframe src="https://bad">bad</iframe><form action="https://bad"><input></form><a href="java&#x73;cript:evil()">bad link</a><svg onload="evil()"></svg>'
        result=sanitize_received_html(value)
        for expected in ('<b><i>Mark James</i></b>','<table width="600">','<ul><li>One</li></ul>','href="https://example.test/product"','src="https://example.test/art.jpg"','color:#123','referrerpolicy="no-referrer"'):
            self.assertIn(expected,result)
        for forbidden in ('script','onerror','onload','iframe','<form','<input','<svg','position:','url('):self.assertNotIn(forbidden,result)
        self.assertIn('max-width:100%!important;height:auto!important',reader_document(result))
    def test_cid_and_missing_and_malformed(self):
        value='<p><b>Hello<img src="cid:logo"><img src="cid:missing"><img src="data:image/svg+xml,bad">'
        result=sanitize_received_html(value,{'logo':'data:image/png;base64,aGVsbG8='})
        self.assertIn('data:image/png;base64,aGVsbG8=',result)
        self.assertNotIn('cid:',result);self.assertNotIn('svg+xml',result)
        self.assertIn('Image unavailable',result)
        self.assertEqual(referenced_cids(value),{'logo','missing'})
    def test_wholly_entity_encoded_html(self):
        self.assertEqual(sanitize_received_html('&lt;b&gt;Happy&lt;/b&gt;'),'<b>Happy</b>')
    def test_nested_mime_html_png_jpeg_and_unreferenced_attachment(self):
        for image_type in ('PNG','JPEG'):
            with self.subTest(image_type=image_type):
                image=f'("IMAGE" "{image_type}" NIL "<logo>" NIL "BASE64" 8 NIL ("INLINE" NIL))'.encode()
                pdf=b'("APPLICATION" "PDF" ("NAME" "proof.pdf") NIL NIL "BASE64" 8 NIL ("ATTACHMENT" ("FILENAME" "proof.pdf")))'
                structure=b'(( '+ALTERNATIVE+image+b' "RELATED" NIL NIL)'+pdf+b' "MIXED" NIL NIL)'
                wire=FakeImap(structure=structure)
                wire.parts={'1.1.1':b'Plain alternative','1.1.2':base64.b64encode(b'<b>Happy</b><img src="cid:logo">'),'1.2':base64.b64encode(b'image'),'2':base64.b64encode(b'pdf')}
                adapter=ImapProvider(CONFIG,connection_factory=lambda *a,**k:wire)
                body=adapter.read_message(header())
                self.assertIn('<b>Happy</b>',body['html']);self.assertEqual(body['text'],'Happy')
                self.assertTrue(body['inline_images']['logo'].startswith('data:image/'+image_type.lower()))
                self.assertEqual(body['attachments'][-1]['filename'],'proof.pdf')
                calls=str(wire.calls)
                self.assertNotIn('PEEK[2]',calls);self.assertNotIn('PEEK[1.1.1]',calls)
    def test_plain_is_never_assumed_html(self):
        wire=FakeImap(structure=PLAIN);wire.parts['1']=b'<b>Literal plain text</b>'
        body=ImapProvider(CONFIG,connection_factory=lambda *a,**k:wire).read_message(header())
        self.assertEqual(body['html'],'');self.assertEqual(body['text'],'<b>Literal plain text</b>')
    def test_deferred_body_no_read_mutation_and_cache(self):
        from tests.test_support_email_v2 import WorkspaceTests
        fixture=WorkspaceTests();fixture.setUp()
        try:
            fixture.w.bodies.clear();fixture.state.update(selected=None,conversation=[])
            fixture.imap.calls.clear();fixture.w.load(force=True,defer_body=True)
            self.assertFalse(any(c[0] in ('body','attachment','flag','move') for c in fixture.imap.calls))
            model=fixture.w.model();key=model['body_pending']
            fixture.w.handle({'id':str(uuid.uuid4()),'action':'load_visible_body','message_key':key})
            self.assertEqual(sum(c[0]=='body' for c in fixture.imap.calls),1)
            self.assertFalse(any(c[0] in ('attachment','flag','move') for c in fixture.imap.calls))
            fixture.w.model();fixture.w.model()
            self.assertEqual(sum(c[0]=='body' for c in fixture.imap.calls),1)
        finally:fixture.doCleanups()
    def test_inbox_and_sent_share_document_without_changing_plain_quote(self):
        from tests.test_support_email_v2 import WorkspaceTests
        fixture=WorkspaceTests();fixture.setUp()
        try:
            with patch.object(fixture.imap,'read_message',return_value={'text':'Hello','html':'<b>Hello</b>','attachments':[],'warnings':[]}):
                documents=[]
                for folder in ('INBOX','INBOX.Sent Items'):
                    message=copy.deepcopy(fixture.state['conversation'][0]);message['folder']=folder
                    fixture.w.bodies.clear();fixture.w._body(message)
                    content=fixture.w._content(message)
                    documents.append(content['reader_document']);self.assertIn('Hello',content['html'])
                self.assertEqual(documents[0],documents[1]);self.assertIn('<b>Hello</b>',documents[0])
        finally:fixture.doCleanups()

if __name__=='__main__':unittest.main()
