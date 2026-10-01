"""Session-owned review jobs; workers never access Streamlit or send email."""
from concurrent.futures import Future
from copy import deepcopy
import hashlib
import json
import logging
import threading
import time
from uuid import UUID

from crm_campaign_recovery import checkpoint, save_checkpoint
from crm_campaign_send import review

LOG = logging.getLogger(__name__)
_SLOTS = threading.BoundedSemaphore(4)


class TimedReads:
    """Safe per-operation timings; never log arguments, recipients or credentials."""
    def __init__(self, target, names):self.target,self.names=target,names
    def __getattr__(self, name):
        value=getattr(self.target,name)
        if name not in self.names:return value
        def measured(*args,**kwargs):
            started=time.monotonic()
            try:return value(*args,**kwargs)
            finally:LOG.info('campaign_review stage=%s duration_ms=%.1f',name,(time.monotonic()-started)*1000)
        return measured


def identity(editor):
    # psycopg returns UUID columns as UUID objects; browser/session fixtures may
    # carry strings. Normalize only this database identity, not campaign content.
    campaign_id = editor.get('id')
    if isinstance(campaign_id, UUID):
        campaign_id = str(campaign_id)
    return hashlib.sha256(json.dumps([campaign_id,editor.get('version'),checkpoint(editor)],sort_keys=True).encode()).hexdigest()


class ReviewJob:
    def __init__(self, shop, store, user, editor, saved, cfg=None):
        self.editor = deepcopy(editor)
        self.identity = identity(editor)
        self.requested_settings = deepcopy(cfg)
        self.started = time.monotonic()
        self.future = Future()
        self.closed = False
        self.applied = False
        needs_save = not editor.get('id') or not saved or checkpoint(editor) != checkpoint(saved)
        actor = deepcopy(user)
        if not _SLOTS.acquire(blocking=False):
            self.future.set_exception(ValueError('Review service is busy. Retry shortly.'))
            return
        def work():
            try:
                started = time.monotonic()
                if needs_save:
                    self.editor.update(save_checkpoint(store,actor,self.editor))
                LOG.info('campaign_review stage=draft_save duration_ms=%.1f',(time.monotonic()-started)*1000)
                result = review(TimedReads(shop,{'segments','campaign_member_ids','campaign_subscribers'}),
                                TimedReads(store,{'active_suppression_hashes','recent_marketing_hashes','render_settings'}),self.editor)
                self.future.set_result(result)
            except Exception as exc:
                self.future.set_exception(exc)
            finally:
                LOG.info('campaign_review stage=total duration_ms=%.1f',(time.monotonic()-self.started)*1000)
                _SLOTS.release()
        threading.Thread(target=work,name='campaign-review',daemon=True).start()


def start_review(previous, shop, store, user, editor, saved, cfg=None):
    # Reopening the same in-flight or just-completed review never duplicates a snapshot.
    if previous and previous.identity == identity(editor) and getattr(previous,'requested_settings',None) == cfg:
        reusable = not previous.future.done() or (previous.future.exception() is None and time.monotonic()-previous.started < 30)
        if reusable:
            previous.closed = False
            return previous
    return ReviewJob(shop,store,user,editor,saved,cfg)
