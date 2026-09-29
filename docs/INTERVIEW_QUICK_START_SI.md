# ClearPay: interview එකට ඉක්මන් මඟපෙන්වීම

මෙය **original Python/FastAPI application එක**. Hosted synthetic walkthrough එක මෙහි backend එක නොවේ. මේ project එක local computer එකේ run කළ විට actual image OCR, order creation, payment decision, demo SMS recheck, SQLite audit trail වැඩ කරයි. මෙය prototype එකක්; real bank settlement verify කරන production service එකක් ලෙස පෙන්වන්න එපා.

## Windows වල පටන් ගන්න (internet අවශ්‍යයි: පළමු install එකට)

1. ZIP එක extract කර `clearpay` folder එක open කරන්න. Python **3.12** install කර තිබිය යුතුයි.
2. එම folder එකේ PowerShell open කර මෙය run කරන්න:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\start.ps1
   ```

3. Browser එකෙන් `http://127.0.0.1:8000` යන්න. Password: `demo-operator`.
4. **Load demo scenarios** click කරන්න. එය synthetic examples 9ක් load කරයි. Existing records මකන්නේ නැහැ.
5. නැවත run කරන විට එම command එකම භාවිතා කරන්න. Server නවත්වන්න `Ctrl+C`.

Installation ප්‍රශ්නයක් ආවොත් README.md හි manual commands බලන්න. පළමු dependency install එකට ටික වේලාවක් යා හැක. Interview එකට කලින් install කර run කර බලන්න. Port 8000 busy නම් කලින් run වන server එක නවත්වන්න.

## විනාඩි 5ක demo flow එක

1. **Ayesha / ORD-1001:** amount, account, reference, bank credit, order code ඔක්කොම match; **APPROVED**.
2. **Nimal / ORD-1002:** amount වැරදියි; **REJECTED**.
3. **Kavindi / ORD-1003:** image වෙනස් වුණත් එකම transaction reference එක නැවත භාවිතා කරයි; **REJECTED**.
4. **Ravindu / ORD-1004:** slip සහ bank SMS amounts වෙනස්; **NEEDS VERIFICATION**.
5. **Tharushi / ORD-1005:** blurred slip; OCR විශ්වාසදායක නැහැ; **NEEDS VERIFICATION**.
6. **Isuru / ORD-1006:** පළමුව SMS නැති නිසා pending. Details තුළ **Prepare matching demo SMS**, පසුව **Receive SMS & recheck pending**; එවිට approve වේ.
7. **Sara / ORD-1009:** amount/reference match වුණත් bank SMS තුළ unique order code නැහැ; ownership තහවුරු නොවේ.

මෙම seed කළ examples OCR accuracy test එකක් නොවේ. **Real OCR** පෙන්වන්න: Orders → New order (LKR 25,000) → generated payment code copy කරන්න → terminal එකක `python scripts/make_sample.py --code PAY-... --reference TXNEW001` run කරන්න → generated `samples/upload-demo.png` upload කරන්න. SMS නැති නිසා pending; generated `samples/upload-demo.sms.txt` හි text එක demo SMS dialog එකට paste කර recheck කරන්න. Exact code එක භාවිතා කරන්න; `PAY-...` යනු placeholder එකක්.

## Interview එකේ සරලව පැහැදිලි කරන විදිහ

**Problem:** Customer screenshot එකක් පමණක් ලබා දුන්නා කියා transfer එකක් ලැබුණා යැයි පිළිගැනීම අවදානම්.

**Flow:** Order එකක් සහ unique payment code එකක් create කරයි → customer slip එක upload කරයි → local RapidOCR fields කියවයි → deterministic rules order එකට compare කරයි → authenticated merchant-phone bank SMS evidence compare කරයි → unused transaction එක atomic SQLite transaction එකක claim කරයි → decision, reason, customer-safe reply සහ audit event save කරයි.

**Why three outcomes?** Evidence සම්පූර්ණයෙන් match නම් approve. පැහැදිලි වැරැද්දක් නම් reject. OCR අසාර්ථක හෝ bank evidence නැති/ගැටුම් සහිත නම් human verification. OCR confidence එක fraud probability එකක් ලෙස භාවිතා කරන්නේ නැහැ.

**Fraud/reuse protection:** Exact image SHA-256 එක byte-identical duplicate අල්ලයි; receiving account + bank reference එක වෙනස් screenshot එකකින් එකම transfer එක නැවත භාවිතා කිරීම අල්ලයි. Bank SMS එකේ unique order code නැත්නම් matching amount එකෙන් පමණක් ownership establish කරන්නේ නැහැ.

**Cost choice:** OCR local CPU එකේ; paid AI API නැහැ. Reused image එකකට cached extraction ඇත. Hosting, CPU, phone connectivity සහ manual reviews සඳහා තවමත් පිරිවැයක් ඇත.

**Honest limitations:** Synthetic test receipts සහ SMS භාවිතා කර validation කර ඇත. Real bank corpus, real phone, live settlement, WhatsApp integration හෝ public production deployment test කර නැහැ. SMS gateway signature එක phone relay එක authenticate කරයි; bank එකම authenticate කරන එකක් නොවේ. Real money fulfilment සඳහා statement reconciliation සහ bank-specific integration අවශ්‍යයි.

## Files ගැන මතක තියාගන්න

| File | කරන්නේ මොකක්ද |
| --- | --- |
| `app/extraction.py` | Image validation, OCR, text fields parse කිරීම |
| `app/engine.py` | Approval/rejection/review policy (pure decision rules) |
| `app/main.py` | API, login, upload, SMS gateway, decision allocation |
| `app/store.py` | SQLite tables සහ audit trail |
| `app/demo.py` | Synthetic scenario 9 සහ slip images |
| `static/` | Operator dashboard |
| `tests/` | API, rules, OCR, concurrency සහ SMS bridge tests |

## මම මේ turn එකේ කළ දේ

- Original ZIP source එක inspect කළා; project එකේ implementation වෙනස් කළේ නැහැ.
- Fresh Python 3.12 environment එකක dependencies install කර **55 tests pass** බව තහවුරු කළා.
- App homepage, health endpoint, operator login, dashboard route එක run වෙන බව check කළා.
- මේ Sinhala interview guide එක add කළා. Hosted static demo එක සහ original Python app එක වෙනම බව පැහැදිලි කළා.

වැඩි technical Q&A සඳහා `docs/INTERVIEW_GUIDE.md`, run instructions සඳහා `README.md`, test evidence සඳහා `docs/VALIDATION.md` බලන්න.

## BuildStart brief එකට ගැළපීම

Brief එකේ ප්‍රධාන outcomes තුන (`APPROVED`, `REJECTED`, `NEEDS VERIFICATION`), fraud/reuse/old/unclear/conflicting/missing cases, business UI, customer-safe reply, SMS arriving late, low-cost OCR, tests, debugging problems තුනකට වඩා, 2-3 page report සහ live demonstration මෙහි ඇත. `docs/ENGINEERING_REPORT.pdf` පිටු 3කි; `docs/DEBUGGING.md` තුළ real bugs 4ක් සහ fixes ඇත; `docs/DEMO_SCRIPT.md` live demo එකටයි.

**Submission එකට තවමත් ඔයා කළ යුතු දේ:** Source code එක GitHub හෝ interviewer ට ප්‍රවේශ විය හැකි repository එකකට upload කර link එක දෙන්න. මේ ZIP එක complete source copy එකක්, නමුත් repository link එකක් නොවේ. Live demo එක local app එකෙන් පෙන්වන්න; hosted synthetic walkthrough එක original app එක ලෙස ඉදිරිපත් කරන්න එපා. Interview එකට කලින් laptop එකේ full launch එක rehearsal කරන්න.

**තත්පර 45ක pitch:** “Customer එවන slip එක තනිව proof එකක් නොවේ. මගේ prototype එක local OCR එකෙන් fields කියවලා order එක, authenticated merchant-phone bank SMS එක සහ කලින් accepted transaction records එක්ක compare කරනවා. Exact amount/account/time/reference සහ bank memo එකේ unique order code එක match වුණොත් පමණක් approve කරනවා. Wrong evidence reject කරනවා; unclear හෝ missing evidence human review එකට දානවා. Duplicate image hash සහ transaction identity දෙකම check කරන නිසා crop කළ reused screenshot එකත් අල්ලනවා. Paid AI API නැහැ; uncertain case එකකට fabricated certainty නොදෙනවා.”
