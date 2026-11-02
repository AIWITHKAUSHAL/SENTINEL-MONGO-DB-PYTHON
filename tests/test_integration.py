"""Real MongoDB tests. TEST_MONGODB_URI must point at a disposable test server."""
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from pymongo import MongoClient
from sentinel.queries import fraud_pipeline, top_customers_pipeline

@pytest.fixture
def db():
    uri=os.getenv('TEST_MONGODB_URI')
    if not uri:
        pytest.skip('Set TEST_MONGODB_URI to run real MongoDB integration tests')
    with MongoClient(uri, serverSelectionTimeoutMS=5000) as client:
        name='sentinel_test_'+uuid4().hex
        try:
            yield client[name]
        finally:
            client.drop_database(name)

def test_last_activity_is_per_customer_and_boundary_inclusive(db):
    start=datetime(2025,1,1,tzinfo=timezone.utc)
    db.transactions.insert_many([
       {'customer_id':'A','time':start,'amount_paise':100},
       {'customer_id':'A','time':start+timedelta(hours=24),'amount_paise':200},
       {'customer_id':'A','time':start-timedelta(milliseconds=1),'amount_paise':9000},
       {'customer_id':'B','time':start+timedelta(days=30),'amount_paise':400},
    ])
    result=list(db.transactions.aggregate(top_customers_pipeline()))
    assert [(r['customer_id'],r['amount_paise']) for r in result]==[('B',400),('A',300)]

def test_fraud_denominator_excludes_unknown_labels(db):
    db.transactions.insert_many([
      {'merchant_category':'food','fraud_label':1},
      {'merchant_category':'food','fraud_label':0},
      {'merchant_category':'food','fraud_label':None},
      {'merchant_category':'other','fraud_label':None}])
    result={r['merchant_category']:r for r in db.transactions.aggregate(fraud_pipeline())}
    assert result['food']['fraud_rate']==0.5
    assert result['food']['transactions']==3 and result['food']['labeled']==2
    assert result['other']['fraud_rate'] is None

def test_sample_matches_independent_python_calculation(db):
    from pathlib import Path
    from bson import json_util
    path=Path('outputs/private/sample.json')
    if not path.exists(): pytest.skip('Run prepare first for sample validation')
    data=json_util.loads(path.read_text())['transactions']
    db.transactions.insert_many(data)
    latest={}
    for t in data: latest[t['customer_id']]=max(latest.get(t['customer_id'],t['time']),t['time'])
    totals=defaultdict(int)
    for t in data:
        if t['time']>=latest[t['customer_id']]-timedelta(hours=24):
            totals[t['customer_id']]+=t['amount_paise']
    expected=sorted(totals.items(),key=lambda x:(-x[1],x[0]))[:10]
    actual=list(db.transactions.aggregate(top_customers_pipeline()))
    assert [(r['customer_id'],r['amount_paise']) for r in actual]==expected
    expected_fraud=defaultdict(lambda:[0,0])
    for t in data:
        if t['fraud_label'] is not None:
            expected_fraud[t['merchant_category']][0]+=1
            expected_fraud[t['merchant_category']][1]+=t['fraud_label']
    for r in db.transactions.aggregate(fraud_pipeline()):
        n,f=expected_fraud[r['merchant_category']]
        assert r['fraud_rate']==pytest.approx(f/n) if n else r['fraud_rate'] is None
