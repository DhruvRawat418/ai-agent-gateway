import unittest
import test_dashboard
from types import SimpleNamespace as S
from unittest.mock import Mock
from fastapi.security import HTTPAuthorizationCredentials as Credentials
from pricing import estimate, usd
from database import UsageRecord, RequestCost
from main import proxy_chat, ChatRequest, departments, usage_history

class CostTests(unittest.TestCase):
    setUp = test_dashboard.DashboardTests.setUp
    tearDown = test_dashboard.DashboardTests.tearDown
    create = test_dashboard.DashboardTests.create
    def response(self, model='gpt-4o-mini-2024-07-18', tier='default', cached=400):
        return S(model=model,service_tier=tier,usage=S(prompt_tokens=1000,completion_tokens=200,total_tokens=1200,prompt_tokens_details=S(cached_tokens=cached)),choices=[S(message=S(content='Hi'))])
    def test_exact_cached_cost(self):
        result=estimate(self.response())
        self.assertEqual(result['cost_nano_usd'],240000)
        self.assertEqual(usd(result['cost_nano_usd']),'0.00024')
        self.assertEqual(result['input_rate'],150)
        self.assertEqual(result['cached_rate'],75)
    def test_unknown_missing_and_invalid(self):
        for r in [self.response(model='unknown'),self.response(tier='priority'),self.response(cached=1001),S(usage=S(total_tokens=74))]:
            self.assertIsNone(estimate(r)['cost_nano_usd'])
        r=self.response(); r.usage.prompt_tokens_details=None
        self.assertEqual(estimate(r)['cost_nano_usd'],270000)
    def test_recording_and_partial_totals(self):
        created=self.create(budget=10000)
        self.db.add(UsageRecord(tenant_id=created['id'],tokens=74,model='gpt-4o-mini'));self.db.commit()
        client=Mock(); client.chat.completions.create.return_value=self.response()
        result=proxy_chat(ChatRequest(prompt='Hi'),Credentials(scheme='Bearer',credentials=created['api_key']),self.db,client)
        self.assertEqual(result['estimated_cost_usd'],'0.00024')
        row=departments(self.db)['departments'][0]
        self.assertEqual((row['priced_requests'],row['unpriced_requests']),(1,1))
        self.assertEqual(row['estimated_cost_usd'],'0.00024')
        history=usage_history(7,None,1,self.db)
        self.assertEqual(history['estimated_cost_usd'],'0.00024')
        self.assertEqual(history['requests'][0]['input_tokens'],1000)
        self.assertIsNone(history['requests'][1]['estimated_cost_usd'])
    def test_unpriced_legacy_not_zero(self):
        created=self.create()
        self.db.add(UsageRecord(tenant_id=created['id'],tokens=74,model='gpt-4o-mini'));self.db.commit()
        self.assertIsNone(departments(self.db)['departments'][0]['estimated_cost_usd'])
        self.assertIsNone(usage_history(7,None,1,self.db)['estimated_cost_usd'])
    def test_additive_table_idempotent(self):
        created=self.create()
        self.db.add(UsageRecord(tenant_id=created['id'],tokens=74,model='gpt-4o-mini'));self.db.commit()
        RequestCost.__table__.drop(self.engine)
        RequestCost.__table__.create(self.engine,checkfirst=True)
        RequestCost.__table__.create(self.engine,checkfirst=True)
        self.assertEqual(self.db.query(UsageRecord).count(),1)
        self.assertEqual(departments(self.db)['departments'][0]['remaining'],1000)
