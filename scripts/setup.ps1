param([switch]$WithOcr)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if ($uvCommand) { uv venv .venv --python 3.12 }
    else { py -3.12 -m venv .venv }
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 or uv, then run setup again.' }
}
$requirements = if ($WithOcr) { 'backend\requirements-ocr.txt' } else { 'backend\requirements.txt' }
$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
if ($uvCommand) { uv --no-cache pip install --python .venv\Scripts\python.exe -r $requirements }
else {
    .\.venv\Scripts\python.exe -m ensurepip --upgrade
    .\.venv\Scripts\python.exe -m pip install -r $requirements
}
if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
Push-Location frontend
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
} finally { Pop-Location }
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
Write-Host 'Ready. Run .\scripts\start.ps1, then open http://localhost:8000'
