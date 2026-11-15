"""Bounded in-request PSD relay. PostgreSQL checkpoints, never RAM, own resume.

Two 4 MiB frame permits per request; one ordered writer. Transaction advisory
leases admit at most two uploads across processes, and one request per intake.
No persistent queue, scheduler, background job or credential is introduced.
"""
from contextlib import contextmanager
import uuid
import anyio
from starlette.concurrency import run_in_threadpool
from product_upload_intake import CHUNK, TRANSPORT_CHUNK

MAX_RELAYS = 2
GLOBAL_LOCK = 1624420001
UPLOAD_LOCK = 1624420002


class RelayBusy(RuntimeError):
    pass


@contextmanager
def lease(connect, key, actor, *, capacity=True):
    key = str(uuid.UUID(key))
    failure = None
    with connect() as conn, conn.cursor() as cur:
        # Ordinary DB connections expire idle transactions after eight seconds.
        # Reception is bounded to 15 minutes and an active append must settle;
        # retain this guard for that window instead of silently losing its locks.
        cur.execute("SET LOCAL idle_in_transaction_session_timeout = '20min'", ())
        if capacity:
            for slot in range(MAX_RELAYS):
                cur.execute('SELECT pg_try_advisory_xact_lock(%s,%s) AS acquired', (GLOBAL_LOCK, slot))
                if cur.fetchone()['acquired']:
                    break
            else:
                raise RelayBusy('Upload capacity is busy. Your saved bytes are retained; retry shortly.')
        cur.execute('SELECT pg_try_advisory_xact_lock(%s,hashtext(%s)) AS acquired', (UPLOAD_LOCK, key))
        if not cur.fetchone()['acquired']:
            raise RelayBusy('The previous request is still settling. Retry from its confirmed offset shortly.')
        cur.execute('SELECT * FROM product_upload_intakes WHERE id=%s AND actor_id=%s', (key, str(actor)))
        row = cur.fetchone()
        if not row:
            raise ValueError('This saved upload is unavailable to this account.')
        # This transaction owns advisory leases only. Each Intakes.chunk uses its
        # own connection/transaction and commits before the next frame is saved.
        # Commit the guard even on disconnect; never undo an accepted checkpoint.
        try:
            yield dict(row)
        except BaseException as error:
            failure = error
    if failure is not None:
        raise failure


def settled(store, key, actor):
    with lease(store.connect, key, actor, capacity=False) as row:
        return row


def first_error(error):
    while isinstance(error, BaseExceptionGroup):
        error = error.exceptions[0]
    return error


async def transfer(request, store, key, actor, offset, provider, timings, clock):
    content_length = request.headers.get('content-length')
    length = int(content_length) if content_length is not None else None
    if length is not None and not 0 < length <= TRANSPORT_CHUNK:
        raise ValueError('Upload chunk must contain 1 byte to 8 MiB.')
    if offset < 0 or offset % CHUNK:
        raise ValueError('Invalid upload offset.')
    send, receive = anyio.create_memory_object_stream(1)
    permits = anyio.Semaphore(2)
    ready = anyio.Event()
    result = []

    def writer():
        with lease(store.connect, key, actor) as initial:
            size = initial['data']['size']
            if length is not None and (offset + length > size or (offset + length < size and length % CHUNK)):
                raise ValueError('A complete bounded upload chunk is required.')
            anyio.from_thread.run_sync(ready.set)
            while True:
                try:
                    position, data = anyio.from_thread.run(receive.receive)
                except anyio.EndOfStream:
                    break
                started = clock()
                try:
                    row = store.chunk(key, actor, position, data, provider)
                    result[:] = [row]
                finally:
                    timings['intake'] = timings.get('intake', 0) + (clock() - started) * 1000
                    # Drop this frame before returning the permit to reception.
                    del data
                    anyio.from_thread.run_sync(permits.release)
            if not result:
                raise ValueError('An upload chunk is required.')

    async def consume():
        await run_in_threadpool(writer)

    try:
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(consume)
            await ready.wait()
            total = 0; position = offset; data = None
            received = clock()
            try:
                stream = request.stream().__aiter__()
                while True:
                    if clock() - received > 900:
                        raise TimeoutError('The upload exceeded its bounded transfer deadline.')
                    try:
                        with anyio.fail_after(90):
                            block = await anext(stream)
                    except StopAsyncIteration:
                        break
                    total += len(block)
                    if total > TRANSPORT_CHUNK or (length is not None and total > length):
                        raise ValueError('Upload chunk exceeds its bounded size.')
                    view = memoryview(block)
                    while view:
                        if data is None:
                            await permits.acquire()
                            data = bytearray()
                        take = min(CHUNK - len(data), len(view))
                        data.extend(view[:take]); view = view[take:]
                        if len(data) == CHUNK:
                            await send.send((position, data))
                            position += len(data); data = None
                if length is not None and total != length:
                    raise ValueError('The upload request was interrupted before its complete body arrived.')
                if data:
                    await send.send((position, data)); data = None
                if not total:
                    raise ValueError('An upload chunk is required.')
            finally:
                timings['receive'] = (clock() - received) * 1000
                if data is not None:
                    permits.release()
                await send.aclose()
    except ExceptionGroup as errors:
        raise first_error(errors) from None
    finally:
        await receive.aclose()
    return result[0]
