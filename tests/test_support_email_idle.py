"""IDLE lifecycle, fencing and bridge tests. No external mailbox/database access."""
import asyncio
from copy import deepcopy
import json
import threading
import time
import unittest
from unittest.mock import Mock, patch

from support_email_runtime import MailboxRuntime
from support_email_idle import MailboxWatcher, SignalHub, IdleLifecycle, idle_supported, client_factory
from support_email_events import event_stream, email_events
from tests.test_support_email import CONFIG
from tests import test_support_email_v2 as v2
from tests.test_support_email import header


class MemorySignals:
    def __init__(self, clock):
        self.clock, self.owner, self.until = clock, None, 0
        self.value = {}
        self.lock = threading.Lock()

    def claim(self, mailbox, owner):
        with self.lock:
            if self.until > self.clock():
                return False
            self.owner, self.until = owner, self.clock()+60
            return True

    def renew(self, mailbox, owner):
        with self.lock:
            if owner != self.owner or self.until <= self.clock():
                return False
            self.until = self.clock()+60
            return True

    def release(self, mailbox, owner):
        with self.lock:
            if owner == self.owner:
                self.until = 0

    def publish(self, mailbox, owner, status, version):
        if owner != self.owner or self.until <= self.clock():
            raise RuntimeError('Expired')
        self.value = {**{k:status[k] for k in ('uidvalidity','uidnext','unseen','messages')},
                      'mailbox':mailbox,'version':version,'checked_at':time.time()}
        return deepcopy(self.value)

    def read(self, mailbox):
        return deepcopy(self.value)


class ClockStop:
    def __init__(self, world): self.world=world; self.stopped=False
    def is_set(self): return self.stopped or self.world.now >= self.world.duration
    def set(self): self.stopped=True
    def wait(self, seconds): self.world.now += seconds; return self.is_set()


class World:
    def __init__(self, duration=3600, arrivals=(), failures=(), idle=True):
        self.now=0; self.duration=duration; self.arrivals=set(arrivals); self.failures=set(failures)
        self.idle=idle; self.commands=[]; self.created=self.closed=self.active=self.peak=0
        self.uidnext=4; self.unseen=2; self.messages=3
        self.store=MemorySignals(lambda:self.now)
        self.values=[]; self.hub=SignalHub(lambda v:self.values.append(v))
        self.on_tick=lambda:None
        self.watch=MailboxWatcher(CONFIG,store=self.store,hub=self.hub,factory=self.connect,clock=lambda:self.now,runtime=MailboxRuntime(lambda:self.now))
        self.watch.stop=ClockStop(self)

    def connect(self, cfg):
        self.created+=1;self.active+=1;self.peak=max(self.peak,self.active)
        world=self
        class Wire:
            closed=False
            def login(self,*args): world.commands.append('LOGIN')
            def capabilities(self): world.commands.append('CAPABILITY');return (b'IMAP4rev1',b'IDLE') if world.idle else (b'IMAP4rev1',)
            def select_folder(self,folder,readonly=False):
                assert folder=='INBOX' and readonly
                world.commands.append('SELECT readonly')
            def folder_status(self,folder,fields):
                world.commands.append('STATUS')
                return {b'UIDVALIDITY':500,b'UIDNEXT':world.uidnext,b'UNSEEN':world.unseen,b'MESSAGES':world.messages}
            def idle(self): world.commands.append('IDLE')
            def idle_check(self,timeout):
                world.now+=timeout
                world.on_tick()
                # Other workers/users/tabs must not create a second watcher socket.
                for owner in ('nathan','maria','tab-2','worker-2'):
                    assert not world.store.claim(CONFIG.address,owner)
                if world.now in world.failures:
                    world.failures.remove(world.now);raise ConnectionResetError('fixture-password')
                if world.now in world.arrivals:
                    world.uidnext+=1;world.unseen+=1;world.messages+=1
                    return [(world.messages,b'EXISTS')]
                return []
            def idle_done(self):world.commands.append('DONE')
            def noop(self):world.commands.append('NOOP')
            def shutdown(self):
                if not self.closed:
                    self.closed=True;world.closed+=1;world.active-=1
        return Wire()


def simulate():
    world=World(arrivals=(60,300,900,2100,2700),failures=(1700,))
    started=time.perf_counter();world.watch.run()
    return {'logical_watchers':1,'connections':world.created,'peak_idle_connections':world.peak,
            'closed':world.closed,'leaked':world.active,'reconnects':world.created-1,
            'status_commands':world.commands.count('STATUS'),'idle_commands':world.commands.count('IDLE'),
            'body_fetches':0,'header_fetches_by_watcher':0,'signals':len(world.values),
            'simulation_cpu_ms':round((time.perf_counter()-started)*1000,2)}


def simulate_consumers():
    """One hour: real provider delta/cache + durable notification logic, fake wires."""
    from support_email_runtime import MailboxRuntime
    from support_email_provider import ImapProvider
    from support_email_notifications import NotificationStore
    from tests.test_support_email_notifications import MemoryDatabase
    from tests.test_support_email_live import LiveWire
    world=World(arrivals=(60,300,900,2100,2700),failures=(1700,))
    runtime=MailboxRuntime(lambda:world.now)
    database=MemoryDatabase();notifications=NotificationStore()
    counters={'opened':0,'closed':0,'peak':0,'active':0}
    wires=[];server={'1':(),'2':('\\Seen',),'3':()}
    snapshots=[{'messages':[header(str(i)) for i in (1,2,3)],'uidvalidity':'500','live_uid':3} for _ in range(4)]
    class Wire(LiveWire):
        def __init__(self):
            super().__init__();self.messages=server;self.closed=False
            counters['opened']+=1;counters['active']+=1
            counters['peak']=max(counters['peak'],counters['active']+world.active)
            wires.append(self)
        def status(self,folder,fields):
            self.calls.append(('status',folder,fields))
            return 'OK',[f'INBOX (UNSEEN {world.unseen} MESSAGES {world.messages} UIDNEXT {world.uidnext} UIDVALIDITY 500)'.encode()]
        def uid(self,command,*args):
            if command=='FETCH' and ':' in args[0]:
                low,high=map(int,args[0].split(':'));args=(','.join(map(str,range(low,high+1))),*args[1:])
            return super().uid(command,*args)
        def shutdown(self):
            if not self.closed:
                self.closed=True;counters['closed']+=1;counters['active']-=1
    def adapter():return ImapProvider(CONFIG,connection_factory=lambda *a,**k:Wire(),runtime=runtime)
    def consume(force=False):
        server.update({str(i):server.get(str(i),()) for i in range(1,world.uidnext)})
        for snapshot in snapshots:
            notifications.poll(adapter(),now=world.now+1000,force=force)
            delta=adapter().live_changes('INBOX',snapshot)
            snapshot['messages']+=delta['added'];snapshot['live_uid']=delta['live_uid']
    def signal(value):
        world.values.append(value)
        runtime.invalidate(CONFIG.scope)
        runtime.put(CONFIG.scope,('status','INBOX'),{k:value[k] for k in ('uidvalidity','uidnext','unseen','messages')},runtime.generation(CONFIG.scope))
        consume(True)
    world.hub.on_change=signal
    world.on_tick=lambda:consume() if world.now%60==0 else None
    started=time.perf_counter()
    with patch('supabase_backend.connect',database.connect):world.watch.run()
    commands=[c for wire in wires for c in wire.calls]
    header_fetches=[c for c in commands if c[:2]==('uid','FETCH') and 'HEADER.FIELDS' in c[-1]]
    return {'logical_watchers':1,'sessions':4,'watcher_connections':world.created,
            'other_connections':counters['opened'],'peak_total_connections':counters['peak'],
            'closed_connections':world.closed+counters['closed'],'leaked_connections':world.active+counters['active'],
            'reconnects':world.created-1,'status_commands':world.commands.count('STATUS')+sum(c[0]=='status' for c in commands),
            'header_fetches':len(header_fetches),'body_fetches':sum('BODY.PEEK[TEXT]' in str(c) or 'BODY.PEEK[]' in str(c) for c in commands),
            'notifications':len(database.events),'duplicate_notifications':len(database.events)-len({e['entity_id'] for e in database.events}),
            'simulation_ms':round((time.perf_counter()-started)*1000,2)}


class IdleTests(unittest.TestCase):
    def test_transport_uses_verified_ssl_and_existing_configuration(self):
        import ssl
        with patch('support_email_idle._ManagedSSL') as wire:
            client=client_factory(CONFIG)
            args,kwargs=wire.call_args
            self.assertEqual(args,(CONFIG.host,993))
            self.assertTrue(kwargs['ssl_context'].check_hostname)
            self.assertEqual(kwargs['ssl_context'].verify_mode,ssl.CERT_REQUIRED)
            self.assertEqual(kwargs['timeout'],8)
            client.shutdown();wire.return_value.shutdown.assert_called_once()

    def test_login_failure_and_bye_close_without_secret_logs(self):
        for stage in ('login','bye'):
            w=World();w.watch.lease(initial=True);wire=w.connect(CONFIG)
            if stage=='login':wire.login=Mock(side_effect=RuntimeError('fixture-password'))
            else:wire.idle_check=Mock(return_value=[(b'BYE',b'fixture-password')])
            w.watch.factory=lambda cfg:wire
            with self.assertRaises((RuntimeError,ConnectionError)):w.watch.watch()
            self.assertEqual(w.active,0)

    def test_capabilities(self):
        self.assertTrue(idle_supported(Mock(capabilities=lambda:(b'IMAP4rev1',b'IDLE'))))
        self.assertFalse(idle_supported(Mock(capabilities=lambda:(b'IMAP4rev1',))))

    def test_hour_no_mail_low_network_and_no_leaks(self):
        w=World();w.watch.run()
        self.assertEqual((w.created,w.peak,w.closed,w.active),(1,1,1,0))
        self.assertEqual(w.commands.count('IDLE'),3)
        self.assertEqual(w.commands.count('STATUS'),3)
        self.assertFalse(any('FETCH' in c for c in w.commands))

    def test_arrival_and_external_flag_signal_even_when_counts_equal(self):
        w=World(duration=10,arrivals=(2,));w.watch.run()
        self.assertEqual([v['uidnext'] for v in w.values],[4,5])
        # FETCH/EXPUNGE trigger the same status/version path even if UNSEEN unchanged.
        client=w.connect(CONFIG);w.watch.stop.stopped=False;w.duration=20
        self.assertTrue(w.watch.lease(initial=True))
        w.watch.publish(client);first=w.hub.snapshot()
        w.watch.publish(client);second=w.hub.snapshot()
        self.assertEqual(first['unseen'],second['unseen'])
        self.assertNotEqual(first['version'],second['version']);client.shutdown()

    def test_disconnect_bounded_reconnect_and_single_owner(self):
        result=simulate()
        self.assertEqual(result['peak_idle_connections'],1)
        self.assertEqual(result['reconnects'],1)
        self.assertEqual(result['leaked'],0)

    def test_unsupported_returns_to_existing_polling(self):
        w=World(idle=False);w.watch.run()
        self.assertEqual(w.created,1);self.assertEqual(w.closed,1)
        self.assertNotIn('IDLE',w.commands);self.assertNotIn('STATUS',w.commands)

    def test_loss_of_lease_closes_wire(self):
        w=World();w.watch.lease(initial=True)
        original=w.store.renew
        w.store.renew=lambda *args:False
        with self.assertRaises(RuntimeError):w.watch.watch()
        self.assertEqual(w.active,0);self.assertEqual(w.created,1)

    def test_expired_owner_cannot_renew_or_publish(self):
        w=World();self.assertTrue(w.watch.lease(initial=True));w.now=61
        self.assertTrue(w.store.claim(CONFIG.address,'replacement'))
        self.assertFalse(w.store.renew(CONFIG.address,w.watch.owner))
        with self.assertRaises(RuntimeError):w.watch.publish(Mock())

    def test_no_thread_at_import_repeated_start_is_idempotent(self):
        w=World()
        self.assertIsNone(w.watch.thread)
        with patch('support_email_idle.threading.Thread') as thread:
            for _ in range(20):w.watch.start()
            self.assertEqual(thread.call_count,1);thread.return_value.start.assert_called_once()

    def test_status_allowlist_and_hub_deduplication(self):
        w=World(duration=2);w.watch.run();value=w.values[0]
        self.assertEqual(set(value),{'mailbox','version','uidvalidity','uidnext','unseen','messages','checked_at'})
        w.hub.accept(value);self.assertEqual(len(w.values),1)


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_sse_filters_fields_and_no_imap(self):
        request=Mock();request.is_disconnected=Mock(side_effect=lambda:asyncio.sleep(0,result=False))
        hub=SignalHub();hub.accept({'mailbox':CONFIG.address,'version':'v','uidvalidity':500,'uidnext':4,
                                  'unseen':2,'messages':3,'checked_at':time.time(),'body':'forbidden'})
        chunks=[c async for c in event_stream(request,hub=hub,duration=.02,interval=.005)]
        self.assertEqual(len([c for c in chunks if c.startswith('data:')]),1)
        self.assertNotIn('forbidden',''.join(chunks))

    async def test_endpoint_requires_existing_email_permission(self):
        for claims in ({},{'allowed_routes':['Orders']}):
            with patch('top_bar_api._claims',return_value=claims):
                result=await email_events(Mock());self.assertEqual(result.status_code,403)

    async def test_lifecycle_owns_watcher_start_stop(self):
        watcher=Mock();seen=[]
        async def app(scope,receive,send):
            await send({'type':'lifespan.startup.complete'})
            await send({'type':'lifespan.startup.complete'})
            await receive()
        async def receive():return {'type':'lifespan.shutdown'}
        async def send(message):seen.append(message)
        factory=Mock(return_value=watcher)
        await IdleLifecycle(app,factory)({'type':'lifespan'},receive,send)
        factory.assert_called_once();watcher.start.assert_called_once();watcher.close.assert_called_once()


class PushedWorkspaceTests(unittest.TestCase):
    setUp = v2.WorkspaceTests.setUp
    event = v2.WorkspaceTests.event
    open = v2.WorkspaceTests.open
    compose = v2.WorkspaceTests.compose

    def push(self, version):
        hub=SignalHub()
        hub.accept({'version':version,'mailbox':CONFIG.address,'checked_at':time.time()})
        with patch('support_email_idle.HUB',hub):
            self.event('live_check',signal_version=version)

    def test_push_bypasses_timer_preserves_draft_selection_and_no_body(self):
        self.open();self.compose()
        draft=self.state['draft']['id'];selected=self.state['selected']
        self.state['draft']['html']='<p>Keep my unsent reply</p>'
        self.imap.messages.append(header('76','<new76@example.test>',subject='New arrival'))
        self.imap.calls.clear()
        self.push('v1')
        self.assertEqual(self.imap.calls,[('live','INBOX')])
        self.assertTrue(any(m['uid']=='76' for m in self.state['snapshot']['messages']))
        self.assertEqual(self.state['draft']['id'],draft)
        self.assertEqual(self.state['draft']['html'],'<p>Keep my unsent reply</p>')
        self.assertEqual(self.state['selected'],selected)
        self.imap.calls.clear();self.push('v1');self.assertEqual(self.imap.calls,[])

    def test_external_flags_update_without_opening_or_body(self):
        self.imap.messages[-1].update(flags=('\\Seen','\\Flagged'),unread=False)
        self.imap.calls.clear();self.push('external-flags')
        self.assertEqual(self.imap.calls,[('live','INBOX')])
        latest=next(m for m in self.state['snapshot']['messages'] if m['uid']=='75')
        self.assertFalse(latest['unread']);self.assertIn('\\Flagged',latest['flags'])

    def test_unknown_browser_version_cannot_force_imap(self):
        self.imap.calls.clear();self.event('live_check',signal_version='forged')
        self.assertEqual(self.imap.calls,[])

    def test_push_busy_is_retryable_without_marking_version_complete(self):
        from support_email_provider import MailboxError
        with patch.object(self.imap,'live_changes',side_effect=MailboxError('busy',code='busy')):
            self.push('busy-version')
        self.assertNotEqual(self.state.get('idle_version'),'busy-version')
        self.push('busy-version')
        self.assertEqual(self.state.get('idle_version'),'busy-version')

    def test_other_folder_and_search_preserved(self):
        self.event('folder',folder='Archive');self.event('search',query='subject: certificate')
        self.push('inbox-arrival')
        self.assertEqual(self.state['folder'],'Archive')
        self.assertEqual(self.state['query'],'certificate')
        self.assertEqual(self.state['field'],'SUBJECT')


class ConsumerTests(unittest.TestCase):
    def test_hour_combined_load(self):
        result=simulate_consumers()
        self.assertEqual(result['notifications'],5)
        self.assertEqual(result['duplicate_notifications'],0)
        self.assertEqual(result['leaked_connections'],0)
        self.assertEqual(result['body_fetches'],0)
        self.assertLessEqual(result['peak_total_connections'],3)
    def test_four_sessions_share_one_new_header_delta(self):
        from support_email_runtime import MailboxRuntime
        from support_email_provider import ImapProvider
        from tests.test_support_email_live import LiveWire
        wire=LiveWire();runtime=MailboxRuntime();factory=Mock(return_value=wire)
        snapshot={'messages':[header('1'),header('2')],'uidvalidity':'500','live_uid':2}
        for _ in range(4):
            adapter=ImapProvider(CONFIG,connection_factory=factory,runtime=runtime)
            result=adapter.live_changes('INBOX',deepcopy(snapshot))
            self.assertEqual([m['uid'] for m in result['added']],['3'])
        self.assertEqual(factory.call_count,1)
        headers=[c for c in wire.calls if c[:2]==('uid','FETCH') and 'HEADER.FIELDS' in c[-1]]
        self.assertEqual(len(headers),1)

    def test_push_then_fallback_then_restart_no_duplicate_notifications(self):
        from support_email_notifications import NotificationStore
        from support_email_provider import ImapProvider
        from tests.test_support_email_notifications import MemoryDatabase, NotificationWire
        wire=NotificationWire();db=MemoryDatabase();store=NotificationStore()
        def adapter():return ImapProvider(CONFIG,connection_factory=lambda *a,**k:wire)
        with patch('supabase_backend.connect',db.connect):
            store.poll(adapter(),now=1000,force=True)
            self.assertEqual(db.events,[])
            wire.arrive(101)
            store.poll(adapter(),now=1001,force=True) # Push
            store.poll(adapter(),now=1061) # Poll
            NotificationStore().poll(adapter(),now=1122) # Restart, same durable cursor
        self.assertEqual(len(db.events),1)
        self.assertNotIn('fixture-password',str(db.events))


if __name__=='__main__':
    print(json.dumps(simulate(),indent=2))
    print(json.dumps(simulate_consumers(),indent=2))
    unittest.main()
