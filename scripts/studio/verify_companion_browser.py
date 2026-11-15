"""Disposable limited-UI acceptance fixture. Not an application preview."""
import json,sys,threading
from pathlib import Path
from http.server import HTTPServer
import test_drafts,studio,draft_ui
from verify_phase4a_browser import Panel, panel_html
if "--panel-only" in sys.argv:
    import time
    class CandidatePanel(Panel):
        def do_GET(self):
            if self.path!="/" or self.headers.get("Host")!="127.0.0.1:"+str(self.server.server_port):
                self.send_error(404);return
            import secrets
            nonce=secrets.token_urlsafe(24)
            html=panel_html().replace("<body>","<body><aside><strong>V5 LOCAL ACCEPTANCE · LIMITED UI · NOT THE LIVE APPLICATION</strong></aside>")
            html=html.replace("<script>",'<script nonce="'+nonce+'">').replace("<style>",'<style nonce="'+nonce+'">')
            data=html.encode()
            self.send_response(200)
            self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Cache-Control","no-store")
            self.send_header("Content-Security-Policy","default-src 'none'; script-src 'nonce-"+nonce+"'; style-src 'nonce-"+nonce+"'; img-src data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.send_header("Content-Length",str(len(data)))
            self.end_headers();self.wfile.write(data)
    class ExclusivePanelServer(HTTPServer):
        allow_reuse_address=False
        def server_bind(self):
            import socket
            if hasattr(socket,"SO_EXCLUSIVEADDRUSE"):
                self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            super().server_bind()
    panel=ExclusivePanelServer(("127.0.0.1",18861),CandidatePanel)
    panel.timeout=1
    print("V5 LIMITED UI acceptance: http://127.0.0.1:18861 (not the application; stops after 4 hours)",flush=True)
    deadline=time.monotonic()+14400
    try:
        while time.monotonic()<deadline:panel.handle_request()
    finally:panel.server_close()
    raise SystemExit(0)
fixture=test_drafts.DraftTests();fixture.setUp()
server=draft_ui.DraftServer(fixture.home,"task-a","owner-a",persistent=True)
# Fixed synthetic bootstrap is valid only for this disposable, non-production fixture.
server.token="synthetic_browser_fixture_"+"x"*24
panel=HTTPServer(("127.0.0.1",0),Panel)
threading.Thread(target=server.run,daemon=True).start()
print(json.dumps({"panel":"http://127.0.0.1:"+str(panel.server_port),"companion":server.origin,"bootstrap":server.origin+"/pair#bootstrap="+server.token}),flush=True)
try:panel.serve_forever()
finally:server.stopping=True;panel.server_close();fixture.doCleanups()
