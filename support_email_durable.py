"""Private durable Inbox drafts and SMTP intents. Never retries uncertain DATA."""
import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import logging
import random
import threading
import time
import uuid

from support_email_idle_store import SignalStore
from support_email_compose import ComposeError, MAX_MIME_BYTES
from support_email_smtp import report_progress

LOG = logging.getLogger(__name__)


def encode(value):
    def convert(item):
        if isinstance(item, bytes):return {'_mail_bytes':base64.b64encode(item).decode('ascii')}
        if isinstance(item, datetime):return item.isoformat()
        if isinstance(item, set):return list(item)
        raise TypeError('Unsupported mail data')
    result = json.dumps(value, default=convert)
    if len(result.encode()) > 30*1024*1024:raise ComposeError('Draft exceeds mailbox storage limit.')
    return result


def decode(value):
    return json.loads(json.dumps(value), object_hook=lambda obj:
        base64.b64decode(obj['_mail_bytes'],validate=True) if set(obj)=={'_mail_bytes'} else obj)


def receipt(row):
    status = row.get('status', '')
    due=row.get('due_at')
    if isinstance(due,str):due=datetime.fromisoformat(due.replace('Z','+00:00'))
    delay=max(1000,int((due-datetime.now(timezone.utc)).total_seconds()*1000)) if due and status=='queued' else 1000
    return {'operation_id':str(row['operation_id']), 'status':'in_progress' if status=='queued' else status,
            'retry_delay_ms':delay,
            'message_id':row['message_id'], 'fingerprint':row['fingerprint'],
            'sent_at':str(row.get('accepted_at') or ''),
            'notice':{'queued':'Queued securely', 'in_progress':'Sending…', 'accepted':'Sent',
                      'rejected':'Original send was not accepted. Review the draft before retrying.',
                      'unknown':'Confirming original send. Do not resend.'}.get(status,''),
            'error_category':row.get('error_category','')}


class MailStore(SignalStore):
    def save_draft(self, mailbox, actor, draft):
        data=deepcopy(draft);expected=int(data.pop('_storage_version',0))
        payload=encode(data)
        with self.transaction() as cur:
            cur.execute('''INSERT INTO support_email_drafts(mailbox,actor,draft_id,operation_id,payload)
                VALUES(%s,%s,%s,%s,%s::jsonb) ON CONFLICT(mailbox,actor,draft_id) DO UPDATE
                SET payload=EXCLUDED.payload,operation_id=EXCLUDED.operation_id,
                    revision=support_email_drafts.revision+1,updated_at=now()
                WHERE support_email_drafts.revision=%s AND support_email_drafts.state='active'
                RETURNING revision''',(mailbox.lower(),str(actor),draft['id'],draft['operation_id'],payload,expected))
            row=cur.fetchone()
            if not row:raise ComposeError('This draft changed in another session. Reopen it before saving; your text is still here.')
        draft['_storage_version']=row['revision']

    def restore_draft(self, mailbox, actor, draft_id=None):
        with self.transaction() as cur:
            cur.execute('''SELECT d.payload,d.revision FROM support_email_drafts d
                WHERE d.mailbox=%s AND d.actor=%s AND d.state='active'
                AND (%s::uuid IS NULL OR d.draft_id=%s::uuid)
                AND NOT EXISTS(SELECT 1 FROM support_email_outbox o WHERE o.mailbox=d.mailbox
                    AND o.operation_id=d.operation_id AND o.status='accepted')
                ORDER BY d.updated_at DESC LIMIT 1''',(mailbox.lower(),str(actor),draft_id,draft_id))
            row=cur.fetchone()
        if not row:return None
        draft=decode(row['payload']);draft['_storage_version']=row['revision'];return draft

    def list_drafts(self,mailbox,actor):
        with self.transaction() as cur:
            cur.execute('''SELECT d.draft_id,d.payload->>'subject' AS subject,d.payload->>'to' AS recipients,d.updated_at
                FROM support_email_drafts d WHERE mailbox=%s AND actor=%s AND state='active'
                AND NOT EXISTS(SELECT 1 FROM support_email_outbox o WHERE o.mailbox=d.mailbox
                    AND o.operation_id=d.operation_id AND o.status='accepted')
                ORDER BY updated_at DESC LIMIT 50''',(mailbox.lower(),str(actor)))
            return [{k:str(v or '') for k,v in row.items()} for row in cur.fetchall()]

    def discard(self,mailbox,actor,draft_id):
        with self.transaction() as cur:
            cur.execute("UPDATE support_email_drafts SET state='discarded',updated_at=now() WHERE mailbox=%s AND actor=%s AND draft_id=%s",
                        (mailbox.lower(),str(actor),draft_id))

    def get(self,mailbox,operation):
        with self.transaction() as cur:
            cur.execute('SELECT * FROM support_email_outbox WHERE mailbox=%s AND operation_id=%s',(mailbox.lower(),operation))
            return dict(cur.fetchone() or {})

    def latest_sent(self,mailbox,actor):
        with self.transaction() as cur:
            cur.execute("""SELECT o.* FROM support_email_outbox o WHERE mailbox=%s AND actor=%s
                AND status='accepted' ORDER BY accepted_at DESC LIMIT 1""",(mailbox.lower(),str(actor)))
            return dict(cur.fetchone() or {})

    def get_receipt(self,mailbox,operation):
        # Status refreshes must not repeatedly transfer frozen MIME/attachments.
        with self.transaction() as cur:
            cur.execute('''SELECT operation_id,status,message_id,fingerprint,accepted_at,error_category,due_at
                FROM support_email_outbox WHERE mailbox=%s AND operation_id=%s''',(mailbox.lower(),operation))
            return dict(cur.fetchone() or {})

    def prepare(self,mailbox,operation,mime,actor='',folder='',policy='append'):
        operation=str(uuid.UUID(str(operation)))
        if len(mime['bytes'])>MAX_MIME_BYTES:raise ComposeError('Email exceeds the message size limit.')
        with self.transaction() as cur:
            cur.execute('''INSERT INTO support_email_outbox
                (mailbox,operation_id,actor,message_id,fingerprint,payload,sent_folder,sent_policy)
                VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s,%s) ON CONFLICT(mailbox,operation_id) DO NOTHING''',
                (mailbox.lower(),operation,str(actor),mime['message_id'],hashlib.sha256(mime['bytes']).hexdigest(),encode(mime),folder or '',policy))
        return self.get(mailbox,operation)

    def claim(self,mailbox,operation):
        with self.transaction() as cur:
            cur.execute("""UPDATE support_email_outbox SET status='in_progress',attempts=attempts+1,
                updated_at=now(),due_at=now()+interval '2 minutes'
                WHERE mailbox=%s AND operation_id=%s AND status='queued' AND due_at<=now() RETURNING *""",(mailbox.lower(),operation))
            return dict(cur.fetchone() or {})

    def finish(self,mailbox,operation,result):
        status=result['status'] if result.get('status') in {'accepted','rejected','unknown'} else 'unknown'
        with self.transaction() as cur:
            cur.execute("""UPDATE support_email_outbox SET status=%s,error_category=%s,
                accepted_at=CASE WHEN %s='accepted' THEN COALESCE(accepted_at,now()) ELSE accepted_at END,
                updated_at=now(),due_at=now()+interval '10 seconds'
                WHERE mailbox=%s AND operation_id=%s AND status<>'accepted'""",
                (status,result.get('error_category',''),status,mailbox.lower(),operation))
            if status=='rejected' and result.get('retryable'):
                # Only an explicit negative acknowledgement / failure BEFORE DATA
                # can be retried. Never retry an ambiguous SMTP handoff.
                cur.execute("""UPDATE support_email_outbox SET status='queued',
                    due_at=now()+(30*power(2,attempts-1)+random()*5)*interval '1 second'
                    WHERE mailbox=%s AND operation_id=%s AND status='rejected' AND attempts<3""",
                    (mailbox.lower(),operation))
        LOG.info('email_send_result operation_id=%s result=%s category=%s',operation,status,result.get('error_category',''))

    def due(self,mailbox):
        with self.transaction() as cur:
            # Reserve reconciliation/copy work across processes, without holding a DB
            # transaction open during IMAP. Expired sending is NEVER sent again.
            cur.execute("""SELECT operation_id FROM support_email_outbox WHERE mailbox=%s AND due_at<=now()
                AND (status='queued' OR (status IN ('in_progress','unknown') AND reconcile_attempts<6)
                    OR (status='accepted' AND copy_status NOT IN ('present','appended') AND reconcile_attempts<6))
                ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1""",(mailbox.lower(),))
            row=cur.fetchone()
            if not row:return None
            cur.execute("""UPDATE support_email_outbox SET due_at=CASE WHEN status='queued' THEN due_at ELSE now()+interval '2 minutes' END,
                status=CASE WHEN status='in_progress' THEN 'unknown' ELSE status END,
                reconcile_attempts=reconcile_attempts+CASE WHEN status='queued' THEN 0 ELSE 1 END WHERE mailbox=%s AND operation_id=%s RETURNING *""",
                (mailbox.lower(),row['operation_id']))
            return dict(cur.fetchone())

    def copy_state(self,mailbox,operation,state,*,claim=False):
        with self.transaction() as cur:
            cur.execute("""UPDATE support_email_outbox SET copy_status=%s,updated_at=now()
                WHERE mailbox=%s AND operation_id=%s AND status='accepted'
                AND (%s=FALSE OR copy_status IN ('pending','failed')) RETURNING operation_id""",
                (state,mailbox.lower(),operation,claim))
            return cur.fetchone() is not None

    def diagnostics(self,mailbox):
        with self.transaction() as cur:
            cur.execute('SELECT status,count(*) AS count FROM support_email_outbox WHERE mailbox=%s GROUP BY status',(mailbox.lower(),))
            counts={r['status']:r['count'] for r in cur.fetchall()}
            cur.execute('''SELECT status,error_category,updated_at FROM support_email_outbox
                WHERE mailbox=%s AND attempts>0 ORDER BY updated_at DESC LIMIT 1''',(mailbox.lower(),))
            attempt=cur.fetchone()
            return {'counts':counts,'last_attempt':{k:str(v) for k,v in attempt.items()} if attempt else None}


class DurableRegistry:
    def __init__(self,store=None):self.store=store or MailStore();self.cache={};self.lock=threading.Lock()
    def get(self,operation,mailbox):
        if not operation:return {}
        key=(mailbox.lower(),operation)
        with self.lock:
            cached=self.cache.get(key)
            if cached and time.monotonic()-cached[0]<3:return dict(cached[1])
        row=self.store.get_receipt(mailbox,operation);result=receipt(row) if row else {}
        with self.lock:
            if len(self.cache)>1000:self.cache.clear()
            self.cache[key]=(time.monotonic(),result)
        return result
    def invalidate(self,mailbox,operation):
        with self.lock:self.cache.pop((mailbox.lower(),operation),None)
    def prepare(self,operation,mailbox,mime,**kwargs):
        row=self.store.prepare(mailbox,operation,mime,**kwargs);self.invalidate(mailbox,operation);return receipt(row)
    def submit(self,operation,mailbox,mime,provider,*,progress=None):
        self.store.prepare(mailbox,operation,mime)
        row=self.store.claim(mailbox,operation)
        if not row:return receipt(self.store.get(mailbox,operation))
        def accepted(percent,label):
            if percent==100:self.store.finish(mailbox,operation,{'status':'accepted'})
            report_progress(progress,percent,label)
        try:
            result=provider.submit(decode(row['payload']),mailbox=mailbox,progress=accepted)
        except BaseException:
            self.store.finish(mailbox,operation,{'status':'unknown','error_category':'UNKNOWN'})
            raise
        self.store.finish(mailbox,operation,result);self.invalidate(mailbox,operation)
        return receipt(self.store.get(mailbox,operation))
    def reconcile(self,operation,mailbox,imap,folder):
        row=self.store.get(mailbox,operation)
        if not row:return {}
        if row['status']=='unknown' and folder and imap.find_message_id(folder,row['message_id']):
            self.store.finish(mailbox,operation,{'status':'accepted'})
            self.store.copy_state(mailbox,operation,'present');self.invalidate(mailbox,operation)
        return receipt(self.store.get(mailbox,operation))
    def save_sent(self,operation,mailbox,imap,mime,folder,policy,*,retry=False):
        row=self.store.get(mailbox,operation)
        if row.get('status')!='accepted' or hashlib.sha256(mime['bytes']).hexdigest()!=row['fingerprint']:
            return {'status':'unknown','notice':'Sent copy requires confirmed acceptance.'}
        if row['copy_status'] in {'present','appended'}:return {'status':row['copy_status'],'notice':'Sent copy saved.'}
        if not folder:return {'status':'failed','retryable':True,'notice':'Map the Sent folder before saving its copy.'}
        try:
            if imap.find_message_id(folder,row['message_id']):
                self.store.copy_state(mailbox,operation,'present');return {'status':'present','notice':'Sent copy verified.'}
            if policy=='append' and self.store.copy_state(mailbox,operation,'attempting',claim=True):
                try:imap.append_message(folder,mime['bytes'])
                except Exception as error:
                    safe=getattr(error,'code','') in {'append_not_started','append_rejected'}
                    self.store.copy_state(mailbox,operation,'failed' if safe else 'unknown')
                    return {'status':'failed' if safe else 'unknown','retryable':safe,'notice':'Email sent; Sent copy pending.'}
                self.store.copy_state(mailbox,operation,'appended');return {'status':'appended','notice':'Sent copy saved.'}
            return {'status':'pending','notice':'Email sent; checking its Sent copy.'}
        except Exception:
            return {'status':'unknown','notice':'Email sent; Sent copy verification unavailable.'}


REGISTRY=DurableRegistry()


class OutboxWorker:
    """Lifecycle-owned worker; database claims survive browser/app restarts."""
    def __init__(self,imap_config,smtp_config,registry=None):
        self.imap_config=imap_config;self.smtp_config=smtp_config;self.registry=registry or REGISTRY
        self.stop=threading.Event();self.thread=None
    def tick(self,imap=None,smtp=None):
        from support_email_provider import ImapProvider,folder_roles
        from support_email_smtp import SMTPProvider
        mailbox=self.imap_config.address;row=self.registry.store.due(mailbox)
        if not row:return False
        imap=imap or ImapProvider(self.imap_config);smtp=smtp or SMTPProvider(self.smtp_config)
        operation=str(row['operation_id']);mime=decode(row['payload'])
        LOG.info('email_outbox_work operation_id=%s state=%s attempt=%s',operation,row['status'],row['attempts'])
        if row['status']=='queued':self.registry.submit(operation,mailbox,mime,smtp)
        folder=row['sent_folder']
        if not folder:folder=folder_roles(imap.discover_folders()['folders']).get('sent')
        result=self.registry.reconcile(operation,mailbox,imap,folder)
        if result.get('status')=='accepted':
            self.registry.save_sent(operation,mailbox,imap,mime,folder,row['sent_policy'])
        return True
    def run(self):
        failures=0
        while not self.stop.is_set():
            delay=5
            try:
                self.tick();failures=0
            except Exception as error:
                failures=min(6,failures+1)
                delay=min(300,5*2**failures)+random.uniform(0,5)
                LOG.warning('email_outbox_worker category=%s retry_seconds=%d',type(error).__name__,delay)
            self.stop.wait(delay)
    def start(self):
        if not self.thread and self.imap_config.configured and self.smtp_config.configured:
            self.thread=threading.Thread(target=self.run,name='email-outbox',daemon=True);self.thread.start()
    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=2)
