from copy import deepcopy
from datetime import datetime, timezone
import pytest
from app.engine import decide
from app.extraction import money, parse_sms, parse_text

NOW = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)

@pytest.fixture
def evidence():
    order = dict(id="O1", account="1234567890", amount_minor=2500000, currency="LKR", payment_code="PAY-ABC12345",
                 created_at="2026-09-29T10:00:00Z", expires_at="2026-10-01T10:00:00Z", paid=0)
    slip = dict(account=order["account"], amount_minor=2500000, currency="LKR", reference="TX839201",
                paid_at="2026-09-29T11:00:00Z", order_code=order["payment_code"], confidence=.98, source="ocr", issues=[])
    sms = {**slip, "id":"S1", "trusted":True}
    return order, slip, sms

def run(evidence, **kw):
    o,s,b = evidence
    return decide(o,s,[b],now=NOW,**kw)

def test_normal_payment(evidence):
    assert run(evidence)["status"] == "APPROVED"

@pytest.mark.parametrize("field,value,code", [
    ("amount_minor",2499999,"WRONG_AMOUNT"), ("amount_minor",2500001,"WRONG_AMOUNT"),
    ("account","9999999999","WRONG_ACCOUNT"), ("currency","USD","WRONG_CURRENCY"),
    ("paid_at","2026-09-20T11:00:00Z","OLD_PAYMENT"),
    ("paid_at","2026-09-29T15:00:00Z","FUTURE_DATE"),
    ("paid_at","2026-09-29T11:00:00","INVALID_DATE"),
    ("confidence",.89,"UNRELIABLE_EXTRACTION"), ("source","manual","UNRELIABLE_EXTRACTION"),
    ("reference",None,"MISSING_FIELDS"), ("issues",["Suspicious extraction"],"UNRELIABLE_EXTRACTION")])
def test_bad_slip(evidence, field, value, code):
    evidence[1][field] = value
    result = run(evidence)
    assert result["code"] == code
    assert result["status"] != "APPROVED"

def test_amount_alone_is_not_ownership(evidence):
    evidence[2].pop("order_code")
    assert run(evidence)["code"] == "UNPROVEN_OWNERSHIP"

def test_other_customer_code(evidence):
    evidence[2]["order_code"] = "PAY-OTHER123"
    assert run(evidence)["status"] == "NEEDS VERIFICATION"

def test_no_sms(evidence):
    assert decide(evidence[0],evidence[1],[],now=NOW)["code"] == "NO_BANK_EVIDENCE"

def test_duplicate_image(evidence):
    assert run(evidence,image_used=True)["code"] == "DUPLICATE_IMAGE"

def test_same_transaction_different_image(evidence):
    assert run(evidence,claims=["1234567890:TX839201"])["code"] == "REUSED_TRANSACTION"

@pytest.mark.parametrize("field,value,code", [
    ("trusted",False,"UNTRUSTED_BANK_EVIDENCE"), ("amount_minor",2000000,"CONFLICTING_EVIDENCE"),
    ("account","9999999999","CONFLICTING_EVIDENCE"), ("paid_at","2026-09-29T10:00:00Z","CONFLICTING_TIME"),
    ("conflict",True,"BANK_CONFLICT")])
def test_conflicts(evidence, field, value, code):
    evidence[2][field] = value
    assert run(evidence)["code"] == code

def test_ambiguous_sms(evidence):
    o,s,b=evidence
    assert decide(o,s,[b,{**b,"id":"S2"}],now=NOW)["code"] == "AMBIGUOUS_BANK_MATCH"

def test_order_already_paid(evidence):
    evidence[0]["paid"] = 1
    assert run(evidence)["code"] == "ORDER_ALREADY_PAID"

@pytest.mark.parametrize("value,expected", [("25,000.01",2500001),("0.01",1),("100",10000)])
def test_decimal_money(value,expected):
    assert money(value) == expected

@pytest.mark.parametrize("value", ["1,00", "-25", "nan", "0", "2.001", "1e4"])
def test_invalid_money(value):
    with pytest.raises(ValueError): money(value)

def test_sms_adapters():
    for text in ["Rs. 25,000 credited to A/C 1234567890. Ref 839201.", "Credited LKR 25,000.00 to A/C 1234567890; Ref 839201"]:
        result = parse_sms(text)
        assert result["amount_minor"] == 2500000
        assert result["account"] == "1234567890"
        assert not result["issues"]

def test_masked_sms_not_full_account():
    assert parse_sms("Rs. 25,000 credited to A/C XXXX1234. Ref 839201.")["issues"]

def test_debit_rejected():
    assert parse_sms("Debited LKR 25,000 to A/C 1234567890 Ref 839201")["issues"]

def test_conflicting_fields_not_silently_chosen():
    result=parse_text("Amount LKR 25000\nAmount LKR 20000")
    assert "amount_minor" not in result
    assert result["issues"]

def test_ocr_label_correction_does_not_change_account_digits():
    assert parse_text('Acc0unt:1234567890')['account'] == '1234567890'
    assert parse_text('Account:1234567890')['account'] == '1234567890'

def test_ocr_joined_currency_and_amount():
    fields = parse_text('Amount:LKR25,000.00')
    assert fields['amount_minor'] == 2500000 and fields['currency'] == 'LKR'
    assert parse_text('Amount:LKR25,000.00\nUSD25000')['issues']
