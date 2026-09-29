# Version 2 validation

## Scope

BOC Flex English receipt adapter; persistent merchant account and per-order evidence mode; strict operator bank CSV import; auto recheck; explicit evidence provenance; reparse older saved OCR on recheck.

## Executed

- `python -m pytest -q`: 79 passed (one dependency deprecation warning).
- `node --check static/app.js`: passed.
- Python module compilation: passed.
- Actual uploaded BOC receipt OCR text: amount, full receiving account, reference, timezone-aware transaction time and currency extracted with no parser issues. Private values and image are not included in this package.
- Actual OCR on a synthetic BOC-layout image, with no extraction mocking: pending without bank evidence; approved after matching merchant CSV import.
- Negative tests: ambiguous receipt values, masked recipient, failed or missing receipt status, invalid dates, currency mismatch, wrong bank reference/amount/time, missing payment code, debit/reversal, bad CSV, replay, synthetic-source exclusion, repeated transaction allocation and late conflicting evidence.
- Existing 56 tests retained, including signed gateway, auth, concurrent claims, cache and blurred-image handling. Test doubles now mark the parser version so they are not mistaken for old persisted OCR.

## Limits

No measured population accuracy, precision or recall. One user receipt is not a benchmark. The BOC adapter reads the shown English layout; unsupported layouts remain in review. Digits in account/reference/amount are never guessed or repaired. Ambiguous O/0 readings remain unresolved.

Bank CSV uses an explicit normalized schema; it does not automatically discover arbitrary bank export column names. Import only merchant-origin bank data, retaining the original values. The app records operator import provenance rather than claiming bank authentication. It cannot detect a deliberately fabricated operator CSV. HMAC on the gateway authenticates the enrolled sender device, not the bank network itself.

The UI source and JavaScript syntax were checked. An attempted browser preview was blocked from reaching the local test port by this environment, so visual browser validation of the new dialogs was not completed here. The Windows update installer has not been executed on Windows in this development environment. Existing dependencies are reused; no additional package downloads are required by this update.

Old orders retain their original account and evidence mode. Existing accepted decisions/claims are preserved. Real-record mode excludes demo and legacy synthetic bank records for new orders. Automatic approval still requires the unique order code in the independent bank memo; without it, review remains necessary.
