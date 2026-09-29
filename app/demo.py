"""Labelled synthetic fixtures. Seeded extraction is a simulation, never an OCR benchmark."""
import hashlib
import io
import json
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from . import store

def render_slip(fields, blurred=False):
    image = Image.new("RGB", (1200, 950), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 32)
        title = ImageFont.truetype("DejaVuSans.ttf", 44)
    except OSError:
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 32)
            title = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 44)
        except OSError:
            font = title = ImageFont.load_default(size=32)
    draw.text((70, 55), "DEMO BANK", fill="#182a3b", font=title)
    draw.text((70, 130), "SYNTHETIC TEST RECEIPT", fill="#5d6b78", font=font)
    draw.line((70, 210, 1130, 210), fill="#d5dde5", width=2)
    labels = ["Transfer completed", f"Amount: LKR {fields.get('amount_minor', 0)/100:,.2f}",
              f"Account: {fields.get('account', '')}", f"Reference: {fields.get('reference', '')}",
              f"Date: {fields.get('paid_at', '')}", f"Memo: {fields.get('order_code', '')}", "For demonstration only"]
    for index, line in enumerate(labels):
        draw.text((70, 260+index*76), line, fill="#172838", font=font)
    if blurred:
        image = image.resize((150, 119)).resize((1200, 950)).filter(ImageFilter.GaussianBlur(7))
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()

def seed_database(db, evaluate, account):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    paid_at = (now - timedelta(minutes=10)).isoformat()
    base = dict(amount_minor=2500000, currency="LKR", account=account, reference="TX839201",
                paid_at=paid_at, order_code="PAY-DEMO000001", confidence=.99, source="ocr", issues=[],
                text="Synthetic seeded extraction; use Upload to exercise real local OCR.", demo_fixture=True)
    scenarios = [
        ("Ayesha Perera", "Normal payment", {}, True),
        ("Nimal Fernando", "Wrong amount", {"amount_minor": 2400000}, False),
        ("Kavindi Silva", "Different image, reused payment", {"reference": "TX839201", "order_code": "PAY-DEMO000001"}, False),
        ("Ravindu Jay", "Conflicting bank evidence", {}, True),
        ("Tharushi Dias", "Unclear slip", {"confidence": .42, "issues": ["Blurred image"]}, False),
        ("Isuru Senanayake", "Waiting for bank SMS", {}, False),
        ("Maya De Silva", "Wrong receiving account", {"account": "9999999999"}, False),
        ("Dilan Wijesinghe", "Old transaction", {"paid_at": (now-timedelta(days=5)).isoformat()}, False),
        ("Sara Fernando", "Amount match, ownership missing", {}, True),
    ]
    for i, (customer, label, changes, has_sms) in enumerate(scenarios, 1):
        oid, pid = f"ORD-{1000+i}", f"demo-{i:02d}"
        code = f"PAY-DEMO{i:06d}"
        order = dict(id=oid, customer=customer, amount_minor=2500000, currency="LKR", account=account,
                     payment_code=code, created_at=(now-timedelta(hours=1)).isoformat(),
                     expires_at=(now+timedelta(days=2)).isoformat(), paid=0)
        db.execute("INSERT INTO orders VALUES(:id,:customer,:amount_minor,:currency,:account,:payment_code,:created_at,:expires_at,:paid)", order)
        fields = {**base, "reference": f"TX{839200+i}", "order_code": code, **changes}
        image = render_slip(fields, i == 5)
        if i == 3: # Changed pixels, same bank reference; hash alone cannot catch reuse.
            image = render_slip({**fields, "order_code": code})
        digest = hashlib.sha256(image).hexdigest()
        db.execute("INSERT OR IGNORE INTO images VALUES(?,?,?)", (digest, image, json.dumps(fields)))
        if has_sms:
            bank = {k:v for k,v in fields.items() if k in ("reference", "amount_minor", "currency", "account", "paid_at", "order_code")}
            if i == 4:
                bank["amount_minor"] = 1500000
            if i == 9:
                bank.pop("order_code")
            bank.update(trusted=True, issues=[])
            raw = sms_text(bank)
            db.execute("INSERT INTO sms(id,event_id,body_hash,raw,fields,received_at) VALUES(?,?,?,?,?,?)", (f"sms-{i}", f"seed-{i}", hashlib.sha256(raw.encode()).hexdigest(), raw, json.dumps(bank), store.utcnow()))
        timestamp = (now-timedelta(minutes=9-i)).isoformat()
        db.execute("INSERT INTO payments VALUES(?,?,?,?,?,?,?,?,?)", (pid, oid, digest, json.dumps(fields), "{}", timestamp, timestamp, pid, digest))
        store.log(db, pid, "demo-simulator", "SYNTHETIC_FIXTURE", {"scenario": label, "warning": "Seeded OCR output; not a real bank payment."})
        evaluate(db, db.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone())

def sms_text(fields):
    return (f"Credited LKR {fields['amount_minor']/100:,.2f} to A/C {fields['account']}; "
            f"Ref {fields['reference']}; Date {fields['paid_at']}" +
            (f"; Memo {fields['order_code']}" if fields.get("order_code") else ""))
