# Five-minute demonstration script

Use synthetic data only. The demo is a live walkthrough; no recorded video is included automatically.

## 0:00 — Explain the problem

"ClearPay helps a business decide whether a submitted bank payment can safely be accepted. A screenshot alone cannot prove that money arrived. The system combines order details, extracted receipt fields, authenticated bank SMS and previous payment allocations."

## 0:30 — Show the dashboard

Load demo scenarios on an empty workspace. Point out the three decisions and the visible demo warning. Explain that seeded extraction is for deterministic demonstration; real uploads use local OCR.

"The interface separates what the customer submitted from what the system concluded. It also gives the operator an internal reason and a customer-safe response."

## 1:00 — Valid and wrong-amount cases

Open Ayesha / ORD-1001. Show the matched amount, account, reference, bank memo and audit trail. Open Nimal / ORD-1002 and compare submitted LKR 24,000 to expected LKR 25,000.

"Approval needs all required evidence. The amount is stored in integer cents, so even a one-cent mismatch is handled consistently."

## 1:45 — Reuse and suspicious evidence

Open Kavindi / ORD-1003. Show the related accepted payment. Then open Ravindu / ORD-1004 and point out the different amount in the bank record.

"Changing a screenshot changes its hash, so I also protect the bank transaction identity. Conflicting evidence goes to review rather than being forced into a confident answer."

## 2:30 — Unclear slip and missing evidence

Open Tharushi / ORD-1005 and show the image and safe request for a clearer receipt. Open Isuru / ORD-1006, currently awaiting a bank notification. Prepare the matching demo SMS, receive it and show that the payment becomes approved.

"SMS can arrive late. Pending payments are re-evaluated when new independent evidence arrives."

## 3:20 — Same amount does not prove ownership

Open Sara / ORD-1009. Amount and reference match, but the bank evidence lacks this order's payment code.

"If the bank does not echo a reliable memo or another ownership identifier, I cannot safely link a payment to this order. I prefer a review case to a false approval."

## 3:50 — Show actual OCR separately

Use README's sample-generation flow for a new order. Upload the generated image. Show extracted text and the source label, then provide the matching synthetic notification. If OCR is uncertain, explain the review outcome; do not edit scores or claim a fixture ran OCR.

## 4:30 — Explain quality, cost and limitations

"I used local OCR and content caching to avoid per-image AI charges. Atomic database constraints prevent double allocation. The tests include security, retries, concurrent claims and real synthetic-image OCR. This is a single-merchant prototype; the phone bridge has not been tested with a physical bank phone, and the system does not prove bank settlement."

Finish by showing `app/engine.py` and one test. Be ready to modify an amount rule or add a bank parser case live.
