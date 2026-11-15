"""Disposable loopback HTTP(S) request recorder; no external network forwarding."""
import json, ssl, threading, ipaddress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import base64

root=Path('tmp/email-v2b-listener');root.mkdir(exist_ok=True)
key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')])
cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
      .serial_number(x509.random_serial_number()).not_valid_before(datetime.now(timezone.utc)-timedelta(minutes=1))
      .not_valid_after(datetime.now(timezone.utc)+timedelta(days=1))
      .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),critical=False)
      .sign(key,hashes.SHA256()))
(root/'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
(root/'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
hits=[];lock=threading.Lock()
pixel=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl1sAAAAASUVORK5CYII=')
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path=='/__hits':
            with lock:body=json.dumps(hits).encode()
            mime='application/json'
        else:
            with lock:hits.append({'path':self.path,'port':self.server.server_port,'referer':self.headers.get('Referer')})
            body=pixel;mime='image/png'
        self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_POST(self):
        if self.path!='/__reset':self.send_error(404);return
        with lock:hits.clear()
        self.send_response(204);self.end_headers()
    def log_message(self,*args):pass
http=ThreadingHTTPServer(('127.0.0.1',8843),Handler)
https=ThreadingHTTPServer(('127.0.0.1',8844),Handler)
context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(root/'cert.pem',root/'key.pem')
https.socket=context.wrap_socket(https.socket,server_side=True)
threading.Thread(target=http.serve_forever,daemon=True).start()
print('Synthetic HTTP 8843 and HTTPS 8844 ready',flush=True)
try:https.serve_forever()
finally:http.shutdown();https.server_close()
