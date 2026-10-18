"""Opt-in offline benchmark: real PSD, disposable PostgreSQL, local disk storage.

Run with PRODUCT_UPLOAD_BENCHMARK_PSD set to an explicitly non-production PSD.
No application startup, cloud credentials, customer files, or worker execution.
"""
from contextlib import contextmanager
from copy import deepcopy
import http.client
import socket
import gc
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import tracemalloc
import types
import uuid

import psutil
import pytest
from starlette.applications import Starlette
from starlette.routing import Route
import uvicorn
from tests.test_product_upload_intake import env, database, DiskDropbox, ADMIN, CHUNK


def baseline_module(name, path):
    source = subprocess.check_output(['git', 'show', '5af8499e:' + path], text=True, encoding='utf-8')
    module = types.ModuleType(name)
    module.__file__ = str(Path(path).resolve())
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    return module


@contextmanager
def local_client(application):
    """Only these isolated routes, explicitly stubbed auth/DB/storage; never app.py."""
    listener = socket.socket(); listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(application, log_level='error', lifespan='off'))
    runner = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
    runner.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError('Isolated HTTP server failed to start')
        time.sleep(.005)
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=30)
    class Client:
        base = f'http://127.0.0.1:{port}'
        def post(self, path, headers, json=None, content=None):
            import json as codec
            payload = codec.dumps(json).encode() if json is not None else content
            connection.request('POST', path, body=payload, headers={**headers,
                'Origin': f'http://127.0.0.1:{port}', 'Content-Type': 'application/json' if json is not None else 'application/octet-stream'})
            response = connection.getresponse(); data = response.read()
            return types.SimpleNamespace(status_code=response.status, text=data.decode(),
                headers={k.lower(): v for k, v in response.getheaders()}, json=lambda: codec.loads(data))
    try:
        yield Client()
    finally:
        connection.close(); server.should_exit = True; runner.join(timeout=10); listener.close()


def test_benchmark(env, monkeypatch, tmp_path):
    source = os.environ.get('PRODUCT_UPLOAD_BENCHMARK_PSD')
    if not source:
        pytest.skip('Opt in with an explicitly non-production layered PSD')
    path = Path(source)
    import product_upload_api as current
    import files_upload_api as files
    import auto_editions as ae
    before = baseline_module('baseline_intake', 'product_upload_intake.py')
    api_before = baseline_module('baseline_api', 'product_upload_api.py')
    api_before.Intakes = before.Intakes
    # Warm imports and hash caches identically before measuring request paths.
    t = time.perf_counter(); expected = ae.file_hash(path, dropbox=True)
    identity_seconds = time.perf_counter() - t
    process = psutil.Process(); runs = []
    for label, api in [('before', api_before), ('after', current), ('before', api_before), ('after', current)]:
        provider = DiskDropbox(tmp_path / (label + str(len(runs))))
        storage_seconds = [0.0]
        class TimedProvider:
            def __getattr__(self, name):
                method = getattr(provider, name)
                def call(*args, **kwargs):
                    start = time.perf_counter()
                    try:
                        return method(*args, **kwargs)
                    finally:
                        storage_seconds[0] += time.perf_counter() - start
                return call
        monkeypatch.setattr(api, 'connect', env[0].connect)
        monkeypatch.setattr(api, 'Dropbox', TimedProvider)
        monkeypatch.setattr(files, '_request_user', lambda *args, **kwargs: ADMIN)
        application = Starlette(routes=[Route(p, e, methods=list(m)) for p, e, m in api.ROUTES])
        with local_client(application) as client:
            key = str(uuid.uuid4()); headers = {'Origin': 'http://testserver'}
            response = client.post('/api/product-uploads/start', headers=headers, json=dict(
                id=key, mode='DRAFT', name='NON_PRODUCTION.psd', size=path.stat().st_size, content_hash=expected))
            assert response.status_code == 200, response.text
            gc.collect()
            baseline_rss = process.memory_info().rss; rss = [baseline_rss]; stop = threading.Event()
            def sample():
                while not stop.wait(.005):
                    rss.append(process.memory_info().rss)
            sampler = threading.Thread(target=sample, daemon=True); sampler.start()
            tracemalloc.start(); samples = []; offset = 0; t = time.perf_counter(); storage_start = storage_seconds[0]
            with path.open('rb') as stream:
                while data := stream.read(CHUNK):
                    started = time.perf_counter()
                    response = client.post(f'/api/product-uploads/chunk?id={key}&offset={offset}', headers=headers, content=data)
                    assert response.status_code == 200, response.text
                    offset += len(data); assert response.json()['upload']['offset'] == offset
                    samples.append(dict(seconds=time.perf_counter()-started, server_timing=response.headers.get('server-timing')))
            transfer_seconds = time.perf_counter() - t; storage_transfer = storage_seconds[0] - storage_start
            python_peak = tracemalloc.get_traced_memory()[1]; tracemalloc.stop(); stop.set(); sampler.join()
            t = time.perf_counter()
            response = client.post('/api/product-uploads/finish', headers=headers, json=dict(id=key))
            assert response.status_code == 200, response.text
            assert response.json()['upload']['basic_validated'] is True
            finish_seconds = time.perf_counter() - t
            # Finishing twice may not duplicate the storage object, worker or provider finish.
            response = client.post('/api/product-uploads/finish', headers=headers, json=dict(id=key))
            assert response.status_code == 200
            assert sum(kind == 'finish' for kind, _ in provider.calls) == 1
            runs.append(dict(mode=label, bytes=offset, chunks=len(samples), transfer_seconds=transfer_seconds,
                             transfer_MiB_s=offset/1048576/transfer_seconds, storage_write_seconds=storage_transfer,
                             finalisation_seconds=finish_seconds, peak_python_MiB=python_peak/1048576,
                             sampled_process_rss_MiB=max(rss)/1048576, rss_growth_MiB=(max(rss)-baseline_rss)/1048576,
                             chunk_acknowledgements=samples))
    result = dict(fixture_name=path.name, content_hash=expected, bytes=path.stat().st_size,
                  identity_seconds=identity_seconds, conditions='Same local layered PSD; warm filesystem; real disposable PGlite SQL; loopback HTTP through isolated Uvicorn routes; disk provider double; sequential 4 MiB binary requests',
                  unmeasured=['Real browser/network/Dropbox bandwidth', 'Original 272.7 MiB incident', 'Native worker processing and real handoff latency', 'Browser memory'],
                  memory_scope='Python allocations and sampled RSS include loopback HTTP client and isolated server, exclude PGlite child; OS disk cache is not durable cloud storage',
                  runs=runs, production_calls=0)
    output = Path('output/product-upload-transfer'); output.mkdir(parents=True, exist_ok=True)
    (output/'benchmark.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({**result, 'runs': [{k:v for k,v in r.items() if k != 'chunk_acknowledgements'} for r in runs]}, indent=2))
