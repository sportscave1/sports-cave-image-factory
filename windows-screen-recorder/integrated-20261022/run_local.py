"""Launch only the isolated candidate; no production credentials or installer changes."""
import asyncio
import os
from pathlib import Path
from task_recorder.server import Bridge, instance_lock, protect
from task_recorder.store import atomic

root = Path(os.environ['LOCALAPPDATA']) / 'SportsCaveOS' / 'TaskRecorderPhase1-20261022'
root.mkdir(parents=True, exist_ok=True)
with instance_lock(root / 'recorder.lock'):
    server = Bridge(root, 18932, preview=True)
    atomic(root / 'connection.json', {'origin': server.origin, 'protected': protect(server.token.encode()).hex()})
    async def projection():
        while True:
            atomic(root / 'candidate-state.json', server.runner.state())
            await asyncio.sleep(1)
    projector = asyncio.run_coroutine_threadsafe(projection(), server.loop)
    try:
        asyncio.run_coroutine_threadsafe(server.runner.open_toolbar(), server.loop).result(timeout=10)
        print('Local candidate ready on 127.0.0.1:18932', flush=True)
        server.serve_forever(poll_interval=.2)
    finally:
        projector.cancel()
        server.close()
