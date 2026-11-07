import os
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['OPENAI_API_KEY'] = 'test-only'
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials as Credentials
from pydantic import ValidationError
from database import Base, Tenant
from main import create_department, update_budget, departments, proxy_chat, require_staff, BudgetUpdate, DepartmentCreate, ChatRequest

class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
    def tearDown(self):
        self.db.close()
        self.engine.dispose()
    def create(self, name='Support', budget=1000):
        return create_department(DepartmentCreate(name=name, total_budget=budget), self.db)
    def test_create_and_duplicate(self):
        self.assertTrue(self.create()['api_key'].startswith('sk-gateway-'))
        with self.assertRaises(HTTPException) as error: self.create()
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(len(departments(self.db)['departments']), 1)
    def test_existing_balance_preserved_and_keys_not_exposed(self):
        self.db.add(Tenant(name='Legacy', token_budget=700, api_key='secret'))
        self.db.commit()
        row = departments(self.db)['departments'][0]
        self.assertEqual((row['used'], row['remaining'], row['total_budget']), (0, 700, 700))
        self.assertNotIn('api_key', row)
    def test_usage_and_budget_edit(self):
        created = self.create()
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='Hello'))], usage=SimpleNamespace(total_tokens=200))
        result = proxy_chat(ChatRequest(prompt='Hello'), Credentials(scheme='Bearer', credentials=created['api_key']), self.db, client)
        self.assertEqual(result['remaining_budget'], 800)
        result = update_budget(created['id'], BudgetUpdate(total_budget=500), self.db)
        self.assertEqual(result, {'total_budget':500,'used':200,'remaining':300})
        row = departments(self.db)['departments'][0]
        self.assertEqual((row['used'], row['requests']), (200,1))
        with self.assertRaises(HTTPException): update_budget(created['id'], BudgetUpdate(total_budget=199), self.db)
    def test_failed_provider_does_not_charge(self):
        created = self.create()
        client = Mock()
        client.chat.completions.create.side_effect = RuntimeError('private provider details')
        with self.assertRaises(HTTPException) as error: proxy_chat(ChatRequest(prompt='Hello'), Credentials(scheme='Bearer', credentials=created['api_key']), self.db, client)
        self.assertNotIn('private provider details', error.exception.detail)
        row = departments(self.db)['departments'][0]
        self.assertEqual((row['used'], row['remaining']), (0,1000))
    def test_zero_budget_blocks_provider(self):
        created = self.create(budget=0)
        client = Mock()
        with self.assertRaises(HTTPException) as error: proxy_chat(ChatRequest(prompt='Hello'), Credentials(scheme='Bearer', credentials=created['api_key']), self.db, client)
        self.assertEqual(error.exception.status_code,403)
        client.chat.completions.create.assert_not_called()
    def test_staff_access(self):
        with patch.dict(os.environ, {'ADMIN_API_KEY':'staff-secret'}):
            require_staff(Credentials(scheme='Bearer',credentials='staff-secret'))
            for credentials in [None, Credentials(scheme='Bearer',credentials='department-key')]:
                with self.assertRaises(HTTPException) as error: require_staff(credentials)
                self.assertEqual(error.exception.status_code,401)
        with patch.dict(os.environ, {'ADMIN_API_KEY':''}):
            with self.assertRaises(HTTPException) as error: require_staff(None)
            self.assertEqual(error.exception.status_code,503)
    def test_invalid_allocations(self):
        for value in [-1, 1.5, True, 2000000001]:
            with self.assertRaises(ValidationError): BudgetUpdate(total_budget=value)
        with self.assertRaises(ValidationError): DepartmentCreate(name='  ',total_budget=100)
    def test_unknown_department(self):
        with self.assertRaises(HTTPException) as error: update_budget(99,BudgetUpdate(total_budget=100),self.db)
        self.assertEqual(error.exception.status_code,404)
