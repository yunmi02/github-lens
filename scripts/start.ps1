param([int]$Port = 8000, [switch]$LocalOnly)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { throw 'Run scripts/setup.ps1 first.' }
$bindAddress = if ($LocalOnly) { '127.0.0.1' } else { '0.0.0.0' }
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host $bindAddress --port $Port --workers 1
