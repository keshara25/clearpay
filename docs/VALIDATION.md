# Validation record

Validated on Windows with Python 3.12 on 29 September 2026.

## Automated result

**55 passed, 1 warning, 4.08 seconds** in the final `python -m pytest -q --tb=short` run after the currency-whitespace parser fix.

The warning is a Starlette TestClient deprecation notice about its `httpx` adapter. It did not fail the suite. The project pins its direct dependencies; before upgrading the test stack, re-run the suite and review compatibility.

| Layer | Evidence |
| --- | --- |
| Pure policy | Valid payment; wrong amount/currency/account; old/future/invalid time; missing fields; unreliable extraction; missing/ambiguous/untrusted/conflicting SMS; order attribution; reuse; already-paid order |
| Parsers | Decimal cents, malformed amounts, masked account, debit rejection, conflicting values, OCR label confusion and missing currency whitespace |
| API and storage | Operator authentication, seed preservation, late SMS re-evaluation, request/event idempotency, altered payload rejection, stale/bad signatures, origin rejection, invalid images, late-conflict incident and audit notes |
| Concurrency | Two simultaneous requests sharing one transaction produce exactly one accepted allocation |
| Cost/recovery | Successful OCR result reused; temporary OCR failure retried on a new submission |
| Real local OCR | Generated PNG goes through the actual engine and HTTP upload route; starts pending and approves only after matching signed SMS; a severely blurred generated image fails the reliable-reading gate |
| Phone bridge | Termux-format fixture filtering and persistent event deduplication; no physical Android device test |

API policy tests use an extraction test double so rule behavior is independent of OCR variation. Actual OCR tests are separate. All payment images and bank notifications used for validation were synthetic.

## Browser observations

The local application was opened and operated in the browser. Verified:

- Operator sign-in and initial empty state.
- Nine seeded cases: initially one approved, four rejected and four needing verification.
- Payment details display the original image, both expected and submitted fields, bank evidence, internal reason and customer-safe reply.
- A pending seeded payment becomes approved after a simulated delayed matching bank SMS.
- The Needs verification filter shows only unresolved cases.
- A new order was created through the UI. A generated image was selected through the file chooser and processed by actual local OCR. It initially required bank evidence and became approved after its matching synthetic notification.
- Desktop 1440-pixel and mobile 390-pixel layouts were inspected. Mobile page content remained within the viewport; the payment table has its own horizontal scrolling area.
- No browser error/warning log entries were returned in the inspected upload flow.

`dashboard.png` is a screenshot of the tested synthetic workspace after the late-SMS and real-upload demonstrations. It therefore shows ten submissions and three approved payments, rather than the initial seeded counts.

## Not established by these tests

No real labelled multi-bank receipt corpus, production fraud attempts, physical phone, live bank account, WhatsApp webhook or public hosted deployment was tested. Docker instructions are supplied but the image was not built in this environment. The suite is not a production false-approval/false-rejection estimate, an OCR accuracy benchmark or a load test. Local timing includes this machine and these fixtures only.

Before real use, evaluate field accuracy and decision outcomes on held-out bank-specific data, perform a security review, test device and network failure recovery, measure queue throughput and confirm bank-statement reconciliation.
