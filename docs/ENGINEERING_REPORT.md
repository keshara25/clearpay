# ClearPay — Short Engineering Report

BuildStart Software Engineering Intern Challenge · 29 September 2026

---

## 1. How the Solution Works

ClearPay is a single-merchant, evidence-led payment verification prototype. It treats a customer-uploaded bank slip as a **claim**, not as proof of payment. Approval requires independent corroboration from bank-side evidence before any order is fulfilled.

**Architecture.** The system is built with Python/FastAPI, SQLite (WAL mode) and a browser-based operator dashboard. Key components:

| Layer | Responsibility |
|---|---|
| `extraction.py` | Local CPU OCR via RapidOCR + labelled-field regex parser. Reads amount, account, reference, date and memo from slip images. |
| `engine.py` | Pure decision function (`decide()`). Takes order, slip, bank records and prior claims. Returns APPROVED, REJECTED or NEEDS VERIFICATION with reason codes. |
| `main.py` | FastAPI endpoints — order creation, slip upload, SMS/bank-record ingestion, dashboard, review workflow. |
| `store.py` | SQLite schema, connection management, audit logging, bank-record deduplication. |
| `bank_import.py` | Parses merchant-exported CSV bank statements into structured credit records. |

**Flow.** The operator creates an order → system generates a unique `PAY-XXXXXX` code → customer transfers money with the code in the memo → customer uploads receipt screenshot → system runs OCR, extracts fields, matches against the order and bank evidence → returns a decision. If evidence is incomplete the payment sits in "NEEDS VERIFICATION" and is automatically rechecked when new bank records arrive.

---

## 2. How We Verify a Payment Belongs to an Order

The system issues each order a **server-generated, unpredictable payment code** (e.g. `PAY-A3F92BC108`). The customer is instructed to include this code in the bank transfer memo field.

Automatic approval requires **all of the following to agree** between the slip OCR, the order record and the independent bank evidence:

- The `PAY-` code in the bank notification memo matches the order's `payment_code`.
- The bank transaction reference on the slip matches one found in bank evidence.
- The receiving account number matches the configured merchant account exactly.
- The transfer amount (in integer minor units, LKR cents) matches exactly — no tolerance.
- The currency is LKR.
- The payment timestamp falls within a valid window: after order creation (minus 5 min clock-skew) and before the 2-day expiry.

Matching on **amount and time alone** is deliberately insufficient. Multiple customers can pay the same amount at similar times; only the unique `PAY-` code in the bank memo establishes true ownership.

Money values are parsed as `Decimal` text and stored as integer minor units, completely avoiding floating-point comparison errors.

---

## 3. How We Detect Duplicate / Reused Payments

Duplicate detection operates at **three independent layers**:

1. **Byte-identical image detection.** The SHA-256 hash of the raw uploaded image is computed. If this exact image was already used in an accepted payment, the system immediately returns `DUPLICATE_IMAGE` rejection.

2. **Transaction-reference claim table.** When a payment is approved, the compound key `account:reference` is inserted into a `claims` table with `UNIQUE` constraints on `transaction_key`, `order_id`, `payment_id` and `sms_id`. If a different slip carries the same bank reference (even from a re-screenshot or crop), the engine returns `REUSED_TRANSACTION` — the transfer has already been allocated.

3. **Idempotency keys.** Each upload carries an idempotency key. If the same key arrives again with identical content, the original response is replayed harmlessly. If the same key arrives with *different* content, a `409 Conflict` is returned. This protects against network retries creating phantom payments.

Approval, transaction claim and order-paid state are committed in a **single SQLite IMMEDIATE transaction**, so two concurrent submissions cannot both consume the same transfer.

---

---PAGE---

## 4. How We Handle Suspicious or Manipulated Slips

ClearPay does **not** claim to authenticate screenshots visually. Instead, it detects inconsistencies:

| Check | Response |
|---|---|
| OCR confidence < 90% or extraction issues | `UNRELIABLE_EXTRACTION` → review (not rejection, to avoid accusing a customer based on poor image quality) |
| Required fields missing | `MISSING_FIELDS` → review |
| Wrong receiving account | `WRONG_ACCOUNT` → reject |
| Wrong amount (even 1 cent off) | `WRONG_AMOUNT` → reject |
| Wrong currency | `WRONG_CURRENCY` → reject |
| Payment date before order creation | `OLD_PAYMENT` → reject |
| Future timestamp | `FUTURE_DATE` → review |
| Slip and bank evidence disagree on amount/account/time | `CONFLICTING_EVIDENCE` → review |
| PAY-code in slip belongs to different order | `ORDER_CODE_CONFLICT` → review |
| Readable receipt but unsupported bank format | `UNSUPPORTED_RECEIPT_FORMAT` → review, not reject |

The key design principle: **uncertain extraction triggers review, not rejection**. A blurry photo does not equal fraud — the system avoids turning a guess into an accusation. Conversely, even a perfectly clear slip is never auto-approved without corroborating bank evidence.

Operators can add review notes or reject with a written reason, but **cannot manually approve** — eliminating the social-engineering risk of an "override" button.

---

## 5. How We Use Bank SMS Information

Bank evidence enters the system through two channels:

### a) SMS Gateway (`/api/gateway/sms`)
- **Authentication:** HMAC-SHA256 signature over `timestamp.body` using a pre-shared secret (≥32 chars). Transport timestamps must fall within a 5-minute window.
- **Parsing:** The `parse_sms()` function normalises the text and extracts amount, account, reference, date and memo. It requires an unambiguous "credited" keyword and rejects messages containing "debited", "reversed", "failed" or "pending".
- **Deduplication:** `event_id` uniqueness prevents double-counting. Re-delivery with identical content is harmless; a re-used event ID with different content is rejected (409).
- **Conflict detection:** Two different events that disagree about the same bank reference create an `evidence_conflict` flag.

### b) Merchant Bank CSV Import (`/api/bank/import`)
- The operator exports a CSV from their bank portal and uploads it. Each row is strictly validated (CREDIT direction, COMPLETED status, LKR, valid reference, timezone-aware timestamp).
- Records are SHA-256 fingerprinted to prevent re-import of duplicates.

**Automatic re-evaluation:** When new bank evidence arrives (SMS or CSV), all `NEEDS VERIFICATION` payments are automatically re-evaluated. Late contradictory evidence on an already-approved payment creates an **urgent incident flag** rather than silently revoking the allocation.

---

## 6. How We Minimise Cost

| Strategy | Detail |
|---|---|
| **No paid AI/cloud API calls** | All OCR runs locally on CPU using RapidOCR (ONNX Runtime). Zero per-transaction API costs. |
| **OCR result caching** | Successful extractions are cached by image content hash in the `images` table. Re-uploads of the same image skip OCR entirely. |
| **Idempotent retries** | Repeated submissions with the same idempotency key return cached responses — no re-processing. |
| **Single engine instance** | The OCR engine is initialised once (lazy, thread-safe) and reused for all requests. |
| **Review over expensive fallback** | Low-confidence cases go to human review rather than escalating to a costly cloud vision model. |
| **Temporary failures not cached** | If OCR is transiently unavailable, the `"unavailable"` result is *not* cached, so the next attempt re-tries OCR. Only successful extractions are cached. |
| **Lightweight stack** | SQLite file database, no external message broker, no container orchestration overhead for the prototype. |

---

---PAGE---

## 7. Major Limitations

1. **Single merchant, single account, LKR only.** No multi-tenancy or multi-currency support.
2. **Limited receipt formats.** Only BOC Flex English receipts and one generic labelled format are parsed. Other Sri Lankan banks will trigger `UNSUPPORTED_RECEIPT_FORMAT` and require manual review.
3. **No direct bank API.** The system relies on operator-imported CSV or SMS forwarding — neither is a real-time, authenticated settlement feed.
4. **SMS ≠ settlement proof.** An HMAC-signed SMS proves the configured gateway sent it; it does not prove actual bank settlement or prevent a compromised phone from fabricating messages.
5. **No visual forgery detection.** The system does not perform image forensics (ELA, metadata analysis, font consistency). It relies purely on cross-referencing with bank evidence.
6. **No WhatsApp integration.** The prototype is operator-only; there is no customer-facing chatbot or WhatsApp connector.
7. **No refund/reversal/chargeback workflow.** Approved payments cannot be programmatically reversed.
8. **OCR accuracy is finite.** High-confidence OCR can still misread characters (e.g., `0` ↔ `O`, `1` ↔ `l`). The narrow parser and bank corroboration reduce but cannot eliminate this risk.
9. **Synchronous processing.** All operations are blocking — no background job queue for high-throughput scenarios.
10. **Shared operator password.** No individual user accounts, roles, or MFA.

---

## 8. What We Would Change for Production Scale

For 100,000+ monthly submissions:

- **Database:** Migrate from SQLite to tenant-scoped PostgreSQL with indexed evidence lookups and row-level security.
- **Image storage:** Move images from SQLite BLOBs to private object storage (S3/GCS) with retention policies and signed URLs.
- **Job queue:** Add a durable task queue (Celery/Cloud Tasks) with bounded OCR workers, retry budgets and a transactional outbox pattern so notification delivery survives restarts.
- **Authentication:** Replace the shared password with individual operator identities (OAuth/SSO), role-based access control and persistent session storage.
- **Device security:** Issue each merchant phone a revocable signing key, enforce mutual TLS, monitor device health.
- **Bank integration:** Connect to actual bank APIs or Open Banking feeds for real-time settlement confirmation rather than relying on SMS parsing.
- **Multi-bank parsers:** Add versioned, bank-specific receipt adapters with a parser registry and confidence-weighted fallback.
- **Reconciliation:** Implement automated end-of-day statement reconciliation, reversal/chargeback handling and immutable external audit retention.
- **Monitoring:** Track false-approval rate, false-rejection rate, incorrect attribution, review backlog age, p95 latency and cost per submission.
- **Deployment:** Shadow-mode decisions with human confirmation before automated fulfilment. Gradual rollout with kill switches per merchant.

---

## References

- FastAPI upload documentation: https://fastapi.tiangolo.com/tutorial/request-files/
- SQLite transaction semantics: https://www.sqlite.org/lang_transaction.html
- RapidOCR: https://github.com/RapidAI/RapidOCR
- Termux:API (phone bridge): https://github.com/termux/termux-api
