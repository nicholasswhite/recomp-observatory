param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$dashboardRoot = $PSScriptRoot
$dashboardUrl = 'http://127.0.0.1:8768'
$dashboardReady = $false
try {
    $dashboardHealth = Invoke-RestMethod -Uri "$dashboardUrl/health" -TimeoutSec 2
    if ($dashboardHealth.service -ne 'recomp-observatory') { throw 'Another service is using port 8768.' }
    $dashboardReady = $true
} catch {
    if ($_.Exception.Message -like '*Another service*') { throw }
}
if (-not $dashboardReady) {
    $dashboardPython = (Get-Command python.exe -ErrorAction Stop).Source
    $dashboardWork = Join-Path $dashboardRoot 'work'
    New-Item -ItemType Directory -Path $dashboardWork -Force | Out-Null
    $dashboardProcess = Start-Process -FilePath $dashboardPython -ArgumentList @('"' + (Join-Path $dashboardRoot 'server.py') + '"') -WorkingDirectory $dashboardRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $dashboardWork 'server.stdout.log') -RedirectStandardError (Join-Path $dashboardWork 'server.stderr.log')
    $dashboardProcess.Id | Set-Content -LiteralPath (Join-Path $dashboardWork 'server.pid')
    for ($dashboardAttempt = 0; $dashboardAttempt -lt 30; $dashboardAttempt++) {
        Start-Sleep -Milliseconds 200
        try {
            $dashboardHealth = Invoke-RestMethod -Uri "$dashboardUrl/health" -TimeoutSec 1
            if ($dashboardHealth.service -eq 'recomp-observatory') { $dashboardReady = $true; break }
        } catch {}
        if ($dashboardProcess.HasExited) { throw 'Dashboard exited. See work/server.stderr.log.' }
    }
    if (-not $dashboardReady) { throw 'Dashboard did not become ready. See work/server.stderr.log.' }
}
if (-not $NoBrowser) { Start-Process $dashboardUrl }
Write-Output $dashboardUrl
