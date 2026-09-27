"""Reproducible local before/after profile. Simulated network only, no real I/O.

python -m tests.profile_support_email --baseline
python -m tests.profile_support_email
"""
import argparse
from pathlib import Path
import json
from time import perf_counter, sleep
import subprocess
import types
from unittest.mock import patch

import support_email_workspace as current
import support_email_compose as compose
import support_email_provider as provider
import support_email_store as store
import support_email_smtp as smtp
from tests.email_v2_fixtures import MailboxFixture, fixture_smtp, USER, CONFIG


class DelayedMailbox(MailboxFixture):
    def related_headers(self,*args,**kwargs):
        sleep(.180)
        return super().related_headers(*args,**kwargs)

    def read_message(self,*args,**kwargs):
        sleep(.240)
        return super().read_message(*args,**kwargs)


def profile(baseline=False):
    module=current
    if baseline:
        source=subprocess.check_output(['git','show','335c006:support_email_workspace.py']).decode('utf-8')
        module=types.ModuleType('email_v2_baseline')
        exec(compile(source,'email_v2_baseline.py','exec'),module.__dict__)
    results={'latency_model':{'related_headers_ms':180,'read_message_ms':240,'real_network':False}}
    with (patch.object(store,'load_email_settings',return_value=(compose.default_settings(),None)),
          patch.object(store,'load_orders') as orders,
          patch.object(provider.imaplib,'IMAP4_SSL',side_effect=AssertionError('Real IMAP forbidden')),
          patch.object(smtp.smtplib,'SMTP_SSL',side_effect=AssertionError('Real SMTP forbidden')),
          patch.object(module,'readable_html',wraps=module.readable_html) as html):
        fixture=DelayedMailbox()
        w=module.Workspace({},USER,CONFIG,smtp.SMTPConfiguration(),imap=fixture,smtp=fixture_smtp())
        start=perf_counter();w.load();results['initial_fixture_load_ms']=round((perf_counter()-start)*1000,2)
        key=w.state['threads'][0]['thread_key']
        for label in ['cold','immediate_reopen','after_20s_expiry']:
            if label=='after_20s_expiry':
                for entry in w.cache.values():entry['expires']=0
            fixture.calls.clear();html.reset_mock()
            start=perf_counter();w.open_thread(key);open_ms=(perf_counter()-start)*1000
            start=perf_counter();w.model();model_ms=(perf_counter()-start)*1000
            results[label]={'open_ms':round(open_ms,2),'model_ms':round(model_ms,2),'calls':[c[:2] for c in fixture.calls],
                            'html_calls':html.call_count,'order_queries':orders.call_count}
            if label=='cold' and hasattr(w,'resolve_thread'):
                start=perf_counter();w.resolve_thread(key,w.state['mailbox_version'])
                results['deferred_history_ms']=round((perf_counter()-start)*1000,2)
        html.reset_mock();w.model();w.model();results['html_calls_two_noop_models']=html.call_count
    return results


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',action='store_true');args=parser.parse_args()
    results=profile(args.baseline)
    path=Path('output')/('email_v21_baseline_reproduced.json' if args.baseline else 'email_v21_after.json')
    path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(results,indent=2))
