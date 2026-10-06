import hashlib
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch,Mock
from PIL import Image
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient
import os_accounts
import sc_auth
import security_protection as protection
from protected_web_images import derivative,classify_public_image
from storefront_protection_api import ROUTES
from security_session_api import ROUTES as SESSION_ROUTES


class PolicyTests(unittest.TestCase):
    def test_masters_cannot_be_enabled_publicly(self):
        self.assertTrue(protection.clean_policy({'neverServePrintMasters':False})['neverServePrintMasters'])
    def test_unknown_fields_rejected(self):
        with self.assertRaises(ValueError):protection.clean_policy({'token':'secret'})
    def test_non_boolean_not_truthy_coerced(self):
        with self.assertRaises(ValueError):protection.clean_policy({'enabled':'false'})
    def test_bad_limits_rejected(self):
        for values in ({'maxImageEdge':9000},{'autoLockMinutes':1},{'maxImageEdge':True}):
            with self.subTest(values=values),self.assertRaises(ValueError):protection.clean_policy(values)
    def test_admin_refetched_not_client_claims(self):
        with patch.object(os_accounts.DEFAULT_STORE,'get_user',return_value={'role':'worker','is_active':True}):
            with self.assertRaises(PermissionError):protection.STORE.admin('id')
    def test_disabled_admin_rejected(self):
        with patch.object(os_accounts.DEFAULT_STORE,'get_user',return_value={'role':'admin','is_active':False}):
            with self.assertRaises(PermissionError):protection.STORE.admin('id')
    def test_session_keys_do_not_contain_token(self):
        self.assertEqual(64,len(protection.session_key('private.token')))
        self.assertNotIn('private',protection.session_key('private.token'))
    def test_missing_or_revoked_session_rejected(self):
        with patch.object(protection.STORE,'q',return_value=None):
            with self.assertRaises(PermissionError):protection.STORE.validate_session('x','user')
    def test_sensitive_reauth_required(self):
        with patch.object(protection.STORE,'validate_session',return_value={}),patch('security_protection.cached_policy',return_value=protection.DEFAULTS):
            with self.assertRaises(PermissionError):protection.STORE.require_reauth('user','sid')

    def test_native_transfer_rechecks_durable_session(self):
        import files_upload_api as files
        record=Mock(user_id='user',session_id='revoked')
        with patch.object(os_accounts.DEFAULT_STORE,'get_user',return_value={'id':'user','role':'admin','is_active':True}),patch.object(protection.STORE,'validate_session',side_effect=PermissionError('Revoked')):
            with self.assertRaises(PermissionError):files._validate_transfer_access(record)
    def test_production_signing_refuses_public_default(self):
        with patch.dict('os.environ',{'RENDER':'1'},clear=True):
            with self.assertRaises(RuntimeError):sc_auth.create_user_auth_token('user')
    def test_request_error_is_safe_access_denial(self):
        import files_upload_api as files
        response=files._response_error(PermissionError('Verify your password.'))
        self.assertEqual(403,response.status_code)


class PublicTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(Starlette(routes=[Route(path,fn,methods=list(methods)) for path,fn,methods in (*ROUTES,*SESSION_ROUTES)]))
    def test_public_allowlist_no_secrets(self):
        with patch('storefront_protection_api.public_policy',return_value={k:protection.DEFAULTS[k] for k in protection.PUBLIC_KEYS}):
            value=self.client.get('/api/storefront-protection/config').json()
        self.assertEqual(set(value),set(protection.PUBLIC_KEYS))
        self.assertNotIn('autoLockMinutes',value)
    def test_config_allowed_cors(self):
        r=self.client.options('/api/storefront-protection/config',headers={'Origin':'https://www.sportscaveshop.com'})
        self.assertEqual(204,r.status_code)
        self.assertEqual('https://www.sportscaveshop.com',r.headers['access-control-allow-origin'])
    def test_config_denied_cors(self):
        self.assertEqual(403,self.client.get('/api/storefront-protection/config',headers={'Origin':'https://evil.example'}).status_code)
    def test_script_served_without_credentials(self):
        r=self.client.get('/storefront-protection.js')
        self.assertEqual(200,r.status_code)
        self.assertIn('application/javascript',r.headers['content-type'])
        self.assertNotIn('SHOPIFY_ADMIN',r.text)
    def test_config_failure_safe_baseline(self):
        with patch('storefront_protection_api.public_policy',side_effect=RuntimeError('private secret')):
            r=self.client.get('/api/storefront-protection/config')
        self.assertEqual(200,r.status_code)
        self.assertNotIn('private secret',r.text)
        self.assertTrue(r.json()['neverServePrintMasters'])
    def test_session_cross_origin_rejected(self):
        self.assertEqual(403,self.client.post('/api/os/security/session',json={'action':'reauth','password':'x'},headers={'Origin':'https://evil.example'}).status_code)
    def test_session_malformed_origin_fails_closed(self):
        for origin in ('http://[broken','http://testserver/path','http://testserver?query=1','http://testserver#fragment'):
            with self.subTest(origin=origin):
                self.assertEqual(403,self.client.post('/api/os/security/session',json={'action':'activity'},headers={'Origin':origin}).status_code)
    def test_session_bad_json(self):
        self.assertEqual(400,self.client.post('/api/os/security/session',content='broken',headers={'Origin':'http://testserver'}).status_code)
    def test_session_request_size_actual_body(self):
        self.assertEqual(413,self.client.post('/api/os/security/session',content='x'*4100,headers={'Origin':'http://testserver'}).status_code)
    def test_session_no_auth_denied(self):
        self.assertEqual(423,self.client.post('/api/os/security/session',json={'action':'activity'},headers={'Origin':'http://testserver'}).status_code)
    def test_cookie_is_httponly_and_secure_on_https(self):
        client=TestClient(self.client.app,base_url='https://testserver')
        with patch('security_session_api.identity',return_value=({'id':'u'},{'exp':9999999999})),patch.object(protection.STORE,'register'),patch.object(protection.STORE,'validate_session'),patch.object(protection.STORE,'q'):
            r=client.post('/api/os/security/session',json={'token':'signed-token'},headers={'Origin':'https://testserver'})
        cookie=r.headers['set-cookie']
        self.assertIn('HttpOnly',cookie);self.assertIn('Secure',cookie);self.assertIn('SameSite=lax',cookie)
    def test_public_master_route_absent(self):
        for url in ('/masters/private.psd','/api/storefront-protection/master','/input/private.jpg'):
            self.assertEqual(404,self.client.get(url).status_code)

    def test_main_headers_preserve_assets_and_prevent_external_framing(self):
        from protection_headers import ProtectionHeaders
        from starlette.responses import Response
        async def endpoint(request):return Response('fixture')
        app=ProtectionHeaders(Starlette(routes=[Route('/',endpoint),Route('/storefront-protection.js',endpoint)]))
        client=TestClient(app)
        response=client.get('/')
        self.assertEqual("frame-ancestors 'self'",response.headers['content-security-policy'])
        self.assertNotIn('default-src',response.headers['content-security-policy'])
        self.assertEqual('nosniff',response.headers['x-content-type-options'])
        self.assertNotIn('content-security-policy',client.get('/storefront-protection.js').headers)


class ImageTests(unittest.TestCase):
    def image(self,size=(3000,1500)):
        source=BytesIO();Image.new('RGB',size,'navy').save(source,'JPEG',exif=b'Exif\x00\x00');source.seek(0);return source
    def test_derivative_limit_master_unchanged_metadata_stripped(self):
        source=self.image();original=source.getvalue();out=derivative(source)
        with Image.open(BytesIO(out)) as image:
            self.assertEqual((1800,900),image.size);self.assertNotIn('exif',image.info)
        self.assertEqual(original,source.getvalue())
    def test_smaller_source_not_upscaled(self):
        with Image.open(BytesIO(derivative(self.image((400,300))))) as image:self.assertEqual((400,300),image.size)
    def test_watermark_only_derivative_changes(self):
        source=self.image((500,300));plain=derivative(source);source.seek(0);watermarked=derivative(source,watermark=True)
        self.assertNotEqual(plain,watermarked)
    def test_invalid_file_rejected(self):
        with self.assertRaises(Exception):derivative(BytesIO(b'not an image'))
    def test_audit_classifies(self):
        self.assertEqual('SAFE',classify_public_image(800,600))
        self.assertEqual('HIGH RESOLUTION PUBLIC IMAGE',classify_public_image(6000,4000))
        self.assertEqual('REVIEW',classify_public_image(800,600,'print-master.tif'))


if __name__=='__main__':unittest.main()
