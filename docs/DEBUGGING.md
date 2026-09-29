# Debugging record

These are observed implementation problems, not invented development stories. Tests were run before and after the relevant fixes.

## 1. Bank SMS inserts broke the end-to-end flow

**What failed:** The first full automated run reported **7 failed, 42 passed**. Seeding, delayed SMS processing, replay checks and concurrency tests failed with `sqlite3.OperationalError: table sms has 6 columns but 7 values were supplied`.

**Cause:** The SMS schema had six fields, but two INSERT statements contained seven positional placeholders. The payload itself contained the correct six values.

**How it was identified:** Followed the test traceback to `ingest()` and the demo seeder, compared their INSERT statements with `store.SCHEMA`, and verified the failing tests shared this persistence path rather than independent rule failures.

**Change:** Replaced implicit SMS inserts with explicit named columns and six placeholders in both real ingestion and seeding. The statements now document the schema they expect.

**Result:** The same suite changed to **49 passed**. The test cases cover the actual routes, including claim persistence, rather than merely checking SQL strings.

## 2. Real OCR read the label "Account" as "Acc0unt"

**What failed:** A clean, synthetic receipt passed through the real local OCR engine with minimum line confidence **0.967**, yet no `account` field was extracted. The OCR text contained `Acc0unt:1234567890`. A legitimate supported-format sample therefore could not progress beyond missing-field review.

**Cause:** The label parser accepted only the exact word `Account`. OCR had substituted zero for the letter o in the label. The account digits themselves were intact.

**How it was identified:** Inspected the returned OCR text and parsed field JSON from the same generated image. The amount, reference, timestamp and payment code parsed successfully, isolating the missing account to the label matcher.

**Change:** Allowed `Acc[o0]unt` only in the label. No substitutions were applied to account numbers, references, amounts or memo values. Added a focused regression test.

**Result:** Re-running actual OCR produced `account: 1234567890` with the original transaction values preserved. An integration test now uploads a generated PNG, waits for independent signed SMS evidence, and verifies the resulting approval. This is a synthetic-format check, not evidence of accuracy across real bank templates.

## 3. A temporary OCR outage was cached indefinitely

**What failed:** Inspection showed all extraction results were cached, including `source=unavailable`. Added a regression test where the first extraction fails and the second succeeds. It failed with **expected two calls, observed one**: the retry reused the cached engine failure.

**Cause:** The cache did not distinguish successful processing from a transient OCR service/import failure. Successful results should avoid repeated work; temporary failures should not become permanent facts.

**How it was identified:** Used a two-response extraction test double and counted calls over two separate submissions of the same image, while keeping the existing success-cache test intact.

**Change:** Ignore cached `unavailable` extraction, rerun OCR on a new submission, and update the image's current cached extraction. Existing payment records retain their original extracted evidence for audit. Exact retries using the original idempotency key still return the original response, as intended.

**Result:** Both the outage-retry test and the successful-cache test pass. The suite then reached **51 passed**; subsequent actual OCR tests also passed. If retrying after an OCR outage, submit a new request; the normal evidence-only Recheck button does not reread the image.

## Verification discipline

Decision tests isolate the policy; API tests exercise persistence and signatures; concurrency tests enforce one allocation; real OCR integration tests check the image path; browser checks inspect the operator workflow. These layers provide different evidence and are reported separately. A passing synthetic suite is not a calibrated false-approval rate for production fraud.

## 4. OCR removed whitespace after the currency

**What failed:** A later full run had 53 passing checks and one actual-OCR integration failure. The payment stayed in `MISSING_FIELDS` despite the amount, account, reference and timestamp being readable.

**Cause and diagnosis:** Inspected the failed test's stored extraction, not just the assertion. It contained `Amount:LKR25,000.00`, a parsed amount, and no currency. Currency detection required a word boundary after `LKR`; digits and letters are both word characters, so removing the space defeated that separate matcher.

**Change:** Derive LKR from a successfully parsed amount whose grammar already requires an explicit LKR/Rs prefix. Keep a separate conflict check for unsupported currency tokens, including tokens joined to digits. Added a regression covering both compact LKR text and a conflicting `USD25000` line.

**Result:** The parser now preserves the currency when OCR removes harmless whitespace, without relaxing amount/account matching or approving missing bank evidence. The expanded suite was rerun after this change; the final result is recorded in VALIDATION.md.
