"""Private, version-addressed WebP cache. No delivery or recipient operations."""
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from copy import deepcopy
from pathlib import Path
from threading import Lock
from time import monotonic, time
import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile

LOG = logging.getLogger(__name__)
# At most two isolated Chromium subprocesses, including publication prewarming.
WORKERS = max(1, min(2, int(os.getenv('CRM_THUMBNAIL_WORKERS', '2'))))
POOL = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix='email-thumbnail')
LOCK = Lock()
PENDING = {}
FAILURES = {}
RECHECK = {}
DIAGNOSTICS = {}
REVISION = 'webp-2'


def cache_dir():
    path = Path(os.environ.get('CRM_THUMBNAIL_CACHE_DIR', str(Path(tempfile.gettempdir()) / 'sc-email-thumbnails')))
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def token(value):
    return hashlib.sha256(json.dumps([REVISION, value], sort_keys=True, default=str).encode()).hexdigest()


def selection(row, step):
    live = next((s for s in row.get('steps', []) if s.get('step_id') == step['step_id'] and s.get('template_id')), None)
    if live:
        identity = [str(row['id']), str(live['template_id']), live['template_version']]
        return token(identity), 'LIVE v' + str(live['template_version']), live
    return token([str(row['id']), 'draft', step['step_id'], step['document']]), 'DRAFT', None


@lru_cache(maxsize=128)
def _asset(path, modified, size):
    """Bounded decoded-asset validation, invalidated by atomic file replacement."""
    path=Path(path)
    data=path.read_bytes()
    from crm_thumbnail_store import valid
    if not valid(data):
        path.unlink(missing_ok=True)
        return None
    return data


def cached(key):
    path = cache_dir() / (key + '.webp')
    try:
        info=path.stat()
        if info.st_size>80000:
            path.unlink(missing_ok=True)
            return None
        return _asset(str(path),info.st_mtime_ns,info.st_size)
    except FileNotFoundError:
        return None


def generate(key, load, store=None):
    owner=None
    started=monotonic()
    with LOCK:
        DIAGNOSTICS[key]={'queue_ms':round(1000*(started-PENDING.get(key,started)),2)}
    # Cross-process claim prevents publication/UI overlap; stale claims recover.
    path = cache_dir() / (key + '.lock')
    try:
        if path.exists() and time() - path.stat().st_mtime > 180:
            path.unlink(missing_ok=True)
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            return
        os.close(fd)
        try:
            if cached(key):return
            if store:
                from crm_thumbnail_store import acquire
                phase,data,owner=acquire(store,key)
                if phase=='READY':
                    temporary=cache_dir()/(key+'.part')
                    temporary.write_bytes(data);os.chmod(temporary,0o600)
                    temporary.replace(cache_dir()/(key+'.webp'))
                    return
                if phase=='BUSY':
                    with LOCK:RECHECK[key]=monotonic()+5
                    return
            doc, cfg = load()
            render_started=monotonic()
            with tempfile.TemporaryDirectory(prefix='email-thumb-') as folder:
                source = Path(folder) / 'input.json'
                output = Path(folder) / 'output.webp'
                source.write_text(json.dumps({'document': doc, 'settings': cfg}), encoding='utf8')
                result = subprocess.run([sys.executable, str(Path(__file__).with_name('crm_thumbnail_render.py')), str(source), str(output)],
                    capture_output=True, timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                if result.returncode:
                    # Never log source HTML, URLs, tokens or raw browser stderr.
                    reason = result.stderr.decode('utf8', errors='replace').strip()
                    allowed = {'browser_runtime_unavailable','browser_install_failed','email_render_failed'}
                    raise RuntimeError('renderer_exit_' + (reason if reason in allowed else str(result.returncode)))
                data = output.read_bytes()
                from crm_thumbnail_store import valid
                if not valid(data):raise ValueError('Invalid thumbnail')
                if store:
                    from crm_thumbnail_store import finish
                    finish(store,key,owner,data)
                target = cache_dir() / (key + '.webp')
                temporary = target.with_suffix('.part')
                temporary.write_bytes(data)
                os.chmod(temporary, 0o600)
                temporary.replace(target)
            with LOCK:DIAGNOSTICS[key].update(renderer_ms=round(1000*(monotonic()-render_started),2),category='ready')
            files = sorted(cache_dir().glob('*.webp'), key=lambda p:p.stat().st_mtime)
            for old in files[:-4096]:old.unlink(missing_ok=True)
            LOG.warning('email_thumbnail_ready key=%s bytes=%s', key[:12], len(data))
        finally:
            path.unlink(missing_ok=True)
    except Exception as exc:
        if store and owner:
            try:
                from crm_thumbnail_store import finish
                finish(store,key,owner)
            except Exception:pass
        with LOCK:FAILURES[key] = monotonic()
        category=(str(exc).removeprefix('renderer_exit_') if isinstance(exc,RuntimeError) and str(exc).startswith('renderer_exit_') else
                  'source_unavailable' if isinstance(exc,(ValueError,KeyError)) else 'render_timeout' if isinstance(exc,subprocess.TimeoutExpired) else 'storage_unavailable')
        with LOCK:DIAGNOSTICS[key]['category']=category
        LOG.warning('email_thumbnail_failed key=%s reason=%s', key[:12], str(exc) if isinstance(exc,RuntimeError) and str(exc).startswith('renderer_exit_') else type(exc).__name__)
    finally:
        with LOCK:PENDING.pop(key, None)


def request(key, load, store=None):
    try:data = cached(key)
    except OSError as exc:
        LOG.warning('email_thumbnail_cache_unavailable reason=%s',type(exc).__name__)
        return 'ERROR',None
    if data:return 'READY', data
    with LOCK:
        if RECHECK.get(key,0)>monotonic():return 'LOADING',None
        RECHECK.pop(key,None)
        failure = FAILURES.get(key)
        if failure is not None and monotonic() - failure < 60:return 'ERROR', None
        if key not in PENDING:
            if len(PENDING) >= 24:return 'BUSY', None
            PENDING[key] = monotonic()
            try:POOL.submit(generate, key, load, store)
            except RuntimeError:
                PENDING.pop(key, None)
                return 'ERROR', None
        # Bounded error metadata; completed assets reside on disk, not in RAM.
        for old in list(FAILURES):
            if monotonic() - FAILURES[old] >= 60:FAILURES.pop(old, None)
        for old in list(DIAGNOSTICS)[:-128]:
            if old not in PENDING:DIAGNOSTICS.pop(old,None)
    return 'LOADING', None


def diagnostic(key):
    """Safe process-local timings/categories; never retain source documents."""
    with LOCK:
        return {**DIAGNOSTICS.get(key,{}),'retry_after':max(0,60-(monotonic()-FAILURES.get(key,-60)))}


def source_loader(store, row, step, live):
    if live:
        template_id, version = live['template_id'], live['template_version']
        def load():
            content = store.template(template_id, version)
            if (str(content.get('automation_id')) != str(row['id']) or content.get('step_id') != step['step_id']
                    or content.get('automation_version') != version):
                raise ValueError('Publication identity mismatch')
            return deepcopy(content['document']), deepcopy(content['render_settings'])
        return load
    doc = deepcopy(step['document'])
    return lambda: (doc, store.render_settings())


def prewarm(bundles, version, store=None):
    """Best effort after publication commits; failures cannot change publication."""
    try:
        from crm_thumbnail_store import private_store
        storage=private_store(store)
        for template_id, _, content in bundles:
            key = token([str(content['automation_id']), str(template_id), version])
            snapshot = deepcopy(content)
            request(key, lambda snapshot=snapshot: (snapshot['document'], snapshot['render_settings']),storage)
    except Exception as exc:
        LOG.warning('email_thumbnail_prewarm_failed reason=%s', type(exc).__name__)


def warm_renderer():
    """Background synthetic readiness check, with no DB, customer or provider I/O."""
    def source():
        from crm_campaign_content import new_document, settings
        doc=new_document()
        doc['content'].update(subject='Thumbnail readiness',preheader='Sample email')
        return doc,settings({})
    key=token('synthetic-renderer-readiness')
    phase,_=request(key,source)
    LOG.warning('email_thumbnail_readiness state=%s key=%s',phase,key[:12])
