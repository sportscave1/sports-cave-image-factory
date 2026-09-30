"""Timing comparison with explicit artificial latency; no live network or writes."""
import json
import subprocess
import types
import time
from unittest.mock import Mock,patch
from support_email_workspace import Workspace
from support_email_reads import ReadService,AsyncInbox
from support_email_compose import default_settings
from support_email_smtp import SMTPConfiguration
from tests.test_email_inbox_reliability import Provider
from tests.email_v2_fixtures import CONFIG,USER,fixture_smtp

class TimedMail(Provider):
    def discover_folders(self,**kw):time.sleep(.2);return super().discover_folders(**kw)
    def list_headers(self,*a,**kw):time.sleep(.5);return super().list_headers(*a,**kw)
    def read_message(self,*a,**kw):time.sleep(.8);return super().read_message(*a,**kw)

def elapsed(action):
    start=time.perf_counter();action();return round((time.perf_counter()-start)*1000,2)

def run():
    baseline=types.ModuleType('inbox_baseline')
    exec(compile(subprocess.check_output(['git','show','HEAD:support_email_workspace.py']).decode(),'<baseline>','exec'),baseline.__dict__)
    with patch('support_email_store.load_email_settings',return_value=(default_settings(),None)),patch('support_email_store.audit'):
        old=baseline.Workspace({},USER,CONFIG,SMTPConfiguration(),imap=TimedMail(60),smtp=fixture_smtp())
        results={'fixture_only':True,'latency_ms':{'folders':200,'headers':500,'body':800},
                 'before_list_ms':elapsed(lambda:old.load(defer_body=True))}
        results['before_body_request_ms']=elapsed(lambda:old._body(old.state['conversation'][-1]))
        mail=TimedMail(60);store=Mock();store.read_index.return_value={}
        reads=ReadService(mail,store)
        try:
            reads.sync();reads.start=Mock()
            current=Workspace({},USER,CONFIG,SMTPConfiguration(),imap=AsyncInbox(CONFIG,reads),smtp=fixture_smtp())
            results['after_cached_list_ms']=elapsed(lambda:current.load(defer_body=True))
            key=current.state['threads'][1]['thread_key']
            results['after_body_request_return_ms']=elapsed(lambda:current.open_thread(key))
            for future,_ in list(reads.jobs.values()):future.result(timeout=3)
            results['after_body_result_ms']=elapsed(lambda:current._body(current.state['conversation'][-1],defer=True))
            results['list_body_fetches']=len([c for c in mail.calls if c[0]=='body'])-1
            results['initial_attachment_fetches']=len([c for c in mail.calls if c[0]=='attachment'])
            results['first_page_rows']=len(current.state['threads'])
            results['customer_order_queries']=0
        finally:reads.close()
        return results

if __name__=='__main__':print(json.dumps(run(),indent=2))
