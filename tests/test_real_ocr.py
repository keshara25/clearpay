"""Actual local OCR integration, using synthetic images, not seeded extraction."""
from datetime import datetime, timezone
import hashlib
import hmac
import json
import time
from fastapi.testclient import TestClient
from app.main import create_app
from app.demo import render_slip, sms_text
from app.extraction import extract

def test_actual_image_to_signed_sms_to_approval(tmp_path):
    with TestClient(create_app(tmp_path,demo=True)) as client:
        client.post('/api/login',json={'password':'demo-operator'})
        order=client.post('/api/orders',json={'customer':'Actual OCR Test','amount_minor':2500000}).json()
        fields=dict(amount_minor=2500000,account=order['account'],reference='TXREAL123',
                    paid_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),order_code=order['payment_code'])
        image=render_slip(fields)
        result=client.post('/api/payments',data={'order_id':order['id']},files={'image':('test.png',image,'image/png')},headers={'Idempotency-Key':'real-ocr-test'}).json()
        assert result['decision']['code']=='NO_BANK_EVIDENCE', client.get('/api/dashboard').json()['payments'][0]
        raw=json.dumps(dict(event_id='real-test-event',sender='DEMO-BANK',text=sms_text(fields))).encode()
        stamp=str(int(time.time()))
        signature=hmac.new(client.app.state.sms_secret.encode(),stamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
        assert client.post('/api/gateway/sms',content=raw,headers={'X-Timestamp':stamp,'X-Signature':signature}).status_code==200
        payment=client.get('/api/dashboard').json()['payments'][0]
        assert payment['decision']['status']=='APPROVED', payment['extraction']

def test_blurred_actual_image_fails_closed():
    fields=dict(amount_minor=2500000,account='1234567890',reference='TXBLUR123',
                paid_at='2026-09-29T10:00:00+00:00',order_code='PAY-BLUR123456')
    result=extract(render_slip(fields,blurred=True))
    assert result['confidence'] < .90 or result['issues'] or any(not result.get(k) for k in ('account','reference','amount_minor','paid_at'))
