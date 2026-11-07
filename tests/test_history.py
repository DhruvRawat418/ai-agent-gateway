import test_dashboard
import unittest
from datetime import datetime, timezone, timedelta
from database import UsageRecord
from main import usage_history, usage_window, EASTERN, eastern_date
from fastapi import HTTPException

class HistoryTests(unittest.TestCase):
    setUp = test_dashboard.DashboardTests.setUp
    tearDown = test_dashboard.DashboardTests.tearDown
    create = test_dashboard.DashboardTests.create
    def test_date_boundaries_filter_and_zero_days(self):
        a, b = self.create('Alpha'), self.create('Beta')
        today = datetime.now(EASTERN).replace(hour=0,minute=0,second=0,microsecond=0)
        for tenant, tokens, when in [(a,10,today),(a,20,today-timedelta(days=6)),(a,99,today-timedelta(days=6,microseconds=1)),(b,50,today),(a,999,today+timedelta(days=1))]:
            self.db.add(UsageRecord(tenant_id=tenant['id'],tokens=tokens,model='test-model',created_at=when.astimezone(timezone.utc)))
        self.db.commit()
        result=usage_history(7,a['id'],1,self.db)
        self.assertEqual(result['total_tokens'],30)
        self.assertEqual(result['total_requests'],2)
        self.assertEqual(len(result['daily']),7)
        self.assertEqual(result['daily'][1]['tokens'],0)
        self.assertEqual(result['requests'][0]['tokens'],10)
        self.assertNotIn('api_key',result['requests'][0])
        self.assertEqual(usage_history(30,a['id'],1,self.db)['total_tokens'],129)
        self.assertEqual(usage_history(7,None,1,self.db)['total_tokens'],80)
    def test_pagination_stable_order_and_clamping(self):
        a=self.create()
        timestamp=datetime.now(timezone.utc)
        for i in range(23): self.db.add(UsageRecord(tenant_id=a['id'],tokens=i,model='test',created_at=timestamp))
        self.db.commit()
        first=usage_history(7,None,1,self.db)
        second=usage_history(7,None,2,self.db)
        self.assertEqual(len(first['requests']),20)
        self.assertEqual(len(second['requests']),3)
        self.assertGreater(first['requests'][-1]['id'],second['requests'][0]['id'])
        self.assertEqual(usage_history(7,None,100,self.db)['page'],2)
    def test_empty_and_invalid_filter(self):
        result=usage_history(30,None,1,self.db)
        self.assertEqual(len(result['daily']),30)
        self.assertEqual(result['total_tokens'],0)
        self.assertEqual(result['requests'],[])
        with self.assertRaises(HTTPException): usage_history(7,999,1,self.db)
        with self.assertRaises(HTTPException): usage_history(8,None,1,self.db)

    def test_eastern_evening_and_dst(self):
        self.assertEqual(eastern_date("2026-11-05T01:43:19+00:00"), "2026-11-04")
        self.assertEqual(eastern_date("2026-07-02T03:59:59+00:00"), "2026-07-01")
        for day, hours in [(datetime(2026,3,8,12,tzinfo=EASTERN),23), (datetime(2026,11,1,12,tzinfo=EASTERN),25)]:
            _, start, end = usage_window(day, 1)
            self.assertEqual((end-start).total_seconds()/3600,hours)
            self.assertEqual(eastern_date(start.isoformat()),day.date().isoformat())
