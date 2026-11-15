"""Keep the existing two Orders workers and bound queued/cancelled work too."""
from concurrent.futures import Future, ThreadPoolExecutor
from threading import BoundedSemaphore, Lock


class ReadQueueFull(RuntimeError):
    pass


class OrdersReadExecutor(ThreadPoolExecutor):
    def __init__(self):
        super().__init__(max_workers=2, thread_name_prefix='orders-ledger-read')
        self._slots = BoundedSemaphore(8)
        self._pending = set()
        self._pending_lock = Lock()

    def submit(self, fn, /, *args, **kwargs):
        result = Future()
        if not self._slots.acquire(blocking=False):
            result.set_exception(ReadQueueFull('Orders reads are busy. Please retry.'))
            return result
        with self._pending_lock:
            self._pending.add(result)

        def run():
            try:
                # Cancellation skips queued SQL but holds its slot until the
                # worker removes the item. Rapid searches cannot accumulate an
                # unlimited queue of already-cancelled work items.
                if result.set_running_or_notify_cancel():
                    try:
                        result.set_result(fn(*args, **kwargs))
                    except BaseException as error:
                        result.set_exception(error)
            finally:
                with self._pending_lock:
                    self._pending.discard(result)
                self._slots.release()
        try:
            super().submit(run)
        except BaseException:
            with self._pending_lock:
                self._pending.discard(result)
            self._slots.release()
            raise
        return result

    def shutdown(self, wait=True, *, cancel_futures=False):
        if cancel_futures:
            with self._pending_lock:
                pending = tuple(self._pending)
            for result in pending:
                result.cancel()
        # Let wrappers drain so cancelled requests also release their slots.
        super().shutdown(wait=wait, cancel_futures=False)
