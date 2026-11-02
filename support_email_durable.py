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
    created=row.get('created_at')
    if isinstance(created,str):created=datetime.fromisoformat(created.replace('Z','+00:00'))
    if isinstance(due,str):due=datetime.fromisoformat(due.replace('Z','+00:00'))
    delay=max(1000,int((due-datetime.now(timezone.utc)).total_seconds()*1000)) if due and status=='queued' else 1000
    source = 'smtp' if row.get('accepted_at') else 'provider_sent' if status == 'accepted' and row.get('copy_status') == 'present' else ''
    return {'confirmation_source':source, 'confirmed_at':str(row.get('updated_at') or ''),
            'operation_id':str(row['operation_id']), 'status':'in_progress' if status=='queued' else status,
            'transport_status':status,
            'retry_delay_ms':delay,
            'reconcile_attempts':int(row.get('reconcile_attempts') or 0),
            'next_check_at':str(due or '') if status in {'unknown','in_progress','accepted'} else '',
            'verification_overdue':bool(created and status=='unknown' and (datetime.now(timezone.utc)-created).total_seconds()>900),
            'message_id':row['message_id'], 'fingerprint':row['fingerprint'],
            'sent_at':str(row.get('accepted_at') or ''),
            'notice':{'queued':'Queued securely', 'in_progress':'Sending…',
                      'accepted':'Matching message confirmed in provider Sent; recipient delivery is not verified.' if source == 'provider_sent' else 'Mail server accepted the email; recipient delivery is not verified.',
                      'rejected':'Original send was not accepted. Review the draft before retrying.',
                      'unknown':'Outcome unresolved; background checks continue with backoff. Do not resend.' if int(row.get('reconcile_attempts') or 0)>=6 else 'Confirming original send. Do not resend.'}.get(status,''),
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

    def recent_recipients(self, mailbox, actor):
        """Narrow actor-owned address history; never retrieve MIME or other users' sends."""
        with self.transaction() as cur:
            cur.execute('''SELECT payload->'recipients' AS recipients FROM support_email_outbox
                WHERE mailbox=%s AND actor=%s AND status='accepted'
                ORDER BY accepted_at DESC NULLS LAST LIMIT 20''', (mailbox.lower(), str(actor)))
            return [email for row in cur.fetchall() for email in (row['recipients'] or []) if isinstance(email,str)][:500]

    def unresolved_receipts(self, mailbox, actor):
        """Actor-private startup warnings; never retrieve MIME for status UI."""
        with self.transaction() as cur:
            cur.execute('''SELECT operation_id,status,copy_status,message_id,accepted_at,error_category,
                due_at,reconcile_attempts,created_at,fingerprint FROM support_email_outbox
                WHERE mailbox=%s AND actor=%s AND (status IN ('queued','in_progress','unknown')
                    OR (status='accepted' AND copy_status NOT IN ('present','appended')))
                ORDER BY created_at DESC LIMIT 50''', (mailbox.lower(), str(actor)))
            return [dict(receipt(row), copy_status=row['copy_status']) for row in cur.fetchall()]

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
                AND status='accepted' ORDER BY COALESCE(accepted_at,updated_at) DESC LIMIT 1""",(mailbox.lower(),str(actor)))
            return dict(cur.fetchone() or {})

    def get_receipt(self,mailbox,operation):
        # Status refreshes must not repeatedly transfer frozen MIME/attachments.
        with self.transaction() as cur:
            cur.execute('''SELECT operation_id,status,copy_status,message_id,fingerprint,accepted_at,error_category,due_at,reconcile_attempts,created_at,updated_at
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
        # Cover SMTP connect/auth plus the DATA response deadline before a
        # separate worker treats an interrupted submission as uncertain.
        with self.transaction() as cur:
            cur.execute("""UPDATE support_email_outbox SET status='in_progress',attempts=attempts+1,
                updated_at=now(),due_at=now()+interval '5 minutes'
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
                AND (status IN ('queued','in_progress','unknown')
                    OR (status='accepted' AND copy_status NOT IN ('present','appended')))
                ORDER BY CASE WHEN status='queued' THEN 0 ELSE 1 END,created_at FOR UPDATE SKIP LOCKED LIMIT 1""",(mailbox.lower(),))
            row=cur.fetchone()
            if not row:return None
            cur.execute("""UPDATE support_email_outbox SET due_at=CASE WHEN status='queued' THEN due_at
                    WHEN reconcile_attempts<6 THEN now()+interval '2 minutes'
                    ELSE now()+(LEAST(3600,900*power(2,LEAST(2,reconcile_attempts-6)))+random()*30)*interval '1 second' END,
                status=CASE WHEN status='in_progress' THEN 'unknown' ELSE status END,
                reconcile_attempts=reconcile_attempts+CASE WHEN status='queued' THEN 0 ELSE 1 END WHERE mailbox=%s AND operation_id=%s RETURNING *""",
                (mailbox.lower(),row['operation_id']))
            return dict(cur.fetchone())

    def confirm_sent(self, mailbox, operation):
        # A matching provider Sent copy is not an observed SMTP 250 or delivery
        # receipt. Preserve the absence of an actual SMTP acceptance timestamp.
        with self.transaction() as cur:
            cur.execute("""UPDATE support_email_outbox SET status='accepted',copy_status='present',
                error_category='',updated_at=now() WHERE mailbox=%s AND operation_id=%s
                AND status IN ('unknown','in_progress')""", (mailbox.lower(), operation))

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
    def __init__(self,store=None):self.store=store or MailStore();self.cache={};self.lock=threading.Lock();self.acceptance_pending={}
    def get(self,operation,mailbox):
        if not operation:return {}
        key=(mailbox.lower(),operation)
        with self.lock:
            if key in self.acceptance_pending:return dict(self.acceptance_pending[key])
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
    def _remember_acceptance(self, mailbox, operation, row):
        value=receipt(dict(row,status='accepted',accepted_at=datetime.now(timezone.utc)))
        value.update(persistence_pending=True,notice='Mail server accepted the email; receipt storage is recovering. Do not resend.')
        with self.lock:self.acceptance_pending[(mailbox.lower(),operation)]=value
        self._persist_acceptance(mailbox,operation)

    def _persist_acceptance(self, mailbox, operation):
        key=(mailbox.lower(),operation)
        try:self.store.finish(mailbox,operation,{'status':'accepted'})
        except Exception:
            LOG.warning('email_acceptance_persistence operation_id=%s category=DATABASE',operation)
            return False
        with self.lock:
            value=self.acceptance_pending.pop(key,None)
            if value:
                value=dict(value,persistence_pending=False,notice='Mail server accepted the email; recipient delivery is not verified.')
                if len(self.cache)>=1000:self.cache.clear()
                self.cache[key]=(time.monotonic(),value)
        return True

    def flush_acceptances(self, limit=3):
        with self.lock:keys=list(self.acceptance_pending)[:limit]
        for mailbox,operation in keys:
            if not self._persist_acceptance(mailbox,operation):break

    def submit(self,operation,mailbox,mime,provider,*,progress=None):
        with self.lock:
            pending=self.acceptance_pending.get((mailbox.lower(),operation))
            if pending:return dict(pending)
            if len(self.acceptance_pending)>=1000:
                raise ComposeError('Receipt storage is recovering. Nothing new was submitted.')
        self.store.prepare(mailbox,operation,mime)
        row=self.store.claim(mailbox,operation)
        if not row:return receipt(self.store.get(mailbox,operation))
        known_accepted=False
        def accepted(percent,label):
            nonlocal known_accepted
            if percent==100:
                known_accepted=True
                self._remember_acceptance(mailbox,operation,row)
            report_progress(progress,percent,label)
        try:
            result=provider.submit(decode(row['payload']),mailbox=mailbox,progress=accepted)
        except BaseException:
            if not known_accepted:
                self.store.finish(mailbox,operation,{'status':'unknown','error_category':'UNKNOWN'})
            raise
        if known_accepted or result.get('status')=='accepted':
            # The SMTP progress hook already captured/persisted the 250. Do not
            # overwrite that evidence or create a false recovery warning with a
            # redundant write after the provider returns.
            if not known_accepted:self._remember_acceptance(mailbox,operation,row)
            return self.get(operation,mailbox)
        self.store.finish(mailbox,operation,result);self.invalidate(mailbox,operation)
        return receipt(self.store.get(mailbox,operation))
    def reconcile(self,operation,mailbox,imap,folder):
        row=self.store.get(mailbox,operation)
        if not row:return {}
        if row['status']=='unknown' and folder and imap.find_message_id(folder,row['message_id']):
            self.store.confirm_sent(mailbox,operation);self.invalidate(mailbox,operation)
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
        self.stop=threading.Event();self.thread=None;self.start_lock=threading.Lock()
    def tick(self,imap=None,smtp=None):
        from support_email_provider import ImapProvider,folder_roles
        from support_email_smtp import SMTPProvider
        self.registry.flush_acceptances()
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
        with self.start_lock:
            if (self.stop.is_set() or (self.thread and self.thread.is_alive())
                    or not self.imap_config.configured or not self.smtp_config.configured):return
            self.thread=threading.Thread(target=self.run,name='email-outbox',daemon=True);self.thread.start()
    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=2)
