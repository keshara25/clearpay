# Windows offline setup

Python 3.12 install වී තිබේ නම්, මේ ZIP එකේ `wheelhouse` folder එක තුළ ClearPay සඳහා අවශ්‍ය Windows packages සියල්ල ඇත. ඒවා install කිරීමට PyPI connection එකක් අවශ්‍ය නැහැ.

1. `ClearPay-Windows-Offline.zip` file එක right-click කර **Extract All** කරන්න.
2. Extract කළ `clearpay` folder එක open කරන්න. එහි `start.ps1` සහ `wheelhouse` දෙකම තිබිය යුතුයි.
3. File Explorer address bar එකට `powershell` type කර Enter ඔබන්න.
4. මෙය run කරන්න:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\start.ps1
   ```

5. `ClearPay: http://127.0.0.1:8000` සහ `Uvicorn running` පෙන්වූ විට browser එකෙන් `http://127.0.0.1:8000` open කරන්න. Password: `demo-operator`.

කලින් extract කළ folder එකේ incomplete `.venv` එකක් තිබුණත්, **නව ZIP එක වෙනම folder එකකට extract කිරීම පහසුම ක්‍රමයයි**. `wheelhouse` folder එක ZIP එකෙන් පිටතට copy කරලා package files තනි තනිව open කරන්න එපා. Install එකේ error එකක් ආවොත් terminal එකේ අන්තිම lines වල screenshot එක බලන්න.
