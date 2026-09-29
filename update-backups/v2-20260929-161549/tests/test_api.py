import hashlib
import hmac
import io
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from PIL import Image
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app import store

@pytest.fixture
def client(tmp_path):
    app=create_app(tmp_path, demo=True)
    with TestClient(app) as c:
        assert c.post('/api/login',json={'password':'demo-operator'}).status_code==200
        yield c

def image_bytes(color='white'):
    stream=io.BytesIO(); Image.new('RGB',(500,400),color).save(stream,'PNG'); return stream.getvalue()

def setup_payment(client, monkeypatch):
    order=client.post('/api/orders',json={'customer':'Test Customer','amount_minor':2500000}).json()
    fields=dict(amount_minor=2500000,currency='LKR',account=order['account'],reference='TXTEST123',
                paid_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),order_code=order['payment_code'],
                source='ocr',confidence=.99,issues=[],text='test double')
    monkeypatch.setattr('app.main.extract',lambda _:dict(fields))
    return order,fields

def submit(client,order,key='request-123',raw=None):
    return client.post('/api/payments',data={'order_id':order['id']},files={'image':('slip.png',raw or image_bytes(),'image/png')},headers={'Idempotency-Key':key})

def signed(client, body, stamp=None, signature=None):
    raw=json.dumps(body).encode(); stamp=str(stamp or int(time.time()))
    sig=hmac.new(client.app.state.sms_secret.encode(),stamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
    return client.post('/api/gateway/sms',content=raw,headers={'Content-Type':'application/json','X-Timestamp':stamp,'X-Signature':signature or sig})

def sms(fields,event='event-1'):
    from app.demo import sms_text
    return dict(event_id=event,sender='DEMO-BANK',text=sms_text(fields))

def test_auth_required(tmp_path):
    c=TestClient(create_app(tmp_path,demo=True))
    assert c.get('/api/dashboard').status_code==401
    assert c.get('/api/payments/demo-01/image').status_code==401
    assert c.post('/api/demo/seed').status_code==401

def test_seed_scenarios(client):
    assert client.post('/api/demo/seed').status_code==200
    data=client.get('/api/dashboard').json()
    assert len(data['payments'])==9
    codes={p['decision']['code'] for p in data['payments']}
    assert {'CORROBORATED','WRONG_AMOUNT','REUSED_TRANSACTION','CONFLICTING_EVIDENCE','UNRELIABLE_EXTRACTION','NO_BANK_EVIDENCE','WRONG_ACCOUNT','OLD_PAYMENT','UNPROVEN_OWNERSHIP'} == codes
    assert client.post('/api/demo/seed').status_code==409

def test_late_sms_rechecks_pending(client,monkeypatch):
    order,fields=setup_payment(client,monkeypatch)
    p=submit(client,order).json()
    assert p['decision']['status']=='NEEDS VERIFICATION'
    assert signed(client,sms(fields)).status_code==200
    p=client.get('/api/dashboard').json()['payments'][0]
    assert p['decision']['status']=='APPROVED'
    assert client.post(f"/api/payments/{p['id']}/recheck").json()['status']=='APPROVED'

def test_idempotency_and_changed_body(client,monkeypatch):
    order,fields=setup_payment(client,monkeypatch)
    first=submit(client,order).json()
    retry=submit(client,order).json()
    assert retry['id']==first['id'] and retry['replayed']
    assert submit(client,order,raw=image_bytes('blue')).status_code==409

def test_duplicate_and_different_pixels(client,monkeypatch):
    order,fields=setup_payment(client,monkeypatch)
    signed(client,sms(fields))
    assert submit(client,order).json()['decision']['status']=='APPROVED'
    assert submit(client,order,'request-456').json()['decision']['code']=='DUPLICATE_IMAGE'
    assert submit(client,order,'request-789',image_bytes('blue')).json()['decision']['code']=='REUSED_TRANSACTION'

def test_signed_gateway_replay_and_tampering(client,monkeypatch):
    _,fields=setup_payment(client,monkeypatch)
    assert signed(client,sms(fields),signature='bad').status_code==401
    assert signed(client,sms(fields),stamp=int(time.time())-500).status_code==401
    assert signed(client,sms(fields)).status_code==200
    assert signed(client,sms(fields)).json()['replayed']
    assert signed(client,sms({**fields,'amount_minor':1})).status_code==409
    assert signed(client,{**sms(fields),'sender':'EVIL'}).status_code==422

def test_no_manual_approval_bypass(client,monkeypatch):
    order,fields=setup_payment(client,monkeypatch)
    pid=submit(client,order).json()['id']
    assert client.post(f'/api/payments/{pid}/review',json={'note':'Checked receipt carefully','reject':False}).status_code==200
    assert client.get('/api/dashboard').json()['payments'][0]['decision']['status']=='NEEDS VERIFICATION'
    client.post(f'/api/payments/{pid}/review',json={'note':'Confirmed wrong transfer with customer','reject':True})
    signed(client,sms(fields))
    assert client.get('/api/dashboard').json()['payments'][0]['decision']['status']=='REJECTED'

def test_late_conflict_creates_incident(client,monkeypatch):
    order,fields=setup_payment(client,monkeypatch)
    signed(client,sms(fields)); submit(client,order)
    signed(client,sms({**fields,'amount_minor':20000},'event-2'))
    assert 'incident' in client.get('/api/dashboard').json()['payments'][0]['decision']

def test_cross_origin_writes_blocked(client):
    assert client.post('/api/demo/seed',headers={'Origin':'https://evil.example'}).status_code==403

def test_invalid_upload(client,monkeypatch):
    order,_=setup_payment(client,monkeypatch)
    assert submit(client,order,raw=b'not an image').status_code==422

def test_concurrent_transaction_claim(client,monkeypatch):
    order,fields=setup_payment(client,monkeypatch)
    signed(client,sms(fields))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda i:submit(client,order,f'concurrent-{i}',image_bytes('white' if i==0 else 'blue')).json(),range(2)))
    assert sum(x['decision']['status']=='APPROVED' for x in results)==1
    with store.connect(client.app.state.dbpath) as db:
        assert db.execute('SELECT COUNT(*) FROM claims').fetchone()[0]==1

def test_cache_avoids_repeated_ocr(client,monkeypatch):
    order,fields=setup_payment(client,monkeypatch)
    calls=[]
    monkeypatch.setattr('app.main.extract',lambda _:(calls.append(1) or fields))
    submit(client,order)
    second=submit(client,order,'cache-retry').json()
    assert second['cache_hit'] and len(calls)==1

def test_transient_ocr_failure_is_retried(client,monkeypatch):
    order,fields=setup_payment(client,monkeypatch)
    calls=[]
    def flaky(_):
        calls.append(1)
        return {'source':'unavailable','confidence':0,'issues':['Temporary engine failure']} if len(calls)==1 else fields
    monkeypatch.setattr('app.main.extract',flaky)
    submit(client,order)
    submit(client,order,'retry-after-outage')
    assert len(calls)==2
    assert client.get('/api/dashboard').json()['payments'][0]['extraction']['source']=='ocr'
