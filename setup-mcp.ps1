# Run this separately, NOT as the command in an MCP host's stdio configuration.
# Installation messages on stdout would corrupt the MCP protocol stream.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'run.ps1') -CheckOnly
    if ($LASTEXITCODE -ne 0) { throw 'App environment/index setup failed.' }
    $pythonPath = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
    & $pythonPath -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot 'requirements-mcp.txt')
    if ($LASTEXITCODE -ne 0) { throw 'MCP dependency installation failed.' }
    & $pythonPath -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency compatibility check failed.' }
    Write-Host 'MCP dependencies and the shared index are ready. See MCP.md for client configuration.' -ForegroundColor Green
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
