param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
try {
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        $candidates = @()
        $bundledPython = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
        if (Test-Path -LiteralPath $bundledPython) { $candidates += @{ File = $bundledPython; Arguments = @() } }
        if (Get-Command py.exe -ErrorAction SilentlyContinue) { $candidates += @{ File = 'py.exe'; Arguments = @('-3') } }
        if (Get-Command python.exe -ErrorAction SilentlyContinue) { $candidates += @{ File = 'python.exe'; Arguments = @() } }
        $chosen = $null
        foreach ($candidate in $candidates) {
            $prefix = $candidate.Arguments
            try {
                & $candidate.File @prefix -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>$null
                if ($LASTEXITCODE -eq 0) { $chosen = $candidate; break }
            } catch { }
        }
        if (-not $chosen) { throw 'Install Python 3.11 or newer from python.org, then run Start.bat again.' }
        $prefix = $chosen.Arguments
        & $chosen.File @prefix -m venv (Join-Path $PSScriptRoot '.venv')
        if ($LASTEXITCODE -ne 0) {
            if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Could not create the virtual environment.' }
            & $pythonPath -m ensurepip --upgrade
            if ($LASTEXITCODE -ne 0) { throw 'Could not initialize pip.' }
        }
    }
    $requirements = Join-Path $PSScriptRoot 'requirements.txt'
    $stamp = Join-Path $PSScriptRoot '.venv/requirements.sha256'
    $hash = (Get-FileHash -LiteralPath $requirements).Hash
    if (-not (Test-Path -LiteralPath $stamp) -or (Get-Content -LiteralPath $stamp -Raw).Trim() -ne $hash) {
        & $pythonPath -m pip install --disable-pip-version-check -r $requirements
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
        Set-Content -LiteralPath $stamp -Value $hash
    }
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'storage/desk.sqlite3'))) {
        $samplePaths = @(Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'sample_data') -File |
            Where-Object { $_.Extension -in @('.csv', '.md') -and $_.Name -ne 'README.md' } |
            ForEach-Object { $_.FullName })
        & $pythonPath -m ragbot.cli ingest @samplePaths
        if ($LASTEXITCODE -ne 0) { throw 'Sample indexing failed.' }
    }
    if ($CheckOnly) {
        & $pythonPath -c 'from ragbot.store import Store; Store().documents()'
        if ($LASTEXITCODE -ne 0) { throw 'Index verification failed.' }
        Write-Host 'Local index verified.' -ForegroundColor Green
    } else {
        if (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.runtime/ollama/ollama.exe')) {
            & $pythonPath -m ragbot.local_runtime start
            if ($LASTEXITCODE -ne 0) { Write-Host 'Ollama did not start. See storage/ollama-server.log; evidence mode remains available.' -ForegroundColor Yellow }
        } else {
            Write-Host 'Run Setup Local Model.bat to install the local generator. Evidence mode remains available.' -ForegroundColor Yellow
        }
        & $pythonPath -m streamlit run (Join-Path $PSScriptRoot 'app.py') --server.address 127.0.0.1 --browser.gatherUsageStats false
        if ($LASTEXITCODE -ne 0) { throw 'Streamlit exited with an error.' }
    }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
