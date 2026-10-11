"""Limited HTTPS Studio pairing fixture. Never imports or executes Sports Cave OS."""
import base64
import hashlib
import hmac
import os
from pathlib import Path
import re
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = Path(__file__).resolve().parents[2] if (Path(__file__).parent / 'studio.py').exists() else Path(__file__).parent


def validate_environment(environ):
    # Misconfiguration guard; this fixture is not a sandbox for application code.
    forbidden = ('DATABASE', 'SUPABASE', 'SHOPIFY', 'META_', 'RESEND', 'SMTP',
                 'SENDGRID', 'MAILGUN', 'DROPBOX', 'CRM_', 'AWS_', 'GOOGLE_',
                 'OPENAI', 'STRIPE', 'RENDER_API_KEY', 'GITHUB_TOKEN', 'GH_TOKEN')
    if any(any(part in key.upper() for part in forbidden) for key in environ):
        raise ValueError('Production/integration configuration is forbidden on the pairing fixture.')


def page():
    assets = ROOT / 'components/developer_studio'
    return (assets.joinpath('panel.html').read_text(encoding='utf-8')
            .replace('/*STUDIO_CSS*/', assets.joinpath('panel.css').read_text(encoding='utf-8'))
            .replace('/*STUDIO_JS*/', assets.joinpath('panel.js').read_text(encoding='utf-8')))


def policy(html):
    scripts = ['\'sha256-' + base64.b64encode(hashlib.sha256(s.encode()).digest()).decode() + '\''
               for s in re.findall(r'<script>(.*?)</script>', html, re.S)]
    return ("default-src 'none'; script-src " + (' '.join(scripts) or "'none'") +
            "; style-src 'unsafe-inline'; img-src data:; frame-src 'self'; "
            "connect-src 'none'; base-uri 'none'; object-src 'none'; form-action 'none'; frame-ancestors 'self'")


class Stage(HTTPServer):
    def __init__(self, address, host, password_hash, expires):
        if not re.fullmatch(r'sports-cave-studio-pairing-[a-z0-9-]+\.onrender\.com', host):
            raise ValueError('A dedicated Render staging hostname is required.')
        if not re.fullmatch(r'[a-f0-9]{64}', password_hash):
            raise ValueError('A staging-only random password SHA256 is required.')
        if not time.time() < expires <= time.time() + 86400:
            raise ValueError('Set a fixed future expiry within 24 hours; expired staging fails closed.')
        self.host, self.password_hash, self.expires = host, password_hash, expires
        self.panel = page()
        super().__init__(address, Handler)

    def get_request(self):
        sock, address = super().get_request()
        sock.settimeout(10)
        return sock, address


class Handler(BaseHTTPRequestHandler):
    server_version = 'StudioStage'
    sys_version = ''

    def log_message(self, *_args):
        pass  # Never log credentials, request paths, local metadata or headers.

    def respond(self, code, body='', challenge=False):
        data = body.encode()
        self.send_response(code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'SAMEORIGIN')
        self.send_header('X-Robots-Tag', 'noindex, nofollow, noarchive')
        self.send_header('Content-Security-Policy', policy(body))
        # No COOP: severing the opener would prevent the reviewed postMessage handshake.
        if challenge:
            self.send_header('WWW-Authenticate', 'Basic realm="Temporary Studio pairing test", charset="UTF-8"')
        self.end_headers()
        self.wfile.write(data)

    def authorised(self):
        value = self.headers.get('Authorization', '')
        if not value.startswith('Basic ') or len(value) > 256:
            return False
        try:
            decoded = base64.b64decode(value[6:], validate=True).decode('ascii')
        except (ValueError, UnicodeError):
            return False
        if not re.fullmatch(r'owner:[A-Za-z0-9_-]{43}', decoded):
            return False
        return hmac.compare_digest(hashlib.sha256(decoded[6:].encode()).hexdigest(), self.server.password_hash)

    def do_GET(self):
        if self.path == '/healthz':
            return self.respond(200 if time.time() < self.server.expires else 503, 'Limited pairing fixture')
        if self.headers.get('Host') != self.server.host or self.headers.get('X-Forwarded-Proto') != 'https':
            return self.respond(403, 'HTTPS staging origin required.')
        if time.time() >= self.server.expires:
            return self.respond(403, 'Temporary staging access expired.')
        if not self.authorised():
            return self.respond(401, 'Use the staging-only owner credential over HTTPS.', challenge=True)
        if self.path == '/panel':
            return self.respond(200, self.server.panel)
        if self.path == '/':
            return self.respond(200, '<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>Studio HTTPS pairing acceptance</title><body><h1>Limited UI staging</h1>'
                '<p>This is the actual Studio panel, not the full Sports Cave OS application. '
                'Local data appears only after explicit companion approval. Real Publish is disabled.</p>'
                '<iframe title="Developer Studio pairing test" src="/panel" '
                'sandbox="allow-forms allow-modals allow-popups allow-popups-to-escape-sandbox allow-same-origin allow-scripts allow-downloads" '
                'style="width:100%;height:80vh;border:0"></iframe></body></html>')
        return self.respond(404, 'Not found.')

    def do_POST(self):
        self.respond(405, 'No server-side operation endpoint.')


if __name__ == '__main__':
    validate_environment(os.environ)
    Stage(('0.0.0.0', int(os.environ.get('PORT', '10000'))),
          os.environ['RENDER_EXTERNAL_HOSTNAME'], os.environ['STUDIO_STAGE_PASSWORD_SHA256'],
          int(os.environ['STUDIO_STAGE_EXPIRES_AT'])).serve_forever()
