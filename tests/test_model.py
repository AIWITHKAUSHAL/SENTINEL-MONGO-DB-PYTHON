from copy import deepcopy
from datetime import timezone
import pytest
from sentinel.model import documents, timestamp

@pytest.fixture
def row():
    return {'transaction': {'transaction_id':'T1','customer_id':'C1','merchant_id':'M1',
      'device_id':'D1','amount_paise':12345,'transaction_amount':'123.45',
      'customer_age':30,'customer_location':'{"city":"Pune"}',
      'merchant_location':{'city':'Delhi'},'merchant_category':'food',
      'transaction_time':'2025-01-02T10:00:00+05:30','payment_channel':'UPI','split':'train'},
      'customer':{'customer_id':'C1','created_at':'2024-01-01T00:00:00Z',
                  'customer_age':30,'home_city':'Pune','region':'west'},
      'merchant':{'merchant_id':'M1','synthetic_name':'Merchant'},
      'device':{'device_id':'D1','device_kind':'mobile'},
      'label':{'transaction_id':'T1','fraud_label':1,'label_available_at':'2025-03-01T00:00:00Z'}}

def test_document_types_and_deduplicated_devices(row):
    second=deepcopy(row)
    second['transaction']['transaction_id']='T2'
    second['label']['transaction_id']='T2'
    c,t=documents([row,second])
    assert len(c)==1 and len(c[0]['devices'])==1
    assert t[0]['amount_paise']==12345
    assert t[0]['time'].hour==4 and t[0]['time'].minute==30
    assert t[0]['time'].tzinfo==timezone.utc
    assert t[0]['customer']['location']=={'city':'Pune'}

def test_unlabeled_is_not_legitimate(row):
    row['label']=None
    assert documents([row])[1][0]['fraud_label'] is None

@pytest.mark.parametrize('field,value', [('amount_paise',-1),('transaction_amount','123.46')])
def test_invalid_money_rejected(row,field,value):
    row['transaction'][field]=value
    with pytest.raises(ValueError): documents([row])

def test_missing_device_rejected(row):
    row['device']=None
    with pytest.raises(ValueError): documents([row])

def test_duplicate_rejected(row):
    with pytest.raises(ValueError): documents([row,row])

def test_naive_time_rejected():
    with pytest.raises(ValueError): timestamp('2025-01-01T00:00:00')
