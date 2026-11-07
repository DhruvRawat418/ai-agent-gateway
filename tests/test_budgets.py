import unittest
import test_dashboard
from unittest.mock import Mock, patch
from types import SimpleNamespace as S
from pydantic import ValidationError
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials as Credentials
from database import UsageRecord, RequestAttempt
from main import ChatRequest, proxy_chat, departments

class BudgetTests(unittest.TestCase):
    setUp = test_dashboard.DashboardTests.setUp
    tearDown = test_dashboard.DashboardTests.tearDown
    create = test_dashboard.DashboardTests.create

    def call(self, created, client, **kwargs):
        return proxy_chat(ChatRequest(**kwargs), Credentials(scheme='Bearer', credentials=created['api_key']), self.db, client)

    def response(self, tokens=20, finish='stop'):
        return S(model='gpt-4o-mini', usage=S(total_tokens=tokens, prompt_tokens=10, completion_tokens=tokens-10), choices=[S(message=S(content='Hello'), finish_reason=finish)])

    def test_positive_balance_too_small_blocks_without_charge(self):
        created=self.create(budget=66); client=Mock()
        with self.assertRaises(HTTPException) as error:self.call(created,client,prompt='Hi')
        self.assertEqual(error.exception.status_code,403)
        client.chat.completions.create.assert_not_called()
        self.assertEqual(self.db.query(RequestAttempt).one().error_code,'insufficient_prompt_budget')
        self.assertEqual(self.db.query(UsageRecord).count(),0)
        self.assertEqual(departments(self.db)['departments'][0]['remaining'],66)

    def test_budget_cap_and_actual_charge(self):
        created=self.create(budget=100);client=Mock()
        client.chat.completions.create.return_value=self.response()
        result=self.call(created,client,prompt='Hi',max_completion_tokens=1000)
        self.assertEqual(client.chat.completions.create.call_args.kwargs['max_completion_tokens'],34)
        self.assertEqual(result['completion_token_limit'],34)
        self.assertEqual(result['remaining_budget'],80)

    def test_explicit_limit_and_truncation_visible(self):
        created=self.create();client=Mock()
        client.chat.completions.create.return_value=self.response(finish='length')
        result=self.call(created,client,prompt='Hi',max_completion_tokens=10)
        self.assertEqual(result['completion_token_limit'],10)
        self.assertEqual(result['finish_reason'],'length')

    def test_unicode_boundary_allows_one_output_token(self):
        created=self.create(budget=69);client=Mock()
        client.chat.completions.create.return_value=self.response(tokens=11)
        result=self.call(created,client,prompt='😀')
        self.assertEqual(result['completion_token_limit'],1)

    def test_defaults_and_validation(self):
        self.assertEqual(ChatRequest(prompt='Hi').max_completion_tokens,1024)
        for value in [0,-1,16385,True,1.5,'10']:
            with self.assertRaises(ValidationError): ChatRequest(prompt='Hi',max_completion_tokens=value)
        with self.assertRaises(ValidationError):ChatRequest(prompt='Hi',model='unconfigured-model')
        with self.assertRaises(ValidationError):ChatRequest(prompt='x'*100001)

    def test_no_hidden_retries_on_constructed_client(self):
        created=self.create();client=Mock()
        client.chat.completions.create.return_value=self.response()
        with patch('main.OpenAI',return_value=client) as factory:self.call(created,None,prompt='Hi')
        self.assertEqual(factory.call_args.kwargs['max_retries'],0)
        self.assertEqual(factory.call_args.kwargs['timeout'],30.0)
