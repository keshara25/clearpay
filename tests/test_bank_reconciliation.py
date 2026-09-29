"""Contract and negative tests for real-record mode and the BOC layout adapter."""
import csv
import io
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont
from app.main import create_app
from app.extraction import parse_text, refresh_extraction
from app.bank_import import COLUMNS, parse_statement

BOC = '''BOC
FleX Online Banking
Transaction Amount
：LKR1,000.00
TransactionDate&Time
：29-09-202604:10PM
Transaction ID
：FX12345678901234
Transaction Status
:SUCCESS
Sender AC Details
Account Number
：**4567
ToAccountNumber
：9876543210
Charges&Fee
：LKR0.00
Printedon:29-09-202604:15PM
'''


def test_boc_uses_recipient_and_transaction_time():
    f = parse_text(BOC)
    assert f['account'] == '9876543210'
    assert f['reference'] == 'FX12345678901234'
    assert f['paid_at'] == '2026-09-29T16:10:00+05:30'
    assert f['amount_minor'] == 100000 and f['currency'] == 'LKR'
    assert f['issues'] == []


@pytest.mark.parametrize('change', ['duplicate_amount', 'masked_recipient', 'failed', 'missing_status', 'invalid_date', 'currency'])
def test_boc_ambiguity_cannot_be_silently_accepted(change):
    value = BOC
    if change == 'duplicate_amount': value += '\nTransaction Amount\nLKR2,000.00\n'
    if change == 'masked_recipient': value = value.replace('9876543210', '******3210')
    if change == 'failed': value = value.replace('SUCCESS', 'FAILED')
    if change == 'missing_status': value = value.replace('Transaction Status\n:SUCCESS\n', '')
    if change == 'invalid_date': value = value.replace('29-09-2026', '31-02-2026')
    if change == 'currency': value = value.replace('LKR1,000', 'USD1,000')
    assert parse_text(value)['issues']


def test_cached_ocr_upgrade_preserves_confidence():
    f = refresh_extraction(dict(text=BOC, source='ocr', confidence=.92, issues=[]))
    assert f['account'] == '9876543210' and f['confidence'] == .92


def csv_bytes(order, reference='FX12345678901234', **changes):
    row = dict(account=order['account'], reference=reference, amount='1000.00', currency='LKR',
               paid_at=datetime.now(timezone.utc).isoformat(timespec='seconds'), direction='CREDIT', status='COMPLETED', order_code=order['payment_code'])
    row.update(changes)
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS)
    writer.writeheader(); writer.writerow(row)
    return out.getvalue().encode()


@pytest.fixture
def live(tmp_path):
    with TestClient(create_app(tmp_path, demo=True)) as c:
        c.post('/api/login', json={'password':'demo-operator'})
        assert c.post('/api/settings', json={'account':'9876543210','mode':'bank_records'}).status_code == 200
        o = c.post('/api/orders', json={'customer':'Reconciliation Test', 'amount_minor':100000}).json()
        yield c, o


def upload(c, order, monkeypatch):
    now = datetime.now(timezone(timedelta(hours=5,minutes=30))).strftime('%d-%m-%Y%I:%M%p')
    text = BOC.replace('29-09-202604:10PM', now)
    fields = dict(parse_text(text), source='ocr', confidence=.97, text=text)
    monkeypatch.setattr('app.main.extract', lambda _: fields)
    image = io.BytesIO(); Image.new('RGB',(500,500),'white').save(image,'PNG')
    return c.post('/api/payments',data={'order_id':order['id']},files={'image':('slip.png',image.getvalue())},headers={'Idempotency-Key':'bank-record-test'}).json()


def do_import(c, raw, confirmed='true'):
    return c.post('/api/bank/import',data={'confirmed':confirmed},files={'file':('bank.csv',raw,'text/csv')})


def test_import_autoapproves_pending_and_replay_is_safe(live, monkeypatch):
    c,o = live
    assert upload(c,o,monkeypatch)['decision']['code'] == 'NO_BANK_EVIDENCE'
    raw = csv_bytes(o)
    result = do_import(c,raw)
    assert result.status_code == 200, result.text
    assert result.json()['imported'] == 1
    p = c.get('/api/dashboard').json()['payments'][0]
    assert p['decision']['status'] == 'APPROVED'
    assert p['decision']['evidence_source'] == 'merchant_statement'
    assert p['order']['evidence_mode'] == 'bank_records'
    assert do_import(c,raw).json()['imported'] == 0
    assert c.post('/api/demo/sms',json={'text':'test'}).status_code == 404
    assert c.get('/api/dashboard').json()['demo'] is False
    assert c.post('/api/demo/seed').status_code == 404
    assert do_import(c,csv_bytes(o,amount='2000.00')).status_code == 200
    assert 'incident' in c.get('/api/dashboard').json()['payments'][0]['decision']


@pytest.mark.parametrize('changes,expected', [({'order_code':''},'UNPROVEN_OWNERSHIP'), ({'reference':'FXOTHER1234'},'NO_BANK_EVIDENCE'), ({'amount':'999.00'},'CONFLICTING_EVIDENCE'), ({'paid_at':'2020-01-01T00:00:00Z'},'CONFLICTING_TIME')])
def test_unmatched_bank_records_never_approve(live,monkeypatch,changes,expected):
    c,o=live
    upload(c,o,monkeypatch)
    assert do_import(c,csv_bytes(o,**changes)).status_code == 200
    assert c.get('/api/dashboard').json()['payments'][0]['decision']['code'] == expected


@pytest.mark.parametrize('changes', [{'account':'1234567890'}, {'currency':'USD'}, {'paid_at':'2026-09-29T10:00:00'}, {'amount':'1,00'}, {'direction':'UNKNOWN'}, {'status':'UNKNOWN'}])
def test_bad_import_is_atomic(live,changes):
    c,o=live
    assert do_import(c,csv_bytes(o,**changes)).status_code == 422
    assert c.get('/api/dashboard').json()['sms'] == []


def test_debits_and_reversals_are_not_credit_evidence(live):
    c,o=live
    for change in ({'direction':'DEBIT'},{'status':'REVERSED'}):
        assert do_import(c,csv_bytes(o,**change)).status_code == 422
    assert do_import(c,csv_bytes(o),confirmed='false').status_code == 422


def test_settings_persist_and_do_not_rewrite_existing_orders(live):
    c,o=live
    c.post('/api/settings',json={'account':'1111222233','mode':'test'})
    existing=c.get('/api/dashboard').json()['orders'][0]
    assert existing['account']=='9876543210' and existing['evidence_mode']=='bank_records'
    with TestClient(create_app(c.app.state.dbpath.parent,demo=True)) as restarted:
        restarted.post('/api/login',json={'password':'demo-operator'})
        assert restarted.get('/api/dashboard').json()['account']=='1111222233'


def test_test_evidence_cannot_approve_real_order(live,monkeypatch):
    from app import store
    from app.demo import sms_text
    c,o=live
    p=upload(c,o,monkeypatch)
    c.post('/api/settings',json={'account':o['account'],'mode':'test'})
    with store.connect(c.app.state.dbpath) as db:
        import json
        fields=json.loads(db.execute('SELECT extraction FROM payments').fetchone()[0])
    fields['order_code']=o['payment_code']
    c.post('/api/demo/sms',json={'text':sms_text(fields)})
    assert c.get('/api/dashboard').json()['payments'][0]['decision']['code']=='NO_BANK_EVIDENCE'
    c.post('/api/settings',json={'account':o['account'],'mode':'bank_records'})
    assert do_import(c,csv_bytes(o)).status_code==200
    assert c.get('/api/dashboard').json()['payments'][0]['decision']['status']=='APPROVED'


def test_actual_boc_layout_ocr_to_bank_csv_approval(live):
    c,o=live
    now=datetime.now(timezone(timedelta(hours=5,minutes=30))).strftime('%d-%m-%Y %I:%M%p')
    o=c.post('/api/orders',json={'customer':'OCR Bank Test','amount_minor':123456}).json()
    lines=['BOC','SYNTHETIC TEST RECEIPT','Transaction Amount: LKR 1,234.56',f'Transaction Date & Time: {now}',
           'Transaction ID: FX12345678901234','Transaction Status: SUCCESS','Account Number: **4567',
           'To Account Number: 9876543210']
    im=Image.new('RGB',(1500,650),'white'); draw=ImageDraw.Draw(im)
    try:
        font=ImageFont.truetype('DejaVuSans.ttf',32)
    except OSError:
        font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',32)
    for i,line in enumerate(lines): draw.text((50,40+i*65),line,fill='black',font=font)
    out=io.BytesIO();im.save(out,'PNG')
    r=c.post('/api/payments',data={'order_id':o['id']},files={'image':('synthetic-boc.png',out.getvalue())},headers={'Idempotency-Key':'actual-boc-ocr'}).json()
    assert r['decision']['code']=='NO_BANK_EVIDENCE',c.get('/api/dashboard').json()['payments'][0]['extraction']
    assert do_import(c,csv_bytes(o,amount='1234.56')).status_code==200
    assert c.get('/api/dashboard').json()['payments'][0]['decision']['status']=='APPROVED'
