# ClearPay v2 — Auto approval භාවිතා කරන හැටි

## මේ update එකෙන් ලැබෙන්නේ

- BOC Flex English receipt එකේ amount, receiving account, reference, transaction date/time කියවීම.
- Merchant account එක UI එකෙන් සැකසීම.
- Merchantගේ bank export එකෙන් ලබාගත් CSV credits import කර order + receipt + bank record ගැළපුණාම auto approve කිරීම.
- Signed SMS gateway එක තවම ඇත. සැබෑ phone / bank integration එක වෙනම සකස් කළ යුතුයි.
- Bank records mode හි අලුත් orders සඳහා demo SMS පිළිගන්නේ නැහැ.

## පියවර

1. Bank inbox → Merchant setup.
2. Business එකේ ඇත්ත receiving account එක දාන්න. `Bank records` mode තෝරා Save කරන්න.
3. Orders → New order. Amount එක දී order එක හදන්න.
4. Customerට receiving account එක සහ order එකේ `PAY-...` code එක දෙන්න. Transfer memo එකේ එම code එක දාන්න.
5. Customer මුදල් යැවූ පසු receipt photo එක upload කරන්න.
6. Merchantගේ receiving bank account එකෙන් credit records/export ලබාගන්න. Customerගේ slip එකෙන් මේ records හදන්න එපා.
7. Bank inbox → Import bank CSV → Download empty CSV template.
8. Bank export එකේ ඇත්ත විස්තර template columns වලට map කරන්න. Bank memo එකේ PAY code නැත්නම් order_code හිස්ව තබන්න. Code එක අනුමාන කර පුරවන්න එපා.
9. CSV import කළාම matching pending payments auto approve වෙනවා. Bank records කලින් import කර තිබුණොත් slip upload වෙද්දීම match කරනවා.

## CSV columns

`account,reference,amount,currency,paid_at,direction,status,order_code`

- account: merchant receiving account (full digits; leading zeros රැකගන්න).
- reference: receipt එක සහ bank record එකේ එකම transaction reference.
- amount: decimal rupees, උදාහරණයක් ලෙස `1234.56`.
- currency: `LKR`.
- paid_at: ISO date/time සහ timezone, උදාහරණ format එක `2026-09-29T16:10:00+05:30`.
- direction: `CREDIT`.
- status: `COMPLETED`.
- order_code: bank memo එකේ තිබෙන PAY code එකම; නැත්නම් හිස්.

Bank export එකේ code/time/full account/reference නොමැති නම් system එකට ස්වයංක්‍රීයව ඒවා තහවුරු කළ නොහැක. Masked records හෝ වෙනස් reference numbering formats සඳහා තවත් bank adapter එකක් අවශ්‍ය වේ.

## පරණ receipt එක Recheck කිරීම

Update එකට පෙර saved කළ OCR text එක Recheck වෙද්දී අලුත් parser එකෙන් නැවත parse වෙනවා. Photo එක නැවත upload කළ යුතු නැහැ. Old receipt එකක් අලුත් order එකකට දුන්නොත් date/account වැනි හේතු නිසා reject/review විය හැක. Existing orders වල account සහ mode වෙනස් නොවේ; merchant setup කිරීමෙන් පසු අලුත් order එකක් හදන්න.

## Accuracy ගැන interview එකේ කියන්න

79 automated tests pass විය. Actual OCR සහිත synthetic BOC layout එක → bank CSV → auto approval path එකද පරීක්ෂා කර ඇත. User ලබාදුන් එක් BOC receipt එකේ අවශ්‍ය fields පහම parse විය. මේවා 99%/100% real-world accuracy එකක් තහවුරු නොකරයි. විවිධ banks, photos, blur, rotations සහ fraud cases සහිත labelled dataset එකකින් තව evaluate කළ යුතුයි.

Receipt OCR confidence එක payment එක ඇත්ත බවේ probability එක නොවේ. Auto approval සඳහා exact account/amount/currency/reference, valid time window, bank memo order code සහ unused transaction අවශ්‍යය. CSV provenance එක `Merchant-imported bank record` ලෙස audit වේ. CSV එක bank එකෙන්ම export වුණාද යන්න app එක cryptographically verify නොකරයි. එය operator-supplied evidence මත automated reconciliation එකකි.

මෙම version එක සම්පූර්ණ live bank integration එකක් නොවේ. Signed gateway production setup, bank-specific SMS format, secure deployment සහ broader accuracy evaluation තවම අවශ්‍ය වේ. Bank password/OTP කිසිවක් app එකට අවශ්‍ය නැහැ.
