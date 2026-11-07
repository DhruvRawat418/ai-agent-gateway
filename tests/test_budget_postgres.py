"""Opt-in real row-lock test. Set GATEWAY_TEST_POSTGRES_URL to a disposable test DB."""
import os
import unittest
import uuid
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace as S
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import test_dashboard
from database import Base, Tenant, UsageRecord
from main import proxy_chat, ChatRequest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials as Credentials

@unittest.skipUnless(os.getenv('GATEWAY_TEST_POSTGRES_URL'), 'Requires disposable PostgreSQL test database')
class PostgresBudgetTests(unittest.TestCase):
    def test_competing_requests_recheck_committed_balance(self):
        engine=create_engine(os.environ['GATEWAY_TEST_POSTGRES_URL'])
        self.assertEqual(engine.dialect.name,'postgresql')
        schema='gateway_test_'+uuid.uuid4().hex
        with engine.begin() as conn:conn.execute(text(f'CREATE SCHEMA {schema}'))
        isolated=engine.execution_options(schema_translate_map={None:schema})
        entered, release, second_started=Event(),Event(),Event()
        second_pid=[]
        try:
            Base.metadata.create_all(isolated)
            Session=sessionmaker(bind=isolated)
            with Session.begin() as db:db.add(Tenant(name='Test',api_key='test',token_budget=100))
            class Provider:
                calls=0
                def create(self,**kwargs):
                    self.calls+=1
                    entered.set()
                    if not release.wait(15):raise TimeoutError('test barrier timed out')
                    return S(model='gpt-4o-mini',usage=S(total_tokens=90,prompt_tokens=60,completion_tokens=30),choices=[S(message=S(content='Hello'),finish_reason='stop')])
            provider=Provider();client=S(chat=S(completions=provider))
            def call(second=False):
                with Session() as db:
                    if second:
                        second_pid.append(db.execute(text('SELECT pg_backend_pid()')).scalar_one())
                        second_started.set()
                    try:return proxy_chat(ChatRequest(prompt='Hi'),Credentials(scheme='Bearer',credentials='test'),db,client)
                    except HTTPException as error:return error.status_code
            with ThreadPoolExecutor(max_workers=2) as pool:
                first=pool.submit(call)
                try:
                    self.assertTrue(entered.wait(5))
                    second=pool.submit(call,True)
                    self.assertTrue(second_started.wait(5))
                    deadline=time.monotonic()+5
                    waiting=False
                    with engine.connect() as observer:
                        while time.monotonic()<deadline:
                            blockers=observer.execute(text('SELECT pg_blocking_pids(:pid)'), {'pid':second_pid[0]}).scalar_one()
                            if blockers:
                                waiting=True
                                break
                            time.sleep(0.05)
                    self.assertTrue(waiting, 'Second request never waited on the first request lock')
                    self.assertFalse(second.done())
                    self.assertEqual(provider.calls,1)
                finally:release.set()
                self.assertEqual(first.result(timeout=10)['remaining_budget'],10)
                self.assertEqual(second.result(timeout=10),403)
            self.assertEqual(provider.calls,1)
            with Session() as db:
                self.assertEqual(db.query(Tenant).one().token_budget,10)
                self.assertEqual(db.query(UsageRecord).count(),1)
        finally:
            release.set()
            with engine.begin() as conn:conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
            engine.dispose()
