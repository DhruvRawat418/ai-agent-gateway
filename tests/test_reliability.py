import unittest
import test_dashboard
from unittest.mock import Mock, patch
from types import SimpleNamespace as S
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials as Credentials
from database import UsageRecord, RequestAttempt, RequestCost
from main import proxy_chat, ChatRequest, request_activity, departments, safe_provider_error

class ReliabilityTests(unittest.TestCase):
    setUp=test_dashboard.DashboardTests.setUp
    tearDown=test_dashboard.DashboardTests.tearDown
    create=test_dashboard.DashboardTests.create
    def call(self, created, client):
        return proxy_chat(ChatRequest(prompt='private prompt'),Credentials(scheme='Bearer',credentials=created['api_key']),self.db,client)
    def test_blocked_logged_without_charge(self):
        created=self.create(budget=0);client=Mock()
        with self.assertRaises(HTTPException) as error:self.call(created,client)
        self.assertEqual(error.exception.status_code,403)
        client.chat.completions.create.assert_not_called()
        activity=request_activity(db=self.db)
        self.assertEqual(activity['status_counts'],{'blocked':1})
        self.assertIsNone(activity['requests'][0]['tokens'])
        self.assertEqual(self.db.query(UsageRecord).count(),0)
    def test_provider_failure_safe_and_uncharged(self):
        created=self.create();client=Mock()
        client.chat.completions.create.side_effect=TimeoutError('SECRET key and private prompt')
        with self.assertRaises(HTTPException) as error:self.call(created,client)
        self.assertEqual(error.exception.status_code,504)
        activity=request_activity(db=self.db)
        self.assertEqual(activity['requests'][0]['error_code'],'provider_timeout')
        self.assertNotIn('SECRET',str(activity))
        self.assertNotIn('private prompt',str(activity))
        self.assertEqual(departments(self.db)['departments'][0]['remaining'],1000)
    def test_success_legacy_and_filters(self):
        created=self.create();client=Mock()
        self.db.add(UsageRecord(tenant_id=created['id'],tokens=10,model='legacy'));self.db.commit()
        client.chat.completions.create.return_value=S(model='gpt-4o-mini',choices=[S(message=S(content='Hello'))],usage=S(total_tokens=20,prompt_tokens=10,completion_tokens=10))
        with patch('main.time.perf_counter',side_effect=[100,106]):self.call(created,client)
        activity=request_activity(db=self.db)
        self.assertEqual(activity['total_requests'],2)
        self.assertEqual(activity['status_counts'],{'success':2})
        self.assertEqual(activity['requests'][0]['latency_ms'],6000)
        self.assertIsNone(activity['requests'][1]['latency_ms'])
        self.assertEqual(request_activity(slow_only=True,db=self.db)['total_requests'],1)
        self.assertEqual(request_activity(status='blocked',db=self.db)['total_requests'],0)
        self.assertEqual(self.db.query(RequestAttempt).count(),1)
    def test_recording_error_rolls_back_usage(self):
        created=self.create();client=Mock()
        client.chat.completions.create.return_value=S(model='gpt-4o-mini',choices=[S(message=S(content='Hello'))],usage=S(total_tokens=20,prompt_tokens=10,completion_tokens=10))
        original=self.db.commit
        with patch.object(self.db,'commit',side_effect=[RuntimeError('SECRET DB URL'),None]):
            with self.assertRaises(HTTPException):self.call(created,client)
        # Failure event was flushed by queries even though mocked second commit was a no-op.
        original()
        self.assertEqual(self.db.query(UsageRecord).count(),0)
        self.assertEqual(self.db.query(RequestCost).count(),0)
        result=request_activity(db=self.db)
        self.assertEqual(result['requests'][0]['status'],'recording_error')
        self.assertIn('charges may still apply',result['requests'][0]['error_detail'])
        self.assertNotIn('SECRET',str(result))
    def test_activity_pagination_and_department_isolation(self):
        a=self.create('A');b=self.create('B')
        for i in range(22): self.db.add(RequestAttempt(tenant_id=a['id'],model='test',status='blocked',latency_ms=i))
        self.db.add(RequestAttempt(tenant_id=b['id'],model='test',status='provider_error',latency_ms=5000));self.db.commit()
        result=request_activity(department_id=a['id'],page=2,db=self.db)
        self.assertEqual(len(result['requests']),2)
        self.assertEqual(result['total_requests'],22)
        self.assertEqual(result['status_counts'],{'blocked':22})
        with self.assertRaises(HTTPException):request_activity(status='invalid',db=self.db)
    def test_failure_logging_unavailable_and_invalid_key(self):
        created=self.create(budget=0)
        with patch.object(self.db,'commit',side_effect=RuntimeError('offline')):
            with self.assertLogs('gateway',level='ERROR'):
                with self.assertRaises(HTTPException) as error:self.call(created,Mock())
        self.assertEqual(error.exception.status_code,403)
        with self.assertRaises(HTTPException):proxy_chat(ChatRequest(prompt='Hi'),None,self.db,Mock())
        self.assertEqual(self.db.query(RequestAttempt).count(),0)
