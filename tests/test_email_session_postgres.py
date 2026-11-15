"""Real credentials, signed tokens and PostgreSQL account revocation; no auth mocks."""
import asyncio
from concurrent.futures import Future
import os
import secrets
import time
import unittest
import uuid

import os_accounts
import sc_auth
import top_bar_security
from starlette.requests import Request
from support_email_completion import issue, read_ready, revoke


@unittest.skipUnless(os.getenv('LOCAL_ACCOUNT_TEST_DSN'), 'Requires disposable loopback PostgreSQL')
class EmailSessionPostgresTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import conninfo_to_dict
        dsn=os.environ['LOCAL_ACCOUNT_TEST_DSN']
        cfg=conninfo_to_dict(dsn)
        if cfg.get('host') not in ('127.0.0.1','localhost'):
            raise ValueError('Only isolated loopback PostgreSQL is allowed')
        cls.database='email_auth_'+uuid.uuid4().hex
        cls.admin=psycopg.connect(dsn,autocommit=True)
        cls.admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(cls.database)))
        cls.old_env={k:os.environ.get(k) for k in ('DATABASE_URL','SPORTS_CAVE_AUTH_SECRET')}
        os.environ['DATABASE_URL']=('postgresql://'+cfg['user']+'@'+cfg['host']+':'+cfg.get('port','5432')+'/'+cls.database
            +'?sslmode=disable')
        os.environ['SPORTS_CAVE_AUTH_SECRET']=secrets.token_urlsafe(32)
        cls.old_store=os_accounts.DEFAULT_STORE
        cls.store=os_accounts.PostgresAccountStore()
        os_accounts.DEFAULT_STORE=cls.store
        cls.password=secrets.token_urlsafe(24)
        cls.users=[cls.store.create_user(username='synthetic-'+str(i),email='synthetic-'+str(i)+'@example.test',
            display_name='Synthetic release user '+str(i),password_hash=sc_auth.hash_password(cls.password),
            role='worker',page_keys=['email']) for i in range(2)]

    @classmethod
    def tearDownClass(cls):
        from psycopg import sql
        os_accounts.DEFAULT_STORE=cls.old_store
        for key,value in cls.old_env.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value
        cls.admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(cls.database)))
        cls.admin.close()

    def setUp(self):
        self.scope=uuid.uuid4().hex
        self.future=Future()
        self.ticket=issue(self.future,self.users[0]['id'],self.scope)
        self.addCleanup(revoke,self.scope)

    def login(self,index=0):
        user,reason=os_accounts.authenticate_user(self.users[index]['username'],self.password)
        self.assertIsNotNone(user,reason)
        return top_bar_security.create_top_bar_token(user,allowed_routes=['Email'])

    def request(self,token):
        return Request({'type':'http','method':'GET','path':'/api/os/email/read-ready',
            'headers':[(b'authorization',('Bearer '+token).encode()),(b'x-email-read',self.ticket.encode())]})

    async def test_real_login_signature_actor_and_permission_checks(self):
        self.future.set_result({'private':'must never leave the component'})
        token=self.login()
        response=await read_ready(self.request(token))
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.body,b'{"ready":true}')
        self.assertEqual(response.headers['cache-control'],'no-store')
        for invalid in ('',token+'x',self.login(1)):
            self.assertEqual((await read_ready(self.request(invalid))).status_code,403)
        self.assertIsNone(os_accounts.authenticate_user(self.users[0]['username'],'wrong-password')[0])

    async def test_database_permission_removal_revokes_pending_request(self):
        request=self.request(self.login())
        pending=asyncio.create_task(read_ready(request))
        await asyncio.sleep(.1)
        with self.store._connect() as conn:
            conn.execute('UPDATE os_user_page_permissions SET can_access=false WHERE user_id=%s',(self.users[0]['id'],))
        try:
            self.future.set_result(None)
            self.assertEqual((await pending).status_code,403)
        finally:
            with self.store._connect() as conn:
                conn.execute('UPDATE os_user_page_permissions SET can_access=true WHERE user_id=%s',(self.users[0]['id'],))

    async def test_remote_logout_session_version_rejects_old_bearer(self):
        token=self.login();self.future.set_result(None)
        with self.store._connect() as conn:
            conn.execute('UPDATE os_users SET session_version=session_version+1 WHERE id=%s',(self.users[0]['id'],))
        self.assertEqual((await read_ready(self.request(token))).status_code,403)
        self.assertEqual((await read_ready(self.request(self.login()))).status_code,200)

    async def test_expiry_and_account_disable_are_checked_again(self):
        token=self.login();self.future.set_result(None)
        with self.store._connect() as conn:
            conn.execute('UPDATE os_users SET is_active=false WHERE id=%s',(self.users[0]['id'],))
        try:self.assertEqual((await read_ready(self.request(token))).status_code,403)
        finally:
            with self.store._connect() as conn:
                conn.execute('UPDATE os_users SET is_active=true WHERE id=%s',(self.users[0]['id'],))
        expired=top_bar_security.create_top_bar_token(self.store.get_user(self.users[0]['id']),allowed_routes=['Email'],now=time.time()-7200)
        self.assertEqual((await read_ready(self.request(expired))).status_code,403)

    async def test_real_http_proxy_forwards_bearer_and_ticket_without_public_cache(self):
        import socket
        import httpx
        import uvicorn
        from starlette.applications import Starlette
        from starlette.responses import Response
        from starlette.routing import Route
        from support_email_completion import PATH
        self.future.set_result({'body':'never transport private body'})
        servers=[];tasks=[];sockets=[]
        async def start(app):
            sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen();sockets.append(sock)
            server=uvicorn.Server(uvicorn.Config(app,log_level='error'));servers.append(server)
            tasks.append(asyncio.create_task(server.serve(sockets=[sock])))
            for _ in range(100):
                if server.started:return 'http://127.0.0.1:'+str(sock.getsockname()[1])
                await asyncio.sleep(.01)
            self.fail('Local acceptance server did not start')
        try:
            backend=await start(Starlette(routes=[Route(PATH,read_ready)]))
            async def forward(request):
                async with httpx.AsyncClient() as client:
                    response=await client.get(backend+PATH,headers=dict(request.headers))
                return Response(response.content,status_code=response.status_code,headers=dict(response.headers))
            proxy=await start(Starlette(routes=[Route(PATH,forward)]))
            async with httpx.AsyncClient() as client:
                headers={'Authorization':'Bearer '+self.login(),'X-Email-Read':self.ticket}
                response=await client.get(proxy+PATH,headers=headers)
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.json(),{'ready':True})
                self.assertEqual(response.headers['cache-control'],'no-store')
                self.assertNotIn('access-control-allow-origin',response.headers)
                for h in ({'X-Email-Read':self.ticket,'X-Forwarded-User':self.users[0]['id']},
                          {**headers,'Authorization':'Bearer '+self.login(1)},
                          {**headers,'X-Email-Read':'another-worker-missing-ticket'}):
                    self.assertEqual((await client.get(proxy+PATH,headers=h)).status_code,403)
                self.assertEqual((await client.post(proxy+PATH,headers=headers)).status_code,405)
        finally:
            for server in servers:server.should_exit=True
            if tasks:await asyncio.wait_for(asyncio.gather(*tasks),5)
            for sock in sockets:sock.close()

    async def test_event_stream_closes_after_real_account_revocation(self):
        from support_email_events import email_events
        request=self.request(self.login())
        async def receive():await asyncio.sleep(60)
        request._receive=receive
        response=await email_events(request)
        self.assertEqual(response.status_code,200)
        self.assertEqual(await anext(response.body_iterator),': connected\n\n')
        with self.store._connect() as conn:
            conn.execute('UPDATE os_users SET session_version=session_version+1 WHERE id=%s',(self.users[0]['id'],))
        with self.assertRaises(StopAsyncIteration):
            await asyncio.wait_for(anext(response.body_iterator),3)
