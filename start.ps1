$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$venvPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -m venv .venv
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv .venv
    } else {
        throw 'Install Python 3.12, then run this script again. See README.md.'
    }
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
$check = "import importlib.util,sys; sys.exit(0 if all(importlib.util.find_spec(x) for x in ('fastapi','uvicorn','multipart','PIL','rapidocr_onnxruntime','cv2','onnxruntime')) else 1)"
& $venvPython -c $check
if ($LASTEXITCODE -ne 0) {
    $wheelhouse = Join-Path $PSScriptRoot 'wheelhouse'
    if (Test-Path -LiteralPath $wheelhouse) {
        Write-Host 'Installing bundled Windows dependencies offline...'
        & $venvPython -m pip install --no-index --find-links $wheelhouse -r requirements-dev.txt
    } else {
        Write-Host 'Installing dependencies from the internet...'
        & $venvPython -m pip install -r requirements-dev.txt
    }
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. See the error above.' }
}
Write-Host 'ClearPay: http://127.0.0.1:8000 | Local demo password: demo-operator'
& $venvPython -m uvicorn app.main:app --host 127.0.0.1 --port 8000
