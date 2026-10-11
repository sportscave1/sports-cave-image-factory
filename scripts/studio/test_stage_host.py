"""Loopback-only acceptance for the limited HTTPS pairing host; no application imports."""
import base64
import hashlib
import http.client
from pathlib import Path
import secrets
import threading
import time
import unittest
from unittest.mock import patch
import stage_host as stage


class StageTests(unittest.TestCase):
    def setUp(self):
        self.password = secrets.token_urlsafe(32)
        self.host = 'sports-cave-studio-pairing-stage.onrender.com'
        self.expiry = int(time.time()) + 3600
        self.server = stage.Stage(('127.0.0.1', 0), self.host,
                                  hashlib.sha256(self.password.encode()).hexdigest(), self.expiry)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(2)

    def request(self, path='/', auth=True, method='GET', headers=None):
        values = {'Host':self.host, 'X-Forwarded-Proto':'https'}
        if auth:
            values['Authorization'] = 'Basic ' + base64.b64encode(('owner:'+self.password).encode()).decode()
        values.update(headers or {})
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            connection.request(method, path, headers=values)
            response=connection.getresponse()
            return response.status, dict(response.getheaders()), response.read().decode()
        finally:
            connection.close()

    def test_owner_required_for_shell_and_panel(self):
        for path in ['/', '/panel']:
            code, headers, body=self.request(path,auth=False)
            self.assertEqual(code,401)
            self.assertIn('WWW-Authenticate',headers)
            self.assertNotIn('/*STUDIO',body)

    def test_invalid_credentials_fail_closed(self):
        for value in ['Basic bad', 'Bearer token', 'Basic '+base64.b64encode(b'other:password').decode()]:
            self.assertEqual(self.request(headers={'Authorization':value})[0],401)

    def test_exact_host_and_https_required(self):
        for headers in [{'Host':'evil.example'}, {'Host':self.host+':443'}, {'X-Forwarded-Proto':'http'}, {'X-Forwarded-Proto':''}]:
            self.assertEqual(self.request(headers=headers)[0],403)

    def test_expired_host_denies_existing_auth_and_health(self):
        with patch.object(stage.time,'time',return_value=self.expiry+1):
            self.assertEqual(self.request()[0],403)
            self.assertEqual(self.request('/healthz',auth=False)[0],503)

    def test_panel_is_exact_selected_source(self):
        code,headers,body=self.request('/panel')
        self.assertEqual(code,200); self.assertEqual(body,stage.page())
        self.assertIn('Publish to production',body)
        self.assertIn('connect-src \'none\'',headers['Content-Security-Policy'])
        self.assertIn("'sha256-",headers['Content-Security-Policy'])
        self.assertNotIn('Access-Control-Allow-Origin',headers)
        self.assertNotIn('Cross-Origin-Opener-Policy',headers)
        self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertNotIn(self.password,body)

    def test_shell_labels_limitations_and_preserves_popup_sandbox(self):
        code,_,body=self.request()
        self.assertEqual(code,200)
        self.assertIn('not the full Sports Cave OS',body)
        self.assertIn('allow-popups-to-escape-sandbox',body)
        self.assertIn('src="/panel"',body)

    def test_no_filesystem_or_mutation_routes(self):
        for path in ['/api/action','/.env','/../app.py','/%2e%2e/app.py','/panel?file=secret']:
            self.assertEqual(self.request(path)[0],404)
        self.assertEqual(self.request('/api/action',method='POST')[0],405)

    def test_configuration_missing_expired_or_nonstage_hostname_rejected(self):
        digest=hashlib.sha256(self.password.encode()).hexdigest()
        for host,secret,expiry in [('127.0.0.1',digest,self.expiry),(self.host,'bad',self.expiry),(self.host,digest,0),(self.host,digest,time.time()+90000)]:
            with self.assertRaises(ValueError):stage.Stage(('127.0.0.1',0),host,secret,expiry)

    def test_integration_environment_fails_closed(self):
        stage.validate_environment({'PORT':'10000','RENDER_EXTERNAL_HOSTNAME':self.host})
        for key in ['DATABASE_URL','SUPABASE_URL','SHOPIFY_TOKEN','META_ACCESS_TOKEN','RESEND_API_KEY','SMTP_HOST','CRM_MARKETING_ENABLED','AWS_SECRET_ACCESS_KEY','RENDER_API_KEY','GITHUB_TOKEN']:
            with self.assertRaises(ValueError):stage.validate_environment({key:'synthetic'})

    def test_container_copies_only_host_and_panel(self):
        dockerfile=Path(__file__).with_name('staging.Dockerfile').read_text(encoding='utf-8-sig')
        self.assertEqual(len([line for line in dockerfile.splitlines() if line.startswith('COPY ')]),2)
        self.assertNotIn('COPY . ',dockerfile)
        self.assertNotIn('requirements.txt',dockerfile)
        self.assertIn('USER 65532:65532',dockerfile)


if __name__=='__main__':unittest.main()
