import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS orders (
 id TEXT PRIMARY KEY, customer TEXT NOT NULL, amount_minor INTEGER NOT NULL CHECK(amount_minor>0),
 currency TEXT NOT NULL, account TEXT NOT NULL, payment_code TEXT UNIQUE NOT NULL,
 created_at TEXT NOT NULL, expires_at TEXT NOT NULL, paid INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS images (hash TEXT PRIMARY KEY, data BLOB NOT NULL, extraction TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sms (
 id TEXT PRIMARY KEY, event_id TEXT UNIQUE NOT NULL, body_hash TEXT NOT NULL,
 raw TEXT NOT NULL, fields TEXT NOT NULL, received_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS payments (
 id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(id), image_hash TEXT NOT NULL REFERENCES images(hash),
 extraction TEXT NOT NULL, decision TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 idempotency_key TEXT UNIQUE NOT NULL, request_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS claims (
 transaction_key TEXT PRIMARY KEY, order_id TEXT UNIQUE NOT NULL REFERENCES orders(id),
 payment_id TEXT UNIQUE NOT NULL REFERENCES payments(id), sms_id TEXT UNIQUE NOT NULL REFERENCES sms(id));
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS order_modes (order_id TEXT PRIMARY KEY REFERENCES orders(id), mode TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY AUTOINCREMENT, payment_id TEXT, at TEXT NOT NULL, actor TEXT NOT NULL,
 action TEXT NOT NULL, detail TEXT NOT NULL);
"""

@contextmanager
def connect(path, write=False):
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        if write:
            db.execute("BEGIN IMMEDIATE")
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def init(path):
    with connect(path) as db:
        db.executescript(SCHEMA)

def log(db, payment_id, actor, action, detail):
    db.execute("INSERT INTO audit(payment_id,at,actor,action,detail) VALUES(?,?,?,?,?)",
               (payment_id, utcnow(), actor, action, json.dumps(detail)))

def bank_records(db):
    records = []
    for row in db.execute("SELECT * FROM sms ORDER BY received_at"):
        fields = json.loads(row["fields"])
        fields.update(id=row["id"], raw=row["raw"], received_at=row["received_at"])
        records.append(fields)
    # Re-delivery with a different gateway ID is harmless only if all parsed fields agree.
    groups = {}
    for record in records:
        ref = record.get("reference")
        if not ref:
            continue
        try:
            stamp = datetime.fromisoformat(record.get("paid_at", "").replace("Z", "+00:00"))
            if stamp.tzinfo is not None:
                record["paid_at"] = stamp.astimezone(timezone.utc).isoformat(timespec="seconds")
        except (ValueError, TypeError):
            pass
        fingerprint = tuple(record.get(k) for k in ("amount_minor", "currency", "account", "paid_at", "order_code", "trusted"))
        scope = "bank_records" if record.get("evidence_source") in ("gateway", "merchant_statement") else "test"
        key = (ref, scope)
        if key not in groups:
            groups[key] = (record, fingerprint)
        elif groups[key][1] != fingerprint:
            groups[key][0]["conflict"] = True
    return [item[0] for item in groups.values()]
