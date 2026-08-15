# PASTE - Deployment script (Windows native, no Docker required)
# Usage: .\deploy.ps1 [-ApiPort 8000]
# Starts: Postgres (project-local :5433), Redis (:6379), worker, and API.

param(
    [int]$ApiPort = 8000
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$venvPython = Join-Path $root ".venv-deploy\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Error "Missing venv: $venvPython. Create it first: python -m venv .venv-deploy"
}
$py312 = "C:\Users\Abhishek\AppData\Local\Programs\Python\Python312\python.exe"

function Ensure-Port {
    param([int]$Port, [string]$Name)
    $existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($existing) { Write-Host "[OK] $Name already listening on :$Port" -ForegroundColor Green; return }
    Write-Host "[..] Starting $Name on :$Port" -ForegroundColor Yellow
}

function Start-Background {
    param([string]$Args, [string]$LogFile)
    $env:PYTHONPATH = (Join-Path $root ".venv-deploy\Lib\site-packages")
    $p = Start-Process -FilePath $venvPython -ArgumentList $Args -WorkingDirectory $root `
        -RedirectStandardOutput $LogFile -RedirectStandardError "$LogFile.err" -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 1
    return $p
}

Write-Host "=== PASTE Deployment ===" -ForegroundColor Cyan
Write-Host "Root: $root"

# 1. Postgres (project-local cluster on :5433)
Ensure-Port 5433 "Postgres"
$pg = Test-Path ".pgdata\PG_VERSION"
if ($pg -and -not (Get-NetTCPConnection -LocalPort 5433 -State Listen -ErrorAction SilentlyContinue)) {
    # Try to start via the native install's pg_ctl if present
    $pgctl = "C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe"
    if (Test-Path $pgctl) {
        Write-Host "[..] Starting Postgres cluster (.pgdata)..." -ForegroundColor Yellow
        & $pgctl -D "$root\.pgdata" -l "$root\.pgdata\server.log" start
        Start-Sleep -Seconds 2
    } else {
        Write-Host "[WARN] Postgres data dir exists but pg_ctl not found; start it manually." -ForegroundColor Magenta
    }
}

# 2. Redis
Ensure-Port 6379 "Redis"
$redisExe = Join-Path $root ".tools\redis\redis-server.exe"
if (-not (Get-NetTCPConnection -LocalPort 6379 -State Listen -ErrorAction SilentlyContinue)) {
    if (Test-Path $redisExe) {
        Write-Host "[..] Starting Redis..." -ForegroundColor Yellow
        Start-Process -FilePath $redisExe -ArgumentList "--port 6379" -WindowStyle Hidden
        Start-Sleep -Seconds 2
    } else {
        Write-Host "[WARN] redis-server.exe not found at $redisExe" -ForegroundColor Magenta
    }
}

# 3. Worker
$workerLog = Join-Path $root "logs\worker.log"
New-Item -ItemType Directory -Force -Path (Split-Path $workerLog) | Out-Null
$env:PYTHONPATH = (Join-Path $root ".venv-deploy\Lib\site-packages")
$wp = Start-Process -FilePath $venvPython -ArgumentList "-m app.worker" -WorkingDirectory $root `
    -RedirectStandardOutput $workerLog -RedirectStandardError "$workerLog.err" -WindowStyle Hidden -PassThru
Write-Host "[OK] Worker started (PID $($wp.Id))" -ForegroundColor Green

# 4. API
$apiLog = Join-Path $root "logs\api.log"
$ap = Start-Process -FilePath $venvPython -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port $ApiPort" `
    -WorkingDirectory $root -RedirectStandardOutput $apiLog -RedirectStandardError "$apiLog.err" `
    -WindowStyle Hidden -PassThru
Write-Host "[OK] API started (PID $($ap.Id)) on http://127.0.0.1:$ApiPort" -ForegroundColor Green

# 5. Health check
Write-Host "`n=== Health check ===" -ForegroundColor Cyan
$ok = $false
foreach ($i in 1..10) {
    Start-Sleep -Seconds 1
    try {
        $h = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/health" -TimeoutSec 3
        Write-Host "[OK] API health: $($h.status)" -ForegroundColor Green
        $ok = $true
        break
    } catch {
        Write-Host "[..] waiting for API ($i/10)..."
    }
}
if (-not $ok) {
    Write-Host "[ERR] API did not become healthy. Check $apiLog.err" -ForegroundColor Red
    exit 1
}

Write-Host "`n=== Deployed ===" -ForegroundColor Green
Write-Host "  Dashboard : http://127.0.0.1:$ApiPort/dashboard"
Write-Host "  API Docs   : http://127.0.0.1:$ApiPort/docs"
Write-Host "  SSE stream : http://127.0.0.1:$ApiPort/api/v1/events"
Write-Host "  Logs       : $root\logs\"