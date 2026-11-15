"""Offline real-browser publication burst; no DB, provider, or remote images.

Run with .venv Python, --phase before/after, and an installed --channel chrome.
The before snapshot is copied locally before editing (tmp/worker-memory-before).
Windows RSS is a comparison, not a Linux cgroup capacity certification.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def deny_network(*_args, **_kwargs):
    raise AssertionError('Offline benchmark: external I/O forbidden')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=('before', 'after'), default='after')
    parser.add_argument('--channel', default='chrome')
    parser.add_argument('--render', nargs=3)
    parser.add_argument('--cycles', type=int, default=3)
    parser.add_argument('--reserve-mib', type=int, default=0,
                        help='Touched RAM representing live CRM/SEO work beyond import-only idle')
    args = parser.parse_args()
    import socket
    original_connect = socket.socket.connect
    def local_connect(sock, address):
        if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1'):
            return original_connect(sock, address)
        return deny_network()
    socket.socket.connect = local_connect
    if args.render:
        module, source, output = args.render
        renderer = load(module, 'benchmark_renderer')
        renderer.image_url = lambda _url: None  # Browser also denies every URL.
        source = json.loads(Path(source).read_text(encoding='utf8'))
        Path(output).write_bytes(renderer.render(source['document'], source['settings']))
        return
    import psutil
    import worker_memory
    source = ROOT / 'tmp/worker-memory-before' if args.phase == 'before' else ROOT
    # Imports exercised by the CRM worker; no main()/tick() or credential reads.
    import crm_engine, crm_automation_publication, crm_campaign_preparation
    import wall_preview_archive, reviews_worker, crm_buyer_segments
    from crm_campaign_content import new_document, settings
    from crm_thumbnail_store import valid
    reserve = bytearray(args.reserve_mib * 1024**2)
    clean_env = {k: v for k, v in os.environ.items() if k.upper() in (
        'SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP', 'LOCALAPPDATA', 'USERPROFILE',
        'PROGRAMFILES', 'PROGRAMFILES(X86)', 'PROGRAMW6432', 'PLAYWRIGHT_BROWSERS_PATH')}
    clean_env.update(PYTHONPATH=str(ROOT), CRM_THUMBNAIL_BROWSER_CHANNEL=args.channel)
    seo = subprocess.Popen([sys.executable, '-c', 'import google_seo_import,time; time.sleep(300)'],
                           cwd=ROOT, env=clean_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    stopped = threading.Event()
    samples = []
    process = psutil.Process()
    def sample():
        while not stopped.wait(.05):
            rss = 0
            processes = [process, *process.children(recursive=True)]
            for item in processes:
                try: rss += item.memory_info().rss
                except psutil.Error: pass
            samples.append((time.monotonic(), rss, len(processes), worker_memory.cgroup_memory()))
    monitor = threading.Thread(target=sample)
    monitor.start()
    original_run = subprocess.run
    from crm_thumbnail_process import run_renderer
    def render_command(command, **kwargs):
        kwargs.setdefault('capture_output', True)
        rewritten = [sys.executable, str(Path(__file__).resolve()), '--render', command[1], command[2], command[3]]
        if args.phase == 'after':
            # Real cleanup/output-bound code, with only credentials/network removed.
            result = run_renderer(rewritten, env=clean_env)
        else:
            result = original_run(rewritten, env=clean_env, **kwargs)
        if result.returncode:
            print(result.stderr.decode(errors='replace'), file=sys.stderr)
        return result
    try:
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, CRM_THUMBNAIL_CACHE_DIR=directory):
            with patch.object(worker_memory, 'cgroup_memory', return_value={'limit': 512*1024**2}):
                cache = load(source / 'crm_thumbnail_cache.py', 'benchmark_cache')
            settled = []
            started = time.monotonic()
            target, attribute = (cache.subprocess, 'run') if args.phase == 'before' else (cache, 'run_renderer')
            with patch.object(target, attribute, side_effect=render_command):
                for cycle in range(args.cycles):
                    keys = []
                    for index in range(6):
                        doc = new_document()
                        doc['content'].update(subject='Synthetic publication %s/%s' % (cycle,index),
                                              headline='Collector edition', body='Synthetic email content. '*100)
                        cfg = settings({})
                        cfg['logo'] = ''
                        key = cache.token([cycle, index])
                        keys.append(key)
                        cache.request(key, lambda doc=doc, cfg=cfg: (doc,cfg))
                    deadline = time.monotonic()+180
                    while cache.PENDING:
                        if time.monotonic()>deadline: raise TimeoutError('Thumbnail burst did not drain')
                        time.sleep(.05)
                    assert all(valid(cache.cached(key) or b'') for key in keys), cache.DIAGNOSTICS
                    settled.append(samples[-1][1])
            cache.POOL.shutdown(wait=True)
            print(json.dumps({'phase':args.phase, 'workers':cache.WORKERS, 'thumbnails':6*args.cycles,
                'reserve_mib':len(reserve)/1024**2,
                'seconds':round(time.monotonic()-started,2), 'peak_tree_mib':round(max(s[1] for s in samples)/1024**2,2),
                'settled_tree_mib':[round(v/1024**2,2) for v in settled],
                'max_processes':max(s[2] for s in samples),
                'seo_exit_code':seo.poll(),
                'cgroup':worker_memory.cgroup_memory()}, indent=2))
            assert seo.poll() is None, 'SEO sibling died during thumbnail workload'
    finally:
        print(json.dumps({'final_cgroup':worker_memory.cgroup_memory(),
                          'memory_events':Path('/sys/fs/cgroup/memory.events').read_text() if Path('/sys/fs/cgroup/memory.events').exists() else None}))
        seo.terminate(); seo.wait(timeout=10)
        stopped.set(); monitor.join()


if __name__ == '__main__':
    main()
