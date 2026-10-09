"""One thread-owned connection for the publication lane, no shared UI pool.

Each Store.db block remains an explicit, independent transaction. Disconnects
are surfaced, never replayed here: the durable job executor reconciles/fences
the outcome before any retry. Idle polling holds no database transaction.
"""
from threading import get_ident


class Connection:
    def __init__(self,connect):
        self.connect=connect;self.raw=None;self.owner=None;self.active=False

    def __call__(self):
        owner=get_ident()
        if self.owner is not None and self.owner!=owner:raise RuntimeError('Publication connection is thread-owned')
        if self.active:raise RuntimeError('Publication transactions must not overlap')
        self.owner=owner
        if self.raw is None or self.raw.closed:
            self.raw=self.connect()
            try:self.raw.autocommit=True
            except BaseException:self.close();raise
        return Lease(self)

    def close(self):
        raw,self.raw=self.raw,None
        if raw is not None:raw.close()


class Lease:
    def __init__(self,parent):self.parent=parent;self.tx=None
    def execute(self,*args,**kwargs):return self.parent.raw.execute(*args,**kwargs)
    def __enter__(self):
        self.parent.active=True
        try:
            self.tx=self.parent.raw.transaction();self.tx.__enter__();return self
        except BaseException:
            self.parent.active=False;self.parent.close();raise
    def __exit__(self,kind,error,trace):
        try:return self.tx.__exit__(kind,error,trace)
        except BaseException:
            self.parent.close();raise
        finally:
            self.parent.active=False
            if kind:self.parent.close()
