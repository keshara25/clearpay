# Interview එකට project එක තේරුම් ගන්න

මේක කටපාඩම් කරලා කියන්න හදපු script එකක් විතරක් නෙවෙයි. පහළ කොටස් code එකත් එක්ක බලලා, demo එක ඔයාම run කරලා, වෙනසක් කරලා test එකක් pass කරගන්න. AI භාවිත කළ බව අවංකව කියන්න; ඔයා ඇත්තටම තේරුම් ගත්ත දේ පමණක් explain කරන්න.

## 1. Project එකේ main idea එක

Customer එවපු bank slip එක කියන්නේ **customer කරන claim එකක්**. ඒක ලස්සනට පේන නිසා genuine කියන්න බැහැ. අපි ඒ slip එක order details, business එකට ලැබුණු SMS එක සහ කලින් accepted payments එක්ක සසඳනවා.

Interview එකේ කියන්න පුළුවන් English:

> “I treat a payment slip as a claim, not proof of receipt. I approve only when the order, transaction details, independent bank notification and reuse checks agree. Otherwise I return a reasoned rejection or keep the payment in verification.”

මුලින් flow එක මතක තියාගන්න:

**Upload → image validation → hash/cache → OCR → field parsing → evidence checks → atomic allocation → decision + reply.**

## 2. Components ටික බලන පිළිවෙළ

1. `app/engine.py`: `decide()` function එක මුලින් කියවන්න. Inputs මොනවාද? early returns ඇයි? `APPROVED` වෙන්න සම්පූර්ණ විය යුතු checks මොනවාද?
2. `tests/test_engine.py`: එක condition එකක් වෙනස් කළාම expected decision එක මොකක්ද කියලා බලන්න.
3. `app/extraction.py`: OCR සහ parser දෙක වෙන වෙනම වැඩ දෙකක් කියලා තේරුම් ගන්න. OCR image එක text කරනවා. Parser ඒ text එකෙන් fields ගන්නවා.
4. `app/store.py`: tables සහ `UNIQUE` constraints බලන්න. Code එකේ if statement එකකට අමතරව database එකේ protection එකක් තියෙන්නේ ඇයි?
5. `app/main.py`: upload request එක engine එකට සම්බන්ධ කරන විදිහ සහ signed SMS flow එක බලන්න.
6. `static/app.js`: API response එක dashboard එකට දාන්නේ කොහොමද බලන්න. `esc()` function එක untrusted text HTML විදිහට execute වීම වැළැක්වීමට භාවිත වෙනවා.

## 3. අහන්න ඉඩ තියෙන ප්‍රශ්න

### Why not approve if the amount matches?

දෙන්නෙක් එකම amount එක ගෙවන්න පුළුවන්. Amount + time එක match වුණත් owner කවුද කියලා prove වෙන්නේ නැහැ. ඒ නිසා server එක generate කරපු order payment code එක **bank evidence එකේත්** තිබිය යුතුයි. Slip එකේ විතරක් තිබ්බාට මදි.

> “Matching amount is not proof of ownership. I require an order-specific identifier in independent bank evidence. If it is absent, the case stays in review.”

### What if the bank SMS does not include the payment code?

එහෙනම් මේ implementation එක automatic approve කරන්නේ නැහැ. වෙනත් independently verified mapping එකක් හෝ manual bank-statement check එකක් අවශ්‍යයි. මේ සීමාව hide කරන්න එපා. Challenge එකේ XXXX1234 වගේ masked SMS example එකත් automatic approval එකට මදි.

### How do you catch a cropped or edited copy?

Hash එකෙන් හසු වෙන්නේ exact same bytes විතරයි. Crop කළාම hash එක වෙනස් වෙනවා. ඒ නිසා දෙවැනි check එක bank reference + receiving account එකෙන් transaction එක දැනටම claim කරලාද බලන එක.

> “Image hashing is only the first layer. Transaction-level allocation catches reuse across different screenshots. If I cannot reliably extract the transaction identity, I do not approve.”

### Why use database constraints as well as code checks?

Requests දෙකක් එකවර ආවොත් දෙකම ‘not used yet’ කියලා කියවන්න පුළුවන්. ඒකට race condition කියනවා. `BEGIN IMMEDIATE` write transaction එකත් `UNIQUE` constraints ටිකත් නිසා එක transaction එක orders දෙකකට allocate කරන්න බැහැ.

### What is idempotency?

Network timeout එකක් නිසා client එක same request එක ආයෙ එවන්න පුළුවන්. Same key + same content නම් කලින් result එකම දෙන්න ඕනේ. New payment එකක් create කරන්න ඕනේ නැහැ. Same key වෙනස් content එකකට භාවිත කළොත් 409 conflict එකක් දෙනවා.

### Why not use a big AI model for everything?

Image එක කියවන්න local OCR ප්‍රමාණවත් වෙන්න පුළුවන්. Paid model එකක් confidence එකෙන් answer කළත් bank account එකට money ආවද කියලා ඒකට prove කරන්න බැහැ. Cost එක අඩු කරගන්න cache, local CPU සහ human review භාවිත කළා. AI fallback එකක් add කරන්නේ measured benefit එකක් තියෙනවා නම් පමණයි.

### Does an OCR score of 97% mean the payment is 97% genuine?

නැහැ. ඒක text recognition engine එකේ score එකක්. Fraud probability එකක් හෝ calibrated accuracy rate එකක් නෙවෙයි. Dashboard එකේ ඒ වෙනස පැහැදිලිව දාලා තියෙනවා.

### What does the SMS signature prove?

Configured gateway secret එක දන්න device එකෙන් message එක එවලා තියෙන බව සහ transport අතර body එක වෙනස් වෙලා නැති බව පරීක්ෂා කරනවා. ඒක bank settlement prove කරන්නේ නැහැ. Phone එක compromise වුණොත් හෝ sender spoof වුණොත් risks ඉතිරි වෙනවා.

### What happens if SMS arrives late?

මුලින් `NEEDS VERIFICATION`. Signed SMS එක ආවම pending submissions recheck කරනවා. Already approved payment එකකට පස්සේ conflicting SMS එකක් ආවොත් urgent incident එකක් පෙන්වනවා. Fulfilled order එක silently undo කරනවා කියලා බොරු කියන්නේ නැහැ.

### Why three decisions instead of yes/no?

Evidence මදි කියන්නේ fraudulent කියන එක නෙවෙයි. Missing SMS එකක් හෝ blurry image එකක් තිබ්බාම uncertainty එක represent කරන්න වෙනම state එකක් අවශ්‍යයි.

### Why SQLite and plain JavaScript?

Prototype එක local setup කරන්න ලේසියි. Core engineering problem එක evidence rules සහ safe allocation එක. ඒක unnecessary services වලට බෙදලා explain කරන්න අමාරු කරන්නේ නැහැ. Scale එකට tenant-aware PostgreSQL, queues සහ separate workers වලට යන්න පුළුවන්.

## 4. ඇත්තටම හමුවුණු bugs තුන

`DEBUGGING.md` කියවන්න. “What failed → how I reproduced it → cause → fix → regression test” පිළිවෙළට explain කරන්න.

- SMS INSERT එකේ columns ගණන සහ placeholders ගණන වෙනස් වුණා. API tests හතක් fail වුණා. Explicit columns දාලා fix කළා.
- OCR එක `Account` label එක `Acc0unt` කියලා කියෙව්වා. Label එක පමණක් tolerate කළා. Account digits rewrite කළේ නැහැ.
- OCR temporary failure එක cache වෙලා තිබුණා. Retry test එකෙන් හඳුනාගෙන failures reusable cache එකෙන් ඉවත් කළා.

ඔයාම ඒ tests run කරලා බලන තුරු “I independently debugged all of this” කියලා කියන්න එපා. “I used AI assistance, reviewed the failure evidence, and can explain and reproduce the fixes” කියන එක honest.

## 5. Practice tasks — ඔයාම කරන්න

1. `test_engine.py` එකේ normal case එකේ amount එක cent එකකින් අඩු කරලා result එක predict කරන්න. පස්සේ test කරන්න.
2. Bank SMS එකේ `order_code` ඉවත් කරන්න. Why not approved කියලා explain කරන්න.
3. Same image twice submit කරන්න. Same idempotency key retry එක සහ new submission එක අතර වෙනස කියන්න.
4. `parse_sms()` ට අලුත් bank format එකක් support කරන්න කලින් ඒ format එකට test එකක් ලියන්න. Negative/debit message එකක් approve නොවෙන බවත් test කරන්න.
5. Time tolerance එක configuration එකකට ගෙනියන්න හිතලා බලන්න: code එකේ කොහෙද වෙනස් වෙන්නේ, edge tests මොනවාද?

## 6. Production scale answer

> “At higher volume, I would preserve the same allocation invariants while moving to tenant-scoped PostgreSQL constraints, durable queues, bounded OCR workers and private object storage. I would add per-device keys, reconciliation, monitoring and a measured review process before enabling automatic fulfilment.”

100,000 per month කියන එකෙන් peak requests per second දැනගන්න බැහැ. Traffic pattern සහ OCR service time measure කරලා capacity තීරණය කරන්න.

## 7. Submit කරන්න කලින් ඔයාට explain කරන්න පුළුවන් විය යුතු දේ

- Slip එක proof එකක් නොවෙන්නේ ඇයි?
- Approve වෙන්න අවශ්‍ය independent evidence මොනවාද?
- Amount match එකෙන් ownership prove නොවෙන්නේ ඇයි?
- Hash සහ transaction reference දෙකේ වෙනස මොකක්ද?
- Concurrent requests වලදී double allocation නවත්තන්නේ කොහොමද?
- What is implemented, simulated, tested, and still unverified?

මේ ප්‍රශ්නවලට ඔයාගේම වචනෙන් answer දෙන්න පුළුවන් නම් code walkthrough සහ small modification එකකට හොඳ පදනමක් තියෙනවා.
