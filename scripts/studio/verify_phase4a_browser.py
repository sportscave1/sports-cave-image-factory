"""Opt-in localhost browser fixture for the shipped panel. Never imports/runs app.py.
Actual application checks must use the existing isolated Docker preview separately.
"""
import sys
import argparse
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import draft_ui
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from developer_studio_page import panel_html

class Panel(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        if self.path!="/" or self.headers.get("Host")!="127.0.0.1:"+str(self.server.server_port):
            self.send_error(404);return
        data=panel_html().encode()
        self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8")
        self.send_header("Cache-Control","no-store");self.send_header("Content-Length",str(len(data)));self.end_headers();self.wfile.write(data)

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--task",default="20261011-c24ca137");parser.add_argument("--owner",default="me/phase2");args=parser.parse_args()
    home=Path(r"C:\Dev\SportsCaveWorktrees")
    local=draft_ui.DraftServer(home,args.task,args.owner,idle_seconds=900)
    fixture=HTTPServer(("127.0.0.1",0),Panel)
    thread=threading.Thread(target=local.run,daemon=True);thread.start()
    print("Browser fixture (panel only): http://127.0.0.1:"+str(fixture.server_port),flush=True)
    print("Private local session: "+local.origin+"/#"+local.token,flush=True)
    try:fixture.serve_forever()
    except KeyboardInterrupt:pass
    finally:local.stopping=True;thread.join(10);fixture.server_close()
