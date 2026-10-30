"""Bounded callback transport reuse; each checkout is an explicit transaction."""
import atexit
from contextlib import ExitStack
import threading

_lock=threading.Lock()
_pool=None


def pool():
    global _pool
    with _lock:
        if _pool is None:
            from psycopg_pool import ConnectionPool
            from psycopg.rows import dict_row
            import supabase_backend as db
            timeout=db._db_statement_timeout_ms()
            _pool=ConnectionPool(db._database_url_with_ssl(),min_size=1,max_size=4,
                timeout=2,max_waiting=4,max_idle=60,max_lifetime=300,open=True,
                kwargs={'row_factory':dict_row,'connect_timeout':8,'prepare_threshold':None,
                        'autocommit':True,'options':f'-c statement_timeout={timeout} -c idle_in_transaction_session_timeout={timeout}'})
        return _pool


class Connection:
    def __enter__(self):
        self.stack=ExitStack()
        try:
            self.conn=self.stack.enter_context(pool().connection(timeout=2))
            # Autocommit pool connections still need atomic event + queue receipts
            # and atomic reconciliation + DONE. Never retry an ambiguous commit.
            self.stack.enter_context(self.conn.transaction())
            return self
        except BaseException:
            self.stack.close();self.conn=None;raise
    def __exit__(self,*args):
        try:return self.stack.__exit__(*args)
        finally:self.conn=None
    def execute(self,*args,**kwargs):return self.conn.execute(*args,**kwargs)


def close():
    global _pool
    with _lock:
        previous=_pool;_pool=None
    if previous is not None:previous.close()


atexit.register(close)
