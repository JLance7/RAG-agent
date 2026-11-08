$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'run.ps1') -CheckOnly
    if ($LASTEXITCODE -ne 0) { throw 'App setup failed.' }
    & (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') -u -m ragbot.local_runtime setup
    if ($LASTEXITCODE -ne 0) { throw 'Local model setup failed.' }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
