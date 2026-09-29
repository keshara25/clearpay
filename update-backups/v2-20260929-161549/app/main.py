"""Single-merchant prototype: operator UI, local OCR and signed SMS ingestion."""
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, UploadFile, File, Form, Depends
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from . import store
from .engine import decide
from .extraction import extract, normalize_image, parse_sms, MAX_BYTES

ROOT = Path(__file__).resolve().parents[1]

def create_app(data_dir=None, demo=None):
    app = FastAPI(title="ClearPay | Evidence-led payment verification", version="1.0.0")
    data = Path(data_dir or os.getenv("DATA_DIR", ROOT / "data"))
    data.mkdir(parents=True, exist_ok=True)
    dbpath = data / "clearpay.sqlite3"
    store.init(dbpath)
    demo = (os.getenv("DEMO_MODE", "true").lower() == "true") if demo is None else demo
    password = os.getenv("OPERATOR_PASSWORD", "demo-operator" if demo else "")
    if len(password) < 12:
        raise RuntimeError("Set OPERATOR_PASSWORD to at least 12 characters")
    secret_file = data / "gateway.key"
    sms_secret = os.getenv("SMS_SECRET")
    if not sms_secret:
        if not demo:
            raise RuntimeError("SMS_SECRET is required outside demo mode")
        if not secret_file.exists():
            secret_file.write_text(secrets.token_hex(32))
        sms_secret = secret_file.read_text().strip()
    if len(sms_secret) < 32:
        raise RuntimeError("SMS_SECRET must contain at least 32 characters")
    sessions, attempts = {}, {}
    account = os.getenv("MERCHANT_ACCOUNT", "1234567890")
    bank_sender = os.getenv("BANK_SENDER", "DEMO-BANK")
    app.state.dbpath, app.state.sms_secret = dbpath, sms_secret
    app.state.demo = demo

    @app.middleware("http")
    async def safeguards(request, call_next):
        if request.headers.get("content-length", "0").isdigit() and int(request.headers.get("content-length", "0")) > MAX_BYTES + 100_000:
            return JSONResponse({"detail": "Request too large"}, status_code=413)
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "Cross-origin write blocked"}, status_code=403)
        result = await call_next(request)
        result.headers["X-Content-Type-Options"] = "nosniff"
        result.headers["X-Frame-Options"] = "DENY"
        result.headers["Referrer-Policy"] = "no-referrer"
        result.headers["Cache-Control"] = "no-store"
        result.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; frame-ancestors 'none'"
        return result

    def operator(request: Request):
        token = request.cookies.get("session", "")
        if sessions.get(token, 0) < time.time():
            sessions.pop(token, None)
            raise HTTPException(401, "Sign in to review payments")
        return "operator"

    class Login(BaseModel):
        password: str = Field(max_length=200)

    @app.post("/api/login")
    def login(body: Login, request: Request, response: Response):
        ip = request.client.host
        recent = [t for t in attempts.get(ip, []) if t > time.time() - 60]
        attempts[ip] = recent
        if len(recent) >= 8:
            raise HTTPException(429, "Too many attempts; wait one minute")
        recent.append(time.time())
        if not secrets.compare_digest(body.password, password):
            raise HTTPException(401, "Incorrect password")
        token = secrets.token_urlsafe(32)
        sessions[token] = time.time() + 8 * 3600
        response.set_cookie("session", token, httponly=True, samesite="strict", secure=not demo, max_age=8*3600)
        return {"ok": True}

    @app.post("/api/logout")
    def logout(request: Request, response: Response, actor=Depends(operator)):
        sessions.pop(request.cookies.get("session"), None)
        response.delete_cookie("session")
        return {"ok": True}

    @app.get("/api/health")
    def health():
        return {"status": "ok", "demo": demo}

    class Order(BaseModel):
        customer: str = Field(min_length=2, max_length=100)
        amount_minor: int = Field(gt=0, le=100_000_000_00, strict=True)

    @app.post("/api/orders", status_code=201)
    def new_order(body: Order, actor=Depends(operator)):
        now = datetime.now(timezone.utc)
        order = dict(id="ORD-" + secrets.token_hex(3).upper(), customer=body.customer.strip(),
                     amount_minor=body.amount_minor, currency="LKR", account=account,
                     payment_code="PAY-" + secrets.token_hex(5).upper(), created_at=now.isoformat(timespec="seconds"),
                     expires_at=(now + timedelta(days=2)).isoformat(timespec="seconds"), paid=0)
        with store.connect(dbpath, True) as db:
            db.execute("INSERT INTO orders VALUES(:id,:customer,:amount_minor,:currency,:account,:payment_code,:created_at,:expires_at,:paid)", order)
            store.log(db, None, actor, "ORDER_CREATED", order)
        return order

    def evaluate(db, payment):
        order = dict(db.execute("SELECT * FROM orders WHERE id=?", (payment["order_id"],)).fetchone())
        own = db.execute("SELECT * FROM claims WHERE payment_id=?", (payment["id"],)).fetchone()
        if own:
            return json.loads(payment["decision"])
        claims = [r[0] for r in db.execute("SELECT transaction_key FROM claims")]
        used = db.execute("SELECT 1 FROM claims c JOIN payments p ON p.id=c.payment_id WHERE p.image_hash=?", (payment["image_hash"],)).fetchone()
        slip = json.loads(payment["extraction"])
        result = decide(order, slip, store.bank_records(db), claims, bool(used))
        db.execute("UPDATE payments SET decision=?,updated_at=? WHERE id=?", (json.dumps(result), store.utcnow(), payment["id"]))
        if result["status"] == "APPROVED":
            db.execute("INSERT INTO claims VALUES(?,?,?,?)", (f"{order['account']}:{slip['reference']}", order["id"], payment["id"], result["sms_id"]))
            db.execute("UPDATE orders SET paid=1 WHERE id=?", (order["id"],))
        store.log(db, payment["id"], "rules-engine", "DECISION", result)
        return result

    @app.post("/api/payments", status_code=201)
    def submit(request: Request, order_id: str = Form(...), image: UploadFile = File(...), actor=Depends(operator)):
        key = request.headers.get("idempotency-key", "")
        if not 8 <= len(key) <= 100:
            raise HTTPException(400, "Provide an Idempotency-Key of 8–100 characters")
        raw = image.file.read(MAX_BYTES + 1)
        digest = hashlib.sha256(raw).hexdigest()
        reqhash = hashlib.sha256((order_id + ":" + digest).encode()).hexdigest()
        with store.connect(dbpath) as db:
            previous = db.execute("SELECT * FROM payments WHERE idempotency_key=?", (key,)).fetchone()
            if previous:
                if previous["request_hash"] != reqhash:
                    raise HTTPException(409, "This idempotency key was used for different content")
                return {"id": previous["id"], "decision": json.loads(previous["decision"]), "replayed": True}
            if not db.execute("SELECT 1 FROM orders WHERE id=?", (order_id,)).fetchone():
                raise HTTPException(404, "Order not found")
            cached = db.execute("SELECT extraction FROM images WHERE hash=?", (digest,)).fetchone()
            if cached and json.loads(cached[0]).get("source") == "unavailable":
                cached = None  # Cache successful processing, never a transient engine outage.
        try:
            clean = normalize_image(raw)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        extraction = json.loads(cached[0]) if cached else extract(clean)
        pid, now = str(uuid.uuid4()), store.utcnow()
        with store.connect(dbpath, True) as db:
            # Repeat under the write lock: two concurrent retries must yield one payment.
            previous = db.execute("SELECT * FROM payments WHERE idempotency_key=?", (key,)).fetchone()
            if previous:
                if previous["request_hash"] != reqhash:
                    raise HTTPException(409, "Idempotency key conflict")
                return {"id": previous["id"], "decision": json.loads(previous["decision"]), "replayed": True}
            db.execute("INSERT INTO images VALUES(?,?,?) ON CONFLICT(hash) DO UPDATE SET extraction=excluded.extraction", (digest, clean, json.dumps(extraction)))
            db.execute("INSERT INTO payments VALUES(?,?,?,?,?,?,?,?,?)", (pid, order_id, digest, json.dumps(extraction), "{}", now, now, key, reqhash))
            store.log(db, pid, actor, "SUBMITTED", {"ocr_cache_hit": bool(cached), "image_hash": digest})
            payment = db.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
            decision = evaluate(db, payment)
        return {"id": pid, "decision": decision, "cache_hit": bool(cached)}

    def ingest(body, actor):
        if body.get("sender") != bank_sender:
            raise HTTPException(422, "Unrecognised bank sender")
        if not isinstance(body.get("event_id"), str) or not 1 <= len(body["event_id"]) <= 100:
            raise HTTPException(422, "Missing or invalid event_id")
        if not isinstance(body.get("text"), str) or not 1 <= len(body["text"]) <= 2000:
            raise HTTPException(422, "Missing or invalid SMS text")
        fields = parse_sms(body["text"])
        fields["trusted"] = not bool(fields["issues"])
        bodyhash = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        with store.connect(dbpath, True) as db:
            prev = db.execute("SELECT * FROM sms WHERE event_id=?", (body["event_id"],)).fetchone()
            if prev:
                if prev["body_hash"] != bodyhash:
                    raise HTTPException(409, "Gateway event ID reused with different content")
                return {"id": prev["id"], "replayed": True, "rechecked": 0}
            sid = str(uuid.uuid4())
            db.execute("INSERT INTO sms(id,event_id,body_hash,raw,fields,received_at) VALUES(?,?,?,?,?,?)", (sid, body["event_id"], bodyhash, body["text"], json.dumps(fields), store.utcnow()))
            store.log(db, None, actor, "SMS_RECEIVED", {"sms_id": sid, "parse_issues": fields["issues"]})
            pending = [p for p in db.execute("SELECT * FROM payments") if json.loads(p["decision"]).get("status") == "NEEDS VERIFICATION"]
            for p in pending:
                evaluate(db, p)
            # A contradictory late notification cannot safely revoke fulfilled goods.
            # Surface an urgent incident on already-approved evidence instead.
            conflicts = {m.get("reference") for m in store.bank_records(db) if m.get("conflict")}
            for p in db.execute("SELECT p.* FROM payments p JOIN claims c ON c.payment_id=p.id").fetchall():
                if json.loads(p["extraction"]).get("reference") in conflicts:
                    decision = json.loads(p["decision"])
                    decision["incident"] = "Late conflicting bank evidence. Stop fulfilment and investigate immediately."
                    db.execute("UPDATE payments SET decision=? WHERE id=?", (json.dumps(decision), p["id"]))
                    store.log(db, p["id"], "rules-engine", "LATE_EVIDENCE_CONFLICT", {"sms_id": sid})
        return {"id": sid, "fields": fields, "rechecked": len(pending)}

    @app.post("/api/gateway/sms")
    async def gateway(request: Request):
        raw = await request.body()
        if len(raw) > 5000:
            raise HTTPException(413, "SMS payload too large")
        timestamp = request.headers.get("x-timestamp", "")
        try:
            if abs(time.time() - int(timestamp)) > 300:
                raise ValueError()
        except ValueError:
            raise HTTPException(401, "Stale or missing gateway timestamp")
        expected = hmac.new(sms_secret.encode(), timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(request.headers.get("x-signature", ""), expected):
            raise HTTPException(401, "Invalid gateway signature")
        try:
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise ValueError()
        except ValueError:
            raise HTTPException(422, "Expected JSON object")
        return ingest(body, "authenticated-gateway")

    class DemoSMS(BaseModel):
        text: str = Field(min_length=1, max_length=2000)

    @app.post("/api/demo/sms")
    def demo_sms(body: DemoSMS, actor=Depends(operator)):
        if not demo:
            raise HTTPException(404)
        return ingest({"event_id": str(uuid.uuid4()), "sender": bank_sender, "text": body.text}, "demo-simulator")

    @app.post("/api/payments/{pid}/recheck")
    def recheck(pid: str, actor=Depends(operator)):
        with store.connect(dbpath, True) as db:
            payment = db.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
            if not payment:
                raise HTTPException(404)
            if json.loads(payment["decision"]).get("manual_rejection"):
                raise HTTPException(409, "A reviewed rejection is final in this prototype")
            return evaluate(db, payment)

    class Note(BaseModel):
        note: str = Field(min_length=5, max_length=1000)
        reject: bool = False

    @app.post("/api/payments/{pid}/review")
    def review(pid: str, body: Note, actor=Depends(operator)):
        with store.connect(dbpath, True) as db:
            payment = db.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
            if not payment:
                raise HTTPException(404)
            decision = json.loads(payment["decision"])
            if body.reject:
                if decision["status"] == "APPROVED":
                    raise HTTPException(409, "Accepted allocations cannot be silently reversed")
                decision.update(status="REJECTED", code="OPERATOR_REJECTED", reason=body.note,
                                manual_rejection=True, certainty="Operator reviewed",
                                next_action="Contact the customer to resolve this payment.",
                                customer_message="We could not accept this payment. Please contact the business.")
                db.execute("UPDATE payments SET decision=?,updated_at=? WHERE id=?", (json.dumps(decision), store.utcnow(), pid))
            store.log(db, pid, actor, "REJECTED_BY_OPERATOR" if body.reject else "REVIEW_NOTE", {"note": body.note})
        return {"ok": True}

    @app.get("/api/dashboard")
    def dashboard(actor=Depends(operator)):
        with store.connect(dbpath) as db:
            orders = [dict(r) for r in db.execute("SELECT * FROM orders ORDER BY created_at DESC")]
            payments = []
            for r in db.execute("SELECT * FROM payments ORDER BY created_at DESC, rowid DESC"):
                p = dict(r)
                p["extraction"], p["decision"] = json.loads(p["extraction"]), json.loads(p["decision"])
                p["order"] = next(o for o in orders if o["id"] == p["order_id"])
                payments.append(p)
            messages = store.bank_records(db)
        return {"orders": orders, "payments": payments, "sms": messages, "demo": demo, "account": account}

    @app.get("/api/payments/{pid}/audit")
    def audit(pid: str, actor=Depends(operator)):
        with store.connect(dbpath) as db:
            return [dict(r) for r in db.execute("SELECT * FROM audit WHERE payment_id=? ORDER BY id", (pid,))]

    @app.get("/api/payments/{pid}/image")
    def payment_image(pid: str, actor=Depends(operator)):
        with store.connect(dbpath) as db:
            row = db.execute("SELECT i.data FROM images i JOIN payments p ON p.image_hash=i.hash WHERE p.id=?", (pid,)).fetchone()
        if not row:
            raise HTTPException(404)
        return Response(row[0], media_type="image/png")

    @app.post("/api/demo/seed")
    def seed(actor=Depends(operator)):
        if not demo:
            raise HTTPException(404)
        from .demo import seed_database
        with store.connect(dbpath, True) as db:
            if db.execute("SELECT 1 FROM orders").fetchone():
                raise HTTPException(409, "Demo seeding requires an empty workspace; existing work is preserved")
            seed_database(db, evaluate, account)
        return {"ok": True}

    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

    @app.get("/")
    def index():
        return FileResponse(ROOT / "static" / "index.html")

    return app

app = create_app()
