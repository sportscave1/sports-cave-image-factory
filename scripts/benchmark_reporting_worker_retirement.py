"""Offline import-only process comparison; no CRM tick, Google request or DB I/O.
Windows RSS/CPU is a local comparison, not a Render peak-load certification.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import psutil

ROOT = Path(__file__).resolve().parents[1]
CHILD = '''import socket,sys,time
from pathlib import Path
def denied(*a,**k): raise AssertionError("offline benchmark network denied")
socket.socket.connect = denied
socket.create_connection = denied
import dotenv
dotenv.load_dotenv = lambda *a,**k: False
sys.path.insert(0,sys.argv[1])
if sys.argv[2] == "seo":
    import google_seo_import,google_seo_phase4
else:
    import crm_engine,crm_automation_publication,crm_campaign_preparation
    import wall_preview_archive,reviews_worker,crm_buyer_segments
Path(sys.argv[3]).write_text("ready")
time.sleep(3)
'''


def measure(names):
    processes = []
    env = {key: os.environ[key] for key in ('SystemRoot','WINDIR','PATH','TEMP','TMP') if key in os.environ}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    with tempfile.TemporaryDirectory() as directory:
        try:
            for name in names:
                marker = Path(directory)/name
                child = subprocess.Popen([sys.executable,'-B','-c',CHILD,str(ROOT),name,str(marker)],
                    cwd=directory,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                processes.append(child)
            deadline=time.monotonic()+20
            while not all((Path(directory)/name).exists() for name in names):
                for child in processes:
                    if child.poll() is not None:
                        raise RuntimeError(child.communicate()[1].decode(errors='replace'))
                if time.monotonic()>deadline: raise TimeoutError('Import fixture did not become ready')
                time.sleep(.05)
            def tree():
                result = []
                for child in processes:
                    parent = psutil.Process(child.pid)
                    result.extend([parent, *parent.children(recursive=True)])
                return result
            readings=[]
            for _ in range(10):
                readings.append(sum(p.memory_info().rss for p in tree()))
                time.sleep(.1)
            cpu=sum(sum(p.cpu_times()[:2]) for p in tree())
            process_count = len(tree())
            for child in processes:
                child.communicate(timeout=10)
            return dict(children=list(names),process_count=process_count,peak_child_rss_mib=round(max(readings)/2**20,3),
                        import_and_idle_cpu_seconds=round(cpu,4),sample_seconds=1)
        finally:
            for child in processes:
                if child.poll() is None:
                    descendants = psutil.Process(child.pid).children(recursive=True)
                    for descendant in descendants:
                        try: descendant.terminate()
                        except psutil.NoSuchProcess: pass
                    child.terminate()
            for child in processes:
                child.communicate(timeout=10)


if __name__=='__main__':
    before=measure(('seo','crm'))
    after=measure(('crm',))
    print(json.dumps(dict(kind='offline-import-only',before=before,after=after,
        saved_child_rss_mib=round(before['peak_child_rss_mib']-after['peak_child_rss_mib'],3)),indent=2))
