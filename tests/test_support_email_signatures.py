"""Branded signatures, role defaults, private CID MIME and managed draft roundtrips."""
from copy import deepcopy
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path
import json
import unittest
from unittest.mock import patch

import support_email_compose as compose
import support_email_signatures as brand
import support_email_store as store
from tests.email_v2_fixtures import USER, WORKER, MAILBOX
from tests.test_support_email import header
from tests import test_support_email_v2 as v2_tests


class SignatureTests(unittest.TestCase):
    def setUp(self):
        self.settings = compose.default_settings()

    def draft(self, signature="nathan", mode="new"):
        d = compose.new_draft(MAILBOX, signature=signature, mode=mode,
                              header=header() if mode != "new" else None, text="Prior customer message")
        d.update(to="customer@example.test", subject="Signature fixture", html="<p>Hi John,</p><p>Thanks for getting in touch.</p>")
        return d

    def mime(self, draft, **kwargs):
        raw = compose.build_mime(draft, MAILBOX, "Sports Cave", self.settings["signatures"], **kwargs)["bytes"]
        return BytesParser(policy=policy.default).parsebytes(raw)

    def test_explicit_user_requested_role_defaults_not_display_name_guesses(self):
        self.assertEqual(compose.selected_signature(self.settings, USER), "nathan")
        self.assertEqual(compose.selected_signature(self.settings, WORKER), "reina")
        self.assertEqual(compose.selected_signature(self.settings, {**USER, "display_name": "Another admin"}), "nathan")
        self.assertEqual(compose.selected_signature(self.settings, {**WORKER, "display_name": "Another staff member"}), "reina")
        for user in ({}, {"display_name": "Nathan"}, {**USER, "role": "unknown"}, {**WORKER, "is_active": False}):
            self.assertEqual(compose.selected_signature(self.settings, user), "company")

    def test_user_preferences_and_per_message_overrides(self):
        for key in compose.SIGNATURE_KEYS:
            self.assertEqual(compose.selected_signature(self.settings, WORKER, key), key)
        self.assertEqual(compose.selected_signature(self.settings, USER, "invalid"), "nathan")

    def test_reina_identity_unchanged_and_only_maria_customer_facing(self):
        before = deepcopy(WORKER)
        key = compose.selected_signature(self.settings, WORKER)
        self.assertEqual(self.settings['signatures'][key]['label'], 'Maria')
        msg = self.mime(self.draft(key))
        self.assertIn('Maria', msg.get_body(('html',)).get_content())
        self.assertNotIn('Reina', msg.get_body(('html',)).get_content())
        self.assertNotIn(WORKER['id'], msg.as_string())
        self.assertEqual(WORKER, before)

    def test_profiles_names_roles_links_table_and_no_social_resources(self):
        for key, name, role in [('nathan', 'Nathan Baker', 'Founder'), ('reina', 'Maria', 'Customer Support')]:
            html = self.settings['signatures'][key]['html']
            for value in (name, role, '<table', 'role="presentation"', 'max-width:520px', 'width="56"',
                          'mailto:hello@sportscaveshop.com', 'https://www.sportscaveshop.com',
                          '#AA8B49', brand.TAGLINE.upper()):
                self.assertIn(value, html)
            for forbidden in ('flex', 'grid', 'facebook', 'instagram', 'linkedin', 'twitter', 'file:', 'C:',
                              'static/', 'assets/', 'Founder &amp; Fan First', 'https://tracker'):
                self.assertNotIn(forbidden, html)

    def test_plain_fallback_exact_requested_text(self):
        for key, name, role in [('nathan', 'Nathan Baker', 'Founder'), ('reina', 'Maria', 'Customer Support')]:
            plain = self.mime(self.draft(key)).get_body(('plain',)).get_content()
            expected = f'Kind regards,\n\n{name}\n{role}\nSports Cave\nhello@sportscaveshop.com\nsportscaveshop.com\n\n{brand.TAGLINE}'
            self.assertIn(expected, plain.replace('\r\n', '\n'))
            self.assertNotIn('cid:', plain)
            self.assertNotIn('mailto:', plain)

    def test_alternative_related_cid_logo_matches_existing_official_asset(self):
        msg = self.mime(self.draft())
        self.assertEqual(msg.get_content_type(), 'multipart/alternative')
        self.assertEqual([p.get_content_type() for p in msg.iter_parts()], ['text/plain', 'multipart/related'])
        related = list(msg.iter_parts())[1]
        self.assertEqual([p.get_content_type() for p in related.iter_parts()], ['text/html', 'image/png'])
        logo = list(related.iter_parts())[1]
        self.assertEqual(logo['Content-ID'], '<'+brand.LOGO_CID+'>')
        self.assertEqual(logo.get_content_disposition(), 'inline')
        self.assertEqual(logo.get_payload(decode=True), brand.LOGO_PATH.read_bytes())
        self.assertIn('cid:'+brand.LOGO_CID, msg.get_body(('html',)).get_content())
        self.assertNotIn('data:image', msg.get_body(('html',)).get_content())

    def test_normal_file_attachments_remain_mixed_and_independent(self):
        d = self.draft(); compose.add_attachment(d, compose.make_attachment('proof.txt', b'proof'))
        msg = self.mime(d)
        self.assertEqual(msg.get_content_type(), 'multipart/mixed')
        files = [p for p in msg.walk() if p.get_content_disposition() == 'attachment']
        self.assertEqual([(p.get_filename(), p.get_payload(decode=True)) for p in files], [('proof.txt', b'proof')])
        self.assertEqual(len([p for p in msg.walk() if p.get('Content-ID')]), 1)

    def test_repeated_build_reruns_do_not_mutate_or_append_signature(self):
        d = self.draft('reina'); original = deepcopy(d)
        for _ in range(4):
            msg = self.mime(d)
            self.assertEqual(msg.get_body(('html',)).get_content().count('<!-- sc-signature:start -->'), 1)
            self.assertEqual(msg.get_body(('plain',)).get_content().count('Kind regards'), 1)
        self.assertEqual(d, original)

    def test_switching_signature_replaces_previous_profile(self):
        d = self.draft('reina'); self.mime(d)
        d['signature'] = 'company'; html = self.mime(d).get_body(('html',)).get_content()
        self.assertNotIn('Maria', html); self.assertEqual(html.count('Kind regards'), 1)
        d['signature'] = 'none'; msg = self.mime(d)
        self.assertNotIn('Kind regards', msg.get_body(('plain',)).get_content())
        self.assertFalse(any(p.get('Content-ID') for p in msg.walk()))

    def test_reply_reply_all_forward_signature_above_history(self):
        for mode in ('reply', 'reply_all', 'forward'):
            draft = self.draft('reina', mode); draft['include_quote'] = True
            msg = self.mime(draft)
            html = msg.get_body(('html',)).get_content()
            self.assertLess(html.index('Thanks for getting in touch'), html.index('Kind regards'))
            self.assertLess(html.index('Kind regards'), html.index('Prior customer message'))
            plain = msg.get_body(('plain',)).get_content()
            self.assertLess(plain.index('Maria'), plain.index('Prior customer message'))

    def test_managed_draft_repeated_roundtrip_and_switch_preserves_body_quote_and_files(self):
        d = self.draft('reina', 'reply_all'); d['include_quote'] = True; compose.add_attachment(d, compose.make_attachment('proof.txt', b'proof'))
        for _ in range(3):
            msg = self.mime(d, as_draft=True)
            d = compose.edit_mailbox_draft(msg.as_bytes(), MAILBOX, header())
            self.assertEqual(d['signature'], 'reina'); self.assertEqual(d['mode'], 'reply_all')
            self.assertNotIn('Kind regards', d['html']); self.assertNotIn('<table', d['html'])
            self.assertIn('Prior customer message', d['quote_html'])
            self.assertEqual(len(d['attachments']), 1)
        d['signature'] = 'nathan'; html = self.mime(d).get_body(('html',)).get_content()
        self.assertEqual(html.count('Kind regards'), 1); self.assertIn('Nathan Baker', html); self.assertNotIn('Maria', html)

    def test_forward_draft_restores_forward_mode(self):
        d = compose.edit_mailbox_draft(self.mime(self.draft('nathan','forward'),as_draft=True).as_bytes(),MAILBOX,header())
        self.assertEqual(d['mode'],'forward');self.assertEqual(d['signature'],'nathan')

    def test_legacy_os_draft_upgrades_reina_signature_without_duplication(self):
        old = EmailMessage();old['X-Sports-Cave-Draft-ID'] = 'fixture'
        old.set_content('<p>My response</p><p>Kind regards,<br><strong>Reina</strong><br>Customer Support · Sports Cave</p><blockquote><p>Old history</p></blockquote>', subtype='html')
        d=compose.edit_mailbox_draft(old.as_bytes(),MAILBOX,header())
        d.update(to='customer@example.test',subject='fixture')
        self.assertEqual(d['signature'],'reina');self.assertEqual(d['html'],'<p>My response</p>')
        html=self.mime(d).get_body(('html',)).get_content()
        self.assertIn('Maria',html);self.assertNotIn('Reina',html);self.assertEqual(html.count('Kind regards'),1)

    def test_external_draft_does_not_guess_or_append_signature(self):
        external=EmailMessage();external.set_content('<p>My custom sign-off</p>',subtype='html')
        d=compose.edit_mailbox_draft(external.as_bytes(),MAILBOX,header())
        self.assertEqual(d['signature'],'none');self.assertIn('My custom sign-off',d['html'])

    def test_signature_sanitizer_keeps_layout_but_blocks_tracking_and_scripts(self):
        malicious='<table onclick="bad()" style="position:fixed;background-image:url(https://tracker);font-size:12px"><tr><td>OK<script>secret</script><img src="https://tracker"><img src="file:///secret"><img src="cid:untrusted"><a href="javascript:bad()">bad</a></td></tr></table>'
        safe=compose.sanitize_signature(malicious)
        for forbidden in ('onclick','position','tracker','secret','file:','untrusted','javascript'):
            self.assertNotIn(forbidden,safe)
        self.assertIn('<table',safe);self.assertIn('font-size:12px',safe)
        self.assertNotIn('<table',compose.sanitize_html(malicious))

    def test_preview_has_local_data_image_and_storage_conversion_restores_cid(self):
        html=self.settings['signatures']['nathan']['html']
        preview=compose.signature_preview(html)
        self.assertIn('data:image/png;base64,',preview);self.assertNotIn(str(brand.LOGO_PATH),preview)
        self.assertEqual(compose.sanitize_signature(preview),html)

    def test_legacy_settings_upgrade_preserves_company_and_preferences(self):
        saved={'company':{'html':'<p>Custom company sign-off</p>'},'nathan':{'html':'<p>Nathan old</p>'},'reina':{'html':'<p>Reina old</p>'}}
        with patch.object(store,'cursor') as cursor:
            cur=cursor.return_value.__enter__.return_value
            cur.fetchone.side_effect=[{'signatures':saved,'sender_name':'Sports Cave','folder_mapping':{},'sent_policy':'verify'},{'signature_key':'reina'}]
            settings,pref=store.load_email_settings(MAILBOX,WORKER['id'])
        self.assertEqual(pref,'reina');self.assertEqual(settings['signatures']['reina']['label'],'Maria')
        self.assertIn('Nathan Baker',settings['signatures']['nathan']['html'])
        self.assertEqual(settings['signatures']['company']['html'],'<p>Custom company sign-off</p>')

    def test_signature_storage_has_metadata_and_cid_only_no_logo_binary_or_message(self):
        signatures=deepcopy(self.settings['signatures'])
        for value in signatures.values():value['html']=compose.signature_preview(value['html'])
        with patch.object(store,'cursor') as cursor, patch.object(store,'audit'):
            store.save_email_settings(MAILBOX,actor=USER,sender_name='Sports Cave',signatures=signatures,
                                      folder_mapping={},sent_policy='verify',discovered_names=set())
            args=cursor.return_value.__enter__.return_value.execute.call_args.args[1]
        saved=json.loads(args[2]);serialized=json.dumps(saved)
        for text in ('data:image',str(brand.LOGO_PATH),'Thanks for getting in touch',USER['id'],WORKER['id']):self.assertNotIn(text,serialized)
        self.assertIn('cid:'+brand.LOGO_CID,serialized);self.assertEqual(saved['reina']['display_name'],'Maria')
        self.assertEqual(saved['nathan']['logo_asset'],brand.LOGO_ASSET)

    def test_signature_source_asset_matches_app_branding(self):
        import app_branding
        self.assertEqual(brand.LOGO_PATH,app_branding.STATIC_ROOT/'branding'/'sports-cave-os-icon-192-v2.png')

    def test_reader_csp_allows_data_logo_and_https_images_without_active_content(self):
        html=(Path(__file__).resolve().parents[1]/'components/support_email/index.html').read_text()
        self.assertIn("img-src data: https:;",html)
        self.assertIn("style-src-attr 'unsafe-inline';",html)
        self.assertIn("script-src 'self';",html)
        self.assertIn("connect-src 'none';",html)
        self.assertNotIn('img-src *',html)


class WorkspaceSignatureTests(unittest.TestCase):
    setUp=v2_tests.WorkspaceTests.setUp
    event=v2_tests.WorkspaceTests.event
    open=v2_tests.WorkspaceTests.open

    def test_all_compose_modes_use_role_default_and_uuid_preference(self):
        for user, expected in ((USER,'nathan'),(WORKER,'reina')):
            self.w.user=user
            for mode in ('new','reply','reply_all','forward'):
                key=self.open()
                self.event('compose',mode=mode,message_key=key)
                self.assertEqual(self.state['draft']['signature'],expected)
            self.state['preference']='company';self.event('compose',mode='new')
            self.assertEqual(self.state['draft']['signature'],'company');self.state.pop('preference')

    def test_client_switch_and_rerun_keep_one_signature_separate_from_editable_body(self):
        self.w.user=WORKER;self.event('compose',mode='new')
        d=self.state['draft'];payload={**d,'html':'<p>Editable response</p>','signature':'company'}
        self.event('close_composer',draft=payload);self.event('resume_composer')
        for _ in range(3):
            model=self.w.model();self.assertEqual(model['draft']['signature'],'company')
            self.assertEqual(model['draft']['html'],'<p>Editable response</p>')
        self.assertIn('data:image/png;base64,',model['signature_logo'])
        self.assertNotIn('Reina',json.dumps(model['settings']['signatures']))


if __name__=='__main__':unittest.main()
